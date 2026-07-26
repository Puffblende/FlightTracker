#include "renderer.h"
#include "display.h"
#include "font.h"
#include "logos.h"
#include "routes.h"
#include "aircraft_types.h"
#include <Arduino.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

// ---------------------------------------------------------------------------
// Value formatters — port of src/core/models.py value_* functions
// ---------------------------------------------------------------------------

static const char* COMPASS[8] = {"N","NE","E","SE","S","SW","W","NW"};

static void fmtCallsign(char* out, int sz, const FlightData& f, const char* fmt) {
    if (strcmp(fmt, "icao24") == 0)
        snprintf(out, sz, "%s", f.icao24);
    else {
        const char* cs = f.callsign[0] ? f.callsign : f.icao24;
        snprintf(out, sz, "%s", cs);
    }
    // upper-case
    for (int i = 0; out[i]; i++) if (out[i] >= 'a') out[i] -= 32;
}

static void fmtAltitude(char* out, int sz, float baro_m, const char* fmt) {
    if (isnan(baro_m)) { strncpy(out, "---", sz); return; }
    float ft = baro_m * 3.28084f;
    if      (strcmp(fmt, "ft_full")    == 0) snprintf(out, sz, "%d",   (int)ft);
    else if (strcmp(fmt, "ft_compact") == 0) snprintf(out, sz, "%d",   (int)(ft / 1000.0f));
    else if (strcmp(fmt, "fl")         == 0) snprintf(out, sz, "%d",   (int)(ft / 100.0f));
    else if (strcmp(fmt, "m_full")     == 0) snprintf(out, sz, "%d",   (int)baro_m);
    else if (strcmp(fmt, "m_compact")  == 0) snprintf(out, sz, "%.1f", baro_m / 1000.0f);
    else                                     snprintf(out, sz, "%d",   (int)(ft / 1000.0f));
}

static void fmtSpeed(char* out, int sz, float vel_ms, const char* fmt) {
    if (isnan(vel_ms)) { strncpy(out, "---", sz); return; }
    if      (strcmp(fmt, "kts") == 0) snprintf(out, sz, "%d", (int)(vel_ms * 1.94384f));
    else if (strcmp(fmt, "kmh") == 0) snprintf(out, sz, "%d", (int)(vel_ms * 3.6f));
    else                              snprintf(out, sz, "%d", (int)(vel_ms * 2.23694f)); // mph
}

static void fmtTrack(char* out, int sz, float deg, const char* fmt) {
    if (isnan(deg)) { strncpy(out, "---", sz); return; }
    int d = (int)deg;
    const char* cmp = COMPASS[((int)roundf(deg / 45.0f)) % 8];
    if      (strcmp(fmt, "compass") == 0) snprintf(out, sz, "%s",    cmp);
    else if (strcmp(fmt, "full")    == 0) snprintf(out, sz, "%03d%s", d, cmp);
    else                                  snprintf(out, sz, "%d",    d);
}

static void fmtVrate(char* out, int sz, float vr_ms, const char* fmt) {
    if (isnan(vr_ms)) { strncpy(out, "---", sz); return; }
    int fpm = (int)(vr_ms * 196.85f);
    char sign = fpm >= 0 ? '+' : '-';
    int  absfpm = fpm < 0 ? -fpm : fpm;
    if      (strcmp(fmt, "ms")    == 0) snprintf(out, sz, "%+.1f", vr_ms);
    else if (strcmp(fmt, "arrow") == 0) snprintf(out, sz, "%c%d",  vr_ms >= 0 ? '^' : 'v', absfpm);
    else                                snprintf(out, sz, "%c%d",  sign, absfpm);  // fpm
}

static void fmtDistance(char* out, int sz, float km, const char* fmt) {
    if      (strcmp(fmt, "nm")   == 0) snprintf(out, sz, "%.1f", km / 1.852f);
    else if (strcmp(fmt, "km_i") == 0) snprintf(out, sz, "%d",   (int)km);
    else if (strcmp(fmt, "nm_i") == 0) snprintf(out, sz, "%d",   (int)(km / 1.852f));
    else                               snprintf(out, sz, "%.1f", km);
}

