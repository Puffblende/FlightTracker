"""Renders one flight's data onto the LED pixel buffer."""
from __future__ import annotations
from PIL import Image
from src.core.models import (
    Flight, LayoutBlock, render_block_text,
)
from src.core.font import draw_text, char_width, text_width, CHAR_H
from src.api.logos import get_logo, prefetch_async
from src.core.displays import get_display_size
from src.core.progress import flight_progress, remaining_distance_km

BG = (0, 0, 0)


def _new_buffer(w: int, h: int):
    return [[BG] * w for _ in range(h)]


def _paste_pil(buf, img: Image.Image, x: int, y: int, W: int, H: int) -> None:
    pw, ph = img.size
    pixels = img.load()
    for iy in range(ph):
        for ix in range(pw):
            bx, by = x + ix, y + iy
            if 0 <= bx < W and 0 <= by < H:
                buf[by][bx] = pixels[ix, iy]


def _txt(buf, block: LayoutBlock, text: str) -> None:
    draw_text(buf, block.x, block.y, text, block.color,
              max_width=block.width, scale=block.font_scale)


def _draw_progress(buf, block: LayoutBlock, flight: Flight, W: int, H: int) -> None:
    x0, y0 = block.x, block.y
    width = max(4, block.width)
    color = block.color

    # Simple 3-pixel-tall bar area: tick line above + bar
    bar_block_h = 3
    bar_y = y0 + 1
    x1 = x0 + width   # exclusive right edge

    prog = flight_progress(flight)
    pos = int(round((width - 1) * max(0.0, min(1.0, prog)))) if prog is not None else None

    # Bar
    if block.show_remaining:
        dim = tuple(c // 2 for c in color)
        for i in range(width):
            bx = x0 + i
            if not (0 <= bx < W and 0 <= bar_y < H):
                continue
            if pos is None:
                if i % 2 == 0:
                    buf[bar_y][bx] = dim
            elif i <= pos:
                buf[bar_y][bx] = color
            elif i % 2 == 0:
                buf[bar_y][bx] = dim
    elif pos is not None:
        for i in range(pos + 1):
            bx = x0 + i
            if 0 <= bx < W and 0 <= bar_y < H:
                buf[bar_y][bx] = color

    # Endpoint dots
    if block.show_endpoints:
        for end_x in (x0, x1 - 1):
            for dy_ in (-1, 0):
                for dx_ in (-1, 0, 1):
                    px, py = end_x + dx_, bar_y + dy_
                    if x0 <= px < x1 and 0 <= py < H:
                        buf[py][px] = color

    # No standalone aircraft-position marker — the bar itself shows the
    # position (its end when show_remaining is off, or the solid → dotted
    # transition when it's on). Keeps the bar a clean straight line.

    # Remaining-distance text
    if block.show_remaining:
        rem = remaining_distance_km(flight)
        if rem is not None:
            unit = block.effective_unit or "km"
            txt = f"{int(rem)}{unit}"
            tw = text_width(txt, block.font_scale)
            tx = x0 + max(0, width - tw)
            ty = y0 + bar_block_h + 1
            draw_text(buf, tx, ty, txt, color,
                      max_width=width, scale=block.font_scale)


def _render_block(buf, block: LayoutBlock, flight: Flight, W: int, H: int) -> None:
    key = block.key

    if key == "logo":
        size = block.width
        iata = flight.airline_iata
        icao = flight.airline_icao
        if iata or icao:
            prefetch_async(iata, size, size, icao)
            logo = get_logo(iata, size, size, icao)
        else:
            from src.api.logos import _generic_plane
            logo = _generic_plane(size, size)
        _paste_pil(buf, logo, block.x, block.y, W, H)
        return

    if key == "progress":
        _draw_progress(buf, block, flight, W, H)
        return

    # All text blocks
    _txt(buf, block, render_block_text(block, flight))


# Emergency border colour and thickness (in LED pixels)
EMERGENCY_BORDER_RGB = (230, 30, 30)
EMERGENCY_BORDER_PX  = 2


def _paint_emergency_border(buf, W: int, H: int) -> None:
    """Overwrite the outer 2 LED pixels with red — part of the matrix, not
    a window-level decoration. Drawn last so it overlays any block content."""
    r = EMERGENCY_BORDER_RGB
    t = EMERGENCY_BORDER_PX
    for y in range(min(t, H)):
        for x in range(W):
            buf[y][x] = r
    for y in range(max(0, H - t), H):
        for x in range(W):
            buf[y][x] = r
    for y in range(H):
        for x in range(min(t, W)):
            buf[y][x] = r
        for x in range(max(0, W - t), W):
            buf[y][x] = r


def render_frame(flight, blocks: list, *,
                 flash_squawk: bool = True,
                 emergency_border: bool = False) -> list:
    """Render an LED buffer. `flash_squawk=False` skips the squawk block
    (used to flash the code on/off during an emergency). `emergency_border`
    paints a 2-pixel red ring on the outer LED rows."""
    W, H = get_display_size()
    buf = _new_buffer(W, H)
    if flight is None:
        msg = "NO FLIGHTS"
        cx = max(0, (W - len(msg) * char_width()) // 2)
        cy = max(0, (H - CHAR_H) // 2)
        draw_text(buf, cx, cy, msg, (80, 80, 80))
        if emergency_border:
            _paint_emergency_border(buf, W, H)
        return buf

    for block in blocks:
        if not block.enabled:
            continue
        if block.key == "squawk" and not flash_squawk:
            continue
        try:
            _render_block(buf, block, flight, W, H)
        except Exception:
            pass

    if emergency_border:
        _paint_emergency_border(buf, W, H)
    return buf


def buffer_to_pil(buf: list) -> Image.Image:
    H = len(buf)
    W = len(buf[0]) if H else 0
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            px[x, y] = buf[y][x]
    return img
