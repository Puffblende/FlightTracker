#include "logos.h"
#include "airlines.h"
#include "display.h"
#include "config.h"
#include "http_utils.h"
#include <esp_heap_caps.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <PNGdec.h>
#include <Arduino.h>
#include <string.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include "esp_http_client.h"
#include "esp_crt_bundle.h"

static const int MAX_LOGO_SIZE = 40;
static const int MAX_PNG_BYTES = 32768;

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

struct LogoRequest {
    char    icao[5];   // 3-char airline ICAO prefix — used for file path + FlightAware URL
    char    iata[4];   // 2-letter IATA code        — used for pics.avs.io URL
    uint8_t size;
};

static QueueHandle_t s_queue     = nullptr;
static TaskHandle_t  s_fetchTask = nullptr;

// Shared flag: set true while fetchFlights() runs so logo task backs off.
// Declared extern in logos.h; set by the fetch task in FlightTracker.ino.
volatile bool g_fetchingFlights = false;
static PNG           s_png;

struct DecodeCtx {
    // Output: scaled-down pixels written to LittleFS
    uint8_t  pixels[MAX_LOGO_SIZE][MAX_LOGO_SIZE][3];
    int      dstSize;
    // Full-resolution intermediate buffer in PSRAM (allocated before decode)
    uint8_t* fullImg;  // [fullH * fullW * 3], freed after scaling
    int      fullW;
    int      fullH;
};
static DecodeCtx s_ctx;

// ---------------------------------------------------------------------------
// PNG row callback — stores every source row into the full-res PSRAM buffer.
// Transparency is composited onto white (mirrors Python _composite_on_white).
// Scaling happens AFTER the full image is decoded — not row-by-row — to
// prevent colour artifacts when many source rows map to the same dest row.
// ---------------------------------------------------------------------------
// Global ctx pointer — PNGdec callbacks can't carry state through pDraw->pUser
// when using the pattern from the official examples, so we use a global.
// Only one logo is ever decoded at a time (logoFetchTask is single-threaded).
static DecodeCtx* g_ctx = nullptr;
static int g_rowCount = 0;  // reset before each decode

static int pngRowCallback(PNGDRAW *pDraw) {
    Serial.printf("[PNG-CB] callback fired y=%d\n", pDraw->y);
    if (g_rowCount < 3 || pDraw->y == 89 || pDraw->y == 179) {
        Serial.printf("[PNG] Row y=%d iWidth=%d g_ctx=%p fullImg=%p\n",
                      pDraw->y, pDraw->iWidth, g_ctx,
                      g_ctx ? g_ctx->fullImg : nullptr);
    }
    g_rowCount++;

    if (!g_ctx || !g_ctx->fullImg) return 1;

    if (pDraw->y == 0) {
        Serial.printf("[PNG] bpp=%d pixel_type=%d w=%d h=%d\n",
                      pDraw->iBpp, pDraw->iPixelType,
                      pDraw->iWidth, g_ctx->fullH);
    }

    // Stack-allocate the line buffer (max 256 pixels × 2 bytes = 512 bytes — safe)
    uint16_t lineBuf[256];
    int w = pDraw->iWidth < 256 ? pDraw->iWidth : 256;
    if (w > g_ctx->fullW) w = g_ctx->fullW;

    // getLineAsRGB565 handles ALL pixel types: palette, RGB, RGBA, grayscale.
    // PNG_RGB565_LITTLE_ENDIAN: internal RGB565 stored without byte-swap.
    // u32Bkgd must be 0xFFFFFFFF for white — PNGdec reads it as 32-bit RRGGBB
    // so 0xFFFF = 0x0000FFFF = cyan background, not white.
    s_png.getLineAsRGB565(pDraw, lineBuf, PNG_RGB565_LITTLE_ENDIAN, 0xFFFFFFFF);

    // With LITTLE_ENDIAN the uint16_t layout is: B[4:0] G[10:5] R[15:11]
    // i.e. B is in the LOW bits, R is in the HIGH bits — opposite of the
    // standard RGB565 big-endian convention used by most displays.
    int rowOffset = pDraw->y * g_ctx->fullW;
    for (int x = 0; x < w; x++) {
        uint16_t px = lineBuf[x];
        uint8_t r = ( px        & 0x1F) << 3;
        uint8_t g = ((px >>  5) & 0x3F) << 2;
        uint8_t b = ((px >> 11) & 0x1F) << 3;
        g_ctx->fullImg[(rowOffset + x) * 3 + 0] = r;
        g_ctx->fullImg[(rowOffset + x) * 3 + 1] = g;
        g_ctx->fullImg[(rowOffset + x) * 3 + 2] = b;
        if (pDraw->y == 0 && x == 0) {
            Serial.printf("[PNG] Writing fullImg[0] = %d,%d,%d\n", r, g, b);
        }
    }

    return 1;
}

