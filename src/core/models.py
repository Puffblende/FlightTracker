"""Core data models for FlightTracker."""
from __future__ import annotations
from dataclasses import dataclass
from typing import NamedTuple
import math

from src.core.font import CHAR_W, CHAR_H, CHAR_SPACING


# ── Geography ─────────────────────────────────────────────────────────────────

@dataclass
class Location:
    lat: float
    lon: float
    city: str = ""
    country: str = ""

    def bounding_box(self, radius_km: float) -> dict:
        R = 6371.0
        dlat = math.degrees(radius_km / R)
        dlon = math.degrees(radius_km / (R * math.cos(math.radians(self.lat))))
        return {
            "lamin": self.lat - dlat,
            "lamax": self.lat + dlat,
            "lomin": self.lon - dlon,
            "lomax": self.lon + dlon,
        }

    def distance_to(self, lat: float, lon: float) -> float:
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(math.radians, [self.lat, self.lon, lat, lon])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))


@dataclass
class Flight:
    icao24: str
    callsign: str
    origin_country: str
    latitude: object       # float | None
    longitude: object      # float | None
    baro_altitude: object  # float | None  (meters)
    on_ground: bool
    velocity: object       # float | None  (m/s)
    true_track: object     # float | None  (degrees clockwise from N)
    vertical_rate: object  # float | None  (m/s)
    squawk: object         # str | None
    distance_km: float = 0.0
    airline_name: str = ""
    airline_iata: str = ""
    airline_icao: str = ""
    aircraft_type: str = ""
    origin: str = ""           # IATA code, e.g. "ORD"
    destination: str = ""      # IATA code, e.g. "LAX"
    origin_icao: str = ""      # ICAO code, e.g. "KORD"
    destination_icao: str = "" # ICAO code, e.g. "KLAX"

    @property
    def display_callsign(self) -> str:
        return self.callsign.strip() or self.icao24.upper()

    @property
    def airline_display(self) -> str:
        return self.airline_name or self.airline_icao or self.callsign[:3].strip()

    @property
    def route_str(self) -> str:
        if self.origin and self.destination:
            return f"{self.origin}-{self.destination}"
        return ""


# ── Block formats ─────────────────────────────────────────────────────────────
# A format only describes how the *value* portion is rendered (e.g. "36000",
# "36", "FL360", "10.9").  Prefix (label) and suffix (unit) are user-driven
# strings on the LayoutBlock; the dropdown labels include unit hints purely
# for readability.

class FormatSpec(NamedTuple):
    id: str
    label: str         # dropdown label (may include unit hint for readability)
    value_chars: int   # max chars in the value portion (for width calc)
    default_label: str # prefilled in the Label input when block is created
    default_unit: str  # prefilled in the Unit input when block is created


