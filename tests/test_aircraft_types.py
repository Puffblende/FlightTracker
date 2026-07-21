from types import SimpleNamespace

from src.core.models import value_aircraft_type


def test_aircraft_type_formats_support_short_manufacturer_and_model_parts() -> None:
    flight = SimpleNamespace(aircraft_type="B738")

    assert value_aircraft_type(flight, "short") == "B738"
    assert value_aircraft_type(flight, "manufacturer") == "BOEING"
    assert value_aircraft_type(flight, "model") == "737-800"
    assert value_aircraft_type(flight, "full") == "BOEING 737-800"
