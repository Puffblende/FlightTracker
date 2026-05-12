"""Main application window."""
from __future__ import annotations
import threading
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QStatusBar, QGroupBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor

from src.core.models import (
    Location, Flight, LayoutBlock, default_layout,
    fmt_altitude, fmt_speed, fmt_distance,
)
from src.core.renderer import render_frame
from src.core.displays import set_display_size, set_custom_display
from src.ui.led_widget import LEDWidget
from src.ui.settings_panel import SettingsPanel
from src.ui.layout_editor import LayoutEditorWidget


class _Worker(QObject):
    """Signals for cross-thread communication."""
    location_ready = pyqtSignal(object)    # Location
    flights_ready = pyqtSignal(list)       # list[Flight]
    flights_enriched = pyqtSignal()        # refresh display, no re-enrich
    error = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FlightTracker — LED Matrix Display")
        self.setMinimumSize(1100, 600)

        self._location = None   # Location | None
        self._flights = []      # list[Flight]
        self._current_idx = 0
        self._layout = default_layout()
        self._os_user = ""
        self._os_pass = ""
        self._speed_unit = "mph"

        self._worker = _Worker()
        self._worker.location_ready.connect(self._on_location)
        self._worker.flights_ready.connect(self._on_flights)
        self._worker.flights_enriched.connect(self._on_enriched)
        self._worker.error.connect(self._on_error)

        self._build_ui()
        self._build_timers()

        # Kick off location detection immediately
        self._fetch_location()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.setCentralWidget(tabs)

        tabs.addTab(self._build_display_tab(), "Display")
        tabs.addTab(self._build_editor_tab(), "Layout Editor")
        tabs.addTab(self._build_list_tab(), "Flight List")

        # Status bar
        self._sb_location = QLabel("Location: detecting…")
        self._sb_count = QLabel("Flights: 0")
        self._sb_status = QLabel("Ready")
        self.statusBar().addWidget(self._sb_location)
        self.statusBar().addWidget(QLabel(" | "))
        self.statusBar().addWidget(self._sb_count)
        self.statusBar().addWidget(QLabel(" | "))
        self.statusBar().addPermanentWidget(self._sb_status)

    def _build_display_tab(self):
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(10, 10, 10, 10)

        # Left: settings panel
        self._settings = SettingsPanel()
        self._settings.location_requested.connect(self._fetch_location)
        self._settings.radius_changed.connect(self._on_radius_changed)
        self._settings.refresh_changed.connect(
            lambda v: self._fetch_timer.setInterval(v * 1000)
        )
        self._settings.cycle_changed.connect(
            lambda v: self._cycle_timer.setInterval(v * 1000)
        )
        self._settings.credentials_changed.connect(self._on_credentials)
        self._settings.display_size_changed.connect(self._on_display_size_changed)
        self._settings.custom_display_size_changed.connect(self._on_custom_display_changed)
        root.addWidget(self._settings)


        # Right: LED display + controls
        right = QVBoxLayout()
        right.setSpacing(8)

        # LED panel header
        header = QHBoxLayout()
        self.lbl_showing = QLabel("Showing: —")
        self.lbl_showing.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        header.addWidget(self.lbl_showing)
        header.addStretch()
        right.addLayout(header)

        # LED widget
        self._led = LEDWidget()
        led_container = QHBoxLayout()
        led_container.addStretch()
        led_container.addWidget(self._led)
        led_container.addStretch()
        right.addLayout(led_container)

        # Navigation controls
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

        # Info line
        self.lbl_info = QLabel("No data yet.")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.lbl_info)
        right.addStretch()

        root.addLayout(right)
        return page

    def _build_editor_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        info = QLabel(
            "Drag blocks to reposition them on the 80×40 LED grid. "
            "Check/uncheck elements to show or hide them."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._editor = LayoutEditorWidget()
        self._editor.layout_changed.connect(self._on_layout_changed)
        layout.addWidget(self._editor)
        return page

    def _build_list_tab(self):
        page = QWidget()
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
        loc = self._location
        user, pw = self._os_user, self._os_pass

        def run():
            try:
                from src.api.flights import fetch_flights, last_source
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
        self._flights = flights
        self._current_idx = 0
        self._update_display()
        self._update_flight_list()
        self._sb_count.setText(f"Flights: {len(flights)}")
        import src.api.flights as flights_mod
        src = f" via {flights_mod.last_source}" if flights_mod.last_source else ""
        self._sb_status.setText(
            f"Updated — {len(flights)} aircraft in range{src}"
        )

        # Prefetch aircraft types in background
        threading.Thread(
            target=self._enrich_types,
            args=(list(flights),),
            daemon=True,
        ).start()

    def _enrich_types(self, flights: list[Flight]):
        from src.api.flights import fetch_aircraft_type
        from src.api.routes import lookup_route
        changed = False
        for f in flights[:10]:  # limit to top 10 nearest
            if not f.aircraft_type:
                # adsb.lol usually already fills this; only fall back to OpenSky
                # metadata when adsb.lol didn't return a type.
                f.aircraft_type = fetch_aircraft_type(
                    f.icao24, self._os_user, self._os_pass
                )
            if not f.origin or not f.destination:
                o, d = lookup_route(f.display_callsign)
                if o or d:
                    f.origin = f.origin or o
                    f.destination = f.destination or d
                    changed = True
        if changed:
            self._worker.flights_enriched.emit()

    def _on_enriched(self):
        # Background enrichment filled in route data — refresh display + list
        self._update_display()
        self._update_flight_list()

    def _on_error(self, msg: str):
        self._sb_status.setText(f"Error: {msg}")

    def _on_radius_changed(self, val: float):
        # Restart fetch timer and fetch immediately
        self._fetch_flights_async()

    def _on_credentials(self, user: str, pw: str):
        self._os_user = user
        self._os_pass = pw

    def _on_layout_changed(self, blocks: list):
        self._layout = blocks
        self._redraw_led()

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
        buf = render_frame(flight, self._layout)
        self._led.set_buffer(buf)
        # Mirror the same flight to the layout editor's preview
        if hasattr(self, "_editor"):
            self._editor.set_flight(flight)

    def _update_flight_list(self):
        self._flight_list.clear()
        for f in self._flights:
            alt  = fmt_altitude(f.baro_altitude, "ft_compact")
            spd  = fmt_speed(f.velocity, "mph_s")
            dist = fmt_distance(f.distance_km, "km")
            line = (
                f"{f.display_callsign:<10}  "
                f"{alt:<8}  "
                f"{spd:<8}  "
                f"{dist:<8}  "
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
