"""Settings panel: location, radius, OpenSky credentials, display options."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QLineEdit,
    QPushButton, QGroupBox, QSpinBox, QFormLayout, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.core.displays import DISPLAY_SIZES, DEFAULT_SIZE_KEY, CUSTOM_KEY


CUSTOM_ITEM = ("__custom__", "Custom size…")

# ADS-B emitter category codes worth letting the user hide. Category "C*"
# (ground vehicles) is already dropped unconditionally upstream in
# adsb_lol.py — these are the ones that are valid airborne traffic but not
# necessarily wanted on a flight-tracker display (gliders, balloons, etc).
CATEGORY_FILTERS = [
    ("B1", "Gliders / sailplanes"),
    ("B2", "Balloons / airships"),
    ("B3", "Parachutists / skydivers"),
    ("B4", "Ultralights / paragliders"),
    ("B5", "Other (reserved category)"),
]


class CustomSizeDialog(QDialog):
    """Ask for LED grid dimensions and an optional target window size."""

    def __init__(self, parent=None, grid_w=80, grid_h=40, win_w=0, win_h=0):
        super().__init__(parent)
        self.setWindowTitle("Custom Display Size")
        self.setModal(True)

        root = QVBoxLayout(self)

        # LED grid
        grid_box = QGroupBox("LED grid (pixels per side)")
        grid_form = QFormLayout(grid_box)
        self.spin_gw = QSpinBox(); self.spin_gw.setRange(8, 1024); self.spin_gw.setValue(grid_w)
        self.spin_gh = QSpinBox(); self.spin_gh.setRange(8, 1024); self.spin_gh.setValue(grid_h)
        grid_form.addRow("Width:",  self.spin_gw)
        grid_form.addRow("Height:", self.spin_gh)
        root.addWidget(grid_box)

        # Window hint
        win_box = QGroupBox("Target window size (screen pixels, 0 = auto)")
        win_form = QFormLayout(win_box)
        self.spin_ww = QSpinBox(); self.spin_ww.setRange(0, 7680); self.spin_ww.setValue(win_w)
        self.spin_wh = QSpinBox(); self.spin_wh.setRange(0, 4320); self.spin_wh.setValue(win_h)
        win_form.addRow("Width:",  self.spin_ww)
        win_form.addRow("Height:", self.spin_wh)
        root.addWidget(win_box)

        hint = QLabel(
            "LED cells are auto-sized to fit the window evenly.\n"
            "Cells stay square — extra space goes on the longer axis."
        )
        hint.setStyleSheet("color: #888; font-style: italic;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> tuple[int, int, int, int]:
        return (
            self.spin_gw.value(), self.spin_gh.value(),
            self.spin_ww.value(), self.spin_wh.value(),
        )


class SettingsPanel(QWidget):
    location_requested = pyqtSignal()
    geocode_requested = pyqtSignal(str)        # free-form address query
    radius_changed = pyqtSignal(float)
    refresh_changed = pyqtSignal(int)
    cycle_changed = pyqtSignal(int)
    credentials_changed = pyqtSignal(str, str)
    display_size_changed = pyqtSignal(str)              # preset key
    custom_display_size_changed = pyqtSignal(int, int, int, int)  # gw,gh,ww,wh
    hidden_categories_changed = pyqtSignal(object)       # set[str] of hidden category codes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Display Size ──────────────────────────────────────
        disp_box = QGroupBox("Display Size")
        disp_layout = QVBoxLayout(disp_box)
        self.combo_display = QComboBox()
        for key, label, _w, _h in DISPLAY_SIZES:
            self.combo_display.addItem(label, key)
        self.combo_display.addItem(CUSTOM_ITEM[1], CUSTOM_ITEM[0])
        for i in range(self.combo_display.count()):
            if self.combo_display.itemData(i) == DEFAULT_SIZE_KEY:
                self.combo_display.setCurrentIndex(i)
                break
        self.combo_display.currentIndexChanged.connect(self._on_display_change)
        disp_layout.addWidget(self.combo_display)
        # Track last preset so we can revert on dialog cancel
        self._last_display_idx = self.combo_display.currentIndex()
        self._custom_grid = (80, 40)
        self._custom_win = (0, 0)
        layout.addWidget(disp_box)

        # ── Location ──────────────────────────────────────────
        loc_box = QGroupBox("Location")
        loc_form = QVBoxLayout(loc_box)

        self.lbl_location = QLabel("Detecting…")
        self.lbl_location.setWordWrap(True)
        loc_form.addWidget(self.lbl_location)

        # Address search (street + city, like Google Maps)
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Street, city or place…")
        self.txt_search.returnPressed.connect(self._search_address)
        btn_search = QPushButton("Find")
        btn_search.setMaximumWidth(45)
        btn_search.clicked.connect(self._search_address)
        search_row.addWidget(self.txt_search)
        search_row.addWidget(btn_search)
        loc_form.addLayout(search_row)

        # Lat/lon row (2 decimal places)
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

        # ── Aircraft Filter ───────────────────────────────────
        filt_box = QGroupBox("Hide Aircraft Categories")
        filt_layout = QVBoxLayout(filt_box)
        self._cat_checks: dict[str, QCheckBox] = {}
        for code, label in CATEGORY_FILTERS:
            cb = QCheckBox(f"{label} ({code})")
            cb.stateChanged.connect(self._on_category_toggle)
            filt_layout.addWidget(cb)
            self._cat_checks[code] = cb
        layout.addWidget(filt_box)

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

    def _on_category_toggle(self, _state: int):
        self.hidden_categories_changed.emit(self.hidden_categories)

    def _on_radius(self, val: int):
        self.lbl_radius.setText(f"{val} km")
        self.radius_changed.emit(float(val))

    def _on_display_change(self, _idx: int):
        key = self.combo_display.currentData()
        if key == CUSTOM_ITEM[0]:
            gw, gh = self._custom_grid
            ww, wh = self._custom_win
            dlg = CustomSizeDialog(self, grid_w=gw, grid_h=gh, win_w=ww, win_h=wh)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                gw, gh, ww, wh = dlg.values()
                self._custom_grid = (gw, gh)
                self._custom_win = (ww, wh)
                self._last_display_idx = self.combo_display.currentIndex()
                self.custom_display_size_changed.emit(gw, gh, ww, wh)
            else:
                # Cancelled — revert dropdown
                self.combo_display.blockSignals(True)
                self.combo_display.setCurrentIndex(self._last_display_idx)
                self.combo_display.blockSignals(False)
            return
        if key:
            self._last_display_idx = self.combo_display.currentIndex()
            self.display_size_changed.emit(key)

    def _manual_location(self):
        try:
            lat = float(self.txt_lat.text())
            lon = float(self.txt_lon.text())
            from src.core.models import Location
            loc = Location(lat, lon, "Manual", "")
            self._apply_location(loc)
        except ValueError:
            pass

    def _search_address(self):
        query = self.txt_search.text().strip()
        if query:
            self.geocode_requested.emit(query)

    def _apply_location(self, loc):
        self.lbl_location.setText(
            f"{loc.city}, {loc.country}\n"
            f"({loc.lat:.2f}, {loc.lon:.2f})"
        )

    def set_location(self, loc):
        self.lbl_location.setText(
            f"{loc.city}, {loc.country}\n({loc.lat:.2f}, {loc.lon:.2f})"
        )
        self.txt_lat.setText(f"{loc.lat:.2f}")
        self.txt_lon.setText(f"{loc.lon:.2f}")

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

    @property
    def hidden_categories(self) -> set[str]:
        return {code for code, cb in self._cat_checks.items() if cb.isChecked()}

    # ── Preset state helpers ──────────────────────────────────────────────────

    def get_state(self) -> dict:
        """Return all UI-controlled settings as a dict (for preset serialisation)."""
        return {
            "display_key":    self.combo_display.currentData(),
            "custom_grid":    list(self._custom_grid),
            "custom_win":     list(self._custom_win),
            "radius":         self.slider_radius.value(),
            "fetch_interval": self.spin_refresh.value(),
            "cycle_interval": self.spin_cycle.value(),
            "opensky_user":   self.txt_user.text(),
            "opensky_pass":   self.txt_pass.text(),
            "hidden_categories": sorted(self.hidden_categories),
        }

    def restore_state(self, data: dict) -> None:
        """Restore settings from a preset dict without emitting any signals."""
        key = data.get("display_key", DEFAULT_SIZE_KEY)
        cg  = data.get("custom_grid", [80, 40])
        cw  = data.get("custom_win",  [0,  0])
        self._custom_grid = tuple(cg)
        self._custom_win  = tuple(cw)

        self.combo_display.blockSignals(True)
        matched = False
        for i in range(self.combo_display.count()):
            if self.combo_display.itemData(i) == key:
                self.combo_display.setCurrentIndex(i)
                self._last_display_idx = i
                matched = True
                break
        if not matched:
            # Fall back to the custom-size entry
            for i in range(self.combo_display.count()):
                if self.combo_display.itemData(i) == CUSTOM_ITEM[0]:
                    self.combo_display.setCurrentIndex(i)
                    self._last_display_idx = i
                    break
        self.combo_display.blockSignals(False)

        radius = int(data.get("radius", 50))
        self.slider_radius.blockSignals(True)
        self.slider_radius.setValue(radius)
        self.lbl_radius.setText(f"{radius} km")
        self.slider_radius.blockSignals(False)

        self.spin_refresh.blockSignals(True)
        self.spin_refresh.setValue(int(data.get("fetch_interval", 15)))
        self.spin_refresh.blockSignals(False)

        self.spin_cycle.blockSignals(True)
        self.spin_cycle.setValue(int(data.get("cycle_interval", 5)))
        self.spin_cycle.blockSignals(False)

        self.txt_user.setText(data.get("opensky_user", ""))
        self.txt_pass.setText(data.get("opensky_pass", ""))

        hidden = set(data.get("hidden_categories", []))
        for code, cb in self._cat_checks.items():
            cb.blockSignals(True)
            cb.setChecked(code in hidden)
            cb.blockSignals(False)
