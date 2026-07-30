#pragma once
#ifndef FT_PROVISIONING_H
#define FT_PROVISIONING_H

// ---------------------------------------------------------------------------
// WiFi credential persistence — NVS (ESP32 Preferences), a separate flash
// partition from LittleFS so a LittleFS reformat can't take WiFi down too.
// ---------------------------------------------------------------------------

// Load saved credentials into out_ssid / out_pass.
// Returns false if none are saved.
bool wifiCredsLoad(char* outSsid, int ssidLen, char* outPass, int passLen);

// Clear saved credentials (call before ESP.restart() to force re-provisioning).
void wifiCredsClear();

// ---------------------------------------------------------------------------
// Provisioning mode
// Enter AP + captive-portal mode.  Does NOT return — restarts the ESP32
// after the user submits valid WiFi credentials.
// ---------------------------------------------------------------------------
void provisionStart();

#endif // FT_PROVISIONING_H
