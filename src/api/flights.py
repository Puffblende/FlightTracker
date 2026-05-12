"""Unified flight-data fetcher.

Tries adsb.lol first (free, no auth, no daily budget); falls back to
OpenSky on any failure. The OpenSky username/password is only used by
the fallback path.
"""
from __future__ import annotations
import logging

from src.core.models import Location, Flight
from src.api import adsb_lol, opensky

log = logging.getLogger("flighttracker.flights")

# Track which source succeeded last — handy for the status bar.
last_source: str = ""


def fetch_flights(location: Location, radius_km: float,
                  username: str = "", password: str = "") -> list[Flight]:
    global last_source
    try:
        flights = adsb_lol.fetch_flights(location, radius_km)
        last_source = "adsb.lol"
        return flights
    except Exception as e:
        log.warning("adsb.lol failed, falling back to OpenSky: %s", e)
        flights = opensky.fetch_flights(location, radius_km, username, password)
        last_source = "OpenSky"
        return flights


# Re-export the OpenSky aircraft-type lookup for the rare cases where
# adsb.lol didn't have the type (call this as a fallback if Flight.aircraft_type
# is empty).
fetch_aircraft_type = opensky.fetch_aircraft_type
