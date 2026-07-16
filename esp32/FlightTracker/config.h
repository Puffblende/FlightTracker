#pragma once
#ifndef FT_CONFIG_H
#define FT_CONFIG_H

// ---------------------------------------------------------------------------
// WiFi credentials — copy config.h to secrets.h and fill in there, or edit
// directly (but don't commit real credentials).
// ---------------------------------------------------------------------------
#ifndef WIFI_SSID
#define WIFI_SSID "FRITZ!Box 6660 Cable HK"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "bmw0005ayl"
#endif

// ---------------------------------------------------------------------------
// HUB75 panel — 128×64 wired as two 64×64 panels chained horizontally.
// For FM6126A panels uncomment:  #define PANEL_DRIVER FM6126A
// ---------------------------------------------------------------------------
#define PANEL_RES_X   64       // resolution of one panel
#define PANEL_RES_Y   64       // height
#define PANEL_CHAIN    2       // panels in chain  → total 128×64
#define TOTAL_WIDTH   (PANEL_RES_X * PANEL_CHAIN)  // 128
#define TOTAL_HEIGHT  PANEL_RES_Y                  // 64

// HUB75 pin mapping (ESP32-S3 N16R8)
#define R1_PIN   4
#define G1_PIN   5
#define B1_PIN   6
#define R2_PIN   7
#define G2_PIN  15
#define B2_PIN  16
#define A_PIN   17
#define B_PIN   18
#define C_PIN    8
#define D_PIN    3
#define E_PIN   46
#define CLK_PIN 48
#define LAT_PIN 45
#define OE_PIN  21

// ---------------------------------------------------------------------------
// Network ports
// ---------------------------------------------------------------------------
#define HTTP_PORT       80
#define UDP_DISC_PORT 4210    // receive FTLD_DISCOVER → reply with device JSON
#define UDP_FRAME_PORT 4211   // receive pre-rendered FTLD frames from PC (Option A)

// ---------------------------------------------------------------------------
// Firmware limits
// ---------------------------------------------------------------------------
#define MAX_FLIGHTS    64
#define MAX_BLOCKS     24
#define CONFIG_PATH    "/config.json"

// Default intervals (ms) if no config loaded
#define DEFAULT_FETCH_MS  30000u
#define DEFAULT_CYCLE_MS   5000u

// Display brightness 0–255
#define PANEL_BRIGHTNESS  100

#endif // FT_CONFIG_H