// Mirrors AIRPORTS in src/core/progress.py exactly, so the progress bar
// covers the same airports on the device as in the Python preview.
static const struct { const char* code; float lat; float lon; } AIRPORTS[] = {
    // Europe
    {"FRA", 50.0379f, 8.5622f},     {"EDDF", 50.0379f, 8.5622f},
    {"MUC", 48.3538f, 11.7861f},    {"EDDM", 48.3538f, 11.7861f},
    {"BER", 52.3667f, 13.5033f},    {"EDDB", 52.3667f, 13.5033f},
    {"HAM", 53.6304f, 9.9882f},     {"EDDH", 53.6304f, 9.9882f},
    {"DUS", 51.2895f, 6.7668f},     {"EDDL", 51.2895f, 6.7668f},
    {"CGN", 50.8659f, 7.1427f},     {"EDDK", 50.8659f, 7.1427f},
    {"STR", 48.6899f, 9.2220f},     {"EDDS", 48.6899f, 9.2220f},
    {"LHR", 51.4700f, -0.4543f},    {"EGLL", 51.4700f, -0.4543f},
    {"LGW", 51.1537f, -0.1821f},    {"EGKK", 51.1537f, -0.1821f},
    {"STN", 51.8849f, 0.2350f},     {"EGSS", 51.8849f, 0.2350f},
    {"MAN", 53.3537f, -2.2750f},    {"EGCC", 53.3537f, -2.2750f},
    {"CDG", 49.0097f, 2.5479f},     {"LFPG", 49.0097f, 2.5479f},
    {"ORY", 48.7233f, 2.3794f},     {"LFPO", 48.7233f, 2.3794f},
    {"AMS", 52.3105f, 4.7683f},     {"EHAM", 52.3105f, 4.7683f},
    {"BRU", 50.9014f, 4.4844f},     {"EBBR", 50.9014f, 4.4844f},
    {"ZRH", 47.4647f, 8.5492f},     {"LSZH", 47.4647f, 8.5492f},
    {"GVA", 46.2381f, 6.1090f},     {"LSGG", 46.2381f, 6.1090f},
    {"VIE", 48.1103f, 16.5697f},    {"LOWW", 48.1103f, 16.5697f},
    {"MAD", 40.4983f, -3.5676f},    {"LEMD", 40.4983f, -3.5676f},
    {"BCN", 41.2974f, 2.0833f},     {"LEBL", 41.2974f, 2.0833f},
    {"LIS", 38.7813f, -9.1359f},    {"LPPT", 38.7813f, -9.1359f},
    {"FCO", 41.8003f, 12.2389f},    {"LIRF", 41.8003f, 12.2389f},
    {"MXP", 45.6306f, 8.7281f},     {"LIMC", 45.6306f, 8.7281f},
    {"ATH", 37.9364f, 23.9445f},    {"LGAV", 37.9364f, 23.9445f},
    {"IST", 41.2753f, 28.7519f},    {"LTFM", 41.2753f, 28.7519f},
    {"SAW", 40.8986f, 29.3092f},    {"LTFJ", 40.8986f, 29.3092f},
    {"ARN", 59.6519f, 17.9186f},    {"ESSA", 59.6519f, 17.9186f},
    {"CPH", 55.6181f, 12.6561f},    {"EKCH", 55.6181f, 12.6561f},
    {"OSL", 60.1939f, 11.1004f},    {"ENGM", 60.1939f, 11.1004f},
    {"HEL", 60.3172f, 24.9633f},    {"EFHK", 60.3172f, 24.9633f},
    {"DUB", 53.4213f, -6.2701f},    {"EIDW", 53.4213f, -6.2701f},
    {"PRG", 50.1008f, 14.2632f},    {"LKPR", 50.1008f, 14.2632f},
    {"WAW", 52.1657f, 20.9671f},    {"EPWA", 52.1657f, 20.9671f},
    {"BUD", 47.4369f, 19.2556f},    {"LHBP", 47.4369f, 19.2556f},
    {"SVO", 55.9726f, 37.4146f},    {"UUEE", 55.9726f, 37.4146f},
    // North America
    {"JFK", 40.6413f, -73.7781f},   {"KJFK", 40.6413f, -73.7781f},
    {"EWR", 40.6925f, -74.1687f},   {"KEWR", 40.6925f, -74.1687f},
    {"LGA", 40.7769f, -73.8740f},   {"KLGA", 40.7769f, -73.8740f},
    {"LAX", 33.9416f, -118.4085f},  {"KLAX", 33.9416f, -118.4085f},
    {"SFO", 37.6188f, -122.3754f},  {"KSFO", 37.6188f, -122.3754f},
    {"SEA", 47.4502f, -122.3088f},  {"KSEA", 47.4502f, -122.3088f},
    {"ORD", 41.9742f, -87.9073f},   {"KORD", 41.9742f, -87.9073f},
    {"MDW", 41.7868f, -87.7522f},   {"KMDW", 41.7868f, -87.7522f},
    {"ATL", 33.6407f, -84.4277f},   {"KATL", 33.6407f, -84.4277f},
    {"DFW", 32.8998f, -97.0403f},   {"KDFW", 32.8998f, -97.0403f},
    {"DEN", 39.8561f, -104.6737f},  {"KDEN", 39.8561f, -104.6737f},
    {"MIA", 25.7959f, -80.2870f},   {"KMIA", 25.7959f, -80.2870f},
    {"BOS", 42.3656f, -71.0096f},   {"KBOS", 42.3656f, -71.0096f},
    {"IAD", 38.9531f, -77.4565f},   {"KIAD", 38.9531f, -77.4565f},
    {"YYZ", 43.6777f, -79.6248f},   {"CYYZ", 43.6777f, -79.6248f},
    {"YVR", 49.1939f, -123.1844f},  {"CYVR", 49.1939f, -123.1844f},
    // Asia / Oceania
    {"HND", 35.5494f, 139.7798f},   {"RJTT", 35.5494f, 139.7798f},
    {"NRT", 35.7720f, 140.3929f},   {"RJAA", 35.7720f, 140.3929f},
    {"ICN", 37.4602f, 126.4407f},   {"RKSI", 37.4602f, 126.4407f},
    {"PEK", 40.0801f, 116.5846f},   {"ZBAA", 40.0801f, 116.5846f},
    {"PVG", 31.1443f, 121.8083f},   {"ZSPD", 31.1443f, 121.8083f},
    {"HKG", 22.3080f, 113.9185f},   {"VHHH", 22.3080f, 113.9185f},
    {"SIN", 1.3644f, 103.9915f},    {"WSSS", 1.3644f, 103.9915f},
    {"BKK", 13.6900f, 100.7501f},   {"VTBS", 13.6900f, 100.7501f},
    {"DXB", 25.2532f, 55.3657f},    {"OMDB", 25.2532f, 55.3657f},
    {"DOH", 25.2731f, 51.6080f},    {"OTHH", 25.2731f, 51.6080f},
    {"DEL", 28.5562f, 77.1000f},    {"VIDP", 28.5562f, 77.1000f},
    {"BOM", 19.0896f, 72.8656f},    {"VABB", 19.0896f, 72.8656f},
    {"SYD", -33.9399f, 151.1753f},  {"YSSY", -33.9399f, 151.1753f},
    {"MEL", -37.6690f, 144.8410f},  {"YMML", -37.6690f, 144.8410f},
};

