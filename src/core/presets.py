"""Preset persistence — save/load named configurations to disk."""
from __future__ import annotations
import json
from pathlib import Path

from src.core.models import LayoutBlock, default_layout


PRESETS_DIR = Path.home() / ".flighttracker" / "presets"
_LAST_FILE   = Path.home() / ".flighttracker" / "last_preset.txt"


def _ensure() -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)


# ── Serialisation ─────────────────────────────────────────────────────────────

def _block_to_dict(b: LayoutBlock) -> dict:
    return {
        "key": b.key, "x": b.x, "y": b.y,
        "enabled": b.enabled, "fmt": b.fmt,
        "custom_color":  list(b.custom_color)  if b.custom_color  else None,
        "custom_width":  b.custom_width,
        "custom_label":  b.custom_label,
        "custom_unit":   b.custom_unit,
        "font_scale":    b.font_scale,
        "show_remaining": b.show_remaining,
        "show_plane":     b.show_plane,
        "show_endpoints": b.show_endpoints,
        "plane_color":   list(b.plane_color) if b.plane_color else None,
        "recognize_emergencies": b.recognize_emergencies,
    }


def _block_from_dict(d: dict) -> LayoutBlock:
    cc = d.get("custom_color")
    pc = d.get("plane_color")
    return LayoutBlock(
        key=d["key"], x=d.get("x", 0), y=d.get("y", 0),
        enabled=d.get("enabled", True), fmt=d.get("fmt", ""),
        custom_color=tuple(cc) if cc else None,
        custom_width=d.get("custom_width"),
        custom_label=d.get("custom_label"),
        custom_unit=d.get("custom_unit"),
        font_scale=d.get("font_scale", 1),
        show_remaining=d.get("show_remaining", False),
        show_plane=d.get("show_plane", False),
        show_endpoints=d.get("show_endpoints", False),
        plane_color=tuple(pc) if pc else None,
        recognize_emergencies=d.get("recognize_emergencies", False),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def list_presets() -> list[str]:
    """Return sorted list of saved preset names (without extension)."""
    _ensure()
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def save_preset(name: str, data: dict) -> None:
    _ensure()
    payload = dict(data, name=name)
    with open(PRESETS_DIR / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    set_last_preset(name)


def load_preset(name: str) -> dict | None:
    path = PRESETS_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_preset(name: str) -> bool:
    """Delete a preset file. Returns True if it existed and was removed."""
    path = PRESETS_DIR / f"{name}.json"
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    # Clear last-preset pointer if this was the active one
    if get_last_preset() == name:
        try:
            _LAST_FILE.unlink()
        except OSError:
            pass
    return True


def get_last_preset() -> str | None:
    if _LAST_FILE.exists():
        name = _LAST_FILE.read_text(encoding="utf-8").strip()
        return name if name else None
    return None


def set_last_preset(name: str) -> None:
    _LAST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_FILE.write_text(name, encoding="utf-8")


def build_preset_data(
    name: str,
    layout: list[LayoutBlock],
    display_key: str,
    custom_grid: tuple,
    custom_win: tuple,
    location,
    radius: float,
    fetch_interval: int,
    cycle_interval: int,
    opensky_user: str,
    opensky_pass: str,
) -> dict:
    loc = None
    if location is not None:
        loc = {
            "lat": location.lat, "lon": location.lon,
            "city": location.city, "country": location.country,
        }
    return {
        "name": name, "version": 1,
        "display": {
            "key": display_key,
            "custom_grid": list(custom_grid),
            "custom_win":  list(custom_win),
        },
        "location": loc,
        "search_radius":  int(radius),
        "fetch_interval": fetch_interval,
        "cycle_interval": cycle_interval,
        "opensky_user":   opensky_user,
        "opensky_pass":   opensky_pass,
        "layout": [_block_to_dict(b) for b in layout],
    }


def layout_from_preset(data: dict) -> list[LayoutBlock]:
    blocks = data.get("layout", [])
    return [_block_from_dict(b) for b in blocks] if blocks else default_layout()
