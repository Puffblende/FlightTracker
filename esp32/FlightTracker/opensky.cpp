#include "opensky.h"
#include "logos.h"
#include "airlines.h"
#include "http_utils.h"
#include <WiFi.h>
#include <esp_heap_caps.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "esp_http_client.h"
#include "esp_crt_bundle.h"

// ---------------------------------------------------------------------------
// ArduinoJson v7 PSRAM allocator (reallocate() required by v7)
// ---------------------------------------------------------------------------
struct SpiRamAllocator {
    void* allocate(size_t size) {
        void* p = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!p) p = malloc(size);
        return p;
    }
    void* reallocate(void* ptr, size_t new_size) {
        void* p = heap_caps_realloc(ptr, new_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!p) p = realloc(ptr, new_size);
        return p;
    }
    void deallocate(void* p) { heap_caps_free(p); }
};
using SpiRamJsonDocument = BasicJsonDocument<SpiRamAllocator>;

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

static float haversineKm(float lat1, float lon1, float lat2, float lon2) {
    const float R = 6371.0f;
    float dlat = (lat2 - lat1) * DEG_TO_RAD;
    float dlon = (lon2 - lon1) * DEG_TO_RAD;
    float a = sinf(dlat * 0.5f) * sinf(dlat * 0.5f) +
              cosf(lat1 * DEG_TO_RAD) * cosf(lat2 * DEG_TO_RAD) *
              sinf(dlon * 0.5f) * sinf(dlon * 0.5f);
    return R * 2.0f * asinf(sqrtf(a));
}

