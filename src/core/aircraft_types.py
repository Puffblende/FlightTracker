"""ICAO aircraft type designators -> human-readable "Manufacturer Model" name.

Sources:
  Wikipedia "List of aircraft type designators"
    https://en.wikipedia.org/wiki/List_of_aircraft_type_designators
  ICAO Doc 8643 (authoritative)
    https://www.icao.int/operational-safety/doc-8643-aircraft-type-designators/search

Keyed by 4-character ICAO type code (case-insensitive). Every value is
"Manufacturer Model" (single space between the two) so value_aircraft_type()
can split it into "manufacturer" and "model" display formats — see
models.py. Grouped by actual manufacturer, not by ICAO-code first letter
(codes don't reliably follow manufacturer). Edit / extend freely, but keep
the single-space-separates-manufacturer-from-model convention.
"""
from __future__ import annotations

AIRCRAFT_TYPES: dict[str, str] = {

    # ── Boeing ────────────────────────────────────────────────────────────────
    "B37M": "Boeing 737 MAX 7",
    "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9",
    "B3XM": "Boeing 737 MAX 10",
    "B703": "Boeing 707",
    "B712": "Boeing 717",
    "B720": "Boeing 720",
    "B721": "Boeing 727-100",
    "B722": "Boeing 727-200",
    "B732": "Boeing 737-200",
    "B733": "Boeing 737-300",
    "B734": "Boeing 737-400",
    "B735": "Boeing 737-500",
    "B736": "Boeing 737-600",
    "B737": "Boeing 737-700",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B741": "Boeing 747-100",
    "B742": "Boeing 747-200",
    "B743": "Boeing 747-300",
    "B744": "Boeing 747-400",
    "B748": "Boeing 747-8",
    "B74F": "Boeing 747F",
    "B74S": "Boeing 747 SP",
    "B752": "Boeing 757-200",
    "B753": "Boeing 757-300",
    "B762": "Boeing 767-200",
    "B763": "Boeing 767-300",
    "B764": "Boeing 767-400",
    "B772": "Boeing 777-200",
    "B773": "Boeing 777-300",
    "B778": "Boeing 777-8",
    "B779": "Boeing 777-9",
    "B77L": "Boeing 777-200LR",
    "B77W": "Boeing 777-300ER",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "B78X": "Boeing 787-10",

    # ── Airbus ────────────────────────────────────────────────────────────────
    "A19N": "Airbus A319neo",
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A306": "Airbus A300-600",
    "A30B": "Airbus A300",
    "A310": "Airbus A310",
    "A318": "Airbus A318",
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A337": "Airbus A330 Beluga",
    "A338": "Airbus A330-800",
    "A339": "Airbus A330-900",
    "A342": "Airbus A340-200",
    "A343": "Airbus A340-300",
    "A345": "Airbus A340-500",
    "A346": "Airbus A340-600",
    "A359": "Airbus A350-900",
    "A35K": "Airbus A350-1000",
    "A388": "Airbus A380-800",
    "BCS1": "Airbus A220-100",
    "BCS3": "Airbus A220-300",

    # ── Cessna ────────────────────────────────────────────────────────────────
    "C152": "Cessna 152",
    "C162": "Cessna C162 Skycat.",
    "C172": "Cessna Skyhawk 172",
    "C177": "Cessna Cardinal 177",
    "C180": "Cessna 180",
    "C182": "Cessna Skylane 182",
    "C206": "Cessna Stationair",
    "C208": "Cessna Caravan 208",
    "C210": "Cessna Centurion 210",
    "C25A": "Cessna Citation CJ2",
    "C25B": "Cessna Citation CJ3",
    "C25C": "Cessna Citation CJ4",
    "C500": "Cessna Citation I",
    "C510": "Cessna Cit. Mustang",
    "C525": "Cessna CitationJet",
    "C550": "Cessna Citation II",
    "C560": "Cessna Citation V",
    "C56X": "Cessna Cit. Excel",
    "C650": "Cessna Citation III",
    "C680": "Cessna Cit. Sov.",
    "C68A": "Cessna Cit. Latitude",
    "C700": "Cessna Cit. Long.",
    "C750": "Cessna Citation X",

    # ── Airbus Helicopters ────────────────────────────────────────────────────
    "AS32": "Airbus Helicopters AS332 S.Puma",
    "AS3B": "Airbus Helicopters AS332L1 SPum",
    "AS50": "Airbus Helicopters AS350 Ecur.",
    "AS55": "Airbus Helicopters AS355 Ecur.",
    "AS65": "Airbus Helicopters AS365 Dauphin",
    "EC20": "Airbus Helicopters EC120 Colibri",
    "EC25": "Airbus Helicopters EC225 S.Puma",
    "EC30": "Airbus Helicopters EC130",
    "EC35": "Airbus Helicopters EC135",
    "EC45": "Airbus Helicopters EC145",
    "EC55": "Airbus Helicopters EC155",
    "EC75": "Airbus Helicopters EC175",
    "H125": "Airbus Helicopters H125",
    "H130": "Airbus Helicopters H130",
    "H135": "Airbus Helicopters H135",
    "H145": "Airbus Helicopters H145",
    "H155": "Airbus Helicopters H155",
    "H160": "Airbus Helicopters H160",
    "H225": "Airbus Helicopters H225",

    # ── Bombardier ────────────────────────────────────────────────────────────
    "CL30": "Bombardier Chal. 300",
    "CL35": "Bombardier Chal. 350",
    "CL60": "Bombardier Chal. 600",
    "CL64": "Bombardier Chal. 650",
    "CRJ1": "Bombardier CRJ-100",
    "CRJ2": "Bombardier CRJ-200",
    "CRJ7": "Bombardier CRJ-700",
    "CRJ9": "Bombardier CRJ-900",
    "CRJX": "Bombardier CRJ-1000",
    "DH8A": "Bombardier Dash 8-100",
    "DH8B": "Bombardier Dash 8-200",
    "DH8C": "Bombardier Dash 8-300",
    "DH8D": "Bombardier Dash 8 Q400",
    "GL5T": "Bombardier Global 5000",
    "GL7T": "Bombardier Global 7500",
    "GLEX": "Bombardier Global Exp.",

    # ── McDonnell Douglas ─────────────────────────────────────────────────────
    "DC10": "McDonnell Douglas DC-10",
    "DC85": "McDonnell Douglas DC-8-50",
    "DC86": "McDonnell Douglas DC-8-60",
    "DC87": "McDonnell Douglas DC-8-70",
    "DC91": "McDonnell Douglas DC-9-10",
    "DC92": "McDonnell Douglas DC-9-20",
    "DC93": "McDonnell Douglas DC-9-30",
    "DC94": "McDonnell Douglas DC-9-40",
    "DC95": "McDonnell Douglas DC-9-50",
    "MD11": "McDonnell Douglas MD-11",
    "MD81": "McDonnell Douglas MD-81",
    "MD82": "McDonnell Douglas MD-82",
    "MD83": "McDonnell Douglas MD-83",
    "MD87": "McDonnell Douglas MD-87",
    "MD88": "McDonnell Douglas MD-88",
    "MD90": "McDonnell Douglas MD-90",

    # ── Embraer ───────────────────────────────────────────────────────────────
    "E110": "Embraer EMB-110",
    "E120": "Embraer EMB-120",
    "E135": "Embraer ERJ-135",
    "E145": "Embraer ERJ-145",
    "E170": "Embraer E170",
    "E175": "Embraer E175",
    "E190": "Embraer E190",
    "E195": "Embraer E195",
    "E290": "Embraer E190-E2",
    "E295": "Embraer E195-E2",
    "E50P": "Embraer Phenom 100",
    "E545": "Embraer Praetor 500",
    "E550": "Embraer Legacy 500",
    "E55B": "Embraer Praetor 600",
    "E55P": "Embraer Phenom 300",

    # ── Antonov ───────────────────────────────────────────────────────────────
    "A124": "Antonov AN-124",
    "A140": "Antonov AN-140",
    "A148": "Antonov AN-148",
    "A158": "Antonov AN-158",
    "A225": "Antonov AN-225 Mriya",
    "AN12": "Antonov AN-12",
    "AN24": "Antonov AN-24",
    "AN26": "Antonov AN-26",
    "AN28": "Antonov AN-28",
    "AN32": "Antonov AN-32",
    "AN72": "Antonov AN-72",

    # ── Beechcraft ────────────────────────────────────────────────────────────
    "B190": "Beechcraft 1900",
    "B350": "Beechcraft King Air 350",
    "BE20": "Beechcraft King Air 200",
    "BE30": "Beechcraft King Air 350",
    "BE36": "Beechcraft Bonanza 36",
    "BE40": "Beechcraft Beechjet 400",
    "BE58": "Beechcraft Baron 58",
    "BE76": "Beechcraft Duchess",
    "BE99": "Beechcraft Beech 99",
    "BE9L": "Beechcraft King Air C90",
    "BE9T": "Beechcraft King Air F90",

    # ── Piper ─────────────────────────────────────────────────────────────────
    "P28A": "Piper PA-28 Cher.",
    "P28B": "Piper PA-28 Six",
    "P28R": "Piper PA-28R Arrow",
    "P28T": "Piper PA-28T Arrow",
    "PA31": "Piper PA-31 Navajo",
    "PA32": "Piper PA-32 Cher.",
    "PA34": "Piper PA-34 Seneca",
    "PA44": "Piper PA-44 Semi.",
    "PA46": "Piper PA-46 Malibu",

    # ── ATR ───────────────────────────────────────────────────────────────────
    "AT42": "ATR 42",
    "AT43": "ATR 42-300",
    "AT45": "ATR 42-500",
    "AT46": "ATR 42-600",
    "AT72": "ATR 72",
    "AT73": "ATR 72-200",
    "AT75": "ATR 72-500",
    "AT76": "ATR 72-600",

    # ── BAe ───────────────────────────────────────────────────────────────────
    "B461": "BAe 146-100",
    "B462": "BAe 146-200",
    "B463": "BAe 146-300",
    "JS31": "BAe Jetstream 31",
    "JS41": "BAe Jetstream 41",
    "RJ1H": "BAe Avro RJ100",
    "RJ70": "BAe RJ70",
    "RJ85": "BAe RJ85",

    # ── Dassault ──────────────────────────────────────────────────────────────
    "F2TH": "Dassault Falcon 2000",
    "F900": "Dassault Falcon 900",
    "FA10": "Dassault Falcon 10",
    "FA20": "Dassault Falcon 20",
    "FA50": "Dassault Falcon 50",
    "FA7X": "Dassault Falcon 7X",
    "FA8X": "Dassault Falcon 8X",

    # ── Learjet ───────────────────────────────────────────────────────────────
    "LJ31": "Learjet 31",
    "LJ35": "Learjet 35",
    "LJ40": "Learjet 40",
    "LJ45": "Learjet 45",
    "LJ55": "Learjet 55",
    "LJ60": "Learjet 60",
    "LJ75": "Learjet 75",

    # ── Bell ──────────────────────────────────────────────────────────────────
    "B06": "Bell 206",
    "B06T": "Bell 206 Twin",
    "B212": "Bell 212",
    "B412": "Bell 412",
    "B429": "Bell 429",

    # ── Fokker ────────────────────────────────────────────────────────────────
    "F100": "Fokker 100",
    "F27": "Fokker F27",
    "F28": "Fokker F28",
    "F50": "Fokker 50",
    "F70": "Fokker 70",

    # ── Gulfstream ────────────────────────────────────────────────────────────
    "GLF2": "Gulfstream II",
    "GLF3": "Gulfstream G-III",
    "GLF4": "Gulfstream IV",
    "GLF5": "Gulfstream V",
    "GLF6": "Gulfstream G650",

    # ── Leonardo ──────────────────────────────────────────────────────────────
    "A109": "Leonardo AW109",
    "A139": "Leonardo AW139",
    "A169": "Leonardo AW169",
    "A189": "Leonardo AW189",
    "EH10": "Leonardo AW101 Merlin",

    # ── De Havilland Canada ───────────────────────────────────────────────────
    "DHC2": "De Havilland Canada DHC-2 Beaver",
    "DHC3": "De Havilland Canada DHC-3 Otter",
    "DHC6": "De Havilland Canada Twin Otter",
    "DHC7": "De Havilland Canada DHC-7 Dash 7",

    # ── Diamond ───────────────────────────────────────────────────────────────
    "DA40": "Diamond DA40",
    "DA42": "Diamond DA42",
    "DA62": "Diamond DA62",
    "DV20": "Diamond DV20 Katana",

    # ── Cirrus ────────────────────────────────────────────────────────────────
    "SF50": "Cirrus SF50",
    "SR20": "Cirrus SR20",
    "SR22": "Cirrus SR22",

    # ── Comac ─────────────────────────────────────────────────────────────────
    "ARJ": "Comac ARJ21",
    "ARJ2": "Comac ARJ21",
    "C919": "Comac C919",

    # ── Daher ─────────────────────────────────────────────────────────────────
    "TBM7": "Daher TBM 700",
    "TBM8": "Daher TBM 850",
    "TBM9": "Daher TBM 900",

    # ── Ilyushin ──────────────────────────────────────────────────────────────
    "IL62": "Ilyushin IL-62",
    "IL76": "Ilyushin IL-76",
    "IL96": "Ilyushin IL-96",

    # ── Robinson ──────────────────────────────────────────────────────────────
    "R22": "Robinson R22",
    "R44": "Robinson R44",
    "R66": "Robinson R66",

    # ── Sikorsky ──────────────────────────────────────────────────────────────
    "S61": "Sikorsky S-61",
    "S76": "Sikorsky S-76",
    "S92": "Sikorsky S-92",

    # ── Tupolev ───────────────────────────────────────────────────────────────
    "TU16": "Tupolev 16",
    "TU54": "Tupolev 154",
    "TU95": "Tupolev 95",

    # ── Lockheed ──────────────────────────────────────────────────────────────
    "L101": "Lockheed L-1011",
    "L188": "Lockheed L-188 Electra",

    # ── Pilatus ───────────────────────────────────────────────────────────────
    "PC12": "Pilatus PC-12",
    "PC24": "Pilatus PC-24",

    # ── Saab ──────────────────────────────────────────────────────────────────
    "SB20": "Saab 2000",
    "SF34": "Saab 340",

    # ── Dornier ───────────────────────────────────────────────────────────────
    "J328": "Dornier Do 328 Jet",

    # ── Harbin ────────────────────────────────────────────────────────────────
    "Y12": "Harbin Y-12",

    # ── Honda ─────────────────────────────────────────────────────────────────
    "HDJT": "Honda HondaJet",

    # ── Piaggio ───────────────────────────────────────────────────────────────
    "P180": "Piaggio P.180 Avanti",

    # ── Sud Aviation ──────────────────────────────────────────────────────────
    "S210": "Sud Aviation Caravelle",

    # ── Sukhoi ────────────────────────────────────────────────────────────────
    "SU95": "Sukhoi Superjet 100",
}


def lookup_type(code: str) -> str:
    """Return the human-readable "Manufacturer Model" name for an ICAO type designator, or ""."""
    if not code:
        return ""
    return AIRCRAFT_TYPES.get(code.strip().upper(), "")
