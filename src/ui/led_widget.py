"""LED matrix simulation widget.
Renders an 80×40 pixel buffer as a realistic LED panel."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QImage, QPen, QBrush


class LEDWidget(QWidget):
    LED_SIZE = 8    # pixels per LED cell
    GAP = 1         # gap between LEDs
    BEZEL = 6       # border around the panel

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buf: list[list[tuple]] = [[(0, 0, 0)] * 80 for _ in range(40)]
        cell = self.LED_SIZE + self.GAP
        w = 80 * cell + self.GAP + self.BEZEL * 2
        h = 40 * cell + self.GAP + self.BEZEL * 2
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_buffer(self, buf: list[list[tuple]]) -> None:
        self._buf = buf
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        cell = self.LED_SIZE + self.GAP
        bz = self.BEZEL

        # Panel background (bezel + gap color)
        painter.fillRect(self.rect(), QColor(8, 8, 8))

        for py in range(40):
            for px in range(80):
                r, g, b = self._buf[py][px]
                sx = bz + self.GAP + px * cell
                sy = bz + self.GAP + py * cell

                if r > 0 or g > 0 or b > 0:
                    # Lit LED: slightly rounded look via a bright center
                    painter.fillRect(sx, sy, self.LED_SIZE, self.LED_SIZE,
                                     QColor(r, g, b))
                    # Highlight (top-left brighten)
                    hr = min(255, r + 60)
                    hg = min(255, g + 60)
                    hb = min(255, b + 60)
                    painter.fillRect(sx, sy, 2, 2, QColor(hr, hg, hb))
                else:
                    # Off LED: dark gray square
                    painter.fillRect(sx, sy, self.LED_SIZE, self.LED_SIZE,
                                     QColor(18, 18, 18))

        painter.end()
