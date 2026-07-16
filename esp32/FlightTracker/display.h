#pragma once
#ifndef FT_DISPLAY_H
#define FT_DISPLAY_H
#include <stdint.h>
#include "config.h"

// ---------------------------------------------------------------------------
// Global framebuffer [row][col][RGB].  Allocated in PSRAM by displayInit().
// Write here, then call displayFlush().
// ---------------------------------------------------------------------------
extern uint8_t (*fb)[TOTAL_WIDTH][3];

bool     displayInit();
void     displayClear();
void     displaySetPixel(int x, int y, uint8_t r, uint8_t g, uint8_t b);
void     displayFlush();           // push framebuffer → HUB75 panel
void     displayBrightness(uint8_t b);  // 0-255

#endif // FT_DISPLAY_H
