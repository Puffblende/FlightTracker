"""OpenSky Network API client for ADS-B flight data."""
import time
import requests
from src.core.models import Location, Flight
from src.core.airlines import lookup_airline

_OPENSKY_URL = "https://opensky-network.org/api/states/all"
_AIRCRAFT_META_URL = "https://opensky-network.org/api/metadata/aircraft/icao/{}"

_last_request_time: float = 0.0
_MIN_INTERVAL = 10.0  # seconds between requests (anonymous rate limit)

# Simple in-memory cache for aircraft metadata (icao24 → type string)
_aircraft_type_cache: dict[str, str] = {}


def fetch_flights(location: Location, radius_km: float,
                  username: str = "", password: str = "") -> list[Flight]:
    """Fetch all flights within radius_km of location."""
    global _last_request_time

    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    bbox = location.bounding_box(radius_km)
    params = {
        "lamin": bbox["lamin"],
        "lamax": bbox["lamax"],
        "lomin": bbox["lomin"],
        "lomax": bbox["lomax"],
    }

    auth = (username, password) if username else None

    try:
        r = requests.get(_OPENSKY_URL, params=params, auth=auth, timeout=15)
        _last_request_time = time.time()

        if r.status_code == 429:
            raise RuntimeError("Rate limited by OpenSky. Wait before retrying.")
        if r.status_code != 200:
            raise RuntimeError(f"OpenSky returned HTTP {r.status_code}")

        data = r.json()
        states = data.get("states") or []
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {e}")

    flights: list[Flight] = []
    for s in states:
        if len(s) < 17:
            continue
        lat = s[6]
        lon = s[5]
        if lat is None or lon is None:
            continue

        callsign = (s[1] or "").strip()
        airline_name, airline_iata, airline_icao = lookup_airline(callsign)

        f = Flight(
            icao24=s[0] or "",
            callsign=callsign,
            origin_country=s[2] or "",
            latitude=lat,
            longitude=lon,
            baro_altitude=s[7],
            on_ground=bool(s[8]),
            velocity=s[9],
            true_track=s[10],
            vertical_rate=s[11],
            squawk=s[14],
            distance_km=location.distance_to(lat, lon),
            airline_name=airline_name,
            airline_iata=airline_iata,
            airline_icao=airline_icao,
            aircraft_type=_aircraft_type_cache.get(s[0] or "", ""),
        )
        flights.append(f)

    flights.sort(key=lambda f: f.distance_km)
    return flights


def fetch_aircraft_type(icao24: str, username: str = "", password: str = "") -> str:
    """Fetch aircraft type for a single ICAO24. Returns empty string on failure."""
    if icao24 in _aircraft_type_cache:
        return _aircraft_type_cache[icao24]

    auth = (username, password) if username else None
    try:
        r = requests.get(
            _AIRCRAFT_META_URL.format(icao24.lower()),
            auth=auth,
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            typ = data.get("typecode") or data.get("model") or ""
            _aircraft_type_cache[icao24] = typ
            return typ
    except Exception:
        pass

    _aircraft_type_cache[icao24] = ""
    return ""