BLOCK_FORMATS: dict[str, list[FormatSpec]] = {
    "logo": [
        FormatSpec("sq16", "16 × 16 px  (tiny)",         0, "", ""),
        FormatSpec("sq24", "24 × 24 px  (small)",        0, "", ""),
        FormatSpec("sq32", "32 × 32 px  (medium)",       0, "", ""),
        FormatSpec("sq40", "40 × 40 px  (full-height)",  0, "", ""),
    ],
    "airline": [
        FormatSpec("full",  "RYANAIR  (full name)",  8, "", ""),
        FormatSpec("short", "RYAN  (first word)",    4, "", ""),
        FormatSpec("icao",  "RYR  (ICAO code)",      3, "", ""),
    ],
    "callsign": [
        # ICAO Mode-S aircraft ID is up to 8 chars (e.g. "BCS75515", "RYR27JN")
        FormatSpec("full",   "RYR27JN  (callsign)",   8, "", ""),
        FormatSpec("icao24", "3C6444  (ICAO24 hex)",  6, "", ""),
    ],
    "route": [
        FormatSpec("iata",  "ORD-LAX  (IATA)",   7, "", ""),
        FormatSpec("icao",  "KORD-KLAX (ICAO)",  9, "", ""),
        FormatSpec("arrow", "ORD>LAX  (arrow)",  7, "", ""),
        FormatSpec("dep",   "ORD  (departure)",  3, "", ""),
        FormatSpec("arr",   "LAX  (arrival)",    3, "", ""),
    ],
    "aircraft_type": [
        FormatSpec("code", "B738  (ICAO code)",        4,  "", ""),
        FormatSpec("full", "B737-800  (full name)",   13,  "", ""),
    ],
    "altitude": [
        FormatSpec("ft_full",    "36000  (ft)",        5, "A:", "ft"),
        FormatSpec("ft_compact", "36  (kft)",          3, "A:", "kft"),
        FormatSpec("fl",         "360  (flight level)", 3, "FL", ""),
        FormatSpec("m_full",     "10973  (m)",          5, "A:", "m"),
        FormatSpec("m_compact",  "10.9  (km)",          4, "A:", "km"),
    ],
    "speed": [
        FormatSpec("mph", "313  (mph)",  3, "S:", "mph"),
        FormatSpec("kts", "272  (kts)",  3, "S:", "kts"),
        FormatSpec("kmh", "504  (km/h)", 3, "S:", "kmh"),
    ],
    "track": [
        FormatSpec("deg",     "263  (degrees)",      3, "T:", "°"),
        FormatSpec("compass", "NW  (compass)",       2, "T:", ""),
        FormatSpec("full",    "263NW  (deg+compass)", 5, "T:", ""),
    ],
    "vrate": [
        FormatSpec("fpm",   "+590  (ft/min)",  5, "V:", "fpm"),
        FormatSpec("ms",    "+3.0  (m/s)",     5, "V:", "m/s"),
        FormatSpec("arrow", "v590  (arrow)",   5, "V:", "fpm"),
    ],
    "squawk": [
        FormatSpec("bare", "1234  (4-digit code)", 4, "",    ""),
    ],
    "country": [
        FormatSpec("full", "GERMANY  (full name)", 8, "", ""),
    ],
    "distance": [
        FormatSpec("km",   "42.3  (km)",          4, "D:", "km"),
        FormatSpec("nm",   "22.8  (nm)",          4, "D:", "nm"),
        FormatSpec("km_i", "42  (km, integer)",    2, "D:", "km"),
        FormatSpec("nm_i", "22  (nm, integer)",    2, "D:", "nm"),
    ],
    "progress": [
        FormatSpec("bar", "Progress bar  (user-defined width)", 0, "", ""),
    ],
}


BLOCK_DEFAULT_FORMAT: dict = {
    "logo":          "sq24",
    "airline":       "full",
    "callsign":      "full",
    "route":         "iata",
    "aircraft_type": "code",
    "altitude":      "ft_compact",
    "speed":         "mph",
    "track":         "deg",
    "vrate":         "fpm",
    "squawk":        "bare",
    "country":       "full",
    "distance":      "km",
    "progress":      "bar",
}


# (key, user-visible label, default RGB color)
BLOCK_TYPES = [
    ("logo",         "Airline Logo",     (30,  80,  200)),
    ("airline",      "Airline Name",     (255, 255, 255)),
    ("callsign",     "Flight Number",    (255, 220,   0)),
    ("route",        "From → To",   (255, 255, 255)),
    ("aircraft_type","Aircraft",         (100, 255, 100)),
    ("altitude",     "Altitude",         (100, 200, 255)),
    ("speed",        "Speed",            (255, 140,   0)),
    ("track",        "Heading",          (180, 180, 255)),
    ("vrate",        "Climb / Desc.",    (255, 100, 100)),
    ("squawk",       "Squawk Code",      (200, 200, 200)),
    ("country",      "Origin Country",   (200, 200, 200)),
    ("distance",     "Distance",         (180, 255, 180)),
    ("progress",     "Flight Progress",  (255, 200,  60)),
]

BLOCK_TYPE_MAP: dict = {k: (label, color) for k, label, color in BLOCK_TYPES}

# Blocks that have a meaningful unit suffix (i.e., the Unit input is shown)
UNIT_BLOCKS = {"altitude", "speed", "vrate", "distance", "track"}

