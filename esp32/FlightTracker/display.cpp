#include "display.h"
#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>
#include <esp_heap_caps.h>
#include <string.h>

// ---------------------------------------------------------------------------
// Global framebuffer — allocated in PSRAM by displayInit() to free ~24 KB
// of regular heap for SSL (which cannot use PSRAM for its TLS context).
// ---------------------------------------------------------------------------
uint8_t (*fb)[TOTAL_WIDTH][3] = nullptr;
static MatrixPanel_I2S_DMA* panel = nullptr;

static const size_t FB_BYTES = TOTAL_HEIGHT * TOTAL_WIDTH * 3;

bool displayInit() {
    // Allocate framebuffer from PSRAM; fall back to heap if unavailable
    fb = (uint8_t(*)[TOTAL_WIDTH][3])heap_caps_malloc(FB_BYTES,
                                                       MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!fb) fb = (uint8_t(*)[TOTAL_WIDTH][3])malloc(FB_BYTES);
    if (!fb) return false;
    memset(fb, 0, FB_BYTES);

    HUB75_I2S_CFG cfg(PANEL_RES_X, PANEL_RES_Y, PANEL_CHAIN);

    cfg.gpio.r1  = R1_PIN;
    cfg.gpio.g1  = G1_PIN;
    cfg.gpio.b1  = B1_PIN;
    cfg.gpio.r2  = R2_PIN;
    cfg.gpio.g2  = G2_PIN;
    cfg.gpio.b2  = B2_PIN;
    cfg.gpio.a   = A_PIN;
    cfg.gpio.b   = B_PIN;
    cfg.gpio.c   = C_PIN;
    cfg.gpio.d   = D_PIN;
    cfg.gpio.e   = E_PIN;
    cfg.gpio.clk = CLK_PIN;
    cfg.gpio.lat = LAT_PIN;
    cfg.gpio.oe  = OE_PIN;

    // Uncomment for FM6126A panels:
    // cfg.driver = HUB75_I2S_CFG::FM6126A;

    cfg.clkphase = false;

    panel = new MatrixPanel_I2S_DMA(cfg);
    if (!panel->begin()) return false;

    panel->setBrightness8(PANEL_BRIGHTNESS);
    panel->clearScreen();
    return true;
}

void displayClear() {
    memset(fb, 0, FB_BYTES);
}

void displaySetPixel(int x, int y, uint8_t r, uint8_t g, uint8_t b) {
    if (x < 0 || x >= TOTAL_WIDTH || y < 0 || y >= TOTAL_HEIGHT) return;
    fb[y][x][0] = r;
    fb[y][x][1] = g;
    fb[y][x][2] = b;
}

void displayFlush() {
    if (!panel) return;
    for (int y = 0; y < TOTAL_HEIGHT; y++) {
        for (int x = 0; x < TOTAL_WIDTH; x++) {
            panel->drawPixelRGB888(x, y, fb[y][x][0], fb[y][x][1], fb[y][x][2]);
        }
    }
}

void displayBrightness(uint8_t b) {
    if (panel) panel->setBrightness8(b);
}
