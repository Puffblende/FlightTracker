#pragma once
#ifndef FT_ROUTES_H
#define FT_ROUTES_H

// Load any previously cached routes/airport coordinates from LittleFS.
// Call once from setup(), after LittleFS.begin(). Without this the device
// starts every boot with an empty cache, unlike the Python app which
// persists its route cache across restarts — same external data source,
// but very different amounts of already-learned data, which shows up as
// the same flight having working route/progress-bar info on one side and
// not the other.
void routesInit();

// Callsign → route lookup via adsbdb.com. Mirrors src/api/routes.py: neither
// OpenSky nor adsb.lol's state-vector data includes route info, so it's a
// separate per-callsign lookup, cached (including negative results) so
// repeated fetch cycles for the same flight never re-hit the network.
//
// Each of origin/dest/originIcao/destIcao must point to a buffer of at
// least 6 bytes. Returns true if at least the IATA pair was filled in
// (from cache or a fresh lookup); ICAO codes may still be empty if
// adsbdb didn't have them. Returns false if the route is unknown or the
// per-cycle lookup budget is exhausted (try again next cycle) — all four
// buffers are set to "" in that case.
bool routeLookup(const char* callsign, char* origin, char* dest,
                  char* originIcao, char* destIcao);

// Call once per fetch cycle, before looping over the flight list, so new
// (uncached) lookups are spread a few at a time across cycles instead of
// blocking the first cycle with dozens of HTTP round-trips.
void routeLookupBudgetReset();

// Airport coordinates learned from adsbdb.com responses (it returns lat/lon
// for both endpoints of every route it knows), same idea as Python's
// _seed_airport() in src/api/routes.py — so the progress bar isn't limited
// to whatever's in the static table in renderer.cpp. Matches on IATA or
// ICAO code. Returns false if this airport hasn't come up in a route
// lookup yet.
bool routeCacheAirportLocation(const char* code, float& lat, float& lon);

#endif