// ---------------------------------------------------------------------------
// .none sentinel — skip retrying logos that aren't available anywhere.
// Mirrors Python: _memory[key] = None (avoids retry spam).
// ---------------------------------------------------------------------------

static void markNone(const char* icao) {
    char path[40];
    snprintf(path, sizeof(path), "/logos/%.3s.none", icao);
    File f = LittleFS.open(path, "w");
    if (f) f.close();
    Serial.printf("[Logo] Marked %s as not found\n", icao);
}

static bool isMarkedNone(const char* icao) {
    char path[40];
    snprintf(path, sizeof(path), "/logos/%.3s.none", icao);
    if (!LittleFS.exists(path)) return false;
    // If NTP is not synced, time() returns 0 — treat the sentinel as permanent
    // until a real timestamp is available.
    time_t now = time(nullptr);
    if (now < 1000000) return true;  // clock not set → assume sentinel is fresh
    File f = LittleFS.open(path, "r");
    if (!f) return true;
    time_t mtime = f.getLastWrite();
    f.close();
    return (now - mtime) < 86400;  // retry after 24 h
}

// ---------------------------------------------------------------------------
// LittleFS cache cleanup — delete oldest .bin files when usage > 80%
// ---------------------------------------------------------------------------

static void cleanupLogoCache() {
    size_t used  = LittleFS.usedBytes();
    size_t total = LittleFS.totalBytes();
    if (total == 0 || used * 100 / total < 80) return;

    Serial.printf("[Logo] LittleFS %d/%d bytes (>80%%), cleaning\n",
                  (int)used, (int)total);
    size_t target = total * 60 / 100;
    int pass = 0;

    while (LittleFS.usedBytes() > target && pass++ < 200) {
        File dir = LittleFS.open("/logos");
        if (!dir) break;

        char toDelete[48] = "";
        time_t oldest = LONG_MAX;
        File f;
        while ((f = dir.openNextFile())) {
            const char* nm = f.name();
            size_t nl = strlen(nm);
            if (nl > 4 && strcmp(nm + nl - 4, ".bin") == 0) {
                time_t mt = f.getLastWrite();
                if (mt < oldest) {
                    oldest = mt;
                    snprintf(toDelete, sizeof(toDelete), "/logos/%s", nm);
                }
            }
            f.close();
        }
        dir.close();

        if (!toDelete[0]) break;
        LittleFS.remove(toDelete);
        Serial.printf("[Logo] Deleted %s\n", toDelete);
    }
    Serial.printf("[Logo] After cleanup: %d/%d bytes\n",
                  (int)LittleFS.usedBytes(), (int)LittleFS.totalBytes());
}

