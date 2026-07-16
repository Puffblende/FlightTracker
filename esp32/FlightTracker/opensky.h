#pragma once
#ifndef FT_OPENSKY_H
#define FT_OPENSKY_H
#include <stdint.h>
#include "config.h"

// ---------------------------------------------------------------------------
// Per-flight data (fields populated from OpenSky state vector)
// ---------------------------------------------------------------------------
struct FlightData {
    char  icao24[8];
    char  callsign[12];
    char  origin_country[36];
    float latitude;
    float longitude;
    float baro_altitude;    // metres; NAN = unknown
    bool  on_ground;
    float velocity;         // m/s;   NAN = unknown
    float true_track;       // deg;   NAN = unknown
    float vertical_rate;    // m/s;   NAN = unknown
    char  squawk[6];
    float distance_km;
    char  aircraft_type[8];       // short ICAO type code e.g. "A320"   (adsb.fi "t")
    char  aircraft_type_full[32]; // full description e.g. "Airbus A320" (adsb.fi "desc")
    char  origin[6];              // IATA departure airport (adsb.fi "dep_iata")
    char  destination[6];         // IATA arrival airport   (adsb.fi "arr_iata")
    char  dep_icao[6];            // ICAO departure airport (adsb.fi "dep_icao")
    char  arr_icao[6];            // ICAO arrival airport   (adsb.fi "arr_icao")
    char  airline_name[48];       // full airline name from AIRLINE_DB / API cache
    char  airline_iata[4];        // 2-letter IATA code e.g. "U2" (from AIRLINE_DB)
    char  airline_icao[4];        // 3-letter ICAO prefix e.g. "EZY" (from callsign)
};

// Fetch flights within radius_km of (lat, lon) and write into outFlights[].
// Returns number of flights stored (≤ maxFlights), 0 on error, -1 on HTTP 429.
// Caller must not clear its flights array when -1 is returned.
// Blocks until the HTTP response is fully parsed.
int fetchFlights(float lat, float lon, float radius_km,
                 const char* user, const char* pass,
                 FlightData* outFlights, int maxFlights);

#endif // FT_OPENSKY_H
