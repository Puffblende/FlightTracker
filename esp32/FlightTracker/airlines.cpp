#include "airlines.h"
#include <Arduino.h>
#include <string.h>

// ---------------------------------------------------------------------------
// Hardcoded ICAO → (name, IATA) table — port of Python src/core/airlines.py
// Maps 3-letter ICAO callsign prefix → full airline name + 2-letter IATA code.
// Instant lookup, no network required.
// ---------------------------------------------------------------------------
struct AirlineEntry { const char* icao; const char* name; const char* iata; };
static const AirlineEntry AIRLINE_DB[] = {
    {"AAL", "American Airlines",      "AA"},
    {"AAR", "Asiana Airlines",        "OZ"},
    {"ABY", "Air Arabia",             "G9"},
    {"ACA", "Air Canada",             "AC"},
    {"AFL", "Aeroflot",               "SU"},
    {"AFR", "Air France",             "AF"},
    {"AIC", "Air India",              "AI"},
    {"AMX", "Aeromexico",             "AM"},
    {"ANZ", "Air New Zealand",        "NZ"},
    {"ASL", "Air Serbia",             "JU"},
    {"AUA", "Austrian Airlines",      "OS"},
    {"AXM", "AirAsia",                "AK"},
    {"AZA", "ITA Airways",            "AZ"},
    {"BAW", "British Airways",        "BA"},
    {"BCS", "DHL (Leipzig)",          "QY"},
    {"BEL", "Brussels Airlines",      "SN"},
    {"BMA", "British Midland",        "BD"},
    {"BOX", "AeroLogic",              "3S"},
    {"BTI", "airBaltic",              "BT"},
    {"CAI", "Corendon Airlines",      "XC"},
    {"CAL", "China Airlines",         "CI"},
    {"CCA", "Air China",              "CA"},
    {"CFE", "BA Cityflyer",           "CJ"},
    {"CFG", "Condor",                 "DE"},
    {"CHH", "Hainan Airlines",        "HU"},
    {"CLH", "Lufthansa CityLine",     "CL"},
    {"CLX", "Cargolux",               "CV"},
    {"CPA", "Cathay Pacific",         "CX"},
    {"CSN", "China Southern",         "CZ"},
    {"CTN", "Croatia Airlines",       "OU"},
    {"CXA", "Xiamen Airlines",        "MF"},
    {"DAL", "Delta Air Lines",        "DL"},
    {"DLA", "Air Dolomiti",           "EN"},
    {"DLH", "Lufthansa",              "LH"},
    {"EFW", "BA Euroflyer",           "A0"},
    {"EIN", "Aer Lingus",             "EI"},
    {"ELY", "El Al",                  "LY"},
    {"ENT", "Enter Air",              "E4"},
    {"ETD", "Etihad Airways",         "EY"},
    {"ETH", "Ethiopian Airlines",     "ET"},
    {"EWG", "Eurowings",              "EW"},
    {"EXS", "Jet2.com",               "LS"},
    {"EZY", "easyJet",                "U2"},
    {"FDB", "flydubai",               "FZ"},
    {"FDX", "FedEx Express",          "FX"},
    {"FIN", "Finnair",                "AY"},
    {"FRF", "Fleet Air International", ""},
    {"GFA", "Gulf Air",               "GF"},
    {"GTI", "Atlas Air",              "5Y"},
    {"HAL", "Hawaiian Airlines",      "HA"},
    {"IBE", "Iberia",                 "IB"},
    {"ICE", "Icelandair",             "FI"},
    {"JAL", "Japan Airlines",         "JL"},
    {"JAT", "Jat Airways",            "JU"},
    {"JBU", "JetBlue Airways",        "B6"},
    {"KAC", "Kuwait Airways",         "KU"},
    {"KAL", "Korean Air",             "KE"},
    {"KLC", "KLM Cityhopper",         "WA"},
    {"KLM", "KLM",                    "KL"},
    {"KQA", "Kenya Airways",          "KQ"},
    {"LAN", "LATAM Airlines",         "LA"},
    {"LHX", "Lufthansa City Airlines", "VL"},
    {"LOT", "LOT Polish Airlines",    "LO"},
    {"LRC", "Avianca Costa Rica",     "LR"},
    {"LZB", "Bulgaria Air",           "FB"},
    {"MAS", "Malaysia Airlines",      "MH"},
    {"MEA", "Middle East Airlines",   "ME"},
    {"MSR", "EgyptAir",               "MS"},
    {"MXD", "Batik Air Malaysia",     "OD"},
    {"NAX", "Norwegian",              "DY"},
    {"NKS", "Spirit Airlines",        "NK"},
    {"NWA", "Northwest Airlines",     "NW"},
    {"OAL", "Olympic Air",            "OA"},
    {"OCN", "Discover Airlines",      "4Y"},
    {"OMA", "Oman Air",               "WY"},
    {"PAC", "Polar Air Cargo",        "PO"},
    {"PAL", "Philippine Airlines",    "PR"},
    {"PGT", "Pegasus Airlines",       "PC"},
    {"PIA", "Pakistan International", "PK"},
    {"QFA", "Qantas",                 "QF"},
    {"QTR", "Qatar Airways",          "QR"},
    {"RAM", "Royal Air Maroc",        "AT"},
    {"RJA", "Royal Jordanian",        "RJ"},
    {"ROT", "TAROM",                  "RO"},
    {"RUK", "Ryanair UK",             "RK"},
    {"RYR", "Ryanair",                "FR"},
    {"SAA", "South African Airways",  "SA"},
    {"SAS", "Scandinavian Airlines",  "SK"},
    {"SBI", "S7 Airlines",            "S7"},
    {"SIA", "Singapore Airlines",     "SQ"},
    {"SVA", "Saudia",                 "SV"},
    {"SWA", "Southwest Airlines",     "WN"},
    {"SWR", "Swiss International",    "LX"},
    {"SXS", "SunExpress",             "XQ"},
    {"TAM", "LATAM Brasil",           "JJ"},
    {"TAP", "TAP Air Portugal",       "TP"},
    {"TAY", "ASL Airlines Belgium",   "3V"},
    {"THA", "Thai Airways",           "TG"},
    {"THY", "Turkish Airlines",       "TK"},
    {"TOM", "TUI Airways",            "BY"},
    {"TSC", "Air Transat",            "TS"},
    {"TUA", "Turkmenistan Airlines",  "T5"},
    {"TUI", "TUI fly",                "X3"},
    {"TVS", "Smartwings",             "QS"},
    {"UAE", "Emirates",               "EK"},
    {"UAL", "United Airlines",        "UA"},
    {"UPS", "UPS Airlines",           "5X"},
    {"VIR", "Virgin Atlantic",        "VS"},
    {"VLG", "Vueling",                "VY"},
    {"VOE", "Volotea",                "V7"},
    {"VOZ", "Virgin Australia",       "VA"},
    {"WJA", "WestJet",                "WS"},
    {"WZZ", "Wizz Air",               "W6"},
    {"XAX", "AirAsia X",              "D7"},
};
static const int AIRLINE_DB_COUNT = (int)(sizeof(AIRLINE_DB) / sizeof(AIRLINE_DB[0]));

