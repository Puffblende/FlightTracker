/*
 * FlightTracker ESP32 Firmware
 *
 * Boot sequence:
 *   1. Init HUB75 panel
 *   2. Load /wifi.json — try to connect (10 s timeout)
 *      If no credentials or timeout → AP provisioning mode (captive portal)
 *   3. Connect to WiFi → show IP on panel
 *   3. Load config from LittleFS (if saved from previous session)
 *   4. Start HTTP server  (POST /config to push new config from PC)
 *   5. Listen for UDP discovery broadcasts (port 4210)
 *   6. Listen for pre-rendered UDP frames from PC (port 4211, Option A)
 *   7. Autonomously fetch OpenSky every fetch_interval_s
 *   8. Cycle through nearest aircraft every cycle_interval_s
 *
 * Libraries required (install via Arduino Library Manager):
 *   - ESP32-HUB75-MatrixPanel-I2S-DMA  (mrfaptastic)
 *   - ArduinoJson  v6.x  (Benoit Blanchon)
 *     (for ArduinoJson 7: replace DynamicJsonDocument with JsonDocument)
 *
 * Board: ESP32S3 Dev Module
 *   - PSRAM: OPI PSRAM  (enables 8 MB PSRAM for large JSON docs)
 *   - Partition Scheme: Default 4MB with spiffs  or  "Huge APP"
 */

#include "config.h"
#include "display.h"
#include "font.h"
#include "opensky.h"
#include "renderer.h"
#include "ft_webserver.h"
#include "provisioning.h"
#include "logos.h"
#include "airlines.h"
#include "routes.h"
#include "aircraft_types.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>
#include <LittleFS.h>
#include <string.h>

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
static FlightData* flights = nullptr;  // allocated in PSRAM during setup()
static int        flightCount        = 0;
static int        flightIdx          = 0;
static uint32_t   lastFetchMs        = 0;
static uint32_t   lastCycleMs        = 0;
static bool       needsRender        = false;
static uint32_t   rateLimitIntervalMs = 0;  // nonzero during 429 backoff

// Mutex protecting flights[], flightCount, flightIdx, needsRender,
// lastFetchMs, rateLimitIntervalMs — shared between Core 0 fetch task
// and Core 1 main loop.
static SemaphoreHandle_t s_flightMutex = nullptr;
static TaskHandle_t      s_fetchHandle = nullptr;

// UDP sockets
static WiFiUDP udpDisc;   // port 4210 — discovery
static WiFiUDP udpFrame;  // port 4211 — Option A pre-rendered frames

// ---------------------------------------------------------------------------
// WiFi connection
//
// Priority order:
//   1. Credentials in /wifi.json (saved by captive portal or /reset-wifi flow)
//   2. Compile-time WIFI_SSID / WIFI_PASS from config.h (if not placeholder)
//   3. Provisioning mode — AP + captive portal (never returns; restarts)
// ---------------------------------------------------------------------------
static void connectWiFi() {
    char ssid[64] = {0}, pass[64] = {0};
    bool hasCreds = wifiCredsLoad(ssid, sizeof(ssid), pass, sizeof(pass));

    // Fall back to compile-time credentials if LittleFS has none
    if (!hasCreds
            && strlen(WIFI_SSID) > 0
            && strcmp(WIFI_SSID, "your_wifi_ssid") != 0) {
        strncpy(ssid, WIFI_SSID, sizeof(ssid) - 1);
        strncpy(pass, WIFI_PASS, sizeof(pass) - 1);
        hasCreds = true;
    }

    if (hasCreds) {
        renderMessage("Connecting", ssid);
        WiFi.mode(WIFI_STA);
        WiFi.begin(ssid, pass);

        unsigned long t0 = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
            delay(200);
        }

        if (WiFi.status() == WL_CONNECTED) {
            char ip[20];
            WiFi.localIP().toString().toCharArray(ip, sizeof(ip));
            renderMessage("Connected", ip);
            delay(2000);
            return;
        }

        renderMessage("WiFi failed", "Starting setup");
        delay(1500);
    }

    // No usable credentials or connection timed out → provisioning
    provisionStart();   // blocks until user submits creds, then restarts
}

