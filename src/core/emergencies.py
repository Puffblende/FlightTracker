"""Emergency squawk codes per ICAO Doc 4444 / ATM.

  7500  Unlawful interference (hijacking)
  7600  Communication failure (radio failure)
  7601  Radio failure — IFR in visual conditions
  7700  General emergency
"""
from __future__ import annotations

EMERGENCY_SQUAWKS: frozenset[str] = frozenset({"7500", "7600", "7601", "7700"})


def is_emergency_squawk(squawk) -> bool:
    if not squawk:
        return False
    return str(squawk).strip() in EMERGENCY_SQUAWKS
