#include "ft_webserver.h"
#include "config.h"
#include "renderer.h"
#include "provisioning.h"
#include "fs_lock.h"
#include <WiFi.h>
#include <WebServer.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <esp_heap_caps.h>
#include <string.h>

// PSRAM-backed allocator for large config payloads (ArduinoJson v7 requires reallocate()).
struct _FtSpiRam {
    void* allocate(size_t n) {
        void* p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        return p ? p : malloc(n);
    }
    void* reallocate(void* ptr, size_t new_size) {
        void* p = heap_caps_realloc(ptr, new_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        return p ? p : realloc(ptr, new_size);
    }
    void deallocate(void* p) { heap_caps_free(p); }
};

// ---------------------------------------------------------------------------
// Decode a hex-encoded logo and save to /logos/{ICAO}_{size}.bin
// Format matches logos.cpp: 1-byte reserved header + size×size×3 raw RGB.
// ---------------------------------------------------------------------------
static void saveLogo(const char* icao, const char* hexStr) {
    if (!icao || !hexStr) return;
    int hexLen = strlen(hexStr);
    if (hexLen == 0 || hexLen % 2 != 0) return;
    int byteCount = hexLen / 2;

    // Infer pixel size from byte count (pixels = size*size*3)
    int logoSize = 0;
    if      (byteCount == 16 * 16 * 3) logoSize = 16;
    else if (byteCount == 24 * 24 * 3) logoSize = 24;
    else if (byteCount == 32 * 32 * 3) logoSize = 32;
    else if (byteCount == 40 * 40 * 3) logoSize = 40;
    else {
        Serial.printf("[Logo] Unknown size %d B for %s\n", byteCount, icao);
        return;
    }

    // Decode the whole image into one buffer first (max 40*40*3 = 4800 B,
    // trivial on the stack) and issue a single write() below. The previous
    // one-byte-at-a-time write loop meant up to ~4800 individual LittleFS
    // writes per logo — tens of thousands across a full-catalog push — which
    // was almost certainly why pushes were timing out at 30s, and gave a lot
    // more opportunity for a write to be interrupted mid-flight than one
    // linear write does.
    static uint8_t buf[1 + 40 * 40 * 3];
    buf[0] = 0;  // reserved header byte (matches logos.cpp cache format)
    auto h = [](char c) -> uint8_t {
        if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
        if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
        if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
        return 0;
    };
    for (int i = 0; i + 1 < hexLen; i += 2)
        buf[1 + i / 2] = (h(hexStr[i]) << 4) | h(hexStr[i + 1]);

    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, logoSize);
    // Guards against fetchTask (a different core) touching LittleFS at the
    // same moment this writes a logo file — see fs_lock.h.
    FsLock _lock;
    LittleFS.mkdir("/logos");
    File f = LittleFS.open(path, "w");
    if (!f) { Serial.printf("[Logo] Cannot write %s\n", path); return; }

    size_t total = 1 + byteCount;
    size_t written = f.write(buf, total);
    f.close();
    if (written != total) {
        Serial.printf("[Logo] Short write %s: %d/%d bytes\n", path, (int)written, (int)total);
        return;
    }
    Serial.printf("[Logo] Saved %s (%d px, from config push)\n", path, logoSize);
}

// ---------------------------------------------------------------------------
// Delete every cached logo .bin file. Called once per fresh POST /config
// (not on configLoad() at boot, and not per POST /logos batch) so a new
// config push always starts from a clean slate — stale logos from a
// previous push (e.g. an airline's logo changed upstream) never linger
// alongside the fresh ones streamed in afterwards.
// ---------------------------------------------------------------------------
void clearLogoCache() {
    // Guards this whole walk-and-delete against fetchTask's concurrent
    // LittleFS writes — see fs_lock.h.
    FsLock _lock;
    File dir = LittleFS.open("/logos");
    if (!dir) { LittleFS.mkdir("/logos"); return; }

    // Pass 1: collect names only. Removing files while dir's own iterator is
    // still walking the same directory can desync/hang LittleFS on some
    // cores — so nothing is deleted until the directory handle is closed.
    //
    // Cap sized generously (not 128): the full airline catalog pushed via
    // _push_all_logos() can leave more logo files than that behind once
    // multiple sizes/pushes accumulate, and silently under-collecting here
    // means those files are never enumerated for deletion again — the
    // directory grows without bound across pushes and every future
    // clearLogoCache() call gets slower walking it.
    static char names[512][32];
    int n = 0;
    File f;
    while (n < 512 && (f = dir.openNextFile())) {
        strncpy(names[n], f.name(), sizeof(names[n]) - 1);
        names[n][sizeof(names[n]) - 1] = '\0';
        f.close();
        n++;
    }
    dir.close();

    // Pass 2: delete, now that the directory isn't being iterated. Yield
    // periodically — deleting hundreds of files back-to-back with no yield
    // can starve the watchdog task long enough to trigger a reboot.
    int removed = 0;
    for (int i = 0; i < n; i++) {
        String path = names[i];
        // openNextFile() may return an absolute path on some cores — avoid
        // doubling the "/logos/" prefix if it already included one.
        if (!path.startsWith("/")) path = "/logos/" + path;
        if (LittleFS.remove(path)) removed++;
        if (i % 10 == 9) delay(1);
    }
    Serial.printf("[Logo] Cleared %d cached logo(s)\n", removed);
}