// ---------------------------------------------------------------------------
// UDP discovery — respond to FTLD_DISCOVER broadcasts
// ---------------------------------------------------------------------------
static void handleDiscovery() {
    int pkt = udpDisc.parsePacket();
    if (pkt <= 0) return;
    uint8_t buf[32] = {0};
    int n = udpDisc.read(buf, sizeof(buf) - 1);
    if (n >= 13 && memcmp(buf, "FTLD_DISCOVER", 13) == 0) {
        char reply[128];
        snprintf(reply, sizeof(reply),
                 "{\"name\":\"FlightMatrix\",\"width\":%d,\"height\":%d,\"port\":%d}",
                 TOTAL_WIDTH, TOTAL_HEIGHT, UDP_FRAME_PORT);
        udpDisc.beginPacket(udpDisc.remoteIP(), udpDisc.remotePort());
        udpDisc.print(reply);
        udpDisc.endPacket();
    }
}

// ---------------------------------------------------------------------------
// UDP Option-A frame receiver — accept pre-rendered FTLD packets from PC
// Packet layout: MAGIC(4) + W(2BE) + H(2BE) + RGB(W×H×3)
// Note: 128×64 = 24 584 bytes → may be IP-fragmented on some routers.
// ---------------------------------------------------------------------------
static void handleUdpFrame() {
    int pkt = udpFrame.parsePacket();
    if (pkt < 8) return;

    uint8_t hdr[8];
    udpFrame.read(hdr, 8);
    if (memcmp(hdr, "FTLD", 4) != 0) return;

    uint16_t w = ((uint16_t)hdr[4] << 8) | hdr[5];
    uint16_t h = ((uint16_t)hdr[6] << 8) | hdr[7];
    int dataExpected = (int)w * h * 3;

    if (w != TOTAL_WIDTH || h != TOTAL_HEIGHT) return;
    if (pkt - 8 < dataExpected) return;

    // Write pixels directly into the framebuffer row by row
    for (int row = 0; row < h; row++) {
        for (int col = 0; col < w; col++) {
            uint8_t rgb[3];
            udpFrame.read(rgb, 3);
            fb[row][col][0] = rgb[0];
            fb[row][col][1] = rgb[1];
            fb[row][col][2] = rgb[2];
        }
    }
    displayFlush();
}

