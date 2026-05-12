"""Flight progress estimation.

Computes 0..1 progress along the great-circle path from the origin airport
to the destination airport, given the aircraft's current lat/lon.

We carry a small built-in lookup for common airports (IATA + ICAO).
If either endpoint is unknown, flight_progress() returns None and the
renderer falls back to an empty bar.
"""
from __future__ import annotations
import math
from typing import Optional

# (lat, lon) for major airports. Keyed by both IATA (3 letters) and ICAO (4 letters)
# where useful. Not exhaustive — extend as needed.
AIRPORTS: dict[str, tuple[float, float]] = {
    # Europe
    "FRA": (50.0379, 8.5622),   "EDDF": (50.0379, 8.5622),
    "MUC": (48.3538, 11.7861),  "EDDM": (48.3538, 11.7861),
    "BER": (52.3667, 13.5033),  "EDDB": (52.3667, 13.5033),
    "HAM": (53.6304, 9.9882),   "EDDH": (53.6304, 9.9882),
    "DUS": (51.2895, 6.7668),   "EDDL": (51.2895, 6.7668),
    "CGN": (50.8659, 7.1427),   "EDDK": (50.8659, 7.1427),
    "STR": (48.6899, 9.2220),   "EDDS": (48.6899, 9.2220),
    "LHR": (51.4700, -0.4543),  "EGLL": (51.4700, -0.4543),
    "LGW": (51.1537, -0.1821),  "EGKK": (51.1537, -0.1821),
    "STN": (51.8849, 0.2350),   "EGSS": (51.8849, 0.2350),
    "MAN": (53.3537, -2.2750),  "EGCC": (53.3537, -2.2750),
    "CDG": (49.0097, 2.5479),   "LFPG": (49.0097, 2.5479),
    "ORY": (48.7233, 2.3794),   "LFPO": (48.7233, 2.3794),
    "AMS": (52.3105, 4.7683),   "EHAM": (52.3105, 4.7683),
    "BRU": (50.9014, 4.4844),   "EBBR": (50.9014, 4.4844),
    "ZRH": (47.4647, 8.5492),   "LSZH": (47.4647, 8.5492),
    "GVA": (46.2381, 6.1090),   "LSGG": (46.2381, 6.1090),
    "VIE": (48.1103, 16.5697),  "LOWW": (48.1103, 16.5697),
    "MAD": (40.4983, -3.5676),  "LEMD": (40.4983, -3.5676),
    "BCN": (41.2974, 2.0833),   "LEBL": (41.2974, 2.0833),
    "LIS": (38.7813, -9.1359),  "LPPT": (38.7813, -9.1359),
    "FCO": (41.8003, 12.2389),  "LIRF": (41.8003, 12.2389),
    "MXP": (45.6306, 8.7281),   "LIMC": (45.6306, 8.7281),
    "ATH": (37.9364, 23.9445),  "LGAV": (37.9364, 23.9445),
    "IST": (41.2753, 28.7519),  "LTFM": (41.2753, 28.7519),
    "SAW": (40.8986, 29.3092),  "LTFJ": (40.8986, 29.3092),
    "ARN": (59.6519, 17.9186),  "ESSA": (59.6519, 17.9186),
    "CPH": (55.6181, 12.6561),  "EKCH": (55.6181, 12.6561),
    "OSL": (60.1939, 11.1004),  "ENGM": (60.1939, 11.1004),
    "HEL": (60.3172, 24.9633),  "EFHK": (60.3172, 24.9633),
    "DUB": (53.4213, -6.2701),  "EIDW": (53.4213, -6.2701),
    "PRG": (50.1008, 14.2632),  "LKPR": (50.1008, 14.2632),
    "WAW": (52.1657, 20.9671),  "EPWA": (52.1657, 20.9671),
    "BUD": (47.4369, 19.2556),  "LHBP": (47.4369, 19.2556),
    "SVO": (55.9726, 37.4146),  "UUEE": (55.9726, 37.4146),

    # North America
    "JFK": (40.6413, -73.7781), "KJFK": (40.6413, -73.7781),
    "EWR": (40.6925, -74.1687), "KEWR": (40.6925, -74.1687),
    "LGA": (40.7769, -73.8740), "KLGA": (40.7769, -73.8740),
    "LAX": (33.9416, -118.4085),"KLAX": (33.9416, -118.4085),
    "SFO": (37.6188, -122.3754),"KSFO": (37.6188, -122.3754),
    "SEA": (47.4502, -122.3088),"KSEA": (47.4502, -122.3088),
    "ORD": (41.9742, -87.9073), "KORD": (41.9742, -87.9073),
    "MDW": (41.7868, -87.7522), "KMDW": (41.7868, -87.7522),
    "ATL": (33.6407, -84.4277), "KATL": (33.6407, -84.4277),
    "DFW": (32.8998, -97.0403), "KDFW": (32.8998, -97.0403),
    "DEN": (39.8561, -104.6737),"KDEN": (39.8561, -104.6737),
    "MIA": (25.7959, -80.2870), "KMIA": (25.7959, -80.2870),
    "BOS": (42.3656, -71.0096), "KBOS": (42.3656, -71.0096),
    "IAD": (38.9531, -77.4565), "KIAD": (38.9531, -77.4565),
    "YYZ": (43.6777, -79.6248), "CYYZ": (43.6777, -79.6248),
    "YVR": (49.1939, -123.1844),"CYVR": (49.1939, -123.1844),

    # Asia / Oceania
    "HND": (35.5494, 139.7798), "RJTT": (35.5494, 139.7798),
    "NRT": (35.7720, 140.3929), "RJAA": (35.7720, 140.3929),
    "ICN": (37.4602, 126.4407), "RKSI": (37.4602, 126.4407),
    "PEK": (40.0801, 116.5846), "ZBAA": (40.0801, 116.5846),
    "PVG": (31.1443, 121.8083), "ZSPD": (31.1443, 121.8083),
    "HKG": (22.3080, 113.9185), "VHHH": (22.3080, 113.9185),
    "SIN": (1.3644, 103.9915),  "WSSS": (1.3644, 103.9915),
    "BKK": (13.6900, 100.7501), "VTBS": (13.6900, 100.7501),
    "DXB": (25.2532, 55.3657),  "OMDB": (25.2532, 55.3657),
    "DOH": (25.2731, 51.6080),  "OTHH": (25.2731, 51.6080),
    "DEL": (28.5562, 77.1000),  "VIDP": (28.5562, 77.1000),
    "BOM": (19.0896, 72.8656),  "VABB": (19.0896, 72.8656),
    "SYD": (-33.9399, 151.1753),"YSSY": (-33.9399, 151.1753),
    "MEL": (-37.6690, 144.8410),"YMML": (-37.6690, 144.8410),
}


def _lookup(code: str) -> Optional[tuple[float, float]]:
    if not code:
        return None
    return AIRPORTS.get(code.strip().upper())


def _gc_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def flight_progress(flight) -> Optional[float]:
    """Return progress 0..1 along origin → destination great-circle, or None."""
    if flight is None:
        return None
    if flight.latitude is None or flight.longitude is None:
        return None
    o = _lookup(flight.origin)
    d = _lookup(flight.destination)
    if o is None or d is None:
        return None
    total = _gc_distance(o[0], o[1], d[0], d[1])
    if total <= 0:
        return None
    done = _gc_distance(o[0], o[1], float(flight.latitude), float(flight.longitude))
    return max(0.0, min(1.0, done / total))


def remaining_distance_km(flight) -> Optional[float]:
    """Great-circle km remaining from current position to destination."""
    if flight is None:
        return None
    if flight.latitude is None or flight.longitude is None:
        return None
    d = _lookup(flight.destination)
    if d is None:
        return None
    return _gc_distance(float(flight.latitude), float(flight.longitude), d[0], d[1])
