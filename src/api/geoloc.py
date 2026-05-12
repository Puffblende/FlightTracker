"""IP-based geolocation with fallback."""
import requests
from src.core.models import Location


def get_location(timeout: int = 5):
    """Fetch current location via IP geolocation. Returns a default on failure."""
    services = [
        ("https://ipapi.co/json/",      _parse_ipapi),
        ("https://ip-api.com/json/",    _parse_ipapi_com),
    ]
    for url, parser in services:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                loc = parser(r.json())
                if loc:
                    return loc
        except Exception:
            continue
    # Fallback: Munich, Germany
    return Location(48.1351, 11.5820, "Munich", "Germany")


def _parse_ipapi(data: dict):
    try:
        return Location(
            lat=float(data["latitude"]),
            lon=float(data["longitude"]),
            city=data.get("city", ""),
            country=data.get("country_name", ""),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _parse_ipapi_com(data: dict):
    try:
        return Location(
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            city=data.get("city", ""),
            country=data.get("country", ""),
        )
    except (KeyError, ValueError, TypeError):
        return None
