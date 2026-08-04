#pragma once

// Returns the ICAO24 address's registration country (e.g. "Germany"), or ""
// if the address doesn't fall in any known allocation block. Port of
// src/core/icao_country.py's country_for_icao24().
const char* countryForIcao24(const char* hexStr);
