# FlightTracker

Real-time ADS-B flight tracker with an 80×40 LED matrix display simulation.
Shows nearby aircraft on a pixel-accurate LED panel — and can drive a real 80×40 matrix later.

![LED Display Preview](https://i.imgur.com/placeholder.png)

---

## Features

- **Live flight data** — pulls from the free [OpenSky Network](https://opensky-network.org/) (no account required)
- **Auto-detects your location** via IP geolocation, or enter coordinates manually
- **Radius slider** — search area from 1 km to 200 km
- **Real airline logos** — fetched automatically and cached on disk
- **LED matrix simulation** — renders an authentic 80×40 dot-matrix display in a window
- **Tetris-style layout editor** — drag each data block to any position on the grid
- **Per-element display formats** — choose how each value is shown (e.g. `FL350` vs `36kft` vs `10973m` for altitude)
- **Auto-cycle** — rotates through nearby aircraft every few seconds
- **Flight list** — full table of all aircraft in range, click to jump to any

---

## Requirements

| Requirement | Version |
|---|---|
| Python | **3.9 or newer** |
| PyQt6 | 6.4+ |
| Pillow | 10.0+ |
| requests | 2.28+ |

> Python 3.9, 3.10, 3.11, 3.12 and 3.13 are all supported.
> The app runs on **Windows 10/11** and **macOS 11+** (Intel and Apple Silicon).

---

## Installation

### macOS

**1. Check Python is installed**

Open Terminal and run:
```bash
python3 --version
```
If you see `Python 3.9` or higher, you're good.  
If not, download Python from [python.org](https://www.python.org/downloads/).

**2. Install dependencies**

Double-click **`install.command`** in the FlightTracker folder.

Or open Terminal in the folder and run:
```bash
pip3 install -r requirements.txt
```

**3. Run**

Double-click **`run.command`**, or open Terminal and run:
```bash
python3 main.py
```

> **First-time double-click on macOS:** Gatekeeper may block unidentified scripts.
> If `install.command` or `run.command` won't open, right-click the file → "Open"
> → confirm. After that, double-clicking works normally.

---

### Windows

**1. Install Python**

Download and install Python 3.9 or newer from [python.org](https://www.python.org/downloads/windows/).

> **Important:** During installation, check **"Add Python to PATH"** — otherwise Windows won't find the `python` command.

**2. Install dependencies**

Double-click **`install.bat`** in the FlightTracker folder.

Or open a Command Prompt in the folder and run:
```bat
python -m pip install -r requirements.txt
```

**3. Run**

Double-click **`run.bat`**, or open a Command Prompt and run:
```bat
python main.py
```

---

## First Launch

On first launch the app will:

1. **Detect your location** automatically via IP geolocation (takes ~2 seconds)
2. **Fetch nearby flights** from OpenSky Network (takes ~5–15 seconds)
3. **Download airline logos** for visible aircraft in the background (cached to disk after first fetch)

The LED panel will start cycling through aircraft automatically once data arrives.

---

## Using the App

### Display tab

| Control | What it does |
|---|---|
| **◀ Prev / Next ▶** | Manually step through nearby aircraft |
| **⏸ Pause Cycle** | Stop/resume automatic cycling |
| **⟳ Fetch Now** | Force an immediate data refresh |
| **Radius slider** | Set the search area (1–200 km) |
| **Auto-detect location** | Re-run IP geolocation |
| **Manual lat/lon** | Enter coordinates and click "Set" |
| **Fetch every** | How often to poll OpenSky (min 10 s) |
| **Cycle every** | How often to switch aircraft on the display |

### Layout Editor tab

- **Check/uncheck** an element to show or hide it on the LED display
- **Drag blocks** to reposition them anywhere on the 80×40 grid
- Each block **snaps to the LED pixel grid** — no fractional positions
- The **format dropdown** under each element changes how the value is displayed and how wide the block is:

| Element | Example formats |
|---|---|
| Altitude | `A:36kft` · `FL360` · `36kft` · `A:10973m` |
| Speed | `S:250mph` · `250mph` · `S:217kts` · `217kts` · `S:402kmh` |
| From → To | `ORD-LAX` · `KORD-KLAX` · `ORD>LAX` · departure only · arrival only |
| Airline Logo | 16×16 · 24×24 · 32×32 · 40×40 pixels |
| Heading | `T:263` · `T:E` · `T:263E` |
| Climb/Desc | `V:-590f` · `-590fpm` · `V:-3.0m` |

> **Tip:** Compact formats (no prefix) are narrower and let you fit two values side-by-side on one row. Labeled formats (with prefix like `A:`, `S:`) are wider but self-explanatory.

- Click **Reset to Default** to restore the factory layout

### Flight List tab

Shows all aircraft currently in range as a table.  
Click any row to display that aircraft on the LED panel.

---

## Optional: OpenSky Account

The app works without an account, but anonymous requests are rate-limited to roughly one fetch per 10 seconds.

Creating a **free account** at [opensky-network.org](https://opensky-network.org/index.php?option=com_users&view=registration) gives you higher rate limits.

Enter your username and password in the **OpenSky Credentials** section of the Display tab and click **Apply**.

---

## Logo Cache

Airline logos are downloaded once and stored at:

| Platform | Cache location |
|---|---|
| macOS | `~/.flighttracker/logos/` |
| Windows | `C:\Users\YourName\.flighttracker\logos\` |

To force a fresh download (e.g. after a logo update), delete the files in that folder.

---

## Connecting a Real LED Matrix

The renderer outputs a plain 80×40 RGB pixel buffer (`list[list[tuple]]`).  
To drive a physical panel, replace the `LEDWidget.set_buffer()` call in `src/ui/led_widget.py` with your matrix driver — the pixel data is already in the right format.

---

## Troubleshooting

**"No flights" shown / display stays blank**

- Check your internet connection
- OpenSky may be temporarily unavailable — try "⟳ Fetch Now" after a minute
- Try increasing the search radius

**Logos always show a generic plane**

- Logos are fetched in the background; the generic icon is shown on first display and replaced when the download completes
- If logos never appear, check that outbound HTTPS is not blocked by a firewall
- Delete `~/.flighttracker/logos/` to force a re-download

**App looks blurry on Windows**

- Make sure you're using Python 3.9+ and PyQt6 6.4+
- Right-click `python.exe` → Properties → Compatibility → "Override high DPI scaling behaviour" → Application

**`python3` not found on Windows**

- Use `python` instead of `python3`
- Or use the provided `run.bat`

**`pip3` not found on macOS**

- Try `pip3 install -r requirements.txt` — if that also fails, use `python3 -m pip install -r requirements.txt`

---

## Project Structure

```
FlightTracker/
├── main.py                  Entry point
├── requirements.txt         Python dependencies
├── install.bat              Windows: one-click install
├── run.bat                  Windows: one-click launch
├── install.command          macOS: one-click install
├── run.command              macOS: one-click launch
└── src/
    ├── api/
    │   ├── opensky.py       OpenSky Network client
    │   ├── geoloc.py        IP-based location detection
    │   └── logos.py         Airline logo fetching & cache
    ├── core/
    │   ├── font.py          5×7 pixel bitmap font
    │   ├── models.py        Data models + format helpers
    │   ├── renderer.py      Converts flight data → 80×40 pixel buffer
    │   └── airlines.py      ICAO → airline name/IATA lookup table
    └── ui/
        ├── main_window.py   Application window & tabs
        ├── led_widget.py    LED matrix simulation widget
        ├── layout_editor.py Drag-and-drop layout editor
        └── settings_panel.py Location, radius & timing controls
```

---

## Data Sources

| Data | Source | Cost |
|---|---|---|
| Live flight positions | [OpenSky Network](https://opensky-network.org/) | Free |
| Airline logos (primary) | [FlightAware](https://www.flightaware.com/) | Free |
| Airline logos (fallback) | [pics.avs.io](https://pics.avs.io/) | Free |
| IP geolocation | [ipapi.co](https://ipapi.co/) / [ip-api.com](https://ip-api.com/) | Free |
