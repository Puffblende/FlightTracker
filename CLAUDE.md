# FlightTracker — CLAUDE.md

## Project overview

A Python/PyQt6 desktop app that shows nearby aircraft (via OpenSky API) rendered onto a simulated 128×64 LED matrix. A companion ESP32 firmware receives a config from the PC and then operates autonomously: fetches flight data itself, renders it onto a physical HUB75 LED matrix panel, and cycles through aircraft.

## Repository layout

```
main.py                     Entry point
requirements.txt            PyQt6, requests, Pillow
src/
  api/
    opensky.py              Fetches state vectors from OpenSky REST API
    flights.py              Enriches flights (airline name, route, aircraft type)
    adsb_lol.py             Alternate ADS-B data source
    geocode.py / geoloc.py  Reverse-geocode / auto-detect user location
    logos.py                Downloads airline logo PNGs (PIL)
    routes.py               Looks up origin/destination airport IATA codes
  core/
    models.py               Flight, Location, LayoutBlock, FormatSpec, BLOCK_FORMATS
    renderer.py             Renders one Flight onto a pixel buffer (list of RGB rows)
    font.py                 5×7 bitmap font; draw_text(), char_width(), text_width()
    displays.py             Named display size presets (width × height)
    airlines.py             ICAO→airline name/IATA lookup table
    aircraft_types.py       ICAO type code→full name table
    icao_country.py         ICAO24 prefix→country
    emergencies.py          Squawk code→emergency string
    presets.py              Save/load named layout presets (JSON)
    progress.py             flight_progress(), remaining_distance_km()
  external/
    discovery.py            UDP broadcast scan + BLE scan for ESP32 devices
                            Broadcast: b"FTLD_DISCOVER" → port 4210
                            Device replies with JSON: {name, width, height, port}
    protocol.py             UDP frame format (MAGIC "FTLD" + W + H + RGB pixels)
                            UDPSender: fire-and-forget UDP to ESP32
  ui/
    main_window.py          Main PyQt6 window, polling timer, flight cycling
    settings_panel.py       Location, radius, refresh interval settings
    led_widget.py           QWidget that paints the simulated LED matrix
    layout_editor.py        Drag/drop layout block editor
    overlay_window.py       Borderless always-on-top overlay window
    external_tab.py         "External Display" tab — device discovery + UDP streaming
    theme.py                Dark theme stylesheet
esp32/                      ESP32 Arduino firmware (to be built)
```

## Python app — key concepts

### Data flow
1. `opensky.py` polls OpenSky every N seconds → list of raw `Flight` objects
2. `flights.py` enriches each flight (airline, route, aircraft type) via secondary API calls
3. `renderer.py` renders one `Flight` into a pixel buffer (`list[list[(R,G,B)]]`, row-major)
4. `led_widget.py` paints that buffer to screen; `UDPSender` also pushes it to the ESP32

### LayoutBlock system
`models.py` defines `LayoutBlock` — each block has an `(x, y)` pixel position, a `block_type` (logo, callsign, altitude, speed, route, …), a `FormatSpec` id, color, font_scale, optional label/unit strings, and a `width`. `renderer.py` iterates blocks and calls into `font.py` to draw text or `logos.py` to paste logo images.

### UDP streaming (Option A — PC renders, ESP32 displays)
- Discovery: PC broadcasts `b"FTLD_DISCOVER"` on port 4210; ESP32 replies with JSON `{"name":"FlightMatrix","width":128,"height":64,"port":4211}`
- Frame: `MAGIC(4) + W(2BE) + H(2BE) + RGB(W×H×3)` sent to port 4211

## ESP32 firmware plan (Option B — autonomous mode)

**Goal:** ESP32 operates independently after receiving a one-time JSON config from the PC.

### Firmware lives in `esp32/`

