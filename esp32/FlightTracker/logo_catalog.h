#pragma once
#include <stdint.h>

// Full airline logo catalog, baked directly into firmware — generated from
// src/api/logos.py's get_logo() pipeline (which does the actual PNG fetch,
// alpha compositing, and resizing; the ESP32 has no image decoder of its
// own). Covers every airline in airlines.cpp's AIRLINE_DB, i.e. every
// airline the device can ever resolve a name for in the first place, so
// this is the airline's ONLY logo source now — no network fetch, no
// dependency on a Python push ever arriving or surviving a filesystem
// event. Regenerate by re-running the same generation script whenever
// AIRLINE_DB changes (see esp32/README or ask Claude — it wrote this).

#define BAKED_LOGO_SIZE 40

// Returns a pointer to BAKED_LOGO_SIZE*BAKED_LOGO_SIZE*3 raw RGB bytes
// (row-major, matching the LittleFS logo cache format minus the header
// byte), or nullptr if this ICAO isn't in the baked catalog.
const uint8_t* lookupBakedLogo(const char* icao);
