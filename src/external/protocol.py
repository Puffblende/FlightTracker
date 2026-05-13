"""Frame transmission protocol for ESP32 LED matrix displays.

UDP packet layout
-----------------
Offset  Size  Content
0       4     Magic bytes: b"FTLD"
4       2     Grid width  (big-endian uint16)
6       2     Grid height (big-endian uint16)
8       W*H*3 RGB pixel data, row-major, 1 byte per channel

Minimal ESP32 Arduino sketch
-----------------------------
    #include <WiFiUdp.h>
    #include <FastLED.h>

    #define NUM_LEDS  (WIDTH * HEIGHT)
    CRGB leds[NUM_LEDS];
    WiFiUDP udp;
    uint8_t buf[8 + NUM_LEDS * 3];

    void loop() {
        int n = udp.parsePacket();
        if (n >= 8 && memcmp(buf, "FTLD", 4) == 0) {
            udp.read(buf, sizeof(buf));
            uint16_t w = (buf[4]<<8)|buf[5], h = (buf[6]<<8)|buf[7];
            for (int i = 0; i < w*h && i < NUM_LEDS; i++)
                leds[i] = CRGB(buf[8+i*3], buf[8+i*3+1], buf[8+i*3+2]);
            FastLED.show();
        }
    }

Discovery response (JSON, sent from port 4210)
-----------------------------------------------
    {"name":"FlightMatrix","width":32,"height":8,"port":4211}
"""
from __future__ import annotations

import socket
import struct

MAGIC    = b"FTLD"
UDP_PORT = 4211


def make_packet(buf: list) -> bytes:
    """Pack a pixel buffer (list of rows of (R,G,B) tuples) into a UDP frame."""
    H = len(buf)
    W = len(buf[0]) if H else 0
    header = MAGIC + struct.pack(">HH", W, H)
    raw = bytearray(W * H * 3)
    idx = 0
    for row in buf:
        for r, g, b in row:
            raw[idx]     = r
            raw[idx + 1] = g
            raw[idx + 2] = b
            idx += 3
    return header + bytes(raw)


class UDPSender:
    """Stateless UDP sender — no handshake, fire-and-forget."""

    def __init__(self, host: str, port: int = UDP_PORT):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        self._sock = sock

    def send(self, buf: list) -> int:
        """Send one frame. Returns bytes sent, or 0 on error."""
        if self._sock is None:
            return 0
        pkt = make_packet(buf)
        try:
            self._sock.sendto(pkt, (self.host, self.port))
            return len(pkt)
        except OSError:
            return 0

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    @property
    def is_open(self) -> bool:
        return self._sock is not None
