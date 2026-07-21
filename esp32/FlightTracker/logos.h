#pragma once
#ifndef FT_LOGOS_H
#define FT_LOGOS_H

#include <stdint.h>

// Draw a logo at (x, y) at exactly size×size pixels into the global framebuffer.
// Cache path: /logos/{ICAO}_{size}.bin  (1-byte reserved header + size×size×3 raw RGB),
// written by ft_webserver.cpp when the Python app pushes logos via POST /config.
// White pixels (transparent areas composited onto white) are skipped.
// Mono logos are tinted with (r,g,b); colour logos are drawn as-is.
// If the size-specific file is missing, draws the generic plane icon in (r,g,b).
void drawLogo(const char* icao, int x, int y, int size,
              uint8_t r, uint8_t g, uint8_t b);

#endif // FT_LOGOS_H