# Logo size table — derived from format id
_LOGO_SIZES = {"sq16": 16, "sq24": 24, "sq32": 32, "sq40": 40}


def _format_for(key: str, fmt_id: str) -> FormatSpec | None:
    for spec in BLOCK_FORMATS.get(key, []):
        if spec.id == fmt_id:
            return spec
    fmts = BLOCK_FORMATS.get(key, [])
    return fmts[0] if fmts else None


# ── Layout block ──────────────────────────────────────────────────────────────

@dataclass
class LayoutBlock:
    key: str
    x: int
    y: int
    enabled: bool = True
    fmt: str = ""
    custom_color: tuple | None = None
    custom_width: int | None = None       # progress: user-defined pixel width
    custom_label: str | None = None       # None → use format's default_label
    custom_unit: str | None = None        # None → use format's default_unit
    font_scale: float = 1.0               # 1.0 .. 5.0 in 0.25 steps
    # Progress-bar embellishments
    show_remaining: bool = False
    show_plane: bool = False
    show_endpoints: bool = False
    plane_color: tuple | None = None      # progress: plane glyph color; None=bar color
    # Squawk-block emergency monitoring (7500/7600/7601/7700 → flash + red border)
    recognize_emergencies: bool = False

    def __post_init__(self):
        if not self.fmt:
            self.fmt = BLOCK_DEFAULT_FORMAT.get(self.key, "")
        if self.font_scale < 1.0:
            self.font_scale = 1.0

    # ── label/unit resolution ─────────────────────────────────────────────────

    @property
    def effective_label(self) -> str:
        if self.custom_label is not None:
            return self.custom_label
        spec = _format_for(self.key, self.fmt)
        return spec.default_label if spec else ""

    @property
    def effective_unit(self) -> str:
        if not self.has_unit:
            return ""
        if self.custom_unit is not None:
            return self.custom_unit
        spec = _format_for(self.key, self.fmt)
        return spec.default_unit if spec else ""

    @property
    def has_unit(self) -> bool:
        return self.key in UNIT_BLOCKS

    @property
    def has_label(self) -> bool:
        # Logo and progress don't render text directly
        return self.key not in ("logo", "progress")

    # ── geometry ──────────────────────────────────────────────────────────────

    @property
    def text_char_count(self) -> int:
        """Worst-case character count for this block (label + value + unit)."""
        spec = _format_for(self.key, self.fmt)
        value_chars = spec.value_chars if spec else 0
        return len(self.effective_label) + value_chars + len(self.effective_unit)

    @property
    def width(self) -> int:
        if self.key == "logo":
            return _LOGO_SIZES.get(self.fmt, 24)
        if self.key == "progress":
            return max(4, int(self.custom_width)) if self.custom_width else 40
        n = max(1, self.text_char_count)
        char_w_scaled = max(1, int(round(CHAR_W * self.font_scale)))
        spacing_scaled = max(0, int(round(CHAR_SPACING * self.font_scale)))
        return n * (char_w_scaled + spacing_scaled) - spacing_scaled

    @property
    def height(self) -> int:
        if self.key == "logo":
            return _LOGO_SIZES.get(self.fmt, 24)
        if self.key == "progress":
            return 3  # 3-pixel bar strip; remaining is visual-only (no text row)
        return max(1, int(round(CHAR_H * self.font_scale)))

    @property
    def color(self) -> tuple:
        if self.custom_color is not None:
            return tuple(self.custom_color)
        return BLOCK_TYPE_MAP[self.key][1]

    @property
    def label(self) -> str:
        return BLOCK_TYPE_MAP[self.key][0]


