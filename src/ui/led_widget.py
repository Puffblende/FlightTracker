"""LED matrix simulation widget.
Renders an arbitrary W×H pixel buffer as a realistic LED panel."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QSizePolicy, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor

from src.core.displays import get_display_size, get_window_hint

# Default on-screen budget if no explicit window hint is set
MAX_PANEL_W = 880
MAX_PANEL_H = 600


class LEDWidget(QWidget):
    BEZEL = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        W, H = get_display_size()
        self._W, self._H = W, H
        self._buf: list[list[tuple]] = [[(0, 0, 0)] * W for _ in range(H)]
        self._compute_cell()
        self._resize_to_panel()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Opacity effect for fade-in animation
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── public API ────────────────────────────────────────────────────────────

    def set_buffer(self, buf: list[list[tuple]], fade: bool = False) -> None:
        self._buf = buf
        new_h = len(buf)
        new_w = len(buf[0]) if new_h else 0
        if new_w != self._W or new_h != self._H:
            self._W, self._H = new_w, new_h
            self._compute_cell()
            self._resize_to_panel()
        if fade:
            self._fade.stop()
            self._fade.setStartValue(0.35)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.update()

    def apply_display_size(self) -> None:
        """Call after src.core.displays.set_display_size(...)."""
        W, H = get_display_size()
        self._W, self._H = W, H
        self._buf = [[(0, 0, 0)] * W for _ in range(H)]
        self._compute_cell()
        self._resize_to_panel()
        self.update()

    # ── internals ─────────────────────────────────────────────────────────────

    def _compute_cell(self):
        """Pick LED_SIZE and GAP so the panel fits the budget.
        If the user set a custom window hint, target that instead of defaults."""
        win_w, win_h = get_window_hint()
        budget_w = win_w if win_w else MAX_PANEL_W
        budget_h = win_h if win_h else MAX_PANEL_H

        candidates = [
            (32, 2), (24, 2), (20, 2), (16, 2), (12, 1),
            (10, 1), (8, 1), (7, 1), (6, 1), (5, 1), (4, 1),
            (4, 0), (3, 0), (2, 0), (1, 0),
        ]
        for size, gap in candidates:
            cell = size + gap
            pw = self._W * cell + gap + self.BEZEL * 2
            ph = self._H * cell + gap + self.BEZEL * 2
            if pw <= budget_w and ph <= budget_h:
                self.LED_SIZE = size
                self.GAP = gap
                return
        self.LED_SIZE = 1
        self.GAP = 0

    def _resize_to_panel(self):
        cell = self.LED_SIZE + self.GAP
        w = self._W * cell + self.GAP + self.BEZEL * 2
        h = self._H * cell + self.GAP + self.BEZEL * 2
        self.setFixedSize(w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        cell = self.LED_SIZE + self.GAP
        bz = self.BEZEL
        size = self.LED_SIZE
        gap = self.GAP

        painter.fillRect(self.rect(), QColor(8, 8, 8))

        highlight = size >= 5  # only worth drawing for medium+ pixels

        for py in range(self._H):
            row = self._buf[py]
            for px in range(self._W):
                r, g, b = row[px]
                sx = bz + gap + px * cell
                sy = bz + gap + py * cell

                if r > 0 or g > 0 or b > 0:
                    painter.fillRect(sx, sy, size, size, QColor(r, g, b))
                    if highlight:
                        hr = min(255, r + 60)
                        hg = min(255, g + 60)
                        hb = min(255, b + 60)
                        painter.fillRect(sx, sy, 2, 2, QColor(hr, hg, hb))
                else:
                    painter.fillRect(sx, sy, size, size, QColor(18, 18, 18))

        painter.end()
