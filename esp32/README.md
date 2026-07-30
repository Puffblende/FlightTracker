# FlightTracker ESP32 Firmware

Autonomous flight-tracker firmware for a 128×64 HUB75 LED matrix (two 64×64
panels chained horizontally), driven by an ESP32-S3 N16R8. After a one-time
config push from the PC app it fetches flight data and renders on its own —
see the root `CLAUDE.md` for the full data-flow and protocol description.

## Arduino IDE settings

Board package: **esp32 by Espressif Systems** (Boards Manager).

| Setting | Value |
|---|---|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | Enabled (needed to see `Serial` output over the native USB port) |
| PSRAM | **OPI PSRAM** — required; large JSON docs and flight buffers are allocated in PSRAM via `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` and will fail without it |
| Flash Size | 16MB |
| Partition Scheme | Any **16MB** scheme that includes a LittleFS/SPIFFS data partition (e.g. `16M Flash (3MB APP/9.9MB FATFS)`). Do **not** use a `4MB` scheme — the board has 16MB of flash and a 4MB partition table wastes almost all of it. Exact menu label varies by board-package version; the requirement is just "16MB flash, app + filesystem partition." |
| Upload Speed | 921600 (lower it if you get upload errors) |

No SPIFFS/LittleFS *data upload* step is needed — the firmware calls
`LittleFS.begin(true)`, which auto-formats the filesystem on first boot, and
creates `/logos`, `/config.json`, `/wifi.json` etc. at runtime.

## Required libraries

Install via **Arduino IDE → Tools → Manage Libraries…**:

- **ESP32-HUB75-MatrixPanel-I2S-DMA** (mrfaptastic) — panel driver
- **ArduinoJson v7.x** (Benoit Blanchon) — the config/logo endpoints use v7's
  `JsonDocument` / custom-allocator (`BasicJsonDocument<Allocator>` with
  `reallocate()`) API to route large docs through PSRAM. v6 will not compile.

Everything else (`WiFi`, `WiFiClient`, `WiFiClientSecure`, `WiFiUdp`,
`WebServer`, `DNSServer`, `LittleFS`, `esp_http_client`, `esp_crt_bundle`,
`esp_heap_caps`) ships with the ESP32 board package — no separate install.

## Syncing changes — `sync_esp32.sh`

The firmware source lives in two places that must be kept identical:

1. `esp32/FlightTracker/` — canonical source, tracked in this git repo
2. `~/Documents/Arduino/projects/sketch_jun8a/FlightTracker/` — the Arduino
   IDE's sketch directory (the IDE reads/compiles from here, not from the repo)

Always edit files in `esp32/FlightTracker/` (repo), never in the Arduino
sketch directory directly. After any `.ino`/`.h`/`.cpp` change, run from the
project root:

```bash
./sync_esp32.sh
```

This copies every `.ino`/`.h`/`.cpp` file from the repo into the Arduino
sketch directory, overwriting it. Then reopen/re-verify in the Arduino IDE
and upload as usual.

## First-time setup

1. **Install Arduino IDE 2.x**, then add the ESP32 board package: File →
   Preferences → "Additional Boards Manager URLs" →
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`,
   then Tools → Board → Boards Manager → install **esp32**.
2. **Install the libraries** listed above via Library Manager.
3. **Configure WiFi credentials.** `config.h` has compile-time
   `WIFI_SSID`/`WIFI_PASS` fallbacks, but the intended workflow is:
   - leave `config.h`'s placeholders as-is (don't put real credentials in a
     tracked file — see warning below)
   - flash the firmware and let it boot with no known network; it starts a
     captive-portal access point (`FlightTracker-Setup`) via
     `provisionStart()` — connect to that AP from a phone/laptop and submit
     your real WiFi credentials there. They're saved to `/wifi.json` on the
     device's LittleFS, not to any file in this repo.
   - to re-provision later (new network, wrong password), hit
     `GET http://<device-ip>/reset-wifi` — it clears `/wifi.json` and reboots
     into the captive portal again.
4. **Wire the HUB75 panel(s)** per the pin mapping in `config.h` (`R1_PIN`,
   `G1_PIN`, … `OE_PIN`) — also documented in the root `CLAUDE.md`.
5. **Set the Arduino IDE board settings** from the table above (board,
   PSRAM = OPI, 16MB flash + LittleFS partition scheme).
6. **Open the sketch** from the Arduino sketch directory (run
   `./sync_esp32.sh` first if you just cloned the repo, so the sketch
   directory exists and is up to date), select the correct serial port, and
   **Upload**.
7. **Open the Serial Monitor at 115200 baud** to watch the boot sequence:
   panel init → WiFi connect (or captive portal) → IP address → HTTP server
   start → autonomous fetch/render loop.
8. From the Python app's External Display tab, discover the device (or enter
   its IP manually) and **Push Config** — this sends location, layout, and
   airline logos to `http://<device-ip>/config`.

### ⚠ Note on `config.h`

`config.h` is tracked by git and is meant to hold placeholder WiFi
credentials only, with real credentials going through the captive-portal
flow (`/wifi.json`, step 3 above) instead — never committed. If you find a
real SSID/password already filled in on a line you're about to commit,
stop and move it out of the tracked file first.