static void sortFlights(FlightData* arr, int n) {
    for (int i = 1; i < n; i++) {
        FlightData key = arr[i];
        int j = i - 1;
        while (j >= 0 && arr[j].distance_km > key.distance_km) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

static float jfloat(JsonVariant v) {
    if (v.isNull()) return NAN;
    return v.as<float>();
}

// Strip '@' padding (Mode-S artifact) and trailing spaces from callsign.
// Mirrors Python adsb_lol.py: (ac.get("flight") or "").replace("@", "").strip()
static void cleanCallsign(char* s) {
    for (int i = 0; s[i]; i++)
        if (s[i] == '@') s[i] = ' ';
    for (int i = (int)strlen(s) - 1; i >= 0 && s[i] == ' '; i--)
        s[i] = '\0';
}

// ---------------------------------------------------------------------------
// Source 1: adsb.lol  (Python primary source — src/api/adsb_lol.py)
// Source 2: adsb.one  (same format, ESP32 bonus fallback)
//
// Python behaviour ported exactly:
//   - URL: /v2/lat/{lat}/lon/{lon}/dist/{nm}  (adsb.lol)  OR
//           /v2/point/{lat}/{lon}/{nm}          (adsb.one)
//   - Skip aircraft with category starting 'C' (ground vehicles / surface)
//   - Strip '@' padding + trailing spaces from "flight" callsign field
//   - Use "ownOp" or "desc" as fallback airline name when callsign lookup empty
//   - Use precomputed "dst" (nm) field for distance when present; else haversine
//   - alt_baro in feet → metres; gs in knots → m/s; baro_rate fpm → m/s
// ---------------------------------------------------------------------------

static bool parseAcArray(const String& body, float lat, float lon,
                         FlightData* flights, int maxFlights, int* count) {
    StaticJsonDocument<512> filter;
    {
        JsonObject root  = filter.to<JsonObject>();
        JsonArray  outer = root.createNestedArray("ac");
        JsonObject inner = outer.createNestedObject();
        inner["hex"]       = true;
        inner["flight"]    = true;
        inner["lat"]       = true;
        inner["lon"]       = true;
        inner["alt_baro"]  = true;
        inner["gs"]        = true;
        inner["track"]     = true;
        inner["baro_rate"] = true;
        inner["squawk"]    = true;
        inner["t"]         = true;
        inner["desc"]      = true;
        inner["category"]  = true;   // Python: skip "C*" ground vehicles
        inner["ownOp"]     = true;   // Python: fallback airline name
        inner["dst"]       = true;   // Python: precomputed distance (nm)
    }

    SpiRamJsonDocument doc(32768);
    DeserializationError err = deserializeJson(doc, body,
        DeserializationOption::Filter(filter));
    if (err) { Serial.printf("[AC] Parse error: %s\n", err.c_str()); return false; }

    JsonArray ac = doc["ac"];
    if (ac.isNull()) { Serial.println("[AC] No 'ac' array"); return false; }

    *count = 0;
    for (JsonObject a : ac) {
        if (*count >= maxFlights) break;

        // Python adsb_lol.py: skip surface vehicles (ADS-B category C*)
        const char* cat = a["category"] | "";
        if (cat[0] == 'C' || cat[0] == 'c') continue;

        float fLat = jfloat(a["lat"]);
        float fLon = jfloat(a["lon"]);
        if (isnan(fLat) || isnan(fLon)) continue;

        FlightData& f = flights[*count];
        memset(&f, 0, sizeof(FlightData));

        strncpy(f.icao24,             a["hex"]    | "", sizeof(f.icao24)             - 1);
        strncpy(f.callsign,           a["flight"] | "", sizeof(f.callsign)            - 1);
        strncpy(f.squawk,             a["squawk"] | "", sizeof(f.squawk)              - 1);
        strncpy(f.aircraft_type,      a["t"]      | "", sizeof(f.aircraft_type)       - 1);
        strncpy(f.aircraft_type_full, a["desc"]   | "", sizeof(f.aircraft_type_full)  - 1);
        cleanCallsign(f.callsign);

        // Python: airline lookup from callsign prefix; fall back to ownOp/desc
        airlineLookup(f.callsign, f.airline_name, sizeof(f.airline_name));
        if (!f.airline_name[0]) {
            const char* ownOp = a["ownOp"] | "";
            if (ownOp[0])
                strncpy(f.airline_name, ownOp, sizeof(f.airline_name) - 1);
            else if (f.aircraft_type_full[0])
                strncpy(f.airline_name, f.aircraft_type_full, sizeof(f.airline_name) - 1);
        }

        // Store ICAO prefix and IATA code — needed by logo fetcher
        strncpy(f.airline_icao, f.icao24, 0);  // cleared by memset; filled below
        strncpy(f.airline_icao, f.callsign, 3);
        f.airline_icao[3] = '\0';
        for (int i = 0; f.airline_icao[i]; i++)
            if (f.airline_icao[i] >= 'a') f.airline_icao[i] -= 32;
        const char* iata = airlineIcaoToIata(f.airline_icao);
        strncpy(f.airline_iata, iata, sizeof(f.airline_iata) - 1);

        // alt_baro: string "ground" → jfloat returns NAN → on_ground = true
        float alt_ft = jfloat(a["alt_baro"]);
        f.baro_altitude = isnan(alt_ft) ? NAN : alt_ft * 0.3048f;  // ft → m
        f.on_ground     = isnan(alt_ft);

        float gs_kts   = jfloat(a["gs"]);
        float vr_fpm   = jfloat(a["baro_rate"]);
        f.velocity      = isnan(gs_kts)  ? NAN : gs_kts  * 0.514444f;  // kts → m/s
        f.vertical_rate = isnan(vr_fpm)  ? NAN : vr_fpm  / 196.85f;    // fpm → m/s
        f.true_track    = jfloat(a["track"]);
        f.latitude      = fLat;
        f.longitude     = fLon;

        // Python: use precomputed "dst" (nm) when available
        float dst_nm = jfloat(a["dst"]);
        f.distance_km = isnan(dst_nm) ? haversineKm(lat, lon, fLat, fLon)
                                      : dst_nm * 1.852f;

        logoFetchEnqueue(f.callsign, f.airline_iata);
        (*count)++;
    }

    doc.clear();
    Serial.printf("[AC] Parsed %d flights\n", *count);
    return *count > 0;
}

// Plain-HTTP sources — no SSL cost, saves ~30 KB heap.
// Try several URLs in order; first 200 response with data wins.
static bool fetchAdsbAc(float lat, float lon, float radius_nm,
                        FlightData* flights, int maxFlights, int* count) {
    // opendata.adsb.fi plain HTTP — quick attempt before the SSL version.
    // If the server responds on port 80 we get the data for free.
    {
        char url[128];
        snprintf(url, sizeof(url),
                 "http://opendata.adsb.fi/api/v2/lat/%.4f/lon/%.4f/dist/%.0f",
                 lat, lon, radius_nm);
        Serial.printf("[adsb.fi-http] %s\n", url);
        String body;
        int rc = fetchUrlPlain(url, body);
        // adsb.fi uses "aircraft" array key — handled by fetchAdsbFi's parser;
        // parseAcArray looks for "ac" so it will return false here, but a 200
        // means port 80 is open and we should try the SSL path first.
        if (rc == 200 && body.length() >= 10) {
            // If we got data over plain HTTP, parse it with the adsb.fi parser
            // by creating a temporary String and reusing the JSON code inline.
            // For now just note it and fall through to the SSL path.
            Serial.printf("[adsb.fi-http] Got %d bytes over plain HTTP!\n", body.length());
        }
        body = "";
    }

    // adsb.lol — Python's primary source (HTTP, currently may be 502)
    {
        char url[128];
        snprintf(url, sizeof(url),
                 "http://api.adsb.lol/v2/lat/%.4f/lon/%.4f/dist/%.0f",
                 lat, lon, radius_nm);
        Serial.printf("[adsb.lol] %s\n", url);
        String body;
        int rc = fetchUrlPlain(url, body);
        bool ok = (rc == 200 && body.length() >= 10 &&
                   parseAcArray(body, lat, lon, flights, maxFlights, count));
        body = "";
        if (ok) return true;
        Serial.printf("[adsb.lol] HTTP %d\n", rc);
    }

    // adsb.one — same format (HTTP, currently may need auth)
    {
        char url[128];
        snprintf(url, sizeof(url),
                 "http://api.adsb.one/v2/point/%.4f/%.4f/%.0f",
                 lat, lon, radius_nm);
        Serial.printf("[adsb.one] %s\n", url);
        String body;
        int rc = fetchUrlPlain(url, body);
        bool ok = (rc == 200 && body.length() >= 10 &&
                   parseAcArray(body, lat, lon, flights, maxFlights, count));
        body = "";
        if (ok) return true;
        Serial.printf("[adsb.one] HTTP %d\n", rc);
    }

    return false;
}

// ---------------------------------------------------------------------------
// Source: adsb.lol via HTTPS (esp_http_client) — when plain HTTP returns 502.
// Same "ac" array format as plain HTTP adsb.lol, reuses parseAcArray.
// ---------------------------------------------------------------------------
static bool fetchAdsbLolSsl(float lat, float lon, float radius_nm,
                             FlightData* flights, int maxFlights, int* count) {
    char url[160];
    snprintf(url, sizeof(url),
             "https://api.adsb.lol/v2/lat/%.4f/lon/%.4f/dist/%.0f",
             lat, lon, radius_nm);
    Serial.printf("[adsb.lol SSL] GET %s  heap=%d\n", url, ESP.getFreeHeap());

    const int RESP_SIZE = 65536;
    char* respBuf = (char*)heap_caps_malloc(RESP_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!respBuf) respBuf = (char*)malloc(RESP_SIZE);
    if (!respBuf) { Serial.println("[adsb.lol SSL] alloc failed"); return false; }

    esp_http_client_config_t cfg = {};
    cfg.url               = url;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    cfg.timeout_ms        = 10000;
    cfg.buffer_size       = 4096;
    cfg.buffer_size_tx    = 512;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) { free(respBuf); return false; }
    esp_http_client_set_header(client, "User-Agent", "FlightTracker/1.0");

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        Serial.printf("[adsb.lol SSL] open error: %s\n", esp_err_to_name(err));
        esp_http_client_cleanup(client); free(respBuf); return false;
    }

    esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    Serial.printf("[adsb.lol SSL] HTTP %d\n", status);

    int total = 0, n;
    if (status == 200) {
        while ((n = esp_http_client_read(client, respBuf + total,
                                         RESP_SIZE - 1 - total)) > 0) {
            total += n;
            if (total >= RESP_SIZE - 1) break;
        }
        respBuf[total] = '\0';
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (status != 200 || total < 10) { free(respBuf); return false; }

    String body(respBuf);  // ArduinoJson can parse from String or char*
    free(respBuf);
    bool ok = parseAcArray(body, lat, lon, flights, maxFlights, count);
    body = "";
    return ok;
}

// ---------------------------------------------------------------------------
// Source 3: adsb.fi via ESP-IDF HTTP client + full Mozilla CA bundle.
// Arduino WiFiClientSecure rejects Cloudflare's TLS (fatal alert from peer).
// esp_http_client with esp_crt_bundle_attach supports TLS 1.3 and all
// modern cipher suites required by Cloudflare.
// ---------------------------------------------------------------------------
static bool fetchAdsbFi(const char* path, float lat, float lon,
                        FlightData* flights, int maxFlights, int* count) {

    char url[160];
    snprintf(url, sizeof(url), "https://opendata.adsb.fi%s", path);
    Serial.printf("[adsb.fi] GET %s  heap=%d\n", url, ESP.getFreeHeap());

    // Allocate response buffer from PSRAM (adsb.fi JSON can be >32 KB)
    const int RESP_SIZE = 65536;
    char* respBuf = (char*)heap_caps_malloc(RESP_SIZE,
                                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!respBuf) respBuf = (char*)malloc(RESP_SIZE);
    if (!respBuf) { Serial.println("[adsb.fi] alloc failed"); return false; }

    // ESP-IDF HTTP client with full CA bundle — proper TLS 1.3 support
    esp_http_client_config_t cfg = {};
    cfg.url                = url;
    cfg.crt_bundle_attach  = esp_crt_bundle_attach;
    cfg.timeout_ms         = 10000;
    cfg.buffer_size        = 4096;
    cfg.buffer_size_tx     = 512;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) {
        Serial.println("[adsb.fi] esp_http_client_init failed");
        free(respBuf); return false;
    }
    esp_http_client_set_header(client, "User-Agent", "Mozilla/5.0 (compatible; FlightTracker/1.0)");
    esp_http_client_set_header(client, "Accept",     "application/json");

    esp_err_t openErr = esp_http_client_open(client, 0);
    if (openErr != ESP_OK) {
        Serial.printf("[adsb.fi] Open error: %s\n", esp_err_to_name(openErr));
        esp_http_client_cleanup(client);
        free(respBuf); return false;
    }

    int content_length = esp_http_client_fetch_headers(client);
    int status         = esp_http_client_get_status_code(client);
    Serial.printf("[adsb.fi] Status=%d ContentLength=%d heap=%d\n",
                  status, content_length, ESP.getFreeHeap());

    int total = 0;
    if (status == 200) {
        int n;
        while ((n = esp_http_client_read(client, respBuf + total,
                                         RESP_SIZE - 1 - total)) > 0) {
            total += n;
            if (total >= RESP_SIZE - 1) break;
        }
        respBuf[total] = '\0';
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (status != 200 || total < 10) {
        Serial.printf("[adsb.fi] Failed: status=%d body=%d bytes\n", status, total);
        free(respBuf); return false;
    }
    Serial.printf("[adsb.fi] Body: %d bytes\n", total);

    StaticJsonDocument<512> filter;
    {
        JsonObject root  = filter.to<JsonObject>();
        JsonArray  outer = root.createNestedArray("aircraft");
        JsonObject inner = outer.createNestedObject();
        inner["hex"]       = true;
        inner["flight"]    = true;
        inner["lat"]       = true;
        inner["lon"]       = true;
        inner["alt_baro"]  = true;
        inner["gs"]        = true;
        inner["track"]     = true;
        inner["baro_rate"] = true;
        inner["squawk"]    = true;
        inner["t"]         = true;
        inner["desc"]      = true;
        inner["category"]  = true;
        inner["ownOp"]     = true;
        inner["dst"]       = true;
        inner["dep_iata"]  = true;
        inner["arr_iata"]  = true;
        inner["dep_icao"]  = true;
        inner["arr_icao"]  = true;
    }

    SpiRamJsonDocument doc(32768);
    DeserializationError err = deserializeJson(doc, respBuf,
        DeserializationOption::Filter(filter));
    free(respBuf);  // free immediately after parse

    if (err) { Serial.printf("[adsb.fi] Parse error: %s\n", err.c_str()); return false; }

    JsonArray aircraft = doc["aircraft"];
    if (aircraft.isNull()) { Serial.println("[adsb.fi] No aircraft array"); return false; }

    *count = 0;
    for (JsonObject ac : aircraft) {
        if (*count >= maxFlights) break;

        const char* cat = ac["category"] | "";
        if (cat[0] == 'C' || cat[0] == 'c') continue;

        float fLat = jfloat(ac["lat"]);
        float fLon = jfloat(ac["lon"]);
        if (isnan(fLat) || isnan(fLon)) continue;

        FlightData& f = flights[*count];
        memset(&f, 0, sizeof(FlightData));

        strncpy(f.icao24,             ac["hex"]      | "", sizeof(f.icao24)             - 1);
        strncpy(f.callsign,           ac["flight"]   | "", sizeof(f.callsign)            - 1);
        strncpy(f.squawk,             ac["squawk"]   | "", sizeof(f.squawk)              - 1);
        strncpy(f.aircraft_type,      ac["t"]        | "", sizeof(f.aircraft_type)       - 1);
        strncpy(f.aircraft_type_full, ac["desc"]     | "", sizeof(f.aircraft_type_full)  - 1);
        strncpy(f.origin,             ac["dep_iata"] | "", sizeof(f.origin)              - 1);
        strncpy(f.destination,        ac["arr_iata"] | "", sizeof(f.destination)         - 1);
        strncpy(f.dep_icao,           ac["dep_icao"] | "", sizeof(f.dep_icao)            - 1);
        strncpy(f.arr_icao,           ac["arr_icao"] | "", sizeof(f.arr_icao)            - 1);
        cleanCallsign(f.callsign);

        airlineLookup(f.callsign, f.airline_name, sizeof(f.airline_name));
        if (!f.airline_name[0]) {
            const char* ownOp = ac["ownOp"] | "";
            if (ownOp[0]) strncpy(f.airline_name, ownOp, sizeof(f.airline_name) - 1);
        }

        strncpy(f.airline_icao, f.callsign, 3);
        f.airline_icao[3] = '\0';
        for (int i = 0; f.airline_icao[i]; i++)
            if (f.airline_icao[i] >= 'a') f.airline_icao[i] -= 32;
        const char* iata = airlineIcaoToIata(f.airline_icao);
        strncpy(f.airline_iata, iata, sizeof(f.airline_iata) - 1);

        float alt_ft = jfloat(ac["alt_baro"]);
        f.baro_altitude = isnan(alt_ft) ? NAN : alt_ft * 0.3048f;
        f.on_ground     = isnan(alt_ft);

        float gs_kts  = jfloat(ac["gs"]);
        float vr_fpm  = jfloat(ac["baro_rate"]);
        f.velocity      = isnan(gs_kts) ? NAN : gs_kts * 0.514444f;
        f.vertical_rate = isnan(vr_fpm) ? NAN : vr_fpm / 196.85f;
        f.true_track    = jfloat(ac["track"]);
        f.latitude      = fLat;
        f.longitude     = fLon;

        float dst_nm = jfloat(ac["dst"]);
        f.distance_km = isnan(dst_nm) ? haversineKm(lat, lon, fLat, fLon)
                                      : dst_nm * 1.852f;

        logoFetchEnqueue(f.callsign, f.airline_iata);
        (*count)++;
    }

    doc.clear();
    Serial.printf("[adsb.fi] Parsed %d flights\n", *count);
    return *count > 0;
}

// ---------------------------------------------------------------------------
// Source 4: OpenSky Network — Python fallback (src/api/opensky.py)
// Mirrors Python: bounding-box query, state vector fields 0-indexed.
// Returns flight count (≥0), -1 on HTTP 429, -2 on other error.
// ---------------------------------------------------------------------------
static int tryOpenSky(float lat, float lon, float radius_km,
                      const char* user, const char* pass,
                      FlightData* out, int maxFlights) {
    const float R = 6371.0f;
    float dlat = degrees(radius_km / R);
    float dlon = degrees(radius_km / (R * cosf(lat * DEG_TO_RAD)));

    char path[200];
    snprintf(path, sizeof(path),
             "/api/states/all?lamin=%.4f&lamax=%.4f&lomin=%.4f&lomax=%.4f",
             lat - dlat, lat + dlat, lon - dlon, lon + dlon);

    String payload;
    int rc = fetchHTTPS("opensky-network.org", path, payload);
    if (rc == 429) { payload = ""; return -1; }
    if (rc != 200) { payload = ""; return -2; }

    Serial.printf("[OpenSky] Payload %d B\n", payload.length());

    // Filter to only the state-vector fields we use (indices match Python opensky.py)
    StaticJsonDocument<200> filter;
    {
        JsonArray outer = filter.to<JsonObject>().createNestedArray("states");
        JsonArray inner = outer.createNestedArray();
        inner[0]  = true;   // icao24
        inner[1]  = true;   // callsign
        inner[2]  = true;   // origin_country
        inner[5]  = true;   // longitude
        inner[6]  = true;   // latitude
        inner[7]  = true;   // baro_altitude (m)
        inner[8]  = true;   // on_ground
        inner[9]  = true;   // velocity (m/s)
        inner[10] = true;   // true_track (deg)
        inner[11] = true;   // vertical_rate (m/s)
        inner[14] = true;   // squawk
    }

    SpiRamJsonDocument doc(32768);
    auto err = deserializeJson(doc, payload, DeserializationOption::Filter(filter));
    payload = "";  // free immediately after parse

    if (err) {
        Serial.printf("[OpenSky] Parse error: %s\n", err.c_str());
        return -2;
    }

    JsonArray states = doc["states"].as<JsonArray>();
    if (states.isNull()) {
        Serial.println("[OpenSky] No 'states' array");
        return -2;
    }

    int count = 0;
    for (JsonArray sv : states) {
        if (count >= maxFlights) break;
        if (sv.size() < 15) continue;

        float fLat = jfloat(sv[6]);
        float fLon = jfloat(sv[5]);
        if (isnan(fLat) || isnan(fLon)) continue;

        FlightData& f = out[count];
        memset(&f, 0, sizeof(FlightData));

        const char* icao  = sv[0].as<const char*>();
        const char* cs    = sv[1].as<const char*>();
        const char* cntry = sv[2].as<const char*>();
        const char* sq    = sv[14].as<const char*>();

        strncpy(f.icao24,         icao  ? icao  : "", sizeof(f.icao24)         - 1);
        strncpy(f.callsign,       cs    ? cs    : "", sizeof(f.callsign)        - 1);
        strncpy(f.origin_country, cntry ? cntry : "", sizeof(f.origin_country)  - 1);
        strncpy(f.squawk,         sq    ? sq    : "", sizeof(f.squawk)           - 1);
        cleanCallsign(f.callsign);

        airlineLookup(f.callsign, f.airline_name, sizeof(f.airline_name));

        strncpy(f.airline_icao, f.callsign, 3);
        f.airline_icao[3] = '\0';
        for (int i = 0; f.airline_icao[i]; i++)
            if (f.airline_icao[i] >= 'a') f.airline_icao[i] -= 32;
        const char* iata = airlineIcaoToIata(f.airline_icao);
        strncpy(f.airline_iata, iata, sizeof(f.airline_iata) - 1);

        logoFetchEnqueue(f.callsign, f.airline_iata);

        f.latitude      = fLat;
        f.longitude     = fLon;
        f.baro_altitude = jfloat(sv[7]);
        f.on_ground     = sv[8].as<bool>();
        f.velocity      = jfloat(sv[9]);
        f.true_track    = jfloat(sv[10]);
        f.vertical_rate = jfloat(sv[11]);
        f.distance_km   = haversineKm(lat, lon, fLat, fLon);
        count++;
    }

    doc.clear();
    Serial.printf("[OpenSky] %d flights parsed\n", count);
    return count;
}

// ---------------------------------------------------------------------------
// Public API
//   1. Plain HTTP (adsb.fi port 80 probe + adsb.lol + adsb.one) — no SSL cost
//   2. adsb.lol HTTPS — when HTTP returns 502
//   3. adsb.fi  HTTPS — richest data, route fields included
//   4. OpenSky  HTTPS — last resort, strict rate limits
// ---------------------------------------------------------------------------
int fetchFlights(float lat, float lon, float radius_km,
                 const char* user, const char* pass,
                 FlightData* outFlights, int maxFlights) {
    Serial.printf("[Flights] Searching lat=%.4f lon=%.4f radius=%.1fkm\n",
                  lat, lon, radius_km);
    Serial.printf("[MEM] Before fetch — heap: %d free, psram: %d free\n",
                  ESP.getFreeHeap(), ESP.getFreePsram());

    const float radius_nm = radius_km / 1.852f;
    bool anyRateLimited = false;

    // ── 1. Plain HTTP (no SSL cost) ───────────────────────────────────────────
    {
        int n = 0;
        if (fetchAdsbAc(lat, lon, radius_nm, outFlights, maxFlights, &n)) {
            sortFlights(outFlights, n);
            if (n > 20) n = 20;
            Serial.printf("[MEM] After fetch — heap: %d free, psram: %d free\n",
                          ESP.getFreeHeap(), ESP.getFreePsram());
            return n;
        }
        Serial.println("[Flights] Plain-HTTP failed, trying SSL sources");
    }

    // ── 2. adsb.lol HTTPS (same format as plain HTTP, esp_http_client) ───────
    {
        int n = 0;
        if (fetchAdsbLolSsl(lat, lon, radius_nm, outFlights, maxFlights, &n)) {
            sortFlights(outFlights, n);
            if (n > 20) n = 20;
            Serial.printf("[MEM] After fetch — heap: %d free, psram: %d free\n",
                          ESP.getFreeHeap(), ESP.getFreePsram());
            return n;
        }
        Serial.println("[Flights] adsb.lol SSL failed, trying adsb.fi");
    }

    // ── 3. adsb.fi HTTPS (richer data, includes dep/arr route fields) ────────
    {
        char adsbPath[96];
        snprintf(adsbPath, sizeof(adsbPath),
                 "/api/v2/lat/%.4f/lon/%.4f/dist/%.0f", lat, lon, radius_nm);
        int n = 0;
        if (fetchAdsbFi(adsbPath, lat, lon, outFlights, maxFlights, &n)) {
            sortFlights(outFlights, n);
            if (n > 20) n = 20;
            Serial.printf("[MEM] After fetch — heap: %d free, psram: %d free\n",
                          ESP.getFreeHeap(), ESP.getFreePsram());
            return n;
        }
        Serial.println("[Flights] adsb.fi failed, trying OpenSky (last resort)");
    }

    // ── Last resort: OpenSky Network — avoid hammering, it 429s quickly ──────
    for (int attempt = 1; attempt <= 2; attempt++) {
        int n = tryOpenSky(lat, lon, radius_km, user, pass, outFlights, maxFlights);
        if (n >= 0) {
            sortFlights(outFlights, n);
            if (n > 20) n = 20;
            Serial.printf("[MEM] After fetch — heap: %d free, psram: %d free\n",
                          ESP.getFreeHeap(), ESP.getFreePsram());
            return n;
        }
        if (n == -1) { anyRateLimited = true; break; }
        if (attempt < 2) {
            Serial.printf("[Flights] OpenSky attempt %d failed, retrying...\n", attempt);
            delay(2000);
        }
    }

    Serial.println("[Flights] All sources failed");
    Serial.printf("[MEM] After fetch (failed) — heap: %d free, psram: %d free\n",
                  ESP.getFreeHeap(), ESP.getFreePsram());
    return anyRateLimited ? -1 : 0;
}
