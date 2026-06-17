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
    """Minimal palette so Qt's internal fallbacks use light colours."""
    app.setStyle("Fusion")
    p = QPalette()
    white = QColor(255, 255, 255)
    text  = QColor(31, 31, 31)
    p.setColor(QPalette.ColorRole.Window,          white)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            white)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(245, 245, 245))
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          QColor(245, 245, 245))
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.Highlight,       QColor(56,  120, 208))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(250, 250, 250))
    p.setColor(QPalette.ColorRole.ToolTipText,     text)
    p.setColor(QPalette.ColorRole.Link,            QColor(31,  74, 138))
    p.setColor(QPalette.ColorRole.Mid,             QColor(196, 196, 196))
    p.setColor(QPalette.ColorRole.Dark,            QColor(216, 216, 216))
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
