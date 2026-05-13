"""adsb.lol API client.

Returns flights within a radius of a location. Free, no auth required.
Endpoint: https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}

adsb.lol returns values in display units (ft, knots, fpm). We convert back
to SI internally so the rest of the codebase (renderer, formatters) keeps
working unchanged.
"""
from __future__ import annotations
import time
import requests

from src.core.models import Location, Flight
from src.core.airlines import lookup_airline
from src.core.icao_country import country_for_icao24

_API = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
_TIMEOUT = 8.0
_MIN_INTERVAL = 1.0  # be polite — community-run aggregator

# Unit conversions back to SI
FT_TO_M  = 0.3048
KT_TO_MS = 0.514444
FPM_TO_MS = 1.0 / 196.85
NM_TO_KM = 1.852

_last_call: float = 0.0


def fetch_flights(location: Location, radius_km: float,
                  username: str = "", password: str = "") -> list[Flight]:
    """Fetch flights within radius_km of location via adsb.lol.

    `username`/`password` are accepted for signature compatibility with the
    OpenSky fallback but ignored — adsb.lol needs no auth.
    """
    global _last_call

    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    nm = max(1, int(round(radius_km / NM_TO_KM)))
    url = _API.format(lat=location.lat, lon=location.lon, nm=nm)

    try:
        r = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "FlightTracker"})
        _last_call = time.time()
        if r.status_code != 200:
            raise RuntimeError(f"adsb.lol HTTP {r.status_code}")
        data = r.json() or {}
    except requests.RequestException as e:
        raise RuntimeError(f"adsb.lol network error: {e}")

    ac_list = data.get("ac") or []
    flights: list[Flight] = []

    for ac in ac_list:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue

        # Skip surface vehicles (ADS-B category C* = ground vehicles).
        category = (ac.get("category") or "").upper()
        if category.startswith("C"):
            continue

        icao24 = (ac.get("hex") or "").lower()

        # Mode-S aircraft-ID messages pad unused chars with 0x40 ("@"). When the
        # source decoder hasn't resolved the callsign it leaks through as "@@@".
        # Strip those, then whitespace.
        callsign = (ac.get("flight") or "").replace("@", "").strip()

        airline_name, airline_iata, airline_icao = lookup_airline(callsign)
        # If callsign-based lookup didn't find anything, fall back to adsb.lol's
        # enrichment fields (often null, but useful when present).
        if not airline_name:
            airline_name = ((ac.get("ownOp") or "").strip()
                            or (ac.get("desc") or "").strip())

        # Altitude: "ground" sentinel for on-ground aircraft.
        alt_raw = ac.get("alt_baro")
        on_ground = (alt_raw == "ground")
        baro_alt_m = (alt_raw * FT_TO_M) if isinstance(alt_raw, (int, float)) else None

        gs = ac.get("gs")
        velocity = (gs * KT_TO_MS) if isinstance(gs, (int, float)) else None

        baro_rate = ac.get("baro_rate")
        vrate = (baro_rate * FPM_TO_MS) if isinstance(baro_rate, (int, float)) else None

        dst_nm = ac.get("dst")
        if isinstance(dst_nm, (int, float)):
            distance_km = dst_nm * NM_TO_KM
        else:
            distance_km = location.distance_to(lat, lon)

        country = country_for_icao24(icao24)

        f = Flight(
            icao24=icao24,
            callsign=callsign,
            origin_country=country,
            latitude=lat,
            longitude=lon,
            baro_altitude=baro_alt_m,
            on_ground=on_ground,
            velocity=velocity,
            true_track=ac.get("track"),
            vertical_rate=vrate,
            squawk=ac.get("squawk"),
            distance_km=distance_km,
            airline_name=airline_name,
            airline_iata=airline_iata,
            airline_icao=airline_icao,
            aircraft_type=ac.get("t") or "",
        )
        flights.append(f)

    flights.sort(key=lambda f: f.distance_km)
    return flights
