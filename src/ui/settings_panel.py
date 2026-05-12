"""Settings panel: location, radius, OpenSky credentials, display options."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QLineEdit,
    QPushButton, QGroupBox, QSpinBox, QFormLayout, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal


class SettingsPanel(QWidget):
    location_requested = pyqtSignal()
    radius_changed = pyqtSignal(float)
    refresh_changed = pyqtSignal(int)
    cycle_changed = pyqtSignal(int)
    credentials_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(260)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Location ──────────────────────────────────────────
        loc_box = QGroupBox("Location")
        loc_form = QVBoxLayout(loc_box)

        self.lbl_location = QLabel("Detecting…")
        self.lbl_location.setWordWrap(True)
        loc_form.addWidget(self.lbl_location)

        row = QHBoxLayout()
        self.txt_lat = QLineEdit()
        self.txt_lat.setPlaceholderText("Lat")
        self.txt_lat.setMaximumWidth(80)
        self.txt_lon = QLineEdit()
        self.txt_lon.setPlaceholderText("Lon")
        self.txt_lon.setMaximumWidth(80)
        btn_set = QPushButton("Set")
        btn_set.setMaximumWidth(45)
        btn_set.clicked.connect(self._manual_location)
        row.addWidget(self.txt_lat)
        row.addWidget(self.txt_lon)
        row.addWidget(btn_set)
        loc_form.addLayout(row)

        btn_auto = QPushButton("Auto-detect location")
        btn_auto.clicked.connect(self.location_requested.emit)
        loc_form.addWidget(btn_auto)

        layout.addWidget(loc_box)

        # ── Radius ────────────────────────────────────────────
        rad_box = QGroupBox("Search Radius")
        rad_layout = QVBoxLayout(rad_box)

        self.lbl_radius = QLabel("50 km")
        self.lbl_radius.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rad_layout.addWidget(self.lbl_radius)

        self.slider_radius = QSlider(Qt.Orientation.Horizontal)
        self.slider_radius.setMinimum(1)
        self.slider_radius.setMaximum(200)
        self.slider_radius.setValue(50)
        self.slider_radius.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_radius.setTickInterval(25)
        self.slider_radius.valueChanged.connect(self._on_radius)
        rad_layout.addWidget(self.slider_radius)

        labels_row = QHBoxLayout()
        labels_row.addWidget(QLabel("1 km"))
        labels_row.addStretch()
        labels_row.addWidget(QLabel("200 km"))
        rad_layout.addLayout(labels_row)

        layout.addWidget(rad_box)

        # ── Timing ────────────────────────────────────────────
        time_box = QGroupBox("Timing")
        time_form = QFormLayout(time_box)

        self.spin_refresh = QSpinBox()
        self.spin_refresh.setRange(10, 300)
        self.spin_refresh.setValue(15)
        self.spin_refresh.setSuffix(" s")
        self.spin_refresh.valueChanged.connect(self.refresh_changed.emit)
        time_form.addRow("Fetch every:", self.spin_refresh)

        self.spin_cycle = QSpinBox()
        self.spin_cycle.setRange(2, 60)
        self.spin_cycle.setValue(5)
        self.spin_cycle.setSuffix(" s")
        self.spin_cycle.valueChanged.connect(self.cycle_changed.emit)
        time_form.addRow("Cycle every:", self.spin_cycle)

        layout.addWidget(time_box)

        # ── OpenSky credentials (optional) ────────────────────
        cred_box = QGroupBox("OpenSky Credentials (optional)")
        cred_form = QFormLayout(cred_box)
        cred_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Username")
        cred_form.addRow("User:", self.txt_user)

        self.txt_pass = QLineEdit()
        self.txt_pass.setPlaceholderText("Password")
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        cred_form.addRow("Pass:", self.txt_pass)

        btn_cred = QPushButton("Apply")
        btn_cred.clicked.connect(
            lambda: self.credentials_changed.emit(
                self.txt_user.text(), self.txt_pass.text()
            )
        )
        cred_form.addRow("", btn_cred)

        layout.addWidget(cred_box)

        hint = QLabel(
            "Tip: units and display formats\n"
            "are set per element in the\n"
            "Layout Editor tab."
        )
        hint.setStyleSheet("color: #888; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

    def _on_radius(self, val: int):
        self.lbl_radius.setText(f"{val} km")
        self.radius_changed.emit(float(val))

    def _manual_location(self):
        try:
            lat = float(self.txt_lat.text())
            lon = float(self.txt_lon.text())
            from src.core.models import Location
            loc = Location(lat, lon, "Manual", "")
            self._apply_location(loc)
        except ValueError:
            pass

    def _apply_location(self, loc):
        from src.core.models import Location
        self.lbl_location.setText(
            f"{loc.city}, {loc.country}\n"
            f"({loc.lat:.4f}, {loc.lon:.4f})"
        )

    def set_location(self, loc):
        self.lbl_location.setText(
            f"{loc.city}, {loc.country}\n({loc.lat:.4f}, {loc.lon:.4f})"
        )
        self.txt_lat.setText(f"{loc.lat:.5f}")
        self.txt_lon.setText(f"{loc.lon:.5f}")

    @property
    def radius(self) -> float:
        return float(self.slider_radius.value())

    @property
    def refresh_interval(self) -> int:
        return self.spin_refresh.value()

    @property
    def cycle_interval(self) -> int:
        return self.spin_cycle.value()

    @property
    def credentials(self):
        return (self.txt_user.text(), self.txt_pass.text())
