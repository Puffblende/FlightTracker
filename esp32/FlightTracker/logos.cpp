#include "logos.h"
#include "display.h"
#include "config.h"
#include <LittleFS.h>
#include <Arduino.h>

static const int MAX_LOGO_SIZE = 40;

// ---------------------------------------------------------------------------
// Fallback: generic top-down aircraft silhouette
// ---------------------------------------------------------------------------

// Pointed nose → tapering fuselage → diamond-shaped swept wings that peak
// at full width for one row → straight fuselage → a clearly smaller tail
// stabilizer → tapered tail. Mirrors _PLANE_16 in src/api/logos.py exactly.
static const uint16_t PLANE_16[16] = {
    0x0180,  // nose tip
    0x0180,
    0x03C0,
    0x03C0,
    0x03C0,
    0x0FF0,  // wings ramping up
    0x3FFC,
    0xFFFF,  // full wingspan
    0x3FFC,  // wings ramping down
    0x03C0,
    0x03C0,
    0x03C0,
    0x0FF0,  // tail stabilizer — smaller than the main wings
    0x03C0,
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
// Logos are written by ft_webserver.cpp from the "logos" object pushed in
// POST /config (hex-encoded RGB from src/api/logos.py, sized to match the
// layout's logo block — see external_tab.py's _current_logo_size()) — the
// ESP32 never fetches logos from the network itself.
//
// Pixels are drawn exactly as received: no background skipping, no color
// tinting. Python already composited each logo onto its correct background
// (white or black, whichever reads best on that particular mark — see
// _composite_on_white) before sending it, so re-processing here would just
// make the device's rendering diverge from what the Python app shows.
// ---------------------------------------------------------------------------

void drawLogo(const char* icao, int x, int y, int size,
              uint8_t r, uint8_t g, uint8_t b) {
    char path[48];
    snprintf(path, sizeof(path), "/logos/%.3s_%d.bin", icao, size);

    File f = LittleFS.open(path, "r");
    if (!f) {
        Serial.printf("[Logo] MISS %s (not cached at this size) — drawing fallback icon\n", path);
        drawPlaneIcon(x, y, size, r, g, b);
        return;
    }
    Serial.printf("[Logo] HIT %s\n", path);

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
