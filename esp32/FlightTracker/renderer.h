#pragma once
#ifndef FT_RENDERER_H
#define FT_RENDERER_H
#include "opensky.h"
#include <stdint.h>

// ---------------------------------------------------------------------------
// Layout block — mirrors Python LayoutBlock / presets _block_to_dict format
// ---------------------------------------------------------------------------
struct LayoutBlock {
    char    key[16];          // "callsign", "altitude", "speed", …
    int16_t x, y;
    bool    enabled;
    char    fmt[16];          // format id, e.g. "ft_compact", "full"
    uint8_t r, g, b;
    float   font_scale;       // 1.0 .. 5.0
    char    custom_label[32]; // "" = use format default
    char    custom_unit[16];  // "" = use format default
    int16_t custom_width;     // progress bar width; 0 = default
};

// Render current flight blocks into the framebuffer, then flush to display.
void renderFlight(const FlightData& flight, const LayoutBlock* blocks, int nBlocks);

// Show "NO FLIGHTS" centred on the panel.
void renderNoFlights();

// Single- or two-line boot message (used during WiFi connect / init).
void renderMessage(const char* line1, const char* line2 = nullptr);

// Default layout matching Python default_layout() in src/core/models.py
int defaultLayout(LayoutBlock* out, int maxBlocks);

#endif // FT_RENDERER_H
