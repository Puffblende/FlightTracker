"""Borderless always-on-top overlay window showing the LED panel."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QPoint

from src.ui.led_widget import LEDWidget


class OverlayWindow(QWidget):
    """Frameless, always-on-top desktop overlay.

    Drag anywhere on the window to reposition it.
    The ✕ button hides (not destroys) the window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FlightTracker Overlay")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet("QWidget { background: #111; }")
        self._drag_start: QPoint | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # Thin drag bar with close button
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(0)
        drag_hint = QWidget()
        drag_hint.setFixedHeight(12)
        drag_hint.setToolTip("Drag to move")
        drag_hint.setStyleSheet("background: #252525;")
        bar.addWidget(drag_hint, 1)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(16, 12)
        btn_close.setToolTip("Hide overlay")
        btn_close.setStyleSheet(
            "QPushButton { background:#8b2020; color:#fff; border:none; font-size:7px; }"
            "QPushButton:hover { background:#c0392b; }"
        )
        btn_close.clicked.connect(self.hide)
        bar.addWidget(btn_close)
        root.addLayout(bar)

        self._led = LEDWidget()
        root.addWidget(self._led)
        self.adjustSize()

    # ── public ────────────────────────────────────────────────────────────────

    def set_buffer(self, buf) -> None:
        self._led.set_buffer(buf)

    def apply_display_size(self) -> None:
        self._led.apply_display_size()
        self.adjustSize()

    # ── drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start is not None:
            self.move(event.globalPosition().toPoint() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)