Suggested file structure:
```
esp32/
  FlightTracker/
    FlightTracker.ino       Main sketch
    config.h                Pin definitions, constants
    wifi_setup.h/.cpp       WiFi connect + HTTP config server
    opensky.h/.cpp          Fetch & parse OpenSky JSON
    renderer.h/.cpp         Render Flight data onto pixel buffer
    font.h/.cpp             5×7 bitmap font (ported from src/core/font.py)
    hub75.h/.cpp            HUB75 panel driver (or use SmartMatrix / ESP32-HUB75-MatrixPanel-I2S-DMA lib)
    discovery.h/.cpp        Respond to UDP FTLD_DISCOVER broadcasts
```

### Hardware

| Item | Detail |
|------|--------|
| Board | ESP32-S3 N16R8 (16 MB flash, 8 MB PSRAM) |
| Panel | 128×64 HUB75 RGB, 1/32 scan |
| Library | ESP32-HUB75-MatrixPanel-I2S-DMA (recommended) |

**HUB75 pin mapping:**
```
R1=4   G1=5   B1=6
R2=7   G2=15  B2=16
A=17   B=18   C=8   D=3   E=46
CLK=48  LAT=45  OE=21
```

### Firmware startup sequence
1. Connect to WiFi (credentials stored in NVS or hardcoded for dev)
2. Start HTTP server on port 80; `GET /` returns device info JSON, `POST /config` accepts config
3. Respond to UDP discovery broadcasts (`b"FTLD_DISCOVER"` → JSON reply on port 4210)
4. Once config is received, begin autonomous flight loop

### Config JSON (PC → ESP32 via POST /config)
```json
{
  "lat": 48.1351,
  "lon": 11.5820,
  "radius_km": 100,
  "refresh_s": 15,
  "dwell_s": 5,
  "opensky_user": "optional",
  "opensky_pass": "optional"
}
```

### Autonomous loop (after config)
1. Every `refresh_s` seconds: `GET https://opensky-network.org/api/states/all?lamin=...`
2. Parse JSON array: `[icao24, callsign, origin_country, …, lat, lon, baro_alt, on_ground, velocity, true_track, vertical_rate, …, squawk, …]` (17 fields per state vector)
3. Filter to flights within radius, sort by distance
4. Cycle through each aircraft every `dwell_s` seconds
5. Render text onto the 128×64 frame buffer and push to the HUB75 panel

### Rendering on ESP32
Port the 5×7 font from `src/core/font.py` — it is a compact dict of char→bitmap rows. Keep the same pixel layout so the same layout configs work on both PC sim and hardware.

Minimum viable display per aircraft:
- Row 0: callsign (large / 2× scale)
- Row 9: altitude in ft + speed in kts
- Row 18: route (origin→destination) if available
- Row 26: distance in km + track direction

### Protocol compatibility
The ESP32 must also implement Option A (UDP frame receive) so the PC can push pre-rendered frames when directly connected. Both modes coexist: if no config has been received, only UDP frame mode is active.

## Running the Python app

```bash
pip install -r requirements.txt
python main.py
```

Optional BLE support: `pip install bleak`

## OpenSky API notes

- Unauthenticated: 400 requests/day, max 1 req/10 s
- Authenticated: 4 000 requests/day, max 1 req/5 s
- State vector fields (0-indexed): `[icao24, callsign, origin_country, time_position, last_contact, longitude, latitude, baro_altitude, on_ground, velocity, true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source]`
- Bounding-box query: `?lamin=&lamax=&lomin=&lomax=`

## Conventions

- Python: no type-stub imports, use `from __future__ import annotations`
- Pixel buffers are always `list[list[tuple[int,int,int]]]` (row-major, (R,G,B))
- Colors are plain `(R, G, B)` tuples, never Qt objects, in core/renderer code
- ESP32 firmware: Arduino framework, C++17, PlatformIO or Arduino IDE
- ESP32 HTTP JSON responses: always include `{"status":"ok"}` or `{"error":"…"}`
- Do not commit WiFi credentials; use `secrets.h` (gitignored) for dev, NVS for production
