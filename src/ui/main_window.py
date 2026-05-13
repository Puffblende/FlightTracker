"""Main application window."""
from __future__ import annotations
import threading
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QStatusBar, QGroupBox, QScrollArea, QComboBox, QInputDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor

from src.core.models import (
    Location, Flight, LayoutBlock, default_layout,
    fmt_altitude, fmt_speed, fmt_distance,
)
from src.core.renderer import render_frame
from src.core.displays import (
    set_display_size, set_custom_display, get_display_key,
    DEFAULT_SIZE_KEY, CUSTOM_KEY,
)
from src.core.presets import (
    list_presets, save_preset, load_preset,
    get_last_preset, set_last_preset,
    build_preset_data, layout_from_preset,
)
from src.ui.led_widget import LEDWidget
from src.ui.settings_panel import SettingsPanel, CUSTOM_ITEM
from src.ui.layout_editor import LayoutEditorWidget
from src.ui.overlay_window import OverlayWindow


class _Worker(QObject):
    """Signals for cross-thread communication."""
    location_ready  = pyqtSignal(object)    # Location
    flights_ready   = pyqtSignal(list)      # list[Flight]
    flights_enriched = pyqtSignal()
    error           = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(1100, 600)

        self._location      = None   # Location | None
        self._flights       = []     # list[Flight]
        self._current_idx   = 0
        self._layout        = default_layout()
        self._os_user       = ""
        self._os_pass       = ""
        self._speed_unit    = "mph"

        # Preset state
        self._current_preset: str | None = None
        self._dirty          = False
        self._loading_preset = False   # suppress dirty-marking during loads

        # Overlay
        self._overlay: OverlayWindow | None = None

        self._worker = _Worker()
        self._worker.location_ready.connect(self._on_location)
        self._worker.flights_ready.connect(self._on_flights)
        self._worker.flights_enriched.connect(self._on_enriched)
        self._worker.error.connect(self._on_error)

        self._build_ui()
        self._build_timers()
        self._refresh_preset_combo()
        self._update_title()

        # Load last used preset, or fall back to auto-detecting location
        last = get_last_preset()
        if last and load_preset(last) is not None:
            self._load_preset_by_name(last)
        else:
            self._fetch_location()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        self.setCentralWidget(container)

        vbox.addWidget(self._build_preset_bar())

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._build_display_tab(),  "Display")
        tabs.addTab(self._build_editor_tab(),   "Layout Editor")
        tabs.addTab(self._build_list_tab(),     "Flight List")
        vbox.addWidget(tabs)

        # Status bar
        self._sb_location = QLabel("Location: detecting…")
        self._sb_count    = QLabel("Flights: 0")
        self._sb_status   = QLabel("Ready")
        self.statusBar().addWidget(self._sb_location)
        self.statusBar().addWidget(QLabel(" | "))
        self.statusBar().addWidget(self._sb_count)
        self.statusBar().addWidget(QLabel(" | "))
        self.statusBar().addPermanentWidget(self._sb_status)

    def _build_preset_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("presetBar")
        # Scope the dark background to *this* bar by name, so it doesn't
        # cascade into the combobox's dropdown and break the selection
        # highlight on Windows.
        bar.setStyleSheet(
            "QWidget#presetBar { background: #1e1e1e; border-bottom: 1px solid #3a3a3a; }"
            "QWidget#presetBar > QLabel { background: transparent; }"
            "QComboBox QAbstractItemView { "
            "  background: #232323; color: #dcdcdc; "
            "  selection-background-color: #2a82da; "
            "  selection-color: #ffffff; "
            "  outline: 0; "
            "}"
        )
        bar.setFixedHeight(36)

        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(6)

        h.addWidget(QLabel("Preset:"))

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(170)
        self._preset_combo.setToolTip("Select a preset to load it")
        self._preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        h.addWidget(self._preset_combo)

        self._btn_save = QPushButton("Save")
        self._btn_save.setToolTip("Save changes to the current preset")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._save_preset)
        h.addWidget(self._btn_save)

        btn_save_as = QPushButton("Save As…")
        btn_save_as.setToolTip("Save as a new preset name")
        btn_save_as.clicked.connect(self._save_as_preset)
        h.addWidget(btn_save_as)

        btn_new = QPushButton("New")
        btn_new.setToolTip("Reset to defaults (unsaved)")
        btn_new.clicked.connect(self._new_preset)
        h.addWidget(btn_new)

        h.addStretch()

        self._btn_overlay = QPushButton("⧉  Launch Overlay")
        self._btn_overlay.setToolTip(
            "Open a borderless always-on-top window showing the LED panel"
        )
        self._btn_overlay.clicked.connect(self._toggle_overlay)
        h.addWidget(self._btn_overlay)

        return bar

    def _build_display_tab(self):
        page   = QWidget()
        root   = QHBoxLayout(page)
        root.setContentsMargins(10, 10, 10, 10)

        # Left: settings panel
        self._settings = SettingsPanel()
        self._settings.location_requested.connect(self._fetch_location)
        self._settings.radius_changed.connect(self._on_radius_changed)
        self._settings.refresh_changed.connect(self._on_refresh_changed)
        self._settings.cycle_changed.connect(self._on_cycle_changed)
        self._settings.credentials_changed.connect(self._on_credentials)
        self._settings.display_size_changed.connect(self._on_display_size_changed)
        self._settings.custom_display_size_changed.connect(self._on_custom_display_changed)

        # All settings changes mark dirty
        self._settings.radius_changed.connect(lambda _: self._mark_dirty())
        self._settings.refresh_changed.connect(lambda _: self._mark_dirty())
        self._settings.cycle_changed.connect(lambda _: self._mark_dirty())
        self._settings.credentials_changed.connect(lambda *_: self._mark_dirty())
        self._settings.display_size_changed.connect(lambda _: self._mark_dirty())
        self._settings.custom_display_size_changed.connect(lambda *_: self._mark_dirty())

        root.addWidget(self._settings)

        # Right: LED display + controls
        right = QVBoxLayout()
        right.setSpacing(8)

        header = QHBoxLayout()
        self.lbl_showing = QLabel("Showing: —")
        self.lbl_showing.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        header.addWidget(self.lbl_showing)
        header.addStretch()
        right.addLayout(header)

        self._led = LEDWidget()
        led_container = QHBoxLayout()
        led_container.addStretch()
        led_container.addWidget(self._led)
        led_container.addStretch()
        right.addLayout(led_container)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        btn_prev = QPushButton("◀ Prev")
        btn_prev.clicked.connect(self._prev_flight)
        btn_next = QPushButton("Next ▶")
        btn_next.clicked.connect(self._next_flight)
        self.btn_cycle = QPushButton("⏸ Pause Cycle")
        self.btn_cycle.setCheckable(True)
        self.btn_cycle.clicked.connect(self._toggle_cycle)
        btn_refresh = QPushButton("⟳ Fetch Now")
        btn_refresh.clicked.connect(self._fetch_flights_async)
        nav.addWidget(btn_prev)
        nav.addWidget(btn_next)
        nav.addWidget(self.btn_cycle)
        nav.addStretch()
        nav.addWidget(btn_refresh)
        right.addLayout(nav)

        self.lbl_info = QLabel("No data yet.")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.lbl_info)
        right.addStretch()

        root.addLayout(right)
        return page

    def _build_editor_tab(self):
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        info = QLabel(
            "Drag blocks to reposition them on the LED grid. "
            "Check/uncheck elements to show or hide them."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._editor = LayoutEditorWidget()
        self._editor.layout_changed.connect(self._on_layout_changed)
        layout.addWidget(self._editor)
        return page

    def _build_list_tab(self):
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(QLabel("Nearby aircraft — click to display on LED panel:"))

        self._flight_list = QListWidget()
        self._flight_list.setFont(QFont("Courier New", 9))
        self._flight_list.itemClicked.connect(self._on_list_click)
        layout.addWidget(self._flight_list)

        btn_refresh = QPushButton("Refresh List")
        btn_refresh.clicked.connect(self._fetch_flights_async)
        layout.addWidget(btn_refresh)
        return page

    # ── Timers ────────────────────────────────────────────────────────────────

    def _build_timers(self):
        self._fetch_timer = QTimer(self)
        self._fetch_timer.setInterval(15_000)
        self._fetch_timer.timeout.connect(self._fetch_flights_async)

        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(5_000)
        self._cycle_timer.timeout.connect(self._next_flight)
        self._cycle_timer.start()

    # ── Preset management ─────────────────────────────────────────────────────

    def _update_title(self):
        name  = self._current_preset or "(Unsaved)"
        dirty = " *" if self._dirty else ""
        self.setWindowTitle(f"FlightTracker — {name}{dirty}")

    def _mark_dirty(self):
        if self._loading_preset:
            return
        if not self._dirty:
            self._dirty = True
            self._btn_save.setEnabled(self._current_preset is not None)
            self._update_title()

    def _refresh_preset_combo(self):
        self._loading_preset = True
        try:
            self._preset_combo.blockSignals(True)
            self._preset_combo.clear()
            self._preset_combo.addItem("(Unsaved)", None)
            for name in list_presets():
                self._preset_combo.addItem(name, name)
            # Select current
            if self._current_preset:
                for i in range(self._preset_combo.count()):
                    if self._preset_combo.itemData(i) == self._current_preset:
                        self._preset_combo.setCurrentIndex(i)
                        break
            else:
                self._preset_combo.setCurrentIndex(0)
            self._preset_combo.blockSignals(False)
        finally:
            self._loading_preset = False

    def _on_preset_combo_changed(self, idx: int):
        if self._loading_preset:
            return
        name = self._preset_combo.currentData()
        if name is None or name == self._current_preset:
            return
        if self._dirty:
            if not self._confirm_discard():
                # Revert combo to current selection
                self._loading_preset = True
                self._preset_combo.blockSignals(True)
                for i in range(self._preset_combo.count()):
                    if self._preset_combo.itemData(i) == self._current_preset:
                        self._preset_combo.setCurrentIndex(i)
                        break
                else:
                    self._preset_combo.setCurrentIndex(0)
                self._preset_combo.blockSignals(False)
                self._loading_preset = False
                return
        self._load_preset_by_name(name)

    def _confirm_discard(self) -> bool:
        """Show Save/Discard/Cancel dialog. Returns True if caller may proceed."""
        name = self._current_preset or "Unsaved"
        msg  = QMessageBox(self)
        msg.setWindowTitle("Unsaved Changes")
        msg.setText(f"Preset \"{name}\" has unsaved changes.")
        msg.setInformativeText("Save before continuing?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Save)
        reply = msg.exec()
        if reply == QMessageBox.StandardButton.Save:
            return self._do_save()
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _do_save(self) -> bool:
        """Save to current preset name, or prompt for a name if unsaved. Returns True on success."""
        if self._current_preset:
            self._save_preset_impl(self._current_preset)
            return True
        return self._save_as_impl()

    def _save_preset_impl(self, name: str):
        st = self._settings.get_state()
        data = build_preset_data(
            name=name,
            layout=self._editor.get_layout(),
            display_key=st["display_key"],
            custom_grid=tuple(st["custom_grid"]),
            custom_win=tuple(st["custom_win"]),
            location=self._location,
            radius=st["radius"],
            fetch_interval=st["fetch_interval"],
            cycle_interval=st["cycle_interval"],
            opensky_user=st["opensky_user"],
            opensky_pass=st["opensky_pass"],
        )
        save_preset(name, data)
        self._current_preset = name
        self._dirty = False
        self._btn_save.setEnabled(False)
        self._refresh_preset_combo()
        self._update_title()

    def _save_as_impl(self) -> bool:
        text, ok = QInputDialog.getText(
            self, "Save Preset As", "Preset name:",
            text=self._current_preset or "",
        )
        if not ok or not text.strip():
            return False
        self._save_preset_impl(text.strip())
        return True

    def _save_preset(self):
        """Save button handler."""
        self._do_save()

    def _save_as_preset(self):
        """Save As… button handler."""
        self._save_as_impl()

    def _new_preset(self):
        """Reset everything to defaults."""
        if self._dirty and not self._confirm_discard():
            return
        self._loading_preset = True
        try:
            self._settings.restore_state({
                "display_key":    DEFAULT_SIZE_KEY,
                "custom_grid":    [80, 40],
                "custom_win":     [0, 0],
                "radius":         50,
                "fetch_interval": 15,
                "cycle_interval": 5,
                "opensky_user":   "",
                "opensky_pass":   "",
            })
            set_display_size(DEFAULT_SIZE_KEY)
            self._fetch_timer.setInterval(15_000)
            self._cycle_timer.setInterval(5_000)
            self._os_user = ""
            self._os_pass = ""
            self._layout = default_layout()
            self._editor.set_layout(self._layout)
            self._led.apply_display_size()
            self._editor.apply_display_size()
            self._layout = self._editor.get_layout()
            self._current_preset = None
            self._dirty = False
            self._btn_save.setEnabled(False)
            self._refresh_preset_combo()
            self._update_title()
            self._redraw_led()
        finally:
            self._loading_preset = False

    def _load_preset_by_name(self, name: str):
        data = load_preset(name)
        if data is None:
            return
        self._loading_preset = True
        try:
            disp = data.get("display", {})
            key  = disp.get("key", DEFAULT_SIZE_KEY)
            cg   = tuple(disp.get("custom_grid", [80, 40]))
            cw   = tuple(disp.get("custom_win",  [0,  0]))

            # Apply display size to global state
            if key == CUSTOM_ITEM[0] or key == CUSTOM_KEY:
                set_custom_display(cg[0], cg[1], cw[0], cw[1])
            else:
                set_display_size(key)

            # Restore settings panel (no signals)
            self._settings.restore_state({
                "display_key":    key,
                "custom_grid":    list(cg),
                "custom_win":     list(cw),
                "radius":         data.get("search_radius", 50),
                "fetch_interval": data.get("fetch_interval", 15),
                "cycle_interval": data.get("cycle_interval", 5),
                "opensky_user":   data.get("opensky_user", ""),
                "opensky_pass":   data.get("opensky_pass", ""),
            })

            # Apply timer intervals and credentials
            self._fetch_timer.setInterval(data.get("fetch_interval", 15) * 1000)
            self._cycle_timer.setInterval(data.get("cycle_interval", 5) * 1000)
            self._os_user = data.get("opensky_user", "")
            self._os_pass = data.get("opensky_pass", "")

            # Restore layout (no emit)
            blocks = layout_from_preset(data)
            self._layout = blocks
            self._led.apply_display_size()
            self._editor.set_layout(blocks)
            self._editor.apply_display_size()   # clamps positions, emits (suppressed)
            self._layout = self._editor.get_layout()

            # Restore overlay size if open
            if self._overlay and self._overlay.isVisible():
                self._overlay.apply_display_size()

            # Restore location if saved
            loc_data = data.get("location")
            if loc_data:
                loc = Location(
                    loc_data["lat"], loc_data["lon"],
                    loc_data.get("city", ""), loc_data.get("country", ""),
                )
                self._location = loc
                self._settings.set_location(loc)
                self._sb_location.setText(f"Location: {loc.city}, {loc.country}")
                if not self._fetch_timer.isActive():
                    self._fetch_timer.start()

            self._current_preset = name
            self._dirty = False
            self._btn_save.setEnabled(False)
            self._refresh_preset_combo()
            self._update_title()
            self._redraw_led()

            set_last_preset(name)

            # If we got a location from the preset, trigger a fresh fetch
            if loc_data:
                self._fetch_flights_async()
            else:
                self._fetch_location()

        finally:
            self._loading_preset = False

    # ── Overlay ───────────────────────────────────────────────────────────────

    def _toggle_overlay(self):
        if self._overlay is None:
            self._overlay = OverlayWindow()
        if self._overlay.isVisible():
            self._overlay.hide()
            self._btn_overlay.setText("⧉  Launch Overlay")
        else:
            self._overlay.apply_display_size()
            self._redraw_led()          # push current frame into overlay
            self._overlay.show()
            self._btn_overlay.setText("⧉  Hide Overlay")

    # ── Window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._dirty:
            if not self._confirm_discard():
                event.ignore()
                return
        if self._overlay:
            self._overlay.close()
        event.accept()

    # ── Data fetching ─────────────────────────────────────────────────────────

    def _fetch_location(self):
        self._sb_status.setText("Detecting location…")

        def run():
            try:
                from src.api.geoloc import get_location
                loc = get_location()
                self._worker.location_ready.emit(loc)
            except Exception as e:
                self._worker.error.emit(f"Location error: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _fetch_flights_async(self):
        if self._location is None:
            self._sb_status.setText("Waiting for location…")
            return
        self._sb_status.setText("Fetching flights…")

        radius = self._settings.radius
        loc    = self._location
        user, pw = self._os_user, self._os_pass

        def run():
            try:
                from src.api.flights import fetch_flights
                flights = fetch_flights(loc, radius, user, pw)
                self._worker.flights_ready.emit(flights)
            except Exception as e:
                self._worker.error.emit(str(e))

        threading.Thread(target=run, daemon=True).start()

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_location(self, loc: Location):
        self._location = loc
        self._settings.set_location(loc)
        self._sb_location.setText(f"Location: {loc.city}, {loc.country}")
        self._sb_status.setText("Location acquired. Fetching flights…")
        self._fetch_flights_async()
        self._fetch_timer.start()

    def _on_flights(self, flights: list[Flight]):
        self._flights     = flights
        self._current_idx = 0
        self._update_display()
        self._update_flight_list()
        self._sb_count.setText(f"Flights: {len(flights)}")
        import src.api.flights as flights_mod
        src = f" via {flights_mod.last_source}" if flights_mod.last_source else ""
        self._sb_status.setText(f"Updated — {len(flights)} aircraft in range{src}")

        threading.Thread(
            target=self._enrich_types,
            args=(list(flights),),
            daemon=True,
        ).start()

    def _enrich_types(self, flights: list[Flight]):
        from src.api.flights import fetch_aircraft_type
        from src.api.routes import lookup_route
        changed = False
        for f in flights[:10]:
            if not f.aircraft_type:
                f.aircraft_type = fetch_aircraft_type(
                    f.icao24, self._os_user, self._os_pass
                )
            if (not f.origin or not f.destination
                    or not f.origin_icao or not f.destination_icao):
                o_iata, d_iata, o_icao, d_icao = lookup_route(f.display_callsign)
                if o_iata or d_iata or o_icao or d_icao:
                    f.origin           = f.origin           or o_iata
                    f.destination      = f.destination      or d_iata
                    f.origin_icao      = f.origin_icao      or o_icao
                    f.destination_icao = f.destination_icao or d_icao
                    changed = True
        if changed:
            self._worker.flights_enriched.emit()

    def _on_enriched(self):
        self._update_display()
        self._update_flight_list()

    def _on_error(self, msg: str):
        self._sb_status.setText(f"Error: {msg}")

    def _on_radius_changed(self, val: float):
        self._fetch_flights_async()

    def _on_refresh_changed(self, val: int):
        self._fetch_timer.setInterval(val * 1000)

    def _on_cycle_changed(self, val: int):
        self._cycle_timer.setInterval(val * 1000)

    def _on_credentials(self, user: str, pw: str):
        self._os_user = user
        self._os_pass = pw

    def _on_layout_changed(self, blocks: list):
        self._layout = blocks
        self._redraw_led()
        self._mark_dirty()

    def _on_display_size_changed(self, key: str):
        set_display_size(key)
        self._apply_size_change()

    def _on_custom_display_changed(self, gw: int, gh: int, ww: int, wh: int):
        set_custom_display(gw, gh, ww, wh)
        self._apply_size_change()

    def _apply_size_change(self):
        self._led.apply_display_size()
        self._editor.apply_display_size()
        self._layout = self._editor.get_layout()
        if self._overlay and self._overlay.isVisible():
            self._overlay.apply_display_size()
        self._redraw_led()

    def _on_list_click(self, item: QListWidgetItem):
        idx = self._flight_list.row(item)
        if 0 <= idx < len(self._flights):
            self._current_idx = idx
            self._update_display()

    # ── Display update ────────────────────────────────────────────────────────

    def _update_display(self):
        if not self._flights:
            self._led.set_buffer(render_frame(None, self._layout))
            self.lbl_showing.setText("Showing: no flights")
            self.lbl_info.setText("No aircraft in range.")
            return

        n = len(self._flights)
        self._current_idx %= n
        flight = self._flights[self._current_idx]
        self.lbl_showing.setText(
            f"Showing: {flight.display_callsign}  [{self._current_idx + 1}/{n}]"
        )
        alt  = fmt_altitude(flight.baro_altitude, "ft_compact")
        spd  = fmt_speed(flight.velocity, "mph_s")
        dist = fmt_distance(flight.distance_km, "km")
        self.lbl_info.setText(
            f"{flight.airline_display}  ·  {alt}  ·  {spd}  ·  {dist} away"
        )
        self._redraw_led()

    def _redraw_led(self):
        flight = self._flights[self._current_idx] if self._flights else None
        buf    = render_frame(flight, self._layout)
        self._led.set_buffer(buf)
        if hasattr(self, "_editor"):
            self._editor.set_flight(flight)
        if self._overlay and self._overlay.isVisible():
            self._overlay.set_buffer(buf)

    def _update_flight_list(self):
        self._flight_list.clear()
        for f in self._flights:
            alt  = fmt_altitude(f.baro_altitude, "ft_compact")
            spd  = fmt_speed(f.velocity, "mph_s")
            dist = fmt_distance(f.distance_km, "km")
            line = (
                f"{f.display_callsign:<10}  "
                f"{alt:<8}  {spd:<8}  {dist:<8}  "
                f"{f.airline_display}"
            )
            item = QListWidgetItem(line)
            if f.on_ground:
                item.setForeground(QColor(120, 120, 120))
            self._flight_list.addItem(item)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev_flight(self):
        if self._flights:
            self._current_idx = (self._current_idx - 1) % len(self._flights)
            self._update_display()

    def _next_flight(self):
        if self._flights:
            self._current_idx = (self._current_idx + 1) % len(self._flights)
            self._update_display()

    def _toggle_cycle(self, checked: bool):
        if checked:
            self._cycle_timer.stop()
            self.btn_cycle.setText("▶ Resume Cycle")
        else:
            self._cycle_timer.start()
            self.btn_cycle.setText("⏸ Pause Cycle")