def default_layout():
    return [
        LayoutBlock("logo",          0,  0,  True,  "sq24"),
        LayoutBlock("airline",      26,  0,  True,  "full"),
        LayoutBlock("route",        26,  8,  True,  "iata"),
        LayoutBlock("aircraft_type",26, 16,  True,  "code"),
        LayoutBlock("altitude",      0, 25,  True,  "ft_compact"),
        LayoutBlock("speed",        32, 25,  True,  "mph"),
        LayoutBlock("track",         0, 33,  True,  "deg"),
        LayoutBlock("vrate",        32, 33,  True,  "fpm"),
        LayoutBlock("callsign",     26, 24,  False, "full"),
        LayoutBlock("squawk",        0, 24,  False, "bare"),
        LayoutBlock("country",       0, 24,  False, "full"),
        LayoutBlock("distance",     68, 25,  False, "km"),
        LayoutBlock("progress",      0, 38,  False, "bar", custom_width=40),
    ]


# ── Value-only formatters (no label/unit) ─────────────────────────────────────

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def value_altitude(baro_m, fmt_id: str) -> str:
    if baro_m is None:
        return "---"
    ft = baro_m * 3.28084
    m = float(baro_m)
    if fmt_id == "ft_full":    return f"{int(ft)}"
    if fmt_id == "ft_compact": return f"{ft/1000:.0f}"
    if fmt_id == "fl":         return f"{int(ft / 100)}"
    if fmt_id == "m_full":     return f"{int(m)}"
    if fmt_id == "m_compact":  return f"{m/1000:.1f}"
    return f"{ft/1000:.0f}"


def value_speed(vel_ms, fmt_id: str) -> str:
    if vel_ms is None:
        return "---"
    v = float(vel_ms)
    if fmt_id == "mph": return f"{int(v * 2.23694)}"
    if fmt_id == "kts": return f"{int(v * 1.94384)}"
    if fmt_id == "kmh": return f"{int(v * 3.6)}"
    return f"{int(v * 2.23694)}"


def value_track(deg, fmt_id: str) -> str:
    if deg is None:
        return "---"
    d = int(float(deg))
    compass = _COMPASS[round(d / 45) % 8]
    if fmt_id == "deg":     return f"{d}"
    if fmt_id == "compass": return compass
    if fmt_id == "full":    return f"{d:03d}{compass}"
    return f"{d}"


def value_vrate(vr_ms, fmt_id: str) -> str:
    if vr_ms is None:
        return "---"
    v = float(vr_ms)
    fpm = int(v * 196.85)
    sign = "+" if fpm >= 0 else ""
    arrow = "^" if fpm >= 0 else "v"
    if fmt_id == "fpm":   return f"{sign}{fpm}"
    if fmt_id == "ms":    return f"{v:+.1f}"
    if fmt_id == "arrow": return f"{arrow}{abs(fpm)}"
    return f"{sign}{fpm}"


def value_distance(km: float, fmt_id: str) -> str:
    if fmt_id == "nm":   return f"{km / 1.852:.1f}"
    if fmt_id == "km_i": return f"{int(km)}"
    if fmt_id == "nm_i": return f"{int(km / 1.852)}"
    return f"{km:.1f}"


def value_route(flight, fmt_id: str) -> str:
    """Render route per format. ICAO formats use ICAO codes when available,
    IATA formats use IATA codes. Falls back to the other form if one is missing.
    Returns "???" placeholders rather than substituting unrelated data."""
    iata_o = (flight.origin or "").strip()
    iata_d = (flight.destination or "").strip()
    icao_o = (flight.origin_icao or "").strip()
    icao_d = (flight.destination_icao or "").strip()

    if fmt_id == "icao":
        o = icao_o or iata_o or "????"
        d = icao_d or iata_d or "????"
        return f"{o}-{d}"
    if fmt_id == "arrow":
        o = iata_o or icao_o or "???"
        d = iata_d or icao_d or "???"
        return f"{o}>{d}"
    if fmt_id == "dep":
        return iata_o or icao_o or "???"
    if fmt_id == "arr":
        return iata_d or icao_d or "???"
    # default: iata
    o = iata_o or icao_o or "???"
    d = iata_d or icao_d or "???"
    return f"{o}-{d}"


def value_airline(flight, fmt_id: str) -> str:
    name = flight.airline_name or flight.airline_icao or flight.callsign[:3]
    if fmt_id == "short": return (name.split()[0][:8].upper() if name else "---")
    if fmt_id == "icao":  return (flight.airline_icao or flight.callsign[:3]).upper()
    return (name or "---").upper()


