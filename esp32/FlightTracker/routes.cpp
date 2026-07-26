#include "routes.h"
#include "http_utils.h"
#include <ArduinoJson.h>
#include <Arduino.h>
#include <LittleFS.h>
#include <string.h>
#include <math.h>

// ---------------------------------------------------------------------------
// In-memory cache — callsign → (origin, destination) IATA + ICAO codes.
// Small and fixed-size: a callsign is at most 8 chars, and a typical
// in-range flight count is a few dozen, so 128 entries comfortably covers
// many fetch cycles' worth of distinct callsigns.
//
// Persisted to LittleFS (raw struct dump, not JSON — fixed layout, no
// parsing needed) so the device doesn't start from zero on every reboot.
// Without this, the device was effectively always "cold" relative to the
// Python app, which persists its own route cache to disk — same external
// API, same callsign, but wildly different amounts of already-learned
// data, which is what made the same flight look complete on one side and
// not the other. Written only when a lookup actually learns something new
// (not on every cache hit), so this stays well within normal flash wear.
// ---------------------------------------------------------------------------

struct RouteEntry {
    char callsign[9];
    char origin[6];
    char destination[6];
    char originIcao[6];
    char destIcao[6];
    bool used;
};

static const int CACHE_SIZE = 128;
static RouteEntry s_cache[CACHE_SIZE];
static int s_nextSlot = 0;  // ring buffer — overwrite oldest once full

static const char* ROUTE_CACHE_PATH = "/route_cache.bin";

static void saveRouteCache() {
    File f = LittleFS.open(ROUTE_CACHE_PATH, "w");
    if (!f) return;
    f.write((const uint8_t*)&s_nextSlot, sizeof(s_nextSlot));
    f.write((const uint8_t*)s_cache, sizeof(s_cache));
    f.close();
}

static void loadRouteCache() {
    File f = LittleFS.open(ROUTE_CACHE_PATH, "r");
    if (!f) return;
    if (f.size() == sizeof(s_nextSlot) + sizeof(s_cache)) {
        f.read((uint8_t*)&s_nextSlot, sizeof(s_nextSlot));
        f.read((uint8_t*)s_cache, sizeof(s_cache));
        Serial.println("[Routes] Loaded cached routes from LittleFS");
    }
    f.close();
}

// The Python app enriches every flight each cycle (rate-limited to one
// adsbdb.com call per 0.25s internally); a too-small budget here means the
// device takes many more fetch cycles than Python to catch up on route
// data for the same flights, showing up as the progress bar (which needs
// origin+destination) and ICAO route codes lagging behind or missing on
// the device long after the Python app already has them for that flight.
static const int MAX_LOOKUPS_PER_CYCLE = 6;
static int s_budgetRemaining = 0;

void routeLookupBudgetReset() {
    s_budgetRemaining = MAX_LOOKUPS_PER_CYCLE;
}

static RouteEntry* findCached(const char* callsign) {
    for (int i = 0; i < CACHE_SIZE; i++) {
        if (s_cache[i].used && strcmp(s_cache[i].callsign, callsign) == 0)
            return &s_cache[i];
    }
    return nullptr;
}

static void storeCache(const char* callsign, const char* origin, const char* dest,
                        const char* originIcao, const char* destIcao) {
    RouteEntry& e = s_cache[s_nextSlot];
    strncpy(e.callsign, callsign, sizeof(e.callsign) - 1);   e.callsign[sizeof(e.callsign) - 1] = '\0';
    strncpy(e.origin, origin, sizeof(e.origin) - 1);         e.origin[sizeof(e.origin) - 1] = '\0';
    strncpy(e.destination, dest, sizeof(e.destination) - 1); e.destination[sizeof(e.destination) - 1] = '\0';
    strncpy(e.originIcao, originIcao, sizeof(e.originIcao) - 1); e.originIcao[sizeof(e.originIcao) - 1] = '\0';
    strncpy(e.destIcao, destIcao, sizeof(e.destIcao) - 1);       e.destIcao[sizeof(e.destIcao) - 1] = '\0';
    e.used = true;
    s_nextSlot = (s_nextSlot + 1) % CACHE_SIZE;
    saveRouteCache();
}