// ---------------------------------------------------------------------------
// Flight fetch — runs on Core 0 so webserver on Core 1 stays responsive.
//
// During the network call the global flights[] is untouched; results go into
// a PSRAM-allocated temp buffer.  The mutex is held only for the brief
// memcpy at the end, so Core 1 is never blocked during the actual HTTP fetch.
// ---------------------------------------------------------------------------
static void fetchTask(void* /*param*/) {
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));

        if (!gConfig.valid) continue;

        // Read timing state — brief mutex hold
        uint32_t effectiveMs = 0;
        bool due = false;
        if (xSemaphoreTake(s_flightMutex, pdMS_TO_TICKS(200)) == pdTRUE) {
            effectiveMs = rateLimitIntervalMs > 0 ? rateLimitIntervalMs
                                                  : gConfig.fetch_interval_ms;
            due = (lastFetchMs == 0) || (millis() - lastFetchMs >= effectiveMs);
            xSemaphoreGive(s_flightMutex);
        }
        if (!due) continue;

        // Memory guard
        uint32_t freeHeap = ESP.getFreeHeap();
        if (freeHeap < 40000) {
            Serial.printf("[MEM] WARNING: heap %lu < 40000 — skipping fetch\n",
                          (unsigned long)freeHeap);
            if (xSemaphoreTake(s_flightMutex, pdMS_TO_TICKS(200)) == pdTRUE) {
                lastFetchMs = millis();   // avoid hammering the log
                xSemaphoreGive(s_flightMutex);
            }
            continue;
        }

        // Allocate temp buffer from PSRAM — keeps flights[] stable during fetch
        FlightData* tmp = (FlightData*)heap_caps_malloc(
            MAX_FLIGHTS * sizeof(FlightData), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!tmp) tmp = (FlightData*)malloc(MAX_FLIGHTS * sizeof(FlightData));
        if (!tmp) { Serial.println("[Fetch] alloc failed"); continue; }

        Serial.printf("[Fetch] lat=%.4f lon=%.4f radius=%.1f heap=%lu\n",
                      gConfig.lat, gConfig.lon, gConfig.radius_km,
                      (unsigned long)ESP.getFreeHeap());

        int n = fetchFlights(gConfig.lat, gConfig.lon, gConfig.radius_km,
                             gConfig.opensky_user, gConfig.opensky_pass,
                             tmp, MAX_FLIGHTS);

        // Route (origin/destination) isn't in any state-vector source we
        // use (OpenSky, adsb.lol) — only adsb.fi's fallback path includes
        // it, which is rarely reached. Look it up separately per callsign,
        // same as the Python app's src/api/routes.py, via a small per-cycle
        // budget so a batch of new flights doesn't stall this fetch cycle.
        if (n > 0) {
            routeLookupBudgetReset();
            for (int i = 0; i < n; i++) {
                if (tmp[i].origin[0] && tmp[i].destination[0]) continue;
                if (!tmp[i].callsign[0]) continue;
                routeLookup(tmp[i].callsign, tmp[i].origin, tmp[i].destination,
                            tmp[i].dep_icao, tmp[i].arr_icao);
            }
        }

        // Commit results — brief mutex hold
        if (xSemaphoreTake(s_flightMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
            lastFetchMs = millis();
            if (n < 0) {
                // 429 — back off exponentially, cap at 120 s
                uint32_t base = rateLimitIntervalMs > 0 ? rateLimitIntervalMs
                                                        : gConfig.fetch_interval_ms;
                rateLimitIntervalMs = min(base * 2, (uint32_t)120000);
            } else {
                rateLimitIntervalMs = 0;
                memcpy(flights, tmp, n * sizeof(FlightData));
                flightCount = n;
                if (flightIdx >= n) flightIdx = 0;
                needsRender = true;
            }
            xSemaphoreGive(s_flightMutex);
        }
        free(tmp);
    }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    if (!psramFound()) {
        Serial.println("[MEM] WARNING: No PSRAM found!");
        Serial.println("[MEM] Hint: Arduino IDE → Tools → PSRAM → OPI PSRAM");
    } else {
        Serial.printf("[MEM] PSRAM found: %d bytes\n", ESP.getPsramSize());
    }

    // Filesystem (format on first boot)
    if (!LittleFS.begin(true)) {
        Serial.println("LittleFS mount failed");
    }
    routesInit();

    // Allocate flight array from PSRAM — frees ~14 KB of regular heap for SSL
    flights = (FlightData*)heap_caps_malloc(MAX_FLIGHTS * sizeof(FlightData),
                                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!flights) flights = (FlightData*)malloc(MAX_FLIGHTS * sizeof(FlightData));
    if (!flights) { Serial.println("[MEM] FATAL: flights alloc failed"); while(true) delay(1000); }
    memset(flights, 0, MAX_FLIGHTS * sizeof(FlightData));
    Serial.printf("[MEM] After PSRAM allocs — heap: %d free\n", ESP.getFreeHeap());

    if (!displayInit()) {
        Serial.println("Display init failed");
        while (true) delay(1000);
    }

    renderMessage("FlightTracker", "Starting...");
    delay(500);

    connectWiFi();

    // Override DHCP DNS with Google's public resolver — more reliable than
    // router-provided DNS in environments where local DNS fails to resolve
    // external hostnames.  INADDR_NONE leaves IP/gateway/subnet unchanged.
    WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE, IPAddress(8, 8, 8, 8));
    Serial.println("[DNS] Set primary DNS to 8.8.8.8");
    delay(1000);  // let DNS config settle before first lookup

    Serial.printf("[WiFi] IP: %s, Gateway: %s, DNS: %s\n",
                  WiFi.localIP().toString().c_str(),
                  WiFi.gatewayIP().toString().c_str(),
                  WiFi.dnsIP().toString().c_str());

    // DNS probe — confirms resolver works before attempting SSL
    {
        IPAddress ip;
        if (WiFi.hostByName("opendata.adsb.fi", ip))
            Serial.printf("[DNS] opendata.adsb.fi = %s\n", ip.toString().c_str());
        else
            Serial.println("[DNS] Failed to resolve opendata.adsb.fi");
    }

    // Raw TCP tests — isolate whether port 443 is reachable before SSL.
    // A ~200ms fail means TCP is being rejected (firewall/router), not SSL.
    {
        WiFiClient tcpTest;
        bool ok = tcpTest.connect(IPAddress(172, 67, 72, 239), 443);  // opendata.adsb.fi IP
        Serial.printf("[TCP] adsb.fi 172.67.72.239:443 — %s\n",
                      ok ? "WORKS" : "FAILED (router/ISP blocking outbound 443?)");
        if (ok) tcpTest.stop();
    }
    {
        WiFiClient tcpTest2;
        bool ok = tcpTest2.connect(IPAddress(8, 8, 8, 8), 443);  // Google DNS on 443
        Serial.printf("[TCP] Google 8.8.8.8:443 — %s\n",
                      ok ? "WORKS (outbound 443 not blocked)" : "FAILED (router blocks outbound 443!)");
        if (ok) tcpTest2.stop();
    }

    // SSL test — runs once at startup, logs exact error via lastError()
    {
        WiFiClientSecure testClient;
        testClient.setInsecure();
        testClient.setHandshakeTimeout(30);
        Serial.println("[SSL-TEST] Attempting connect to opendata.adsb.fi:443...");
        bool ok = testClient.connect("opendata.adsb.fi", 443);
        Serial.printf("[SSL-TEST] connect() returned: %d\n", ok);
        if (ok) {
            Serial.println("[SSL-TEST] Connected successfully!");
            testClient.stop();
        } else {
            char err[100];
            testClient.lastError(err, sizeof(err));
            Serial.printf("[SSL-TEST] Error: %s\n", err);
        }
        Serial.printf("[SSL-TEST] heap after test: %d free\n", ESP.getFreeHeap());
    }

    // Load persisted config (if any)
    if (configLoad()) {
        Serial.println("Config loaded from flash");
    } else {
        // Use default layout so display is populated if config arrives later
        gConfig.block_count = defaultLayout(gConfig.blocks, MAX_BLOCKS);
        gConfig.fetch_interval_ms = DEFAULT_FETCH_MS;
        gConfig.cycle_interval_ms = DEFAULT_CYCLE_MS;
    }

    airlinesInit();
    webserverBegin();
    udpDisc.begin(UDP_DISC_PORT);
    udpFrame.begin(UDP_FRAME_PORT);

    Serial.print("HTTP server on http://");
    Serial.println(WiFi.localIP());

    // Create mutex before starting the fetch task
    s_flightMutex = xSemaphoreCreateMutex();

    // Fetch task on Core 0 — frees Core 1 (main loop) for webserver + display
    xTaskCreatePinnedToCore(fetchTask, "fetch", 16384, nullptr, 1,
                            &s_fetchHandle, 0);
    Serial.println("[Task] Fetch task started on Core 0");

    renderMessage(gConfig.valid ? "Config ready" : "Waiting for", "config...");
}

