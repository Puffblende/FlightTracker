"""ESP32 LED matrix device discovery — WiFi (UDP broadcast) and Bluetooth LE.

WiFi protocol
-------------
The app broadcasts b"FTLD_DISCOVER" on UDP port 4210.
The ESP32 should reply from the same port with a JSON payload:
    {"name": "FlightMatrix", "width": 32, "height": 8, "port": 4211}

BLE protocol
------------
Scan for devices whose advertised name contains "flighttracker", "flightmatrix",
or "ledmatrix" (case-insensitive).  Requires the optional `bleak` package:
    pip install bleak
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
from dataclasses import dataclass
from typing import Callable

DISCOVER_PORT = 4210
DATA_PORT     = 4211
DISCOVER_MSG  = b"FTLD_DISCOVER"

# BLE keywords that identify a compatible device
_BLE_KEYWORDS = ("flighttracker", "flightmatrix", "ledmatrix", "flightled")


@dataclass
class MatrixDevice:
    name:      str
    transport: str   # "wifi" | "ble"
    address:   str   # IP address for WiFi, MAC/UUID for BLE
    port:      int = DATA_PORT
    width:     int = 0
    height:    int = 0

    def label(self) -> str:
        if self.transport == "wifi":
            dims = f"  {self.width}×{self.height}" if self.width else ""
            return f"{self.name}  ({self.address}:{self.port}){dims}  [WiFi]"
        return f"{self.name}  ({self.address})  [Bluetooth]"


# ── WiFi discovery ────────────────────────────────────────────────────────────

def scan_wifi(timeout: float = 2.0,
              on_found: Callable[[MatrixDevice], None] | None = None,
              ) -> list[MatrixDevice]:
    """
    Broadcast a discovery message and collect responses.
    Blocks for up to `timeout` seconds; call from a daemon thread.
    """
    found: list[MatrixDevice] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(DISCOVER_MSG, ("255.255.255.255", DISCOVER_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(512)
                try:
                    info = json.loads(data.decode())
                except Exception:
                    info = {}
                dev = MatrixDevice(
                    name=info.get("name", f"ESP32@{addr[0]}"),
                    transport="wifi",
                    address=addr[0],
                    port=int(info.get("port", DATA_PORT)),
                    width=int(info.get("width", 0)),
                    height=int(info.get("height", 0)),
                )
                found.append(dev)
                if on_found:
                    on_found(dev)
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return found


# ── Bluetooth LE discovery ────────────────────────────────────────────────────

async def _ble_scan_async(timeout: float) -> list[MatrixDevice]:
    from bleak import BleakScanner
    found = []
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        name = (d.name or "").lower()
        if any(kw in name for kw in _BLE_KEYWORDS):
            found.append(MatrixDevice(
                name=d.name or d.address,
                transport="ble",
                address=d.address,
            ))
    return found


def scan_ble(timeout: float = 5.0,
             on_done: Callable[[list[MatrixDevice], str], None] | None = None,
             ) -> None:
    """
    Start a BLE scan in a daemon thread.
    Results are delivered via on_done(devices, error_string).
    error_string is empty on success.
    """
    def _run():
        try:
            loop = asyncio.new_event_loop()
            devices = loop.run_until_complete(_ble_scan_async(timeout))
            loop.close()
            if on_done:
                on_done(devices, "")
        except ImportError:
            if on_done:
                on_done([], "bleak not installed — run:  pip install bleak")
        except Exception as exc:
            if on_done:
                on_done([], str(exc))

    threading.Thread(target=_run, daemon=True).start()