// ---------------------------------------------------------------------------
// Download one HTTPS URL → PSRAM-allocated buffer.
// Returns byte count (≥ 300), 0 on network/other error, -1 on HTTP 404.
// Caller must free() the returned buffer on success.
//
// Uses ESP-IDF esp_http_client with esp_crt_bundle_attach — same pattern
// as fetchAdsbFi() in opensky.cpp which fixed the Cloudflare TLS rejection.
// ---------------------------------------------------------------------------
static int downloadPng(const char* url, uint8_t** outBuf) {
    if (!ensureWiFi("Logo")) return 0;

    Serial.printf("[Logo] GET %s  heap=%d\n", url, ESP.getFreeHeap());

    esp_http_client_config_t cfg = {};
    cfg.url               = url;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    cfg.timeout_ms        = 10000;
    cfg.buffer_size       = 4096;
    cfg.buffer_size_tx    = 512;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) { Serial.println("[Logo] init failed"); return 0; }
    esp_http_client_set_header(client, "User-Agent",
                               "Mozilla/5.0 (compatible; FlightTracker/1.0)");
    esp_http_client_set_header(client, "Accept", "image/png,image/*");

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        Serial.printf("[Logo] Open error: %s\n", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        return 0;
    }

    int content_length = esp_http_client_fetch_headers(client);
    int status         = esp_http_client_get_status_code(client);
    Serial.printf("[Logo] HTTP %d  len=%d\n", status, content_length);

    if (status == 404) {
        esp_http_client_close(client); esp_http_client_cleanup(client);
        return -1;
    }
    if (status != 200) {
        esp_http_client_close(client); esp_http_client_cleanup(client);
        return 0;
    }

    // Allocate PNG receive buffer from PSRAM; fall back to heap
    uint8_t* buf = (uint8_t*)heap_caps_malloc(MAX_PNG_BYTES,
                                              MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) buf = (uint8_t*)malloc(MAX_PNG_BYTES);
    if (!buf) {
        Serial.println("[Logo] malloc failed");
        esp_http_client_close(client); esp_http_client_cleanup(client);
        return 0;
    }

    // Stream binary body into buffer; freed by caller (or by decodePng)
    int total = 0, n;
    while ((n = esp_http_client_read(client, (char*)buf + total,
                                     MAX_PNG_BYTES - total)) > 0) {
        total += n;
        if (total >= MAX_PNG_BYTES) break;
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    Serial.printf("[Logo] Downloaded %d bytes\n", total);

    // Python: `if r.status_code == 200 and len(r.content) > 300`
    if (total <= 300) { free(buf); return 0; }

    *outBuf = buf;
    return total;
}

// ---------------------------------------------------------------------------
// Decode PNG → s_ctx.pixels[dstSize][dstSize][3].
// Always frees pngBuf (success or failure).
//
// Pipeline:
//   1. Open PNG, read dimensions
//   2. Allocate full-res PSRAM buffer (e.g. 180×180×3 = 97 KB)
//   3. Decode all rows into PSRAM buffer via pngRowCallback
//   4. Nearest-neighbour scale PSRAM buffer → s_ctx.pixels
//   5. Free PSRAM buffer
// ---------------------------------------------------------------------------

