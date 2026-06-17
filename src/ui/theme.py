"""Application-wide dark theme stylesheet and style helpers."""
from __future__ import annotations

# Accent / surface tokens — light theme
ACCENT      = "#3878d0"
ACCENT_DIM  = "#5b9bf2"
ACCENT_GLOW = "#1f4a8a"
BG          = "#ffffff"
SURFACE     = "#f5f5f5"
SURFACE2    = "#eaeaea"
BORDER      = "#d8d8d8"
BORDER2     = "#c4c4c4"
TEXT        = "#1f1f1f"
TEXT_DIM    = "#666666"
TEXT_MUTED  = "#999999"
DANGER      = "#c0392b"
DANGER_DIM  = "#ec8472"


STYLESHEET = f"""
/* ── Reset ─────────────────────────────────────────────────────── */
* {{
    outline: none;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QWidget {{
    background: transparent;
    color: {TEXT};
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
}}

/* ── GroupBox — card style ──────────────────────────────────────── */
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 20px;
    padding: 14px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 1px;
    color: {TEXT_MUTED};
    font-size: 9px;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: {BG};
    padding: 1px 5px;
    border-radius: 3px;
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {{
    background: {SURFACE2};
    color: {TEXT};
    border: 1px solid {BORDER2};
    border-radius: 7px;
    padding: 5px 16px;
    min-height: 26px;
    font-size: 12px;
}}
QPushButton:hover {{
    background: #f0f0f0;
    border-color: #a8a8a8;
    color: #000000;
}}
QPushButton:pressed {{
    background: {SURFACE2};
    border-color: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border-color: #e4e4e4;
    background: {SURFACE};
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT_GLOW};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: #2c66c0;
    border-color: {ACCENT_GLOW};
}}
QPushButton[role="primary"]:pressed {{
    background: {ACCENT_GLOW};
}}
QPushButton[role="danger"] {{
    background: #ffe2dc;
    border-color: {DANGER};
    color: {DANGER};
}}
QPushButton[role="danger"]:hover {{
    background: {DANGER_DIM};
    color: #ffffff;
    border-color: {DANGER};
}}

/* ── Inputs ─────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {{
    background: #ffffff;
    border: 1px solid {BORDER2};
    border-radius: 7px;
    padding: 4px 10px;
    color: {TEXT};
    min-height: 26px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus {{
    border-color: {ACCENT};
    background: #fbfbfb;
}}
QLineEdit[readOnly="true"] {{
    color: {TEXT_DIM};
    background: {SURFACE};
}}
QTextEdit {{
    padding: 6px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0; height: 0;
    border: none;
}}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{
    background: #ffffff;
    border: 1px solid {BORDER2};
    border-radius: 7px;
    padding: 4px 10px;
    color: {TEXT};
    min-height: 26px;
}}
QComboBox:hover {{ border-color: #464646; }}
QComboBox:focus  {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left:   5px solid transparent;
    border-right:  5px solid transparent;
    border-top:    5px solid {TEXT_DIM};
    margin-right:  8px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {BORDER2};
    border-radius: 7px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    color: {TEXT};
    padding: 3px;
}}

/* ── Slider ─────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: #d8d8d8;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    border: none;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_GLOW}; }}
QSlider::sub-page:horizontal {{
    background: {ACCENT_DIM};
    border-radius: 2px;
}}

/* ── Tabs ───────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background: {BG};
    border: none;
    border-top: 1px solid {BORDER};
}}
QTabBar {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 10px 22px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    margin: 0;
}}
QTabBar::tab:selected {{
    color: {ACCENT_GLOW};
    border-bottom: 2px solid {ACCENT};
    background: transparent;
}}
QTabBar::tab:hover:!selected {{
    color: #444444;
    background: rgba(0,0,0,0.03);
}}

/* ── Scrollbars ─────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c4c4c4;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #a8a8a8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c4c4c4;
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: #a8a8a8; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Lists ──────────────────────────────────────────────────────── */
QListWidget {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    padding: 3px;
    outline: none;
}}
QListWidget::item {{
    padding: 5px 10px;
    border-radius: 5px;
}}
QListWidget::item:selected {{
    background: {ACCENT};
    color: #ffffff;
}}
QListWidget::item:hover:!selected {{
    background: {SURFACE2};
}}

/* ── CheckBox ───────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER2};
    border-radius: 5px;
    background: #ffffff;
}}
QCheckBox::indicator:hover {{ border-color: #888888; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT_GLOW};
}}

/* ── Status bar ─────────────────────────────────────────────────── */
QStatusBar {{
    background: {SURFACE};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
QStatusBar QLabel {{
    color: {TEXT_DIM};
    padding: 0 3px;
}}

/* ── Tooltips ───────────────────────────────────────────────────── */
QToolTip {{
    background: #fafafa;
    color: #1f1f1f;
    border: 1px solid #c4c4c4;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 11px;
}}

/* ── Misc ───────────────────────────────────────────────────────── */
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
    height: 1px;
}}
"""


def accent_button(btn) -> None:
    """Mark a QPushButton as the primary accent colour."""
    btn.setProperty("role", "primary")
    btn.style().unpolish(btn)
    btn.style().polish(btn)


def danger_button(btn) -> None:
    btn.setProperty("role", "danger")
    btn.style().unpolish(btn)
    btn.style().polish(btn)