// ---------------------------------------------------------------------------
// Save every {ICAO: hex} entry in a "logos" JSON object. Shared by
// POST /config (logos for currently-visible flights) and POST /logos
// (batched full-catalog pushes — see handlePostLogos below).
// ---------------------------------------------------------------------------
static void saveLogosFromJson(JsonObject logos) {
    if (logos.isNull()) return;
    int n = 0;
    for (JsonPair kv : logos) {
        const char* hex = kv.value().as<const char*>();
        if (hex) { saveLogo(kv.key().c_str(), hex); n++; }
    }
    if (n) Serial.printf("[Logo] Saved %d logo(s) from push\n", n);
}

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
DeviceConfig gConfig = {};
SemaphoreHandle_t gConfigMutex = nullptr;
void configMutexInit() { gConfigMutex = xSemaphoreCreateMutex(); }

static WebServer server(HTTP_PORT);

// ---------------------------------------------------------------------------
// JSON ↔ LayoutBlock helpers
// ---------------------------------------------------------------------------

static void blockFromJson(LayoutBlock& blk, JsonObject obj) {
    memset(&blk, 0, sizeof(blk));
    const char* key = obj["key"] | "";
    const char* fmt = obj["fmt"] | "full";
    strncpy(blk.key, key, sizeof(blk.key) - 1);
    strncpy(blk.fmt, fmt, sizeof(blk.fmt) - 1);

    blk.x       = obj["x"] | 0;
    blk.y       = obj["y"] | 0;
    blk.enabled = obj["enabled"] | true;
    blk.font_scale = obj["font_scale"] | 1.0f;
    blk.custom_width = obj["custom_width"] | 0;

    const char* lbl  = obj["custom_label"] | "";
    const char* unit = obj["custom_unit"]  | "";
    strncpy(blk.custom_label, lbl,  sizeof(blk.custom_label) - 1);
    strncpy(blk.custom_unit,  unit, sizeof(blk.custom_unit)  - 1);

    Serial.printf("[Parse] key=%s fmt='%s' x=%d y=%d enabled=%d\n",
                  blk.key, blk.fmt, blk.x, blk.y, (int)blk.enabled);
    if (strcmp(blk.key, "aircraft_type") == 0) {
        String raw;
        serializeJson(obj, raw);
        Serial.println("[Raw aircraft_type]: " + raw);
    }

    JsonArray col = obj["color"];
    if (col.isNull()) col = obj["custom_color"];  // compat: old LittleFS saves used this key
    if (!col.isNull() && col.size() >= 3) {
        blk.r = col[0]; blk.g = col[1]; blk.b = col[2];
    } else {
        struct { const char* k; uint8_t r,g,b; } DEFAULTS[] = {
            {"airline",       255,255,255}, {"callsign",  255,220,  0},
            {"route",         255,255,255}, {"aircraft_type",100,255,100},
            {"altitude",      100,200,255}, {"speed",    255,140,  0},
            {"track",         180,180,255}, {"vrate",    255,100,100},
            {"squawk",        200,200,200}, {"country",  200,200,200},
            {"distance",      180,255,180}, {"progress", 255,200, 60},
        };
        blk.r = 200; blk.g = 200; blk.b = 200;
        for (auto& d : DEFAULTS) {
            if (strcmp(blk.key, d.k) == 0) {
                blk.r = d.r; blk.g = d.g; blk.b = d.b; break;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Apply parsed JSON document → gConfig
// ---------------------------------------------------------------------------
static void applyConfigDoc(JsonDocument& doc) {
    // Guards against fetchTask (a different core) reading gConfig mid-write
    // — see the comment on gConfigMutex in ft_webserver.h.
    if (gConfigMutex) xSemaphoreTake(gConfigMutex, portMAX_DELAY);
    gConfig.lat             = doc["lat"]              | 0.0f;
    gConfig.lon             = doc["lon"]              | 0.0f;
    gConfig.radius_km       = doc["radius_km"]        | 100.0f;
    gConfig.fetch_interval_ms = (uint32_t)((doc["fetch_interval_s"] | 30) * 1000);
    gConfig.cycle_interval_ms = (uint32_t)((doc["cycle_interval_s"] |  5) * 1000);

    const char* u = doc["opensky_user"] | "";
    const char* p = doc["opensky_pass"] | "";
    strncpy(gConfig.opensky_user, u, sizeof(gConfig.opensky_user) - 1);
    strncpy(gConfig.opensky_pass, p, sizeof(gConfig.opensky_pass) - 1);

    // Hidden category codes, e.g. ["B1","B3"] — see hidden_category_mask
    // comment in ft_webserver.h and categoryHidden() in opensky.cpp.
    gConfig.hidden_category_mask = 0;
    JsonArray hiddenCats = doc["hidden_categories"];
    if (!hiddenCats.isNull()) {
        for (JsonVariant v : hiddenCats) {
            const char* code = v.as<const char*>();
            if (code && code[0] == 'B' && code[1] >= '1' && code[1] <= '5' && code[2] == '\0')
                gConfig.hidden_category_mask |= (1 << (code[1] - '1'));
        }
    }

    JsonArray layout = doc["layout"];
    gConfig.block_count = 0;
    if (!layout.isNull()) {
        // Print raw JSON of first block so we can verify field names + values
        if (layout.size() > 0) {
            String firstBlock;
            serializeJson(layout[0], firstBlock);
            Serial.println("[JSON] First block: " + firstBlock);
        }
        for (JsonObject obj : layout) {
            if (gConfig.block_count >= MAX_BLOCKS) break;
            blockFromJson(gConfig.blocks[gConfig.block_count++], obj);
        }
    }
    if (gConfig.block_count == 0)
        gConfig.block_count = defaultLayout(gConfig.blocks, MAX_BLOCKS);

    gConfig.valid = true;
    if (gConfigMutex) xSemaphoreGive(gConfigMutex);

    // Save logos pushed from Python app (hex-encoded 24×24 RGB, key = ICAO)
    saveLogosFromJson(doc["logos"]);

    // Note: doc["airline_names"] (pushed from the Python app) is
    // intentionally unused — airline names are resolved from the static
    // AIRLINE_DB table (airlines.cpp) via airlineLookup(), not from any
    // per-device data. An earlier design wrote these to /airlines/*.txt on
    // LittleFS, but nothing ever read that back; it was pure dead weight —
    // an extra LittleFS write on every config push for no effect.
}

// ---------------------------------------------------------------------------
// Config persistence — NVS (ESP32 Preferences), not LittleFS.
//
// gConfig is a fixed-size POD struct (no pointers), so it's persisted as a
// raw byte blob — no JSON round-trip needed. NVS is a separate flash
// partition from LittleFS (same reasoning as the WiFi credentials in
// provisioning.cpp), so the device's location/radius/layout now survive a
// LittleFS reformat: after a wipe the device reconnects to WiFi *and* keeps
// fetching flights from the same place, instead of sitting on a blank
// "Waiting for config..." screen until the Python app pushes again. Only
// the logo cache — too large for NVS, and non-essential to core operation —
// is actually lost in that scenario now.
// ---------------------------------------------------------------------------
#define CONFIG_NVS_NAMESPACE "ft-config"

bool configSave() {
    Preferences prefs;
    if (!prefs.begin(CONFIG_NVS_NAMESPACE, false)) return false;
    size_t written = prefs.putBytes("blob", &gConfig, sizeof(gConfig));
    prefs.end();
    return written == sizeof(gConfig);
}

#define LEGACY_CONFIG_JSON_PATH "/config.json"

bool configLoad() {
    Preferences prefs;
    if (prefs.begin(CONFIG_NVS_NAMESPACE, true)) {  // read-only
        size_t stored = prefs.getBytesLength("blob");
        if (stored == sizeof(gConfig)) {
            DeviceConfig loaded;
            prefs.getBytes("blob", &loaded, sizeof(loaded));
            prefs.end();
            gConfig = loaded;
            gConfig.valid = true;
            return true;
        }
        prefs.end();
    }

    // One-time migration: NVS is empty, which is what every device coming
    // from firmware that stored config as /config.json on LittleFS will see
    // on its first boot after this update. Adopt the old file instead of
    // forcing a fresh push from the Python app purely because of where the
    // bytes happen to live.
    if (LittleFS.exists(LEGACY_CONFIG_JSON_PATH)) {
        File f = LittleFS.open(LEGACY_CONFIG_JSON_PATH, "r");
        if (f) {
            DynamicJsonDocument doc(16384);
            auto err = deserializeJson(doc, f);
            f.close();
            if (!err) {
                Serial.println("[Config] Migrating config from legacy /config.json to NVS");
                applyConfigDoc(doc);
                configSave();
                LittleFS.remove(LEGACY_CONFIG_JSON_PATH);
                return true;
            }
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// HTTP handlers
// ---------------------------------------------------------------------------

static void handleRoot() {
    DynamicJsonDocument doc(256);
    doc["name"]    = "FlightMatrix";
    doc["width"]   = TOTAL_WIDTH;
    doc["height"]  = TOTAL_HEIGHT;
    doc["port"]    = UDP_FRAME_PORT;
    doc["version"] = "1.0";
    doc["ip"]      = WiFi.localIP().toString();
    doc["config"]  = gConfig.valid;

    String out;
    serializeJson(doc, out);
    server.send(200, "application/json", out);
}

static void handlePostConfig() {
    String body = server.arg("plain");
    if (body.isEmpty()) {
        server.send(400, "application/json", "{\"error\":\"empty body\"}");
        return;
    }
    Serial.printf("[Config] POST /config body: %d bytes\n", body.length());

    // PSRAM-backed 64 KB doc handles config + logo hex strings (typically 40-50 KB).
    BasicJsonDocument<_FtSpiRam> doc(65536);
    auto err = deserializeJson(doc, body);
    if (err) {
        Serial.printf("[Config] JSON parse error: %s\n", err.c_str());
        server.send(400, "application/json", "{\"error\":\"invalid JSON\"}");
        return;
    }

    // clearLogoCache() used to run here on every push, but saveLogo() already
    // overwrites a given {ICAO}_{size}.bin in place, so nothing actually
    // needed the wipe in the common case — and with a large accumulated
    // cache the walk-and-delete could take long enough to trip the
    // watchdog and reboot mid-request. Cache clearing is now a deliberate,
    // separate action via GET /reset-logos, not an automatic side effect
    // of every config push. This also means a config push no longer
    // discards the full catalog built up by _push_all_logos() — the device
    // keeps working with everything it has already learned, even across
    // pushes, which is what lets it run standalone after a power cycle.
    applyConfigDoc(doc);
    configSave();

    server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Accepts {"logos": {ICAO: hex_string, ...}} — a small batch (a handful of
// airlines) so the doc buffer stays well clear of its 64 KB cap. The Python
// app calls this repeatedly to stream the full airline catalog after the
// main /config push, since sending it all in one request would overflow
// both this buffer and the WebServer's request body handling.
static void handlePostLogos() {
    String body = server.arg("plain");
    if (body.isEmpty()) {
        server.send(400, "application/json", "{\"error\":\"empty body\"}");
        return;
    }

    BasicJsonDocument<_FtSpiRam> doc(65536);
    auto err = deserializeJson(doc, body);
    if (err) {
        Serial.printf("[Logos] JSON parse error: %s\n", err.c_str());
        server.send(400, "application/json", "{\"error\":\"invalid JSON\"}");
        return;
    }

    saveLogosFromJson(doc["logos"]);
    server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handleGetStatus() {
    DynamicJsonDocument doc(128);
    doc["valid"]      = gConfig.valid;
    doc["lat"]        = gConfig.lat;
    doc["lon"]        = gConfig.lon;
    doc["radius_km"]  = gConfig.radius_km;
    doc["blocks"]     = gConfig.block_count;
    String out;
    serializeJson(doc, out);
    server.send(200, "application/json", out);
}

// Manual, deliberate cache wipe — visit this URL (or curl it) when stale
// logos need clearing out. Not called automatically by POST /config
// anymore; see the comment there for why.
static void handleResetLogos() {
    clearLogoCache();
    server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handleNotFound() {
    server.send(404, "application/json", "{\"error\":\"not found\"}");
}

static void handleResetWifi() {
    wifiCredsClear();
    server.send(200, "text/html",
        "<html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:-apple-system,sans-serif;background:#070d1a;"
        "color:#e2e8f0;display:flex;align-items:center;justify-content:center;"
        "min-height:100vh;padding:20px}.card{background:#0f172a;border:1px solid "
        "#1e3a5f;border-radius:20px;padding:28px;max-width:360px;text-align:center}"
        "h2{color:#f87171;margin-bottom:10px}p{color:#94a3b8;font-size:.9rem}</style>"
        "</head><body><div class='card'>"
        "<h2>WiFi credentials cleared</h2>"
        "<p>Restarting into setup mode&hellip;<br><br>"
        "Connect to <strong style='color:#e2e8f0'>FlightTracker-Setup</strong> "
        "WiFi to reconfigure.</p>"
        "</div></body></html>");
    delay(1500);
    ESP.restart();
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void webserverBegin() {
    server.on("/",           HTTP_GET,  handleRoot);
    server.on("/config",     HTTP_POST, handlePostConfig);
    server.on("/logos",      HTTP_POST, handlePostLogos);
    server.on("/status",     HTTP_GET,  handleGetStatus);
    server.on("/reset-wifi", HTTP_GET,  handleResetWifi);
    server.on("/reset-logos", HTTP_GET, handleResetLogos);
    server.onNotFound(handleNotFound);
    server.begin();
}

void webserverHandle() {
    server.handleClient();
}
