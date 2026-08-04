#pragma once
#ifndef FT_WEBSERVER_H
#define FT_WEBSERVER_H

#include "renderer.h"   // LayoutBlock
#include <stdint.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

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

// Guards gConfig against the same cross-task hazard fs_lock.h protects
// LittleFS against: fetchTask() (its own core) reads lat/lon/radius/creds
// every fetch cycle, while a POST /config push (main loop) can rewrite all
// of it at any moment. Without this, fetchTask could read a lat from before
// a push and a lon from after it (torn read across a multi-field struct) —
// lower-impact than the LittleFS race (self-corrects next cycle rather than
// corrupting anything on disk), but the same class of bug, so closed the
// same way. Take it around any block that reads or writes more than one
// gConfig field where the fields need to be mutually consistent.
extern SemaphoreHandle_t gConfigMutex;
void configMutexInit();

// Persist / restore config from NVS (survives a LittleFS reformat)
bool configSave();
bool configLoad();

// Delete every cached logo .bin file. Exposed (not just the /reset-logos
// HTTP handler) so the boot-time crash-loop recovery in FlightTracker.ino
// can call it directly as an escalation step.
void clearLogoCache();

// Start the HTTP server (call once in setup, after WiFi connects).
void webserverBegin();

// Poll the server — call every loop iteration.
void webserverHandle();

#endif // FT_WEBSERVER_H
