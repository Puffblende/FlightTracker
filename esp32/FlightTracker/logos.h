#pragma once
#ifndef FT_LOGOS_H
#define FT_LOGOS_H

// Requires: PNGdec library (Arduino Library Manager → search "PNGdec" by bitbank2)

#include <stdint.h>

// Set true while flight fetch is running so the logo task backs off.
// Defined in logos.cpp; set by the fetch task in FlightTracker.ino.
extern volatile bool g_fetchingFlights;

// Call once from setup() after LittleFS.begin() and WiFi is up.
// Creates /logos/ directory and starts the background fetch task.
void logosInit();

// Returns true if a 24×24 logo binary for this airline ICAO is cached in LittleFS.
bool logoExists(const char* icao);

// Enqueue an airline logo for background download at size 24.
// Mirrors Python logos.py: ICAO prefix used for FlightAware URL,
// IATA code (2-letter, e.g. "U2") used for pics.avs.io URL.
// No-op if already cached, marked none, or queue full.
void logoFetchEnqueue(const char* callsign, const char* airline_iata = "");

// Draw a logo at (x, y) at exactly size×size pixels into the global framebuffer.
// Cache path: /logos/{ICAO}_{size}.bin  (1-byte mono flag + size×size×3 raw RGB).
// White pixels (transparent areas composited onto white) are skipped.
// Mono logos are tinted with (r,g,b); colour logos are drawn as-is.
// If the size-specific file is missing, queues a background fetch and draws the
// generic plane icon in (r,g,b) until next render.
void drawLogo(const char* icao, int x, int y, int size,
              uint8_t r, uint8_t g, uint8_t b);

#endif // FT_LOGOS_H