def value_callsign(flight, fmt_id: str) -> str:
    if fmt_id == "icao24":
        return flight.icao24.upper()
    return flight.display_callsign


def value_aircraft_type(flight, fmt_id: str) -> str:
    typ = (flight.aircraft_type or "").strip()
    if not typ:
        return "----"
    if fmt_id == "full":
        # Lookup table src/core/aircraft_types.py maps ICAO codes → model names.
        from src.core.aircraft_types import lookup_type
        full = lookup_type(typ)
        return (full or typ).upper()
    return typ[:4].upper()


def value_squawk(flight, _fmt_id: str) -> str:
    return (flight.squawk or "----")[:4]


def value_country(flight, _fmt_id: str) -> str:
    return (flight.origin_country or "").upper()


def _is_placeholder(value: str) -> bool:
    """A value is a 'no data' placeholder if it's empty or consists solely of
    dashes / question marks (the conventions our value_* helpers use)."""
    if not value:
        return True
    return all(c in "-?" for c in value.strip())


def render_block_text(block: LayoutBlock, flight: Flight) -> str:
    """Compose the final rendered string for a text block: label + value + unit.
    When the value is a placeholder (no data), render just the placeholder —
    no label, no unit. Avoids ugly "A:---kft" / "S:---mph" output."""
    key = block.key
    fmt = block.fmt
    if key == "altitude":      v = value_altitude(flight.baro_altitude, fmt)
    elif key == "speed":       v = value_speed(flight.velocity, fmt)
    elif key == "track":       v = value_track(flight.true_track, fmt)
    elif key == "vrate":       v = value_vrate(flight.vertical_rate, fmt)
    elif key == "distance":    v = value_distance(flight.distance_km, fmt)
    elif key == "route":       v = value_route(flight, fmt)
    elif key == "airline":     v = value_airline(flight, fmt)
    elif key == "callsign":    v = value_callsign(flight, fmt)
    elif key == "aircraft_type": v = value_aircraft_type(flight, fmt)
    elif key == "squawk":      v = value_squawk(flight, fmt)
    elif key == "country":     v = value_country(flight, fmt)
    else:
        v = ""

    if _is_placeholder(v):
        # No valid data — render only the user-set label (often empty by default);
        # never a "---" / "???" placeholder, never the unit.
        return block.effective_label
    return f"{block.effective_label}{v}{block.effective_unit}"


# ── Status-bar wrappers (used by main_window) ─────────────────────────────────
# These keep working as before – they include the format's natural prefix/unit.

def _decorated(spec: FormatSpec, value: str) -> str:
    return f"{spec.default_label}{value}{spec.default_unit}"


def fmt_altitude(baro_m, fmt_id: str) -> str:
    spec = _format_for("altitude", fmt_id)
    return _decorated(spec, value_altitude(baro_m, fmt_id)) if spec else value_altitude(baro_m, fmt_id)


def fmt_speed(vel_ms, fmt_id: str) -> str:
    spec = _format_for("speed", fmt_id)
    return _decorated(spec, value_speed(vel_ms, fmt_id)) if spec else value_speed(vel_ms, fmt_id)


def fmt_distance(km: float, fmt_id: str) -> str:
    spec = _format_for("distance", fmt_id)
    return _decorated(spec, value_distance(km, fmt_id)) if spec else value_distance(km, fmt_id)


def fmt_track(deg, fmt_id: str) -> str:
    spec = _format_for("track", fmt_id)
    return _decorated(spec, value_track(deg, fmt_id)) if spec else value_track(deg, fmt_id)


def fmt_vrate(vr_ms, fmt_id: str) -> str:
    spec = _format_for("vrate", fmt_id)
    return _decorated(spec, value_vrate(vr_ms, fmt_id)) if spec else value_vrate(vr_ms, fmt_id)


def fmt_route(flight, fmt_id: str) -> str:
    return value_route(flight, fmt_id)
