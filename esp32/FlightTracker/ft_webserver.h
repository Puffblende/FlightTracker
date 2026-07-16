#pragma once
#ifndef FT_WEBSERVER_H
#define FT_WEBSERVER_H

#include "renderer.h"   // LayoutBlock
#include <stdint.h>

// ---------------------------------------------------------------------------
// Runtime configuration (populated from POST /config or loaded from flash)
// ---------------------------------------------------------------------------
struct DeviceConfig {
    float    lat;
    float    lon;
    float    radius_km;
    uint32_t fetch_interval_ms;
    uint32_t cycle_interval_ms;
    char     opensky_user[64];
    char     opensky_pass[64];
    LayoutBlock blocks[MAX_BLOCKS];
    int      block_count;
    bool     valid;          // true once a config has been received / loaded
};

extern DeviceConfig gConfig;

// Persist / restore config from LittleFS (CONFIG_PATH = "/config.json")
bool configSave();
bool configLoad();

// Start the HTTP server (call once in setup, after WiFi connects).
void webserverBegin();

// Poll the server — call every loop iteration.
void webserverHandle();

#endif // FT_WEBSERVER_H