static void toUpper(char* s) {
    for (int i = 0; s[i]; i++) if (s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}

// ---------------------------------------------------------------------------
// Airport coordinate cache — learned from adsbdb.com's lat/lon fields, same
// idea as Python's _seed_airport(). Lets the progress bar work for any
// airport that's come up in a route lookup, not just the static table.
// ---------------------------------------------------------------------------

struct AirportCoord {
    char code[6];
    float lat, lon;
    bool used;
};

static const int AIRPORT_CACHE_SIZE = 128;
static AirportCoord s_airportCache[AIRPORT_CACHE_SIZE];
static int s_airportNextSlot = 0;

static const char* AIRPORT_CACHE_PATH = "/airport_cache.bin";

static void saveAirportCache() {
    File f = LittleFS.open(AIRPORT_CACHE_PATH, "w");
    if (!f) return;
    f.write((const uint8_t*)&s_airportNextSlot, sizeof(s_airportNextSlot));
    f.write((const uint8_t*)s_airportCache, sizeof(s_airportCache));
    f.close();
}

static void loadAirportCache() {
    File f = LittleFS.open(AIRPORT_CACHE_PATH, "r");
    if (!f) return;
    if (f.size() == sizeof(s_airportNextSlot) + sizeof(s_airportCache)) {
        f.read((uint8_t*)&s_airportNextSlot, sizeof(s_airportNextSlot));
        f.read((uint8_t*)s_airportCache, sizeof(s_airportCache));
        Serial.println("[Routes] Loaded cached airport coordinates from LittleFS");
    }
    f.close();
}

static void seedAirport(const char* code, float lat, float lon) {
    if (!code || !code[0] || isnan(lat) || isnan(lon)) return;
    for (int i = 0; i < AIRPORT_CACHE_SIZE; i++) {
        if (s_airportCache[i].used && strcmp(s_airportCache[i].code, code) == 0) {
            s_airportCache[i].lat = lat;
            s_airportCache[i].lon = lon;
            saveAirportCache();
            return;
        }
    }
    AirportCoord& e = s_airportCache[s_airportNextSlot];
    strncpy(e.code, code, sizeof(e.code) - 1);
    e.code[sizeof(e.code) - 1] = '\0';
    e.lat = lat;
    e.lon = lon;
    e.used = true;
    s_airportNextSlot = (s_airportNextSlot + 1) % AIRPORT_CACHE_SIZE;
    saveAirportCache();
}

bool routeCacheAirportLocation(const char* code, float& lat, float& lon) {
    if (!code || !code[0]) return false;
    for (int i = 0; i < AIRPORT_CACHE_SIZE; i++) {
        if (s_airportCache[i].used && strcmp(s_airportCache[i].code, code) == 0) {
            lat = s_airportCache[i].lat;
            lon = s_airportCache[i].lon;
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------

void routesInit() {
    loadRouteCache();
    loadAirportCache();
}

bool routeLookup(const char* callsign, char* origin, char* dest,
                  char* originIcao, char* destIcao) {
    origin[0] = dest[0] = originIcao[0] = destIcao[0] = '\0';
    if (!callsign || !callsign[0]) return false;

    RouteEntry* cached = findCached(callsign);
    if (cached) {
        strcpy(origin, cached->origin);
        strcpy(dest, cached->destination);
        strcpy(originIcao, cached->originIcao);
        strcpy(destIcao, cached->destIcao);
        Serial.printf("[Routes] CACHE %s -> '%s'-'%s' (icao '%s'-'%s')\n",
                      callsign, origin, dest, originIcao, destIcao);
        return origin[0] && dest[0];
    }

    if (s_budgetRemaining <= 0) {
        Serial.printf("[Routes] %s uncached, no budget left this cycle\n", callsign);
        return false;  // uncached, out of budget — retry next cycle
    }
    s_budgetRemaining--;

    char url[96];
    snprintf(url, sizeof(url), "https://api.adsbdb.com/v0/callsign/%s", callsign);
    String body;
    int code = fetchUrl(url, body, nullptr, nullptr);
    Serial.printf("[Routes] FETCH %s -> HTTP %d\n", callsign, code);

    if (code == 200) {
        DynamicJsonDocument doc(4096);
        if (!deserializeJson(doc, body)) {
            JsonObject fr = doc["response"]["flightroute"];
            if (!fr.isNull()) {
                JsonObject o = fr["origin"];
                JsonObject d = fr["destination"];

                strncpy(origin, o["iata_code"] | "", 5);      origin[5] = '\0';
                strncpy(dest, d["iata_code"] | "", 5);        dest[5] = '\0';
                strncpy(originIcao, o["icao_code"] | "", 5);  originIcao[5] = '\0';
                strncpy(destIcao, d["icao_code"] | "", 5);    destIcao[5] = '\0';
                toUpper(origin);
                toUpper(dest);
                toUpper(originIcao);
                toUpper(destIcao);

                seedAirport(origin, o["latitude"] | NAN, o["longitude"] | NAN);
                seedAirport(originIcao, o["latitude"] | NAN, o["longitude"] | NAN);
                seedAirport(dest, d["latitude"] | NAN, d["longitude"] | NAN);
                seedAirport(destIcao, d["latitude"] | NAN, d["longitude"] | NAN);
            }
        }
    }

    Serial.printf("[Routes] RESULT %s -> '%s'-'%s' (icao '%s'-'%s')\n",
                  callsign, origin, dest, originIcao, destIcao);

    // Cache the result either way — including empty, so a callsign
    // adsbdb doesn't know about isn't re-queried every single cycle.
    storeCache(callsign, origin, dest, originIcao, destIcao);
    return origin[0] && dest[0];
}
