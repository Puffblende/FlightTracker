#pragma once
#ifndef FT_FONT_H
#define FT_FONT_H
#include <stdint.h>

// 5×7 bitmap font — exact port of src/core/font.py
// Pixel bits per row: MSB = leftmost pixel, 5 bits used (bits 4..0).

static constexpr int FONT_CHAR_W       = 5;
static constexpr int FONT_CHAR_H       = 7;
static constexpr int FONT_CHAR_SPACING = 1;

// Output pixel width of one character advance (char + spacing) at given scale.
int fontCharAdvance(float scale = 1.0f);

// Total pixel width of a string (no trailing spacing).
int fontTextWidth(const char* text, float scale = 1.0f);

// Draw text into the global framebuffer at (x, y).
// maxWidth: clip width in output pixels (0 = no clip).
// Returns x position after the last character.
int fontDrawText(int x, int y, const char* text,
                 uint8_t r, uint8_t g, uint8_t b,
                 float scale = 1.0f, int maxWidth = 0);

#endif // FT_FONT_H
