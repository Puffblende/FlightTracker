#include "ft_webserver.h"
#include "config.h"
#include "renderer.h"
#include "provisioning.h"
#include <WiFi.h>
#include <WebServer.h>
#include <LittleFS.h>
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

    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, logoSize);
    LittleFS.mkdir("/logos");
    File f = LittleFS.open(path, "w");
    if (!f) { Serial.printf("[Logo] Cannot write %s\n", path); return; }

    uint8_t header = 0;
    f.write(&header, 1);  // reserved header byte (matches logos.cpp cache format)

    for (int i = 0; i + 1 < hexLen; i += 2) {
        auto h = [](char c) -> uint8_t {
            if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
            if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
            if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
            return 0;
        };
        uint8_t b = (h(hexStr[i]) << 4) | h(hexStr[i + 1]);
        f.write(&b, 1);
    }
    f.close();
    Serial.printf("[Logo] Saved %s (%d px, from config push)\n", path, logoSize);
}

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
DeviceConfig gConfig = {};
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

static void blockToJson(JsonObject obj, const LayoutBlock& blk) {
    obj["key"]          = blk.key;
    obj["x"]            = blk.x;
    obj["y"]            = blk.y;
    obj["enabled"]      = blk.enabled;
    obj["fmt"]          = blk.fmt;
    obj["font_scale"]   = blk.font_scale;
    obj["custom_label"] = blk.custom_label;
    obj["custom_unit"]  = blk.custom_unit;
    obj["custom_width"] = blk.custom_width;
    JsonArray col = obj.createNestedArray("color");
    col.add(blk.r); col.add(blk.g); col.add(blk.b);
}

// ---------------------------------------------------------------------------
// Apply parsed JSON document → gConfig
// ---------------------------------------------------------------------------
static void applyConfigDoc(JsonDocument& doc) {
    gConfig.lat             = doc["lat"]              | 0.0f;
    gConfig.lon             = doc["lon"]              | 0.0f;
    gConfig.radius_km       = doc["radius_km"]        | 100.0f;
    gConfig.fetch_interval_ms = (uint32_t)((doc["fetch_interval_s"] | 30) * 1000);
    gConfig.cycle_interval_ms = (uint32_t)((doc["cycle_interval_s"] |  5) * 1000);

    const char* u = doc["opensky_user"] | "";
    const char* p = doc["opensky_pass"] | "";
    strncpy(gConfig.opensky_user, u, sizeof(gConfig.opensky_user) - 1);
    strncpy(gConfig.opensky_pass, p, sizeof(gConfig.opensky_pass) - 1);

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

    // Save logos pushed from Python app (hex-encoded 24×24 RGB, key = ICAO)
    JsonObject logos = doc["logos"];
    if (!logos.isNull()) {
        int n = 0;
        for (JsonPair kv : logos) {
            const char* hex = kv.value().as<const char*>();
            if (hex) { saveLogo(kv.key().c_str(), hex); n++; }
        }
        if (n) Serial.printf("[Config] Saved %d logos to SPIFFS\n", n);
    }

    // Save airline names pushed from Python app (key = ICAO, value = name)
    JsonObject airlineNames = doc["airline_names"];
    if (!airlineNames.isNull()) {
        LittleFS.mkdir("/airlines");
        int n = 0;
        for (JsonPair kv : airlineNames) {
            const char* name = kv.value().as<const char*>();
            if (name && name[0]) {
                char path[40];
                snprintf(path, sizeof(path), "/airlines/%.3s.txt", kv.key().c_str());
                File f = LittleFS.open(path, "w");
                if (f) { f.print(name); f.close(); n++; }
            }
        }
        if (n) Serial.printf("[Config] Saved %d airline names to SPIFFS\n", n);
    }
}

// ---------------------------------------------------------------------------
// LittleFS persistence
// ---------------------------------------------------------------------------
bool configSave() {
    DynamicJsonDocument doc(16384);
    doc["lat"]              = gConfig.lat;
    doc["lon"]              = gConfig.lon;
    doc["radius_km"]        = gConfig.radius_km;
    doc["fetch_interval_s"] = gConfig.fetch_interval_ms / 1000;
    doc["cycle_interval_s"] = gConfig.cycle_interval_ms / 1000;
    doc["opensky_user"]     = gConfig.opensky_user;
    doc["opensky_pass"]     = gConfig.opensky_pass;

    JsonArray layout = doc.createNestedArray("layout");
    for (int i = 0; i < gConfig.block_count; i++)
        blockToJson(layout.createNestedObject(), gConfig.blocks[i]);

    File f = LittleFS.open(CONFIG_PATH, "w");
    if (!f) return false;
    serializeJson(doc, f);
    f.close();
    return true;
}

bool configLoad() {
    if (!LittleFS.exists(CONFIG_PATH)) return false;
    File f = LittleFS.open(CONFIG_PATH, "r");
    if (!f) return false;

    DynamicJsonDocument doc(16384);
    auto err = deserializeJson(doc, f);
    f.close();
    if (err) return false;

    applyConfigDoc(doc);
    return true;
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

    applyConfigDoc(doc);
    configSave();

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
    server.on("/status",     HTTP_GET,  handleGetStatus);
    server.on("/reset-wifi", HTTP_GET,  handleResetWifi);
    server.onNotFound(handleNotFound);
    server.begin();
}

void webserverHandle() {
    server.handleClient();
}
