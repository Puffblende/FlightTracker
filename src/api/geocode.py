"""Forward geocoding via Nominatim (OpenStreetMap).

Free, no auth required. Usage policy asks for a meaningful User-Agent and
no more than 1 request per second — we throttle accordingly.
"""
from __future__ import annotations
import time
import requests

from src.core.models import Location

_API = "https://nominatim.openstreetmap.org/search"
_TIMEOUT = 8.0
_MIN_INTERVAL = 1.0
_last_call: float = 0.0


def geocode(query: str) -> Location | None:
    """Look up a free-form address. Returns Location or None if unresolved.

    Accepts anything Nominatim accepts: "Hauptstraße 5, Munich",
    "Statue of Liberty", "Freudenstadt", lat/lon decimals, postal codes, …
    """
    global _last_call
    q = (query or "").strip()
    if not q:
        return None

    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    try:
        r = requests.get(
            _API,
            params={
                "q": q, "format": "json", "limit": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": "FlightTracker/1.0 (LED matrix tracker)"},
            timeout=_TIMEOUT,
        )
        _last_call = time.time()
        if r.status_code != 200:
            return None
        results = r.json() or []
        if not results:
            return None
        hit = results[0]
        lat = float(hit["lat"])
        lon = float(hit["lon"])
        addr = hit.get("address") or {}
        city = (addr.get("city") or addr.get("town") or addr.get("village")
                or addr.get("hamlet") or addr.get("suburb")
                or addr.get("county") or "")
        country = addr.get("country") or ""
        return Location(lat, lon, city, country)
    except Exception:
        return None
