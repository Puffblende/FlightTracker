"""Core data models for FlightTracker."""
from __future__ import annotations
from dataclasses import dataclass, field
import math


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
    origin: str = ""       # IATA/ICAO departure airport
    destination: str = ""  # IATA/ICAO arrival airport

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


# ── Block format registry ─────────────────────────────────────────────────────
# Each entry: (format_id, user-visible label, pixel_width, pixel_height)
BLOCK_FORMATS: dict = {
    "logo": [
        ("sq16", "16×16 px  (tiny)",    16, 16),
        ("sq24", "24×24 px  (small)",   24, 24),
        ("sq32", "32×32 px  (medium)",  32, 32),
        ("sq40", "40×40 px  (full-height)", 40, 40),
    ],
    "airline": [
        ("full",  "Full name  (RYANAIR)",  48, 7),
        ("short", "First word  (RYAN)",    24, 7),
        ("icao",  "ICAO code  (RYR)",      18, 7),
    ],
    "callsign": [
        ("full",    "Full  (RYR234)",       36, 7),
        ("icao24",  "ICAO24 hex  (3c6444)", 36, 7),
    ],
    "route": [
        ("iata",  "IATA codes  (ORD-LAX)",   42, 7),
        ("icao",  "ICAO codes  (KORD-KLAX)", 54, 7),
        ("arrow", "Arrow  (ORD>LAX)",        42, 7),
        ("dep",   "Departure only  (ORD)",   18, 7),
        ("arr",   "Arrival only  (LAX)",     18, 7),
    ],
    "aircraft_type": [
        ("code", "ICAO code  (B738)",       24, 7),
        ("full", "Full model  (B737-800)",  60, 7),
    ],
    "altitude": [
        # Labeled (prefix A:) — wider, informative
        ("ft_full",    "A:36000ft  (labeled full)",  54, 7),
        ("ft_compact", "A:36kft    (labeled k-ft)",  42, 7),
        ("fl",         "FL360      (flight level)",  30, 7),
        ("m_full",     "A:10973m   (labeled meters)",48, 7),
        ("m_compact",  "A:10.9km   (labeled km)",    48, 7),
        # No prefix — compact, relies on color
        ("ft_s",       "36kft      (short, no label)",30, 7),
        ("ft_v",       "36000ft    (value+unit)",     42, 7),
        ("m_s",        "9500m      (meters, no label)",30, 7),
    ],
    "speed": [
        # Labeled (prefix S:) — wider
        ("mph",    "S:250mph  (labeled mph)",    48, 7),
        ("kts",    "S:217kts  (labeled knots)",  48, 7),
        ("kmh",    "S:402kmh  (labeled km/h)",   48, 7),
        # No prefix — compact, relies on color
        ("mph_s",  "250mph    (short mph)",       36, 7),
        ("kts_s",  "217kts    (short knots)",     36, 7),
        ("kmh_s",  "402kmh    (short km/h)",      36, 7),
    ],
    "track": [
        ("deg",     "T:263    (labeled degrees)",  30, 7),
        ("compass", "T:E      (compass point)",    18, 7),
        ("full",    "T:095E   (degrees+compass)",  36, 7),
        ("bare",    "095      (degrees only)",     18, 7),
    ],
    "vrate": [
        # Labeled (prefix V:)
        ("fpm",    "V:-590f   (labeled ft/min)",  42, 7),
        ("ms",     "V:-3.0m   (labeled m/s)",     42, 7),
        ("arrow",  "V:v590f   (arrow+fpm)",       42, 7),
        # No prefix
        ("fpm_s",  "-590fpm   (short fpm)",       42, 7),
        ("ms_s",   "-3.0m/s   (short m/s)",       42, 7),
    ],
    "squawk": [
        ("bare",  "Code only  (1234)",    24, 7),
        ("label", "Labeled  (SQ:1234)",   36, 7),
    ],
    "country": [
        ("full", "Full name  (GERMANY)",  48, 7),
    ],
    "distance": [
        ("km",   "km  (42.3km)",    36, 7),
        ("nm",   "nm  (22.8nm)",    36, 7),
        ("km_c", "km short  (42km)", 24, 7),
        ("nm_c", "nm short  (22nm)", 24, 7),
    ],
}

BLOCK_DEFAULT_FORMAT: dict = {
    "logo":          "sq24",
    "airline":       "full",
    "callsign":      "full",
    "route":         "iata",
    "aircraft_type": "code",
    "altitude":      "ft_s",    # compact "36kft" — fits side-by-side
    "speed":         "mph_s",   # compact "313mph" — fits side-by-side
    "track":         "deg",
    "vrate":         "fpm_s",   # compact "-590fpm"
    "squawk":        "label",
    "country":       "full",
    "distance":      "km",
}

# (key, user-visible label, RGB color)
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
]

BLOCK_TYPE_MAP: dict = {k: (label, color) for k, label, color in BLOCK_TYPES}


@dataclass
class LayoutBlock:
    key: str
    x: int
    y: int
    enabled: bool = True
    fmt: str = ""  # format_id; empty → use BLOCK_DEFAULT_FORMAT

    def __post_init__(self):
        if not self.fmt:
            self.fmt = BLOCK_DEFAULT_FORMAT.get(self.key, "")

    @property
    def width(self) -> int:
        for fid, _label, fw, _fh in BLOCK_FORMATS.get(self.key, []):
            if fid == self.fmt:
                return fw
        fmts = BLOCK_FORMATS.get(self.key, [])
        return fmts[0][2] if fmts else 24

    @property
    def height(self) -> int:
        for fid, _label, _fw, fh in BLOCK_FORMATS.get(self.key, []):
            if fid == self.fmt:
                return fh
        fmts = BLOCK_FORMATS.get(self.key, [])
        return fmts[0][3] if fmts else 7

    @property
    def color(self) -> tuple:
        return BLOCK_TYPE_MAP[self.key][1]

    @property
    def label(self) -> str:
        return BLOCK_TYPE_MAP[self.key][0]


