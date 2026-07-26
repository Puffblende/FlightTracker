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
_AIRPORT_CACHE_FILE = _CACHE_DIR / "airports_cache.json"

# callsign → (origin_iata, dest_iata, origin_icao, dest_icao)
_cache: dict[str, tuple[str, str, str, str]] = {}
_lock = threading.Lock()
_last_call = 0.0


def _load_disk_cache() -> None:
    if not _CACHE_FILE.exists():
        return
    try:
        data = json.loads(_CACHE_FILE.read_text())
        for cs, v in data.items():
            if isinstance(v, list):
                if len(v) == 4:
                    _cache[cs] = (v[0] or "", v[1] or "", v[2] or "", v[3] or "")
                elif len(v) == 2:
                    # legacy entries — IATA only
                    _cache[cs] = (v[0] or "", v[1] or "", "", "")
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

# Codes learned from adsbdb.com's lat/lon fields, kept separate from the
# static AIRPORTS table so we only ever persist what we ourselves seeded.
_seeded_airports: dict[str, tuple[float, float]] = {}


def _load_airport_cache() -> None:
    if not _AIRPORT_CACHE_FILE.exists():
        return
    try:
        data = json.loads(_AIRPORT_CACHE_FILE.read_text())
        for code, latlon in data.items():
            if isinstance(latlon, list) and len(latlon) == 2:
                coord = (float(latlon[0]), float(latlon[1]))
                _seeded_airports[code] = coord
                _progress.AIRPORTS[code] = coord
    except Exception:
        pass


def _save_airport_cache() -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _AIRPORT_CACHE_FILE.write_text(json.dumps(
            {k: list(v) for k, v in _seeded_airports.items()}
        ))
    except Exception:
        pass


_load_airport_cache()


def _seed_airport(iata: str, icao: str, lat, lon) -> None:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return
    changed = False
    if iata:
        iata = iata.upper()
        _progress.AIRPORTS[iata] = (lat, lon)
        _seeded_airports[iata] = (lat, lon)
        changed = True
    if icao:
        icao = icao.upper()
        _progress.AIRPORTS[icao] = (lat, lon)
        _seeded_airports[icao] = (lat, lon)
        changed = True
    if changed:
        _save_airport_cache()


def lookup_route(callsign: str) -> tuple[str, str, str, str]:
    """Return (origin_iata, dest_iata, origin_icao, dest_icao) for a callsign,
    or empty strings if unknown."""
    cs = (callsign or "").strip().upper()
    if not cs:
        return ("", "", "", "")

    with _lock:
        cached = _cache.get(cs)
        if cached is not None:
            o_i, d_i, o_a, d_a = cached
            # A genuinely-unknown route comes back with all four fields
            # empty. IATA present but ICAO missing means this entry
            # predates ICAO-code support (see _load_disk_cache()'s legacy
            # migration) — worth one re-fetch instead of staying stuck
            # with a partial route forever, since a fresh lookup now
            # returns both.
            if (o_i or d_i) and not (o_a and d_a):
                print(f"[Routes] CACHE-INCOMPLETE {cs} -> {cached}, re-fetching for ICAO codes")
            else:
                print(f"[Routes] CACHE {cs} -> {cached}")
                return cached

    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    o_iata = d_iata = o_icao = d_icao = ""
    try:
        r = requests.get(_API.format(cs), timeout=_TIMEOUT)
        _last_call = time.time()
        print(f"[Routes] FETCH {cs} -> HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json() or {}
            fr = (data.get("response") or {}).get("flightroute") or {}
            o = fr.get("origin") or {}
            d = fr.get("destination") or {}
            o_iata = (o.get("iata_code") or "").upper()
            d_iata = (d.get("iata_code") or "").upper()
            o_icao = (o.get("icao_code") or "").upper()
            d_icao = (d.get("icao_code") or "").upper()
            _seed_airport(o_iata, o_icao,
                          o.get("latitude"), o.get("longitude"))
            _seed_airport(d_iata, d_icao,
                          d.get("latitude"), d.get("longitude"))
    except Exception as exc:
        print(f"[Routes] FETCH {cs} -> error: {exc}")

    print(f"[Routes] RESULT {cs} -> ('{o_iata}', '{d_iata}', '{o_icao}', '{d_icao}')")
    with _lock:
        _cache[cs] = (o_iata, d_iata, o_icao, d_icao)
        _save_disk_cache()
    return (o_iata, d_iata, o_icao, d_icao)
