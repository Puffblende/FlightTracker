#pragma once
#ifndef FT_PROVISIONING_H
#define FT_PROVISIONING_H

// ---------------------------------------------------------------------------
// WiFi credential persistence  (/wifi.json on LittleFS)
// ---------------------------------------------------------------------------

// Load saved credentials into out_ssid / out_pass.
// Returns false if /wifi.json is absent or corrupt.
bool wifiCredsLoad(char* outSsid, int ssidLen, char* outPass, int passLen);

// Delete /wifi.json (call before ESP.restart() to force re-provisioning).
void wifiCredsClear();

// ---------------------------------------------------------------------------
// Provisioning mode
// Enter AP + captive-portal mode.  Does NOT return — restarts the ESP32
// after the user submits valid WiFi credentials.
// ---------------------------------------------------------------------------
void provisionStart();

#endif // FT_PROVISIONING_H