def default_layout():
    # Display map (80×40 LED pixels):
    #   [logo 24×24] [airline 48px      ]   ← y=0
    #   [logo      ] [route 42px        ]   ← y=8
    #   [logo      ] [aircraft 24px     ]   ← y=16
    #   [alt 30px  ] [speed 36px] [dist ]   ← y=25
    #   [track30px ] [vrate 42px        ]   ← y=33
    return [
        LayoutBlock("logo",          0,  0,  True,  "sq24"),
        LayoutBlock("airline",      26,  0,  True,  "full"),
        LayoutBlock("route",        26,  8,  True,  "iata"),
        LayoutBlock("aircraft_type",26, 16,  True,  "code"),
        LayoutBlock("altitude",      0, 25,  True,  "ft_s"),    # "36kft" = 30px
        LayoutBlock("speed",        32, 25,  True,  "mph_s"),   # "313mph" = 36px → ends at 67
        LayoutBlock("track",         0, 33,  True,  "deg"),     # "T:95" = 30px
        LayoutBlock("vrate",        32, 33,  True,  "fpm_s"),   # "-590fpm" = 42px → ends at 73
        LayoutBlock("callsign",     26, 24,  False, "full"),
        LayoutBlock("squawk",        0, 24,  False, "label"),
        LayoutBlock("country",       0, 24,  False, "full"),
        LayoutBlock("distance",     68, 25,  False, "km"),
    ]


# ── Format helper functions ───────────────────────────────────────────────────

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def fmt_altitude(baro_m, fmt_id: str) -> str:
    if baro_m is None:
        return "---"
    ft = baro_m * 3.28084
    m = float(baro_m)
    if fmt_id == "ft_full":
        return f"A:{int(ft)}ft"
    if fmt_id == "ft_compact":
        return f"A:{ft/1000:.0f}kft"
    if fmt_id == "fl":
        return f"FL{int(ft / 100)}"
    if fmt_id == "m_full":
        return f"A:{int(m)}m"
    if fmt_id == "m_compact":
        return f"A:{m/1000:.1f}km"
    if fmt_id == "ft_s":          # compact, no prefix
        return f"{ft/1000:.0f}kft"
    if fmt_id == "ft_v":          # value+unit, no prefix
        return f"{int(ft)}ft"
    if fmt_id == "m_s":           # meters, no prefix
        return f"{int(m)}m"
    return f"{ft/1000:.0f}kft"


def fmt_speed(vel_ms, fmt_id: str) -> str:
    if vel_ms is None:
        return "---"
    v = float(vel_ms)
    mph  = int(v * 2.23694)
    kts  = int(v * 1.94384)
    kmh  = int(v * 3.6)
    if fmt_id == "mph":    return f"S:{mph}mph"
    if fmt_id == "kts":    return f"S:{kts}kts"
    if fmt_id == "kmh":    return f"S:{kmh}kmh"
    if fmt_id == "mph_s":  return f"{mph}mph"   # no prefix
    if fmt_id == "kts_s":  return f"{kts}kts"
    if fmt_id == "kmh_s":  return f"{kmh}kmh"
    return f"{mph}mph"


def fmt_track(deg, fmt_id: str) -> str:
    if deg is None:
        return "---"
    d = int(float(deg))
    compass = _COMPASS[round(d / 45) % 8]
    if fmt_id == "deg":     return f"T:{d}"
    if fmt_id == "compass": return f"T:{compass}"
    if fmt_id == "full":    return f"T:{d:03d}{compass}"
    if fmt_id == "bare":    return f"{d:03d}"
    return f"T:{d}"


def fmt_vrate(vr_ms, fmt_id: str) -> str:
    if vr_ms is None:
        return "---"
    v = float(vr_ms)
    fpm = int(v * 196.85)
    sign = "+" if fpm >= 0 else ""
    arrow = "^" if fpm >= 0 else "v"
    if fmt_id == "fpm":    return f"V:{sign}{fpm}f"
    if fmt_id == "ms":     return f"V:{v:+.1f}m"
    if fmt_id == "arrow":  return f"V:{arrow}{abs(fpm)}f"
    if fmt_id == "fpm_s":  return f"{sign}{fpm}fpm"  # no prefix
    if fmt_id == "ms_s":   return f"{v:+.1f}m/s"
    return f"{sign}{fpm}fpm"


def fmt_distance(km: float, fmt_id: str) -> str:
    if fmt_id == "nm":
        return f"{km / 1.852:.1f}nm"
    if fmt_id == "km_c":
        return f"{int(km)}km"
    if fmt_id == "nm_c":
        return f"{int(km / 1.852)}nm"
    return f"{km:.1f}km"


def fmt_route(flight, fmt_id: str) -> str:
    o = flight.origin or "???"
    d = flight.destination or "???"
    if not flight.origin and not flight.destination:
        return flight.origin_country[:7].upper() if flight.origin_country else ""
    if fmt_id == "icao":
        return f"{o}-{d}"
    if fmt_id == "arrow":
        return f"{o}>{d}"
    if fmt_id == "dep":
        return o
    if fmt_id == "arr":
        return d
    return f"{o}-{d}"  # iata default