static bool airportLocation(const char* code, float& lat, float& lon) {
    if (!code || !code[0]) return false;
    char key[5] = {0};
    strncpy(key, code, sizeof(key) - 1);
    for (int i = 0; key[i]; i++) if (key[i] >= 'a') key[i] -= 32;

    // Airports learned live from adsbdb.com route lookups (routes.cpp) —
    // checked first since it covers anything the static table below
    // doesn't, same as Python's dynamically-seeded AIRPORTS dict.
    if (routeCacheAirportLocation(key, lat, lon)) return true;

    for (size_t i = 0; i < sizeof(AIRPORTS) / sizeof(AIRPORTS[0]); i++) {
        if (strcmp(key, AIRPORTS[i].code) == 0) {
            lat = AIRPORTS[i].lat;
            lon = AIRPORTS[i].lon;
            return true;
        }
    }
    return false;
}

static float gcDistanceKm(float lat1, float lon1, float lat2, float lon2) {
    constexpr float R = 6371.0f;
    float p1 = lat1 * 0.0174532925f;
    float p2 = lat2 * 0.0174532925f;
    float dp = (lat2 - lat1) * 0.0174532925f;
    float dl = (lon2 - lon1) * 0.0174532925f;
    float a = sinf(dp / 2.0f) * sinf(dp / 2.0f) + cosf(p1) * cosf(p2) * sinf(dl / 2.0f) * sinf(dl / 2.0f);
    return R * 2.0f * asinf(sqrtf(a));
}

