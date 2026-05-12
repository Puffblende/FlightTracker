"""Display size presets for the LED panel.

A "display" is two things:
  - LED grid:   how many LEDs across × down (e.g. 80×40, 64×32, 256×256)
  - Window hint: optional target on-screen footprint in screen pixels
                 (e.g. 1920×1080). When set, the LED renderer/editor pick
                 a per-LED cell size that fits that footprint; LEDs stay
                 square (min of the two ratios).
"""
from __future__ import annotations

# (key, label, width, height)
DISPLAY_SIZES: list[tuple[str, str, int, int]] = [
    ("80x40",    "80 × 40   (classic)",       80,  40),
    ("128x64",   "128 × 64  (wide)",         128,  64),
    ("256x128",  "256 × 128 (cinema)",       256, 128),
    ("64x64",    "64 × 64   (square S)",      64,  64),
    ("128x128",  "128 × 128 (square M)",     128, 128),
    ("256x256",  "256 × 256 (square L)",     256, 256),
]

DEFAULT_SIZE_KEY = "80x40"
CUSTOM_KEY = "custom"

_current_key = DEFAULT_SIZE_KEY
_custom_w = 80
_custom_h = 40
_window_w = 0   # 0 → no target window size (use editor/widget defaults)
_window_h = 0


def get_display_size() -> tuple[int, int]:
    if _current_key == CUSTOM_KEY:
        return _custom_w, _custom_h
    for key, _label, w, h in DISPLAY_SIZES:
        if key == _current_key:
            return w, h
    return 80, 40


def get_display_key() -> str:
    return _current_key


def get_window_hint() -> tuple[int, int]:
    """Returns (W, H) of the target window in screen pixels, or (0, 0) if unset."""
    return _window_w, _window_h


def set_display_size(key: str) -> tuple[int, int]:
    """Switch to a preset. Clears any custom window hint."""
    global _current_key, _window_w, _window_h
    for k, _label, w, h in DISPLAY_SIZES:
        if k == key:
            _current_key = k
            _window_w = 0
            _window_h = 0
            return w, h
    return get_display_size()


def set_custom_display(grid_w: int, grid_h: int,
                       window_w: int = 0, window_h: int = 0) -> tuple[int, int]:
    """Set a custom LED grid and an optional target window size."""
    global _current_key, _custom_w, _custom_h, _window_w, _window_h
    _custom_w = max(8, min(1024, int(grid_w)))
    _custom_h = max(8, min(1024, int(grid_h)))
    _window_w = max(0, int(window_w))
    _window_h = max(0, int(window_h))
    _current_key = CUSTOM_KEY
    return _custom_w, _custom_h
