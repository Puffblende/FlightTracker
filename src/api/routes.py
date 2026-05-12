"""Callsign → route lookup via adsbdb.com.

adsbdb is a free, community-maintained ADS-B database. We hit it once per
unique callsign and cache the result both in memory and on disk so repeated
fetches don't hammer the service.

Each successful lookup also seeds the airport coordinate table used by
src.core.progress, so the flight-progress bar gets accurate origin/dest
coords for whatever airports we encounter — no built-in airport DB needed.
"""
from __future__ import annotations
import json
import os
import threading
import time
from pathlib import Path

import requests

from src.core import progress as _progress

_API = "https://api.adsbdb.com/v0/callsign/{}"
_TIMEOUT = 5.0
_MIN_INTERVAL = 0.25  # seconds between API calls

_CACHE_DIR = Path.home() / ".flighttracker"
_CACHE_FILE = _CACHE_DIR / "routes.json"

# callsign → (origin_iata, dest_iata, "miss" sentinel allowed)
_cache: dict[str, tuple[str, str]] = {}
_lock = threading.Lock()
_last_call = 0.0


def _load_disk_cache() -> None:
    if not _CACHE_FILE.exists():
        return
    try:
        data = json.loads(_CACHE_FILE.read_text())
        for cs, v in data.items():
            if isinstance(v, list) and len(v) == 2:
                _cache[cs] = (v[0] or "", v[1] or "")
    except Exception:
        pass


def _save_disk_cache() -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(
            {k: list(v) for k, v in _cache.items()}
        ))
    except Exception:
        pass


_load_disk_cache()


def _seed_airport(iata: str, icao: str, lat, lon) -> None:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return
    if iata:
        _progress.AIRPORTS[iata.upper()] = (lat, lon)
    if icao:
        _progress.AIRPORTS[icao.upper()] = (lat, lon)


def lookup_route(callsign: str) -> tuple[str, str]:
    """Return (origin_iata, destination_iata) for a callsign, or ("","")."""
    cs = (callsign or "").strip().upper()
    if not cs:
        return ("", "")

    with _lock:
        if cs in _cache:
            return _cache[cs]

    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    origin = destination = ""
    try:
        r = requests.get(_API.format(cs), timeout=_TIMEOUT)
        _last_call = time.time()
        if r.status_code == 200:
            data = r.json() or {}
            fr = (data.get("response") or {}).get("flightroute") or {}
            o = fr.get("origin") or {}
            d = fr.get("destination") or {}
            origin = (o.get("iata_code") or "").upper()
            destination = (d.get("iata_code") or "").upper()
            _seed_airport(
                o.get("iata_code") or "",
                o.get("icao_code") or "",
                o.get("latitude"), o.get("longitude"),
            )
            _seed_airport(
                d.get("iata_code") or "",
                d.get("icao_code") or "",
                d.get("latitude"), d.get("longitude"),
            )
    except Exception:
        pass

    with _lock:
        _cache[cs] = (origin, destination)
        _save_disk_cache()
    return (origin, destination)