static float flightProgress(const FlightData& f) {
    float oLat, oLon, dLat, dLon;
    if (!airportLocation(f.origin, oLat, oLon) || !airportLocation(f.destination, dLat, dLon))
        return NAN;
    if (isnan(f.latitude) || isnan(f.longitude)) return NAN;

    float total = gcDistanceKm(oLat, oLon, dLat, dLon);
    if (total <= 0.0f) return NAN;
    float done = gcDistanceKm(oLat, oLon, f.latitude, f.longitude);
    return fminf(fmaxf(done / total, 0.0f), 1.0f);
}

static void fmtRoute(char* out, int sz, const FlightData& f, const char* fmt) {
    const char* o = f.origin[0]      ? f.origin      : "???";
    const char* d = f.destination[0] ? f.destination : "???";
    if      (strcmp(fmt, "arrow") == 0) snprintf(out, sz, "%s>%s", o, d);
    else if (strcmp(fmt, "dep")   == 0) snprintf(out, sz, "%s", o);
    else if (strcmp(fmt, "arr")   == 0) snprintf(out, sz, "%s", d);
    else                                snprintf(out, sz, "%s-%s", o, d);
}

static void fmtAirline(char* out, int sz, const FlightData& f, const char* fmt) {
    // Use cached airline name if available; fall back to 3-char ICAO prefix
    if (f.airline_name[0]) {
        snprintf(out, sz, "%s", f.airline_name);
        return;
    }
    char icao[4] = {0};
    strncpy(icao, f.callsign, 3);
    for (int i = 0; icao[i]; i++) if (icao[i] >= 'a') icao[i] -= 32;
    snprintf(out, sz, "%s", icao[0] ? icao : "---");
}

static void fmtSquawk(char* out, int sz, const FlightData& f) {
    snprintf(out, sz, "%s", f.squawk[0] ? f.squawk : "----");
}

static void fmtCountry(char* out, int sz, const FlightData& f) {
    snprintf(out, sz, "%s", f.origin_country);
    for (int i = 0; out[i]; i++) if (out[i] >= 'a') out[i] -= 32;
}

// ---------------------------------------------------------------------------
// Block text composition (label + value + unit), port of render_block_text()
// ---------------------------------------------------------------------------

static bool isPlaceholder(const char* v) {
    if (!v || !v[0]) return true;
    for (int i = 0; v[i]; i++)
        if (v[i] != '-' && v[i] != '?') return false;
    return true;
}