static bool decodePng(uint8_t* pngBuf, int len) {
    Serial.println("[Decode] decodePng() called");
    memset(&s_ctx.pixels, 0, sizeof(s_ctx.pixels));
    s_ctx.fullImg = nullptr;

    int rc = s_png.openRAM(pngBuf, len, pngRowCallback);
    Serial.printf("[Decode] openRAM rc=%d\n", rc);
    if (rc != PNG_SUCCESS) {
        Serial.printf("[Logo] PNG open failed: %d\n", rc);
        free(pngBuf); return false;
    }

    s_ctx.fullW = s_png.getWidth();
    s_ctx.fullH = s_png.getHeight();
    Serial.printf("[Logo] PNG %dx%d → %dx%d  heap=%d psram=%d\n",
                  s_ctx.fullW, s_ctx.fullH, s_ctx.dstSize, s_ctx.dstSize,
                  ESP.getFreeHeap(), ESP.getFreePsram());

    // Allocate full-res buffer in PSRAM (180×180×3 = 97 KB — fits easily)
    size_t fullBytes = (size_t)s_ctx.fullW * s_ctx.fullH * 3;
    s_ctx.fullImg = (uint8_t*)heap_caps_malloc(fullBytes,
                                               MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    Serial.printf("[Decode] fullImg allocated: %p\n", s_ctx.fullImg);
    if (!s_ctx.fullImg) {
        Serial.printf("[Logo] PSRAM alloc failed (%u bytes)\n", (unsigned)fullBytes);
        s_png.close(); free(pngBuf); return false;
    }
    memset(s_ctx.fullImg, 0xFF, fullBytes);  // pre-fill white (transparent → white)

    // Set global pointer so pngRowCallback can access ctx.
    // PNG_FAST_PALETTE accelerates palette-indexed PNG decoding.
    g_ctx = &s_ctx;
    g_rowCount = 0;
    Serial.printf("[Decode] g_ctx set to %p, fullImg=%p\n", g_ctx, g_ctx->fullImg);
    s_png.decode(nullptr, PNG_FAST_PALETTE);
    Serial.printf("[Decode] decode() done, rows processed=%d\n", g_rowCount);
    g_ctx = nullptr;
    s_png.close();
    free(pngBuf);  // PNG compressed buffer no longer needed

    // Nearest-neighbour scale: fullW×fullH → dstSize×dstSize
    for (int dstY = 0; dstY < s_ctx.dstSize; dstY++) {
        int srcY = (dstY * s_ctx.fullH) / s_ctx.dstSize;
        for (int dstX = 0; dstX < s_ctx.dstSize; dstX++) {
            int srcX = (dstX * s_ctx.fullW) / s_ctx.dstSize;
            const uint8_t* src = s_ctx.fullImg + ((size_t)srcY * s_ctx.fullW + srcX) * 3;
            s_ctx.pixels[dstY][dstX][0] = src[0];
            s_ctx.pixels[dstY][dstX][1] = src[1];
            s_ctx.pixels[dstY][dstX][2] = src[2];
        }
    }

    // Scale debug: verify pixel[0,0] read path before freeing fullImg
    {
        int srcX = (0 * s_ctx.fullW) / s_ctx.dstSize;
        int srcY = (0 * s_ctx.fullH) / s_ctx.dstSize;
        int idx  = (srcY * s_ctx.fullW + srcX) * 3;
        Serial.printf("[Scale] dst[0,0] → src[%d,%d] idx=%d val=%d,%d,%d\n",
                      srcX, srcY, idx,
                      s_ctx.fullImg[idx], s_ctx.fullImg[idx+1], s_ctx.fullImg[idx+2]);
    }

    free(s_ctx.fullImg);   // PSRAM buffer freed immediately after scale
    s_ctx.fullImg = nullptr;

    // Pixel debug — expected for Ryanair (RYR):
    //   [0,0]   = white (255,255,255) — corner background
    //   [12,12] = navy blue (0,0,128) or white — centre of logo
    // If R:248 G:0 B:0 → R/B swapped → switch to PNG_RGB565_BIG_ENDIAN extraction
    // If R:0 G:0 B:0   → g_ctx was null during decode or fullImg not written
    Serial.printf("[Logo] pixel[0,0]   R:%d G:%d B:%d\n",
                  s_ctx.pixels[0][0][0],  s_ctx.pixels[0][0][1],  s_ctx.pixels[0][0][2]);
    Serial.printf("[Logo] pixel[12,12] R:%d G:%d B:%d\n",
                  s_ctx.pixels[12][12][0], s_ctx.pixels[12][12][1], s_ctx.pixels[12][12][2]);
    Serial.printf("[Logo] pixel[0,12]  R:%d G:%d B:%d\n",
                  s_ctx.pixels[0][12][0],  s_ctx.pixels[0][12][1],  s_ctx.pixels[0][12][2]);
    Serial.printf("[Logo] pixel[23,23] R:%d G:%d B:%d\n",
                  s_ctx.pixels[23][23][0], s_ctx.pixels[23][23][1], s_ctx.pixels[23][23][2]);
    return true;
}

// ---------------------------------------------------------------------------
// Fetch, decode, and cache one logo at the requested size.
//
// URL order mirrors Python src/api/logos.py _try_fetch():
//   1. FlightAware 180px — ICAO uppercase (e.g. EZY.png)  [solid background]
//   2. pics.avs.io 200×200 — ICAO used as IATA approximation [transparent]
//
// Python tries FlightAware first (ICAO), then pics.avs.io (IATA).
// On ESP32 we lack a separate IATA field, so ICAO prefix serves both.
//
// File format: 1-byte reserved header + size×size×3 raw RGB bytes.
// Path: /logos/{ICAO}_{size}.bin
// ---------------------------------------------------------------------------

// Mirrors Python logos.py _try_fetch(): FlightAware (ICAO) first, then
// pics.avs.io (IATA). Downloads via ESP-IDF HTTP client (TLS 1.3 + CA bundle).
static bool fetchAndSaveLogo(const char* icao, const char* iata, int size) {
    s_ctx.dstSize = size;
    Serial.printf("[MEM] Logo fetch start — heap: %d, psram: %d\n",
                  ESP.getFreeHeap(), ESP.getFreePsram());
    char url[128];
    uint8_t* pngBuf = nullptr;
    int len = 0;
    snprintf(url, sizeof(url),
             "https://www.flightaware.com/images/airline_logos/180px/%s.png", icao);
    Serial.printf("[Logo] Trying FlightAware (ICAO=%s): %s\n", icao, url);
    len = downloadPng(url, &pngBuf);
    if (len <= 0 && iata && iata[0]) {
        int prev = len;
        snprintf(url, sizeof(url), "https://pics.avs.io/200/200/%s.png", iata);
        Serial.printf("[Logo] Trying pics.avs.io (IATA=%s): %s\n", iata, url);
        len = downloadPng(url, &pngBuf);
        if (prev == -1 && len == -1) { markNone(icao); return false; }
    } else if (len <= 0) {
        if (len == -1) { markNone(icao); return false; }
    }

    if (len <= 0) {
        // Network error on both — don't mark none (may succeed later)
        Serial.printf("[MEM] Logo fetch end (network fail) — heap: %d, psram: %d\n",
                      ESP.getFreeHeap(), ESP.getFreePsram());
        return false;
    }

    // Decode PNG → pixel buffer; pngBuf freed inside decodePng
    if (!decodePng(pngBuf, len)) {
        markNone(icao);
        Serial.printf("[MEM] Logo fetch end (decode fail) — heap: %d, psram: %d\n",
                      ESP.getFreeHeap(), ESP.getFreePsram());
        return false;
    }

    // Save: 1-byte reserved header + size×size×3 raw RGB
    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, size);
    File f = LittleFS.open(path, "w");
    if (!f) {
        Serial.printf("[Logo] Cannot create %s\n", path);
        Serial.printf("[MEM] Logo fetch end (save fail) — heap: %d, psram: %d\n",
                      ESP.getFreeHeap(), ESP.getFreePsram());
        return false;
    }
    uint8_t header = 0;
    f.write(&header, 1);
    f.write((uint8_t*)s_ctx.pixels, size * size * 3);
    f.close();
    Serial.printf("[Logo] Saved %s (%d bytes)\n", path, size * size * 3 + 1);

    cleanupLogoCache();
    Serial.printf("[MEM] Logo fetch end — heap: %d, psram: %d\n",
                  ESP.getFreeHeap(), ESP.getFreePsram());
    return true;
}

