#pragma once

// Returns the human-readable model name for an ICAO type designator
// (e.g. "A320" -> "A320", "A21N" -> "A321neo"), or "" if unknown.
// Port of src/core/aircraft_types.py's lookup_type().
const char* lookupAircraftType(const char* code);