static void blockText(char* out, int sz, const LayoutBlock& blk, const FlightData& f) {
    char value[48] = {0};
    const char* k   = blk.key;
    const char* fmt = blk.fmt;

    if      (strcmp(k, "callsign")     == 0) fmtCallsign(value,sizeof(value),f,fmt);
    else if (strcmp(k, "altitude")     == 0) fmtAltitude(value,sizeof(value),f.baro_altitude,fmt);
    else if (strcmp(k, "speed")        == 0) fmtSpeed(value,sizeof(value),f.velocity,fmt);
    else if (strcmp(k, "track")        == 0) fmtTrack(value,sizeof(value),f.true_track,fmt);
    else if (strcmp(k, "vrate")        == 0) fmtVrate(value,sizeof(value),f.vertical_rate,fmt);
    else if (strcmp(k, "distance")     == 0) fmtDistance(value,sizeof(value),f.distance_km,fmt);
    else if (strcmp(k, "route")        == 0) fmtRoute(value,sizeof(value),f,fmt);
    else if (strcmp(k, "airline")      == 0) fmtAirline(value,sizeof(value),f,fmt);
    else if (strcmp(k, "squawk")       == 0) fmtSquawk(value,sizeof(value),f);
    else if (strcmp(k, "country")      == 0) fmtCountry(value,sizeof(value),f);
    // aircraft_type is handled as a special case in renderFlight (bypasses isPlaceholder)

    if (isPlaceholder(value)) {
        // No valid data — show label only (often empty), no unit
        snprintf(out, sz, "%s", blk.custom_label);
    } else {
        snprintf(out, sz, "%s%s%s", blk.custom_label, value, blk.custom_unit);
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void renderFlight(const FlightData& flight,
                  const LayoutBlock* blocks, int nBlocks) {
    displayClear();
    char text[64];
    for (int i = 0; i < nBlocks; i++) {
        const LayoutBlock& blk = blocks[i];
        Serial.printf("[Render] key=%-16s x=%3d y=%3d enabled=%d\n",
                      blk.key, blk.x, blk.y, (int)blk.enabled);
        if (!blk.enabled) continue;
        if (strcmp(blk.key, "logo") == 0) {
            const char* src = flight.callsign[0] ? flight.callsign : flight.icao24;
            char icao[5] = {0};
            strncpy(icao, src, 3);
            for (int j = 0; icao[j]; j++) if (icao[j] >= 'a') icao[j] -= 32;
            int sz = 24;
            if      (strcmp(blk.fmt, "sq16") == 0) sz = 16;
            else if (strcmp(blk.fmt, "sq24") == 0) sz = 24;
            else if (strcmp(blk.fmt, "sq32") == 0) sz = 32;
            else if (strcmp(blk.fmt, "sq40") == 0) sz = 40;
            drawLogo(icao, blk.x, blk.y, sz, blk.r, blk.g, blk.b);
            continue;
        }
        if (strcmp(blk.key, "aircraft_type") == 0) {
            // Port of value_aircraft_type()/value_aircraft_type_auto() in
            // src/core/models.py. Python resolves full/model/manufacturer
            // names purely from the static AIRCRAFT_TYPES table keyed by
            // the short ICAO code — it never touches live "desc" data.
            // The ESP32 used to prefer the live aircraft_type_full field
            // instead, which is sparsely populated by the upstream feeds;
            // that's why the same flight could show "A321NEO" in the
            // Python app but the raw code "A21N" on the panel. Using the
            // same static table here as the primary source closes that gap.
            const char* typ = flight.aircraft_type;
            if (!typ[0]) continue;  // no type data at all → skip block

            char code4[8] = {0};
            snprintf(code4, sizeof(code4), "%.4s", typ);
            for (int j = 0; code4[j]; j++) if (code4[j] >= 'a') code4[j] -= 32;

            const char* full = lookupAircraftType(typ);  // "" if unknown
            char manufacturer[32] = {0}, model[32] = {0};
            if (full[0]) {
                const char* sp = strchr(full, ' ');
                int mlen = sp ? (int)(sp - full) : (int)strlen(full);
                snprintf(manufacturer, sizeof(manufacturer), "%.*s", mlen, full);
                snprintf(model, sizeof(model), "%s", sp ? sp + 1 : full);
                for (int j = 0; manufacturer[j]; j++) if (manufacturer[j] >= 'a') manufacturer[j] -= 32;
                for (int j = 0; model[j]; j++) if (model[j] >= 'a') model[j] -= 32;
            }

            char typeStr[32] = {0};
            if (strcmp(blk.fmt, "auto") == 0) {
                // Longest representation that fits the pixel budget:
                // full name, then model, then manufacturer, then code.
                int budget = blk.custom_width > 0 ? blk.custom_width : (TOTAL_WIDTH - blk.x);
                char fullUpper[32] = {0};
                snprintf(fullUpper, sizeof(fullUpper), "%s", full);
                for (int j = 0; fullUpper[j]; j++) if (fullUpper[j] >= 'a') fullUpper[j] -= 32;
                const char* candidates[4] = { fullUpper, model, manufacturer, code4 };
                const char* chosen = nullptr;
                for (int c = 0; c < 4; c++) {
                    if (!candidates[c][0]) continue;
                    if (fontTextWidth(candidates[c], blk.font_scale) <= budget) {
                        chosen = candidates[c];
                        break;
                    }
                }
                if (!chosen) chosen = code4;
                snprintf(typeStr, sizeof(typeStr), "%s", chosen);
            } else if (strcmp(blk.fmt, "code") == 0 || strcmp(blk.fmt, "short") == 0) {
                snprintf(typeStr, sizeof(typeStr), "%s", code4);
            } else if (strcmp(blk.fmt, "manufacturer") == 0) {
                snprintf(typeStr, sizeof(typeStr), "%s", manufacturer[0] ? manufacturer : code4);
            } else if (strcmp(blk.fmt, "model") == 0) {
                snprintf(typeStr, sizeof(typeStr), "%s", model[0] ? model : code4);
            } else {
                // "full"
                snprintf(typeStr, sizeof(typeStr), "%s", full[0] ? full : code4);
                for (int j = 0; typeStr[j]; j++) if (typeStr[j] >= 'a') typeStr[j] -= 32;
            }
            Serial.printf("[aircraft_type] fmt=%s value='%s'\n", blk.fmt, typeStr);
            fontDrawText(blk.x, blk.y, typeStr, blk.r, blk.g, blk.b, blk.font_scale,
                         blk.custom_width > 0 ? blk.custom_width : 0);
            continue;
        }

        if (strcmp(blk.key, "route") == 0) {
            // Mirrors value_route() in src/core/models.py: "icao" prefers
            // the 4-char ICAO codes, everything else prefers the 3-char
            // IATA codes, each falling back to the other form if its
            // preferred one is missing (adsbdb.com doesn't always have
            // both for every airport).
            const char* iataO = flight.origin;
            const char* iataD = flight.destination;
            const char* icaoO = flight.dep_icao;
            const char* icaoD = flight.arr_icao;
            char route[24] = {0};
            if (strcmp(blk.fmt, "icao") == 0) {
                const char* o = icaoO[0] ? icaoO : iataO;
                const char* d = icaoD[0] ? icaoD : iataD;
                if (!o[0] || !d[0]) continue;
                snprintf(route, sizeof(route), "%s-%s", o, d);
            } else if (strcmp(blk.fmt, "arrow") == 0) {
                const char* o = iataO[0] ? iataO : icaoO;
                const char* d = iataD[0] ? iataD : icaoD;
                if (!o[0] || !d[0]) continue;
                snprintf(route, sizeof(route), "%s>%s", o, d);
            } else if (strcmp(blk.fmt, "dep") == 0) {
                const char* o = iataO[0] ? iataO : icaoO;
                if (!o[0]) continue;
                snprintf(route, sizeof(route), "%s", o);
            } else if (strcmp(blk.fmt, "arr") == 0) {
                const char* d = iataD[0] ? iataD : icaoD;
                if (!d[0]) continue;
                snprintf(route, sizeof(route), "%s", d);
            } else {
                // "iata" (default)
                const char* o = iataO[0] ? iataO : icaoO;
                const char* d = iataD[0] ? iataD : icaoD;
                if (!o[0] || !d[0]) continue;
                snprintf(route, sizeof(route), "%s-%s", o, d);
            }
            fontDrawText(blk.x, blk.y, route, blk.r, blk.g, blk.b, blk.font_scale,
                         blk.custom_width > 0 ? blk.custom_width : 0);
            continue;
        }

        if (strcmp(blk.key, "progress") == 0) {
            int barW = blk.custom_width > 0 ? blk.custom_width : TOTAL_WIDTH - blk.x;
            if (barW < 1) continue;

            float prog = flightProgress(flight);
            int pos = !isnan(prog) ? (int)roundf((barW - 1) * fminf(fmaxf(prog, 0.0f), 1.0f)) : -1;
            for (int dx = 0; dx < barW; dx++) {
                int px = blk.x + dx;
                if (px < 0 || px >= TOTAL_WIDTH) continue;
                if (pos >= 0 && dx <= pos) {
                    displaySetPixel(px, blk.y, blk.r, blk.g, blk.b);
                } else if ((dx & 1) == 0) {
                    displaySetPixel(px, blk.y, 60, 60, 60);
                }
            }
            continue;
        }

        blockText(text, sizeof(text), blk, flight);
        if (!text[0]) continue;

        int mw = blk.custom_width > 0 ? (int)blk.custom_width : 0;
        fontDrawText(blk.x, blk.y, text,
                     blk.r, blk.g, blk.b,
                     blk.font_scale, mw);
    }
    displayFlush();
}

void renderNoFlights() {
    displayClear();
    const char* msg = "NO FLIGHTS";
    int tw = fontTextWidth(msg);
    int cx = (TOTAL_WIDTH  - tw) / 2;
    int cy = (TOTAL_HEIGHT - FONT_CHAR_H) / 2;
    if (cx < 0) cx = 0;
    if (cy < 0) cy = 0;
    fontDrawText(cx, cy, msg, 80, 80, 80);
    displayFlush();
}

void renderMessage(const char* line1, const char* line2) {
    displayClear();
    if (line1) {
        int tw = fontTextWidth(line1);
        int cx = (TOTAL_WIDTH - tw) / 2;
        if (cx < 0) cx = 0;
        int cy = line2 ? (TOTAL_HEIGHT / 2 - FONT_CHAR_H - 1) : (TOTAL_HEIGHT - FONT_CHAR_H) / 2;
        fontDrawText(cx, cy, line1, 200, 200, 200);
    }
    if (line2) {
        int tw = fontTextWidth(line2);
        int cx = (TOTAL_WIDTH - tw) / 2;
        if (cx < 0) cx = 0;
        fontDrawText(cx, TOTAL_HEIGHT / 2 + 1, line2, 140, 140, 140);
    }
    displayFlush();
}

// ---------------------------------------------------------------------------
// Default layout — mirrors Python default_layout() in src/core/models.py
// ---------------------------------------------------------------------------
int defaultLayout(LayoutBlock* out, int maxBlocks) {
    struct Def {
        const char* key; int x; int y; bool en;
        const char* fmt;
        uint8_t r, g, b;
        float scale;
        const char* label; const char* unit;
    };
    static const Def DEFS[] = {
        {"airline",       26,  0, true,  "full",       255,255,255, 1.0f, "",   ""},
        {"route",         26,  8, true,  "iata",       255,255,255, 1.0f, "",   ""},
        {"aircraft_type", 26, 16, true,  "code",       100,255,100, 1.0f, "",   ""},
        {"altitude",       0, 25, true,  "ft_compact", 100,200,255, 1.0f, "A:", "kft"},
        {"speed",         32, 25, true,  "mph",        255,140,  0, 1.0f, "S:", "mph"},
        {"track",          0, 33, true,  "deg",        180,180,255, 1.0f, "T:", ""},
        {"vrate",         32, 33, true,  "fpm",        255,100,100, 1.0f, "V:", "fpm"},
        // disabled by default:
        {"callsign",      26, 24, false, "full",       255,220,  0, 1.0f, "",   ""},
        {"squawk",         0, 24, false, "bare",       200,200,200, 1.0f, "",   ""},
        {"country",        0, 24, false, "full",       200,200,200, 1.0f, "",   ""},
        {"distance",      68, 25, false, "km",         180,255,180, 1.0f, "D:", "km"},
    };
    int n = (int)(sizeof(DEFS) / sizeof(DEFS[0]));
    if (n > maxBlocks) n = maxBlocks;
    for (int i = 0; i < n; i++) {
        LayoutBlock& b = out[i];
        memset(&b, 0, sizeof(b));
        strncpy(b.key, DEFS[i].key, sizeof(b.key) - 1);
        b.x = DEFS[i].x; b.y = DEFS[i].y;
        b.enabled = DEFS[i].en;
        strncpy(b.fmt, DEFS[i].fmt, sizeof(b.fmt) - 1);
        b.r = DEFS[i].r; b.g = DEFS[i].g; b.b = DEFS[i].b;
        b.font_scale = DEFS[i].scale;
        strncpy(b.custom_label, DEFS[i].label, sizeof(b.custom_label) - 1);
        strncpy(b.custom_unit,  DEFS[i].unit,  sizeof(b.custom_unit)  - 1);
    }
    return n;
}
