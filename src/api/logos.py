"""Airline logo fetching and caching.
Sources tried in order:
  1. pics.avs.io  (IATA code)  — fast, consistent transparent PNGs
  2. FlightAware  (ICAO code)  — good fallback with white backgrounds
Falls back to a generic pixel-art plane icon when both fail.
"""
from __future__ import annotations
import io
import threading
from pathlib import Path
from PIL import Image
import requests

from src.core.airlines import AIRLINE_DB

CACHE_DIR = Path.home() / ".flighttracker" / "logos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_memory: dict = {}          # cache_key -> Image.Image | None
_HEADERS = {"User-Agent": "FlightTracker/1.0"}

# 16×16 pixel-art top-down plane (1 = lit, 0 = off)
_PLANE_16 = [
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],
    [0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
]


def _generic_plane(w: int, h: int, color: tuple = (80, 140, 255)) -> Image.Image:
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    for r, row in enumerate(_PLANE_16):
        for c, pix in enumerate(row):
            if pix:
                img.putpixel((c, r), color)
    return img.resize((w, h), Image.Resampling.NEAREST)


def collect_known_airline_catalog() -> list[tuple[str, str, str]]:
    """Return the known airline catalog as (ICAO, IATA, name)."""
    catalog: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for icao, entry in AIRLINE_DB.items():
        icao_code = (icao or "").strip().upper()
        if len(icao_code) != 3 or not icao_code.isalpha() or icao_code in seen:
            continue
        seen.add(icao_code)
        name, iata = entry
        catalog.append((icao_code, (iata or "").strip().upper(), name))
    return catalog


def prefetch_all_known_logos(w: int = 24, h: int = 24) -> None:
    """Warm the logo cache for the full known airline catalog."""
    for icao, iata, _ in collect_known_airline_catalog():
        get_logo(iata, w, h, icao)


def _needs_white_background(img: Image.Image) -> bool:
    """Heuristically detect logos that were authored on a solid white background."""
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode not in ("RGBA", "LA"):
        return False

    rgba = img.convert("RGBA")
    data = list(rgba.getdata())
    if not data:
        return False

    alpha = [p[3] for p in data]
    opaque = sum(1 for a in alpha if a >= 250)
    if opaque == len(alpha):
        return True

    # Some airline marks are authored with a light or neutral background that isn't
    # pure white. These are still easier to read on a dark LED panel if we bake a
    # white background into the image before resizing.
    white_pixels = sum(1 for r, g, b, a in data if a > 0 and r > 230 and g > 230 and b > 230)
    bright_pixels = sum(1 for r, g, b, a in data if a > 0 and (r + g + b) / 3 > 210)

    if white_pixels > len(data) * 0.15 or bright_pixels > len(data) * 0.35:
        return True

    transparent = sum(1 for a in alpha if a < 10)
    if transparent < len(alpha) * 0.02:
        return True

    # Dark, compact logos with very little transparency often need a white matte to
    # keep their edges readable on a dark display.
    if opaque > len(data) * 0.15 and transparent < len(data) * 0.6:
        return True

    # Some airline marks use a dark, narrow motif with a lot of transparency. These
    # can look washed out on a dark LED display unless we composite them onto white.
    if opaque > len(data) * 0.12 and transparent > len(data) * 0.55:
        return True

    return False


def _composite_on_white(img: Image.Image, w: int, h: int) -> Image.Image:
    """Flatten transparency onto white only when the source likely needs it."""
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        if _needs_white_background(img):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            mask = img.split()[-1]
            bg.paste(img.convert("RGB"), mask=mask)
            img = bg
        else:
            img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    if img.mode == "RGBA":
        img = img.convert("RGB")
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _try_fetch(iata: str, icao: str, w: int, h: int):
    """Try CDN sources in order; return resized RGB Image or None."""
    candidates = []
    if icao:
        # FlightAware: 3-letter ICAO code, solid color backgrounds → best for LED
        candidates.append(
            f"https://www.flightaware.com/images/airline_logos/180px/{icao.upper()}.png"
        )
    if iata:
        # pics.avs.io: 2-letter IATA code, transparent backgrounds
        candidates.append(f"https://pics.avs.io/200/200/{iata.upper()}.png")

    for url in candidates:
        try:
            r = requests.get(url, timeout=8, headers=_HEADERS)
            if r.status_code == 200 and len(r.content) > 300:
                img = Image.open(io.BytesIO(r.content))
                return _composite_on_white(img, w, h)
        except Exception:
            continue
    return None


def get_logo(iata: str, w: int = 24, h: int = 24, icao: str = "") -> Image.Image:
    """Return airline logo as w×h RGB PIL Image.
    Uses memory → disk cache → CDN fetch → generic icon."""
    key = f"{iata or icao}_{w}_{h}"
    with _lock:
        if key in _memory:
            cached = _memory[key]
            return cached if cached is not None else _generic_plane(w, h)

    # Try disk cache first
    cache_file = CACHE_DIR / f"{key}.png"
    if cache_file.exists():
        try:
            img = Image.open(cache_file).convert("RGB")
            with _lock:
                _memory[key] = img
            return img
        except Exception:
            pass

    # Fetch from network
    img = _try_fetch(iata, icao, w, h)
    if img:
        try:
            img.save(cache_file)
        except Exception:
            pass

    with _lock:
        _memory[key] = img   # store None if all sources failed (avoids retry spam)
    return img if img is not None else _generic_plane(w, h)


def prefetch_async(iata: str, w: int = 24, h: int = 24, icao: str = "") -> None:
    """Kick off a background logo fetch so the next render hits the cache."""
    key = f"{iata or icao}_{w}_{h}"
    with _lock:
        if key in _memory:
            return  # already cached or attempted
    t = threading.Thread(target=get_logo, args=(iata, w, h, icao), daemon=True)
    t.start()