// ---------------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------------
void loop() {
    webserverHandle();
    handleDiscovery();
    handleUdpFrame();

    // WiFi reconnect
    if (WiFi.status() != WL_CONNECTED) {
        renderMessage("WiFi lost", "Reconnecting");
        WiFi.reconnect();
        delay(5000);
        return;
    }

    if (!gConfig.valid) {
        delay(100);
        return;
    }

    uint32_t now = millis();

    // ── Heartbeat — confirm loop is alive every 30 s ──────────────────────────
    static uint32_t lastHeartbeatMs = 0;
    if (now - lastHeartbeatMs >= 30000) {
        lastHeartbeatMs = now;
        // Read shared state non-critically for logging (no mutex — values are
        // 32-bit and reads are effectively atomic on this architecture)
        Serial.printf("[Main] Loop alive at %lu ms, configValid=%d flightCount=%d\n",
                      now, (int)gConfig.valid, flightCount);
        Serial.printf("[Main] Last fetch: %lu ms ago, rateLimit=%lu ms\n",
                      now - lastFetchMs, (unsigned long)rateLimitIntervalMs);
    }

    // ── Memory monitor — every 60 s ──────────────────────────────────────────
    static uint32_t lastMemLogMs = 0;
    if (now - lastMemLogMs >= 60000) {
        lastMemLogMs = now;
        uint32_t freeHeap = ESP.getFreeHeap();
        Serial.printf("[MEM] Heap: %d free, PSRAM: %d free\n",
                      freeHeap, ESP.getFreePsram());
        if (freeHeap < 50000)
            Serial.println("[MEM] WARNING: low memory!");
    }

    // ── Cycle timer — advance to next flight ─────────────────────────────────
    if (xSemaphoreTake(s_flightMutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        if (flightCount > 1 && (now - lastCycleMs >= gConfig.cycle_interval_ms)) {
            flightIdx = (flightIdx + 1) % flightCount;
            needsRender = true;
            lastCycleMs = millis();
        }
        xSemaphoreGive(s_flightMutex);
    }

    // ── Re-render if something changed ────────────────────────────────────────
    if (needsRender) {
        if (xSemaphoreTake(s_flightMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
            needsRender = false;
            if (flightCount == 0) {
                renderNoFlights();
            } else {
                renderFlight(flights[flightIdx], gConfig.blocks, gConfig.block_count);
            }
            xSemaphoreGive(s_flightMutex);
            heap_caps_check_integrity_all(true);
        }
    }

    delay(20);
}