// ---------------------------------------------------------------------------
// Internal enqueue — just adds to the queue; the persistent task drains it.
// ---------------------------------------------------------------------------

static void enqueueLogoAt(const char* icao, const char* iata, uint8_t size) {
    if (!s_queue || isMarkedNone(icao)) return;
    LogoRequest req;
    memset(&req, 0, sizeof(req));
    strncpy(req.icao, icao, 3);
    if (iata && iata[0]) {
        strncpy(req.iata, iata, sizeof(req.iata) - 1);
        for (int i = 0; req.iata[i]; i++)
            if (req.iata[i] >= 'a' && req.iata[i] <= 'z') req.iata[i] -= 32;
    }
    req.size = size;
    xQueueSend(s_queue, &req, 0);  // drop silently if full
}

// ---------------------------------------------------------------------------
// Persistent low-priority logo fetch task — wakes every 5 s and processes
// one logo from the queue only when:
//   1. Heap is large enough for SSL (> 80 KB)
//   2. No flight fetch is in progress (g_fetchingFlights == false)
// One logo per wake cycle so flight fetches can claim memory between logos.
// ---------------------------------------------------------------------------

static void logoFetchTask(void* /*param*/) {
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(5000));

        uint32_t freeHeap = ESP.getFreeHeap();
        if (freeHeap < 80000) {
            Serial.printf("[Logo] Skip — heap %lu < 80000\n", (unsigned long)freeHeap);
            continue;
        }
        if (g_fetchingFlights) {
            Serial.println("[Logo] Skip — flight fetch in progress");
            continue;
        }

        LogoRequest req;
        if (xQueueReceive(s_queue, &req, 0) != pdTRUE) continue;

        char path[48];
        snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", req.icao, req.size);
        if (!LittleFS.exists(path))
            fetchAndSaveLogo(req.icao, req.iata, (int)req.size);
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void logosInit() {
    // Delete all cached logos to force fresh decode with new code
    LittleFS.rmdir("/logos");
    LittleFS.mkdir("/logos");
    Serial.println("[Logo] Cache cleared for fresh decode");
    s_queue = xQueueCreate(8, sizeof(LogoRequest));
    // Persistent task — started once, runs for the lifetime of the firmware.
    // Low priority (1) so flight fetch and render always win memory contests.
    xTaskCreate(logoFetchTask, "logoFetch", 16384, nullptr, 1, &s_fetchTask);
    Serial.println("[Logo] Init done");
}

