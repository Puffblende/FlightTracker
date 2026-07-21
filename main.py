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
    bg = QColor(15, 17, 21)
    surface = QColor(22, 26, 34)
    text = QColor(243, 246, 251)
    muted = QColor(154, 164, 178)
    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            surface)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(31, 36, 48))
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          surface)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.Highlight,       QColor(79, 156, 255))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(243, 246, 251))
    p.setColor(QPalette.ColorRole.ToolTipBase,     surface)
    p.setColor(QPalette.ColorRole.ToolTipText,     text)
    p.setColor(QPalette.ColorRole.Link,            QColor(119, 180, 255))
    p.setColor(QPalette.ColorRole.Mid,             QColor(57, 66, 83))
    p.setColor(QPalette.ColorRole.Dark,            QColor(43, 49, 64))
    p.setColor(QPalette.ColorRole.Shadow,          QColor(8, 10, 14))
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
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
