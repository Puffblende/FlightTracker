from PIL import Image

from src.api.logos import collect_known_airline_catalog, _needs_white_background
from src.core.airlines import AIRLINE_DB


def test_collect_known_airline_catalog_contains_all_db_entries() -> None:
    catalog = collect_known_airline_catalog()

    assert len(catalog) >= len(AIRLINE_DB)
    icaos = {icao for icao, _, _ in catalog}
    assert icaos.issuperset(set(AIRLINE_DB.keys()))


def test_dark_transparent_logo_is_detected_as_needing_white_background() -> None:
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    img.paste((0, 35, 94, 255), (6, 6, 18, 18))

    assert _needs_white_background(img) is True
