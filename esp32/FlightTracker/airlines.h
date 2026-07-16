#pragma once
#ifndef FT_AIRLINES_H
#define FT_AIRLINES_H

// Call once from setup() after LittleFS.begin() and WiFi is up.
// Creates /airlines/ directory and trims the cache if over 200 entries.
void airlinesInit();

// Fill out_name[out_size] from the hardcoded AIRLINE_DB (instant, no network),
// falling back to the LittleFS API cache for unknown airlines.
// Caller passes the full callsign; the 3-char ICAO prefix is extracted here.
void airlineLookup(const char* callsign, char* out_name, int out_size);

// Return the 2-letter IATA code for a 3-letter ICAO prefix (e.g. "EZY"→"U2").
// Returns "" if the prefix is not in the hardcoded table.
// Mirrors Python src/core/airlines.py AIRLINE_DB.
const char* airlineIcaoToIata(const char* icao_prefix);

#endif // FT_AIRLINES_H