bool logoExists(const char* icao) {
    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_24.bin", icao);
    return LittleFS.exists(path);
}

void logoFetchEnqueue(const char* callsign, const char* airline_iata) {
    if (!s_queue || !callsign || !callsign[0]) return;

    char icao[5] = {0};
    strncpy(icao, callsign, 3);
    for (int i = 0; i < 3; i++) {
        if (icao[i] >= 'a' && icao[i] <= 'z') icao[i] -= 32;
        if (!(icao[i] >= 'A' && icao[i] <= 'Z')) return;
    }

    const char* iata = (airline_iata && airline_iata[0])
                       ? airline_iata
                       : airlineIcaoToIata(icao);

    if (isMarkedNone(icao)) return;
    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_24.bin", icao);
    if (!LittleFS.exists(path))
        enqueueLogoAt(icao, iata, 24);
}

// ---------------------------------------------------------------------------
// Fallback: generic top-down aircraft silhouette
// ---------------------------------------------------------------------------

static const uint16_t PLANE_16[16] = {
    0x0180,  // nose tip
    0x03C0,
    0x03C0,
    0x03C0,
    0x3FFC,  // wings
    0x7FFE,
    0x3FFC,
    0x03C0,
    0x03C0,
    0x03C0,
    0x03C0,
    0x0180,
    0x03C0,  // horizontal stabilizers
    0x0FF0,
    0x03C0,
    0x0180,  // tail tip
};

static void drawPlaneIcon(int x, int y, int size, uint8_t r, uint8_t g, uint8_t b) {
    for (int row = 0; row < 16; row++) {
        for (int col = 0; col < 16; col++) {
            if (!(PLANE_16[row] & (0x8000u >> col))) continue;
            int px = x + col * size / 16;
            int py = y + row * size / 16;
            if (px >= 0 && px < TOTAL_WIDTH && py >= 0 && py < TOTAL_HEIGHT)
                displaySetPixel(px, py, r, g, b);
        }
    }
}

// ---------------------------------------------------------------------------
// Draw logo from LittleFS cache, or plane icon fallback.
//
// File layout: byte 0 = reserved; bytes 1…end = size×size×3 raw RGB.
//
// Pixels were composited onto a WHITE background during PNG decode
// (mirroring Python's _composite_on_white).  White pixels (≥ 241 brightness)
// represent transparent/background areas and are skipped — they would appear
// as bright white squares on the dark LED panel.
//
// Tinting rule (applied to non-white pixels):
//   brightness > 150  → replace with block color (r,g,b)  — bright logo areas
//   brightness ≤ 150  → draw as-is                        — coloured logo detail
// ---------------------------------------------------------------------------

void drawLogo(const char* icao, int x, int y, int size,
              uint8_t r, uint8_t g, uint8_t b) {
    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, size);

    if (!LittleFS.exists(path)) {
        const char* iata = airlineIcaoToIata(icao);
        enqueueLogoAt(icao, iata, (uint8_t)size);
        drawPlaneIcon(x, y, size, r, g, b);
        return;
    }

    File f = LittleFS.open(path, "r");
    if (!f) {
        drawPlaneIcon(x, y, size, r, g, b);
        return;
    }

    uint8_t header = 0;
    f.read(&header, 1);  // skip reserved byte

    uint8_t row[MAX_LOGO_SIZE * 3];
    for (int srcY = 0; srcY < size; srcY++) {
        if (f.read(row, size * 3) != size * 3) break;
        int py = y + srcY;
        if (py < 0 || py >= TOTAL_HEIGHT) continue;
        for (int srcX = 0; srcX < size; srcX++) {
            int px = x + srcX;
            if (px < 0 || px >= TOTAL_WIDTH) continue;
            uint8_t pr = row[srcX * 3];
            uint8_t pg = row[srcX * 3 + 1];
            uint8_t pb = row[srcX * 3 + 2];
            uint8_t brightness = ((uint16_t)pr + pg + pb) / 3;
            // Skip white background (was transparent in source PNG)
            if (brightness > 240) continue;
            if (brightness > 150)
                displaySetPixel(px, py, r, g, b);   // bright → tint with block color
            else
                displaySetPixel(px, py, pr, pg, pb); // coloured detail → as-is
        }
    }
    f.close();
}
