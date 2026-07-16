#include "renderer.h"
#include "display.h"
#include "font.h"
#include "logos.h"
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

static void fmtAircraftType(char* out, int sz, const FlightData& f, const char* fmt) {
    if (strcmp(fmt, "code") == 0) {
        if (f.aircraft_type[0])
            snprintf(out, sz, "%.4s", f.aircraft_type);
        else
            snprintf(out, sz, "%.4s", f.callsign[0] ? f.callsign : f.icao24);
        for (int i = 0; out[i]; i++) if (out[i] >= 'a') out[i] -= 32;
    } else {
        // "full" — prefer long description, fall back to short code
        const char* src = f.aircraft_type_full[0] ? f.aircraft_type_full
                        : f.aircraft_type[0]       ? f.aircraft_type
                        : nullptr;
        if (src) snprintf(out, sz, "%s", src);
        // leave out[0]='\0' when nothing available — isPlaceholder suppresses rendering
    }
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
            int sz = blk.custom_width > 0 ? blk.custom_width : 24;
            drawLogo(icao, blk.x, blk.y, sz, blk.r, blk.g, blk.b);
            logoFetchEnqueue(flight.callsign, flight.airline_iata);
            continue;
        }
        if (strcmp(blk.key, "aircraft_type") == 0) {
            char typeStr[32] = {0};
            if (strcmp(blk.fmt, "code") == 0) {
                if (!flight.aircraft_type[0]) continue;  // no type data → skip block
                snprintf(typeStr, sizeof(typeStr), "%.4s", flight.aircraft_type);
                for (int j = 0; typeStr[j]; j++) if (typeStr[j] >= 'a') typeStr[j] -= 32;
            } else {
                // "full" — prefer long description, fall back to short code; skip if both empty
                const char* src = flight.aircraft_type_full[0] ? flight.aircraft_type_full
                                : flight.aircraft_type[0]       ? flight.aircraft_type
                                : nullptr;
                if (!src) continue;  // both empty → skip block
                snprintf(typeStr, sizeof(typeStr), "%s", src);
            }
            Serial.printf("[aircraft_type] fmt=%s value='%s'\n", blk.fmt, typeStr);
            fontDrawText(blk.x, blk.y, typeStr, blk.r, blk.g, blk.b, blk.font_scale,
                         blk.custom_width > 0 ? blk.custom_width : 0);
            continue;
        }

        if (strcmp(blk.key, "route") == 0) {
            // Both endpoints must be known; a partial route is never shown.
            if (!flight.origin[0] || !flight.destination[0]) continue;
            char route[16];
            snprintf(route, sizeof(route), "%s-%s", flight.origin, flight.destination);
            fontDrawText(blk.x, blk.y, route, blk.r, blk.g, blk.b, blk.font_scale,
                         blk.custom_width > 0 ? blk.custom_width : 0);
            continue;
        }

        if (strcmp(blk.key, "progress") == 0) {
            int barW = blk.custom_width > 0 ? blk.custom_width : TOTAL_WIDTH - blk.x;
            for (int dx = 0; dx < barW; dx++)
                displaySetPixel(blk.x + dx, blk.y,
                                (dx & 1) ? 0 : blk.r,
                                (dx & 1) ? 0 : blk.g,
                                (dx & 1) ? 0 : blk.b);
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