const char* airlineIcaoToIata(const char* icao_prefix) {
    if (!icao_prefix || !icao_prefix[0]) return "";
    for (int i = 0; i < AIRLINE_DB_COUNT; i++) {
        if (strcmp(AIRLINE_DB[i].icao, icao_prefix) == 0)
            return AIRLINE_DB[i].iata;
    }
    return "";
}

// ---------------------------------------------------------------------------
// Public API — static table only, zero network calls.
// ---------------------------------------------------------------------------

void airlinesInit() {
    Serial.println("[Airline] Init done (static table only, no network)");
}

void airlineLookup(const char* callsign, char* out_name, int out_size) {
    out_name[0] = '\0';
    if (!callsign || !callsign[0]) return;

    char icao[5] = {0};
    strncpy(icao, callsign, 3);
    for (int i = 0; i < 3; i++) {
        if (icao[i] >= 'a' && icao[i] <= 'z') icao[i] -= 32;
        if (!(icao[i] >= 'A' && icao[i] <= 'Z')) return;
    }

    for (int i = 0; i < AIRLINE_DB_COUNT; i++) {
        if (strcmp(AIRLINE_DB[i].icao, icao) == 0) {
            strncpy(out_name, AIRLINE_DB[i].name, out_size - 1);
            out_name[out_size - 1] = '\0';
            return;
        }
    }
    // Unknown prefix — leave out_name empty; no network fallback.
}
