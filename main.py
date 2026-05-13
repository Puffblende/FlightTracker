#!/usr/bin/env python3
"""FlightTracker — real-time ADS-B flight display for an 80×40 LED matrix."""
import sys
import os

# Ensure src/ is importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows: must set DPI awareness BEFORE QApplication is created
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from src.ui.main_window import MainWindow
from src.ui.theme import STYLESHEET


def _base_palette(app: QApplication) -> None:
    """Minimal palette so Qt's internal fallbacks use dark colours."""
    app.setStyle("Fusion")
    p = QPalette()
    dark = QColor(13, 13, 13)
    p.setColor(QPalette.ColorRole.Window,          dark)
    p.setColor(QPalette.ColorRole.WindowText,      QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Base,            QColor(17,  17,  17))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(24,  24,  24))
    p.setColor(QPalette.ColorRole.Text,            QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Button,          QColor(30,  30,  30))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(56,  120, 208))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(28,  32,  48))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(200, 204, 220))
    p.setColor(QPalette.ColorRole.Link,            QColor(72,  138, 224))
    p.setColor(QPalette.ColorRole.Mid,             QColor(42,  42,  42))
    p.setColor(QPalette.ColorRole.Dark,            QColor(22,  22,  22))
    app.setPalette(p)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("FlightTracker")
    _base_palette(app)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
