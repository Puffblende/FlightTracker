#include "logos.h"
#include "display.h"
#include "config.h"
#include "fs_lock.h"
#include "logo_catalog.h"
#include "plane_icon.h"
#include <LittleFS.h>
#include <Arduino.h>

static const int MAX_LOGO_SIZE = 40;

// ---------------------------------------------------------------------------
// Draw a baked-in 40x40 RGB image (real logo or the fallback plane icon,
// below) at any requested size via nearest-neighbor resize — same idea as
// get_logo()'s master-image cache in src/api/logos.py: bake once at a
// single fixed size, derive everything smaller on the fly. Iterates
// DESTINATION pixels and maps back to the source, not the other way
// around — walking the source and scaling each pixel's position up only
// lights one pixel per source cell for any size > 40, leaving gaps in
// between (exactly the "empty pixels in the logo" bug the old hand-rolled
// plane-icon renderer had).
// ---------------------------------------------------------------------------
static void drawBakedLogo(const uint8_t* src, int x, int y, int size,
                          uint8_t /*r*/, uint8_t /*g*/, uint8_t /*b*/) {
    for (int dy = 0; dy < size; dy++) {
        int sy = (dy * BAKED_LOGO_SIZE) / size;
        int py = y + dy;
        if (py < 0 || py >= TOTAL_HEIGHT) continue;
        for (int dx = 0; dx < size; dx++) {
            int sx = (dx * BAKED_LOGO_SIZE) / size;
            int px = x + dx;
            if (px < 0 || px >= TOTAL_WIDTH) continue;
            const uint8_t* p = src + (sy * BAKED_LOGO_SIZE + sx) * 3;
            displaySetPixel(px, py, p[0], p[1], p[2]);
        }
    }
}

// ---------------------------------------------------------------------------
// Fallback: generic plane icon — a real 40x40 RGB asset (plane_icon.cpp,
// composited onto black once in Python from src/assets/plane_icon.png),
// not a hand-drawn 1-bit mask. Drawn the same way as a real baked logo.
// ---------------------------------------------------------------------------
static void drawPlaneIcon(int x, int y, int size, uint8_t r, uint8_t g, uint8_t b) {
    drawBakedLogo(planeIconData(), x, y, size, r, g, b);
}

// ---------------------------------------------------------------------------
// Draw logo: baked-in catalog first, LittleFS cache second, plane icon last.
//
// The baked catalog (logo_catalog.cpp) covers every airline in AIRLINE_DB —
// i.e. every airline the device can ever resolve a name for at all — so in
// practice this is the only path that ever matters now: no network fetch,
// no dependency on a Python push having arrived or survived a filesystem
// event, available immediately after any reflash.
//
// The LittleFS path only still exists as a safety net for an ICAO that
// somehow isn't in the baked catalog (shouldn't happen given the above,
// but costs nothing to keep). File layout there: byte 0 = reserved;
// bytes 1…end = size×size×3 raw RGB, written by ft_webserver.cpp from a
// POST /config or /logos push.
//
// Either way, pixels are drawn exactly as received: no background
// skipping, no color tinting. Python already composited each logo onto its
// correct background (white or black, whichever reads best on that
// particular mark — see _composite_on_white) before it was baked in or
// pushed, so re-processing here would just make the device's rendering
// diverge from what the Python app shows.
// ---------------------------------------------------------------------------

void drawLogo(const char* icao, int x, int y, int size,
              uint8_t r, uint8_t g, uint8_t b) {
    const uint8_t* baked = lookupBakedLogo(icao);
    if (baked) {
        Serial.printf("[Logo] BAKED HIT %.3s\n", icao);
        drawBakedLogo(baked, x, y, size, r, g, b);
        return;
    }

    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, size);

    // Guards against fetchTask (a different core) writing the route/airport
    // cache to LittleFS at the same moment this reads a logo file — without
    // this, the read can come back truncated even though the file opens
    // fine (a HIT that silently renders as solid black). See fs_lock.h.
    FsLock _lock;
    File f = LittleFS.open(path, "r");
    if (!f) {
        Serial.printf("[Logo] MISS %s (not in baked catalog or LittleFS) — drawing fallback icon\n", path);
        drawPlaneIcon(x, y, size, r, g, b);
        return;
    }
    Serial.printf("[Logo] LittleFS HIT %s\n", path);

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
            displaySetPixel(px, py, row[srcX * 3], row[srcX * 3 + 1], row[srcX * 3 + 2]);
        }
    }
    f.close();
}
