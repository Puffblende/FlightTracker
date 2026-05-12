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


# 7×7 plane glyph viewed top-down, nose up. Wings are at row 3 (centre)
# so they land on the bar row when the plane is drawn centred on it.
PLANE_GLYPH = [
    "...X...",
    "...X...",
    "..XXX..",
    "XXXXXXX",
    "..XXX..",
    "...X...",
    ".XX.XX.",
]


def _draw_plane(buf, cx: int, cy: int, color: tuple, W: int, H: int,
               x_min: int = 0, x_max: int = -1) -> None:
    """Draw the plane glyph centred on cx/cy, clipped to [x_min, x_max)."""
    if x_max < 0:
        x_max = W
    for gy, row in enumerate(PLANE_GLYPH):
        for gx, ch in enumerate(row):
            if ch != "X":
                continue
            x = cx + gx - 3
            y = cy + gy - 3
            if x_min <= x < x_max and 0 <= y < H:
                buf[y][x] = color


def _draw_progress(buf, block: LayoutBlock, flight: Flight, W: int, H: int) -> None:
    x0, y0 = block.x, block.y
    width = max(4, block.width)
    color = block.color
    plane_color = tuple(block.plane_color) if block.plane_color is not None else color

    # The bar sits in the vertical centre of the plane area
    bar_block_h = 7 if block.show_plane else 3
    bar_y = y0 + bar_block_h // 2

    prog = flight_progress(flight)
    pos = int(round((width - 1) * max(0.0, min(1.0, prog)))) if prog is not None else None

    x1 = x0 + width   # exclusive right edge of the bar block

    # ── Draw the bar ──
    if block.show_remaining:
        # Solid completed portion + dotted remaining portion (every 2nd pixel, 50 % brightness)
        dim = tuple(c // 2 for c in color)
        for i in range(width):
            bx = x0 + i
            if not (0 <= bx < W and 0 <= bar_y < H):
                continue
            if pos is None:
                if i % 2 == 0:
                    buf[bar_y][bx] = dim         # dotted when no progress data
            elif i <= pos:
                buf[bar_y][bx] = color           # solid = completed
            elif i % 2 == 0:
                buf[bar_y][bx] = dim             # dotted = remaining
    else:
        # Only the completed portion; nothing drawn if progress unknown.
        if pos is not None:
            for i in range(pos + 1):
                bx = x0 + i
                if 0 <= bx < W and 0 <= bar_y < H:
                    buf[bar_y][bx] = color

    # ── Endpoint dots (origin + destination) ──────────────────────────────────
    if block.show_endpoints:
        for end_x in (x0, x1 - 1):
            for dy_ in (-1, 0):
                for dx_ in (-1, 0, 1):
                    px, py = end_x + dx_, bar_y + dy_
                    if x0 <= px < x1 and 0 <= py < H:
                        buf[py][px] = color

    # ── Marker / plane — clipped to bar width ─────────────────────────────────
    if pos is not None:
        marker_x = x0 + pos
        if block.show_plane:
            _draw_plane(buf, marker_x, bar_y, plane_color, W, H,
                        x_min=x0, x_max=x1)
        else:
            for dx_ in (-1, 0, 1):
                bx = marker_x + dx_
                if x0 <= bx < x1 and 0 <= bar_y < H:
                    buf[bar_y][bx] = plane_color
            if 0 <= bar_y - 1 < H and x0 <= marker_x < x1:
                buf[bar_y - 1][marker_x] = plane_color

    # ── Remaining distance text (below the bar block) ──
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


def render_frame(flight, blocks: list) -> list:
    W, H = get_display_size()
    buf = _new_buffer(W, H)
    if flight is None:
        msg = "NO FLIGHTS"
        cx = max(0, (W - len(msg) * char_width()) // 2)
        cy = max(0, (H - CHAR_H) // 2)
        draw_text(buf, cx, cy, msg, (80, 80, 80))
        return buf

    for block in blocks:
        if block.enabled:
            try:
                _render_block(buf, block, flight, W, H)
            except Exception:
                pass
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
