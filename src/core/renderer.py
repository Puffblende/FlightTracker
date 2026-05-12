"""Renders one flight's data onto an 80×40 LED pixel buffer."""
from __future__ import annotations
from PIL import Image
from src.core.models import (
    Flight, LayoutBlock, BLOCK_TYPE_MAP,
    fmt_altitude, fmt_speed, fmt_track, fmt_vrate, fmt_distance, fmt_route,
)
from src.core.font import draw_text, char_width, CHAR_H
from src.api.logos import get_logo, prefetch_async

W = 80
H = 40
BG = (0, 0, 0)


def _new_buffer():
    return [[BG] * W for _ in range(H)]


def _paste_pil(buf, img: Image.Image, x: int, y: int) -> None:
    pw, ph = img.size
    pixels = img.load()
    for iy in range(ph):
        for ix in range(pw):
            bx, by = x + ix, y + iy
            if 0 <= bx < W and 0 <= by < H:
                buf[by][bx] = pixels[ix, iy]


def _txt(buf, block: LayoutBlock, text: str) -> None:
    """Draw text clipped to the block's declared pixel width."""
    draw_text(buf, block.x, block.y, text, block.color,
              max_width=block.width)


def _render_block(buf, block: LayoutBlock, flight: Flight) -> None:
    key = block.key
    fmt = block.fmt

    if key == "logo":
        size = block.width  # always square
        iata = flight.airline_iata
        icao = flight.airline_icao
        if iata or icao:
            prefetch_async(iata, size, size, icao)
            logo = get_logo(iata, size, size, icao)
        else:
            from src.api.logos import _generic_plane
            logo = _generic_plane(size, size)
        _paste_pil(buf, logo, block.x, block.y)

    elif key == "airline":
        name = flight.airline_name or flight.airline_icao or flight.callsign[:3]
        if fmt == "short":
            text = name.split()[0][:8].upper() if name else "---"
        elif fmt == "icao":
            text = (flight.airline_icao or flight.callsign[:3]).upper()
        else:
            text = name.upper()
        _txt(buf, block, text)

    elif key == "callsign":
        if fmt == "icao24":
            _txt(buf, block, flight.icao24.upper())
        else:
            _txt(buf, block, flight.display_callsign)

    elif key == "route":
        _txt(buf, block, fmt_route(flight, fmt))

    elif key == "aircraft_type":
        typ = flight.aircraft_type or "----"
        if fmt == "full":
            _txt(buf, block, typ.upper())
        else:
            _txt(buf, block, typ[:4].upper())

    elif key == "altitude":
        _txt(buf, block, fmt_altitude(flight.baro_altitude, fmt))

    elif key == "speed":
        _txt(buf, block, fmt_speed(flight.velocity, fmt))

    elif key == "track":
        _txt(buf, block, fmt_track(flight.true_track, fmt))

    elif key == "vrate":
        _txt(buf, block, fmt_vrate(flight.vertical_rate, fmt))

    elif key == "squawk":
        sq = flight.squawk or "----"
        text = f"SQ:{sq[:4]}" if fmt == "label" else sq[:4]
        _txt(buf, block, text)

    elif key == "country":
        _txt(buf, block, flight.origin_country.upper())

    elif key == "distance":
        _txt(buf, block, fmt_distance(flight.distance_km, fmt))


def render_frame(flight, blocks: list) -> list:
    """Return an 80×40 RGB pixel buffer for the given flight and layout."""
    buf = _new_buffer()
    if flight is None:
        msg = "NO FLIGHTS"
        cx = (W - len(msg) * char_width()) // 2
        cy = (H - CHAR_H) // 2
        draw_text(buf, cx, cy, msg, (80, 80, 80))
        return buf

    for block in blocks:
        if block.enabled:
            try:
                _render_block(buf, block, flight)
            except Exception:
                pass
    return buf


def buffer_to_pil(buf: list) -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            px[x, y] = buf[y][x]
    return img
