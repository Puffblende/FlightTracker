"""External LED matrix display tab.

Lets the user discover ESP32 devices on the local network (UDP broadcast)
or via Bluetooth LE, connect, and stream live frames to them.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QSpinBox, QTextEdit, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont

from src.external.discovery import scan_wifi, scan_ble, MatrixDevice, DATA_PORT
from src.external.protocol import UDPSender

_DEVICE_IP_FILE = Path.home() / ".flighttracker" / "device_ip.json"


def _parse_host_port(value: str, default_port: int) -> tuple[str, int]:
    text = (value or "").strip()
    if not text:
        return "", default_port

    if text.startswith("http://"):
        text = text[len("http://"):]
    elif text.startswith("https://"):
        text = text[len("https://"):]

    if ":" in text:
        host, port_text = text.rsplit(":", 1)
        host = host.strip()
        port_text = port_text.strip()
        if host and port_text.isdigit():
            return host, int(port_text)

    return text, default_port


def _load_persisted_connection() -> dict[str, object]:
    try:
        data = json.loads(_DEVICE_IP_FILE.read_text())
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    ip = data.get("ip", "")
    port = data.get("port", DATA_PORT)
    push_ip = data.get("push_ip", ip)
    try:
        port_value = int(port)
    except (TypeError, ValueError):
        port_value = DATA_PORT

    return {"ip": str(ip or ""), "port": port_value, "push_ip": str(push_ip or ip or "")}


def _save_persisted_connection(ip: str, port: int, push_ip: str | None = None) -> None:
    try:
        _DEVICE_IP_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"ip": ip, "port": port}
        if push_ip is not None:
            data["push_ip"] = push_ip
        _DEVICE_IP_FILE.write_text(json.dumps(data))
    except Exception:
        pass


class _Sig(QObject):
    """Cross-thread signals for the tab."""
    device_found = pyqtSignal(object)   # MatrixDevice
    scan_done    = pyqtSignal(str)      # "wifi" | "ble"
    ble_error    = pyqtSignal(str)
    push_done    = pyqtSignal(bool, str)  # success, message
    log_msg      = pyqtSignal(str)        # background-thread log line


class ExternalDisplayTab(QWidget):
    """Tab for connecting to ESP32-based LED matrix displays."""

    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self._main_window = main_window
        self._devices: list[MatrixDevice] = []
        self._sender:  UDPSender | None   = None
        self._frame_count = 0
        self._auto_send   = True

        self._sig = _Sig()
        self._sig.device_found.connect(self._on_device_found)
        self._sig.scan_done.connect(self._on_scan_done)
        self._sig.ble_error.connect(lambda e: self._log(f"Bluetooth error: {e}"))
        self._sig.push_done.connect(self._on_push_done)
        self._sig.log_msg.connect(self._log)

        self._build_ui()
        self._restore_connection_state()
        self._connect_connection_persistence()
        self._load_device_ip()
        self._persist_connection_fields()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_discovery())
        root.addWidget(self._build_connection())
        root.addWidget(self._build_push_config())
        root.addWidget(self._build_log())
        root.addWidget(self._build_hint())

    def _build_discovery(self) -> QGroupBox:
        box = QGroupBox("Device Discovery")
        v   = QVBoxLayout(box)

        # Scan buttons + status
        btn_row = QHBoxLayout()
        self._btn_wifi = QPushButton("🔍  Scan WiFi Network")
        self._btn_wifi.clicked.connect(self._scan_wifi)
        btn_row.addWidget(self._btn_wifi)

        self._btn_ble = QPushButton("📶  Scan Bluetooth")
        self._btn_ble.clicked.connect(self._scan_ble)
        btn_row.addWidget(self._btn_ble)

        btn_row.addStretch()
        self._lbl_scan = QLabel("Ready")
        self._lbl_scan.setStyleSheet("color: #888;")
        btn_row.addWidget(self._lbl_scan)
        v.addLayout(btn_row)

        # Results list
        self._device_list = QListWidget()
        self._device_list.setFont(QFont("Courier New", 9))
        self._device_list.setMaximumHeight(110)
        self._device_list.setAlternatingRowColors(True)
        self._device_list.itemDoubleClicked.connect(self._on_device_dbl_click)
        v.addWidget(self._device_list)

        v.addWidget(QLabel(
            "Double-click a WiFi device to connect, or enter IP/port manually below."
        ))
        return box

    def _build_connection(self) -> QGroupBox:
        box = QGroupBox("Connection")
        v   = QVBoxLayout(box)

        # Manual IP / port entry + connect button
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("IP address:"))
        self._txt_ip = QLineEdit()
        self._txt_ip.setPlaceholderText("192.168.x.x")
        self._txt_ip.setMaximumWidth(150)
        self._txt_ip.textChanged.connect(self._persist_connection_fields)
        row1.addWidget(self._txt_ip)

        row1.addSpacing(8)
        row1.addWidget(QLabel("Port:"))
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1024, 65535)
        self._spin_port.setValue(DATA_PORT)
        self._spin_port.setMaximumWidth(80)
        self._spin_port.valueChanged.connect(self._persist_connection_fields)
        row1.addWidget(self._spin_port)

        row1.addSpacing(16)
        self._cb_auto = QCheckBox("Stream frames automatically")
        self._cb_auto.setChecked(True)
        self._cb_auto.toggled.connect(self._on_auto_toggled)
        row1.addWidget(self._cb_auto)

        row1.addStretch()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setMinimumWidth(100)
        self._btn_connect.clicked.connect(self._toggle_connect)
        row1.addWidget(self._btn_connect)
        v.addLayout(row1)

        # Status indicator
        row2 = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #444; font-size: 20px;")
        row2.addWidget(self._dot)
        self._lbl_conn = QLabel("Disconnected")
        row2.addWidget(self._lbl_conn)
        row2.addStretch()
        self._lbl_frames = QLabel("")
        self._lbl_frames.setStyleSheet("color: #666;")
        row2.addWidget(self._lbl_frames)
        v.addLayout(row2)

        return box

    def _build_push_config(self) -> QGroupBox:
        box = QGroupBox("Push Configuration")
        v   = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Device IP:"))
        self._txt_push_ip = QLineEdit()
        self._txt_push_ip.setPlaceholderText("192.168.x.x")
        self._txt_push_ip.setMaximumWidth(150)
        row.addWidget(self._txt_push_ip)
        row.addStretch()
        self._btn_push = QPushButton("Push Config")
        self._btn_push.setMinimumWidth(110)
        self._btn_push.clicked.connect(self._push_config)
        row.addWidget(self._btn_push)
        v.addLayout(row)

        hint = QLabel(
            "Sends location, radius, intervals, credentials, and the full layout "
            "to the ESP32 via HTTP POST /config."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 10px;")
        v.addWidget(hint)

        return box

    def _build_log(self) -> QGroupBox:
        box = QGroupBox("Log")
        v   = QVBoxLayout(box)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Courier New", 8))
        self._log_view.setMaximumHeight(140)
        self._log_view.setStyleSheet("background:#111; color:#aaa;")
        v.addWidget(self._log_view)
        return box

    def _build_hint(self) -> QLabel:
        lbl = QLabel(
            "ℹ  Discovery uses UDP port 4210; the ESP32 replies with its HTTP config URL. "
            "The config endpoint is HTTP port 80, while the UDP frame stream uses the "
            "device-specific port reported by discovery."
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#555; font-style:italic; font-size:10px;")
        return lbl

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _scan_wifi(self):
        self._device_list.clear()
        self._devices.clear()
        self._btn_wifi.setEnabled(False)
        self._lbl_scan.setText("Scanning WiFi…")
        self._log("WiFi broadcast scan started (2 s)…")

        def _run():
            scan_wifi(
                timeout=2.0,
                on_found=lambda d: self._sig.device_found.emit(d),
            )
            self._sig.scan_done.emit("wifi")

        threading.Thread(target=_run, daemon=True).start()

    def _scan_ble(self):
        self._btn_ble.setEnabled(False)
        self._lbl_scan.setText("Scanning Bluetooth (5 s)…")
        self._log("Bluetooth scan started…")

        def _done(devices, err):
            for d in devices:
                self._sig.device_found.emit(d)
            if err:
                self._sig.ble_error.emit(err)
            self._sig.scan_done.emit("ble")

        scan_ble(timeout=5.0, on_done=_done)

    def _on_device_found(self, dev: MatrixDevice):
        self._devices.append(dev)
        item = QListWidgetItem(dev.label())
        item.setData(Qt.ItemDataRole.UserRole, dev)
        self._device_list.addItem(item)
        self._log(f"Found: {dev.label()}")

    def _on_scan_done(self, kind: str):
        if kind == "wifi":
            self._btn_wifi.setEnabled(True)
        else:
            self._btn_ble.setEnabled(True)
        n = self._device_list.count()
        self._lbl_scan.setText(f"Done — {n} device(s) found" if n else "Done — no devices found")
        if n == 0:
            self._log("No devices found.  Make sure the ESP32 is on the same WiFi network.")

    def _on_device_dbl_click(self, item: QListWidgetItem):
        dev: MatrixDevice = item.data(Qt.ItemDataRole.UserRole)
        if dev and dev.transport == "wifi":
            self._txt_ip.setText(dev.address)
            if not self._txt_push_ip.text().strip():
                self._txt_push_ip.setText(dev.address)
            self._connect(dev)

    # ── Connection ────────────────────────────────────────────────────────────

    def _toggle_connect(self):
        if self._sender and self._sender.is_open:
            self._disconnect()
        else:
            host, port = _parse_host_port(self._txt_ip.text(), self._spin_port.value())
            if not host:
                self._log("Enter an IP address first.")
                return
            self._txt_ip.setText(host)
            self._spin_port.setValue(port)
            dev = MatrixDevice(
                name=host, transport="wifi",
                address=host, port=port,
            )
            self._connect(dev)

    def _connect(self, dev: MatrixDevice):
        self._disconnect()
        try:
            sender = UDPSender(dev.address, dev.port)
            sender.connect()
            self._sender = sender
            self._frame_count = 0
            self._txt_ip.setText(dev.address)
            _save_persisted_connection(dev.address, self._spin_port.value(), self._txt_push_ip.text().strip())
            self._set_connected(True, f"Connected  →  {dev.address}:{dev.port}")
            self._btn_connect.setText("Disconnect")
            self._log(f"Connected to {dev.address}:{dev.port}")
        except Exception as exc:
            self._log(f"Connection failed: {exc}")

    def _disconnect(self):
        if self._sender:
            self._sender.close()
            self._sender = None
        self._set_connected(False, "Disconnected")
        self._btn_connect.setText("Connect")
        self._log("Disconnected.")

    def _set_connected(self, ok: bool, text: str):
        self._dot.setStyleSheet(
            f"color: {'#27ae60' if ok else '#444'}; font-size: 20px;"
        )
        self._lbl_conn.setText(text)

    def _on_auto_toggled(self, enabled: bool):
        self._auto_send = enabled

    def _persist_connection_fields(self):
        host, port = _parse_host_port(self._txt_ip.text(), self._spin_port.value())
        _save_persisted_connection(host, port, self._txt_push_ip.text().strip())

    # ── Frame streaming (called by main_window on every redraw) ───────────────

    def send_frame(self, buf: list) -> None:
        if not self._auto_send or self._sender is None or not self._sender.is_open:
            return
        sent = self._sender.send(buf)
        if sent > 0:
            self._frame_count += 1
            if self._frame_count % 30 == 0:
                self._lbl_frames.setText(f"Frames sent: {self._frame_count:,}")

    # ── Push Configuration ────────────────────────────────────────────────────

    def _restore_connection_state(self):
        state = _load_persisted_connection()
        ip = str(state.get("ip", "") or "")
        port = int(state.get("port", DATA_PORT) or DATA_PORT)
        push_ip = str(state.get("push_ip", ip) or "")
        if ip:
            host, saved_port = _parse_host_port(ip, port)
            self._txt_ip.setText(host)
            self._spin_port.setValue(saved_port)
            if push_ip:
                self._txt_push_ip.setText(str(push_ip))
            else:
                self._txt_push_ip.setText(host)
        else:
            self._spin_port.setValue(port)

    def _connect_connection_persistence(self):
        self._txt_ip.textChanged.connect(self._persist_connection_fields)
        self._spin_port.valueChanged.connect(self._persist_connection_fields)
        self._txt_push_ip.textChanged.connect(self._persist_connection_fields)

    def _load_device_ip(self):
        state = _load_persisted_connection()
        push_ip = str(state.get("push_ip", state.get("ip", "")) or "")
        if push_ip:
            host, _ = _parse_host_port(push_ip, self._spin_port.value())
            self._txt_push_ip.setText(host)

    def _save_device_ip(self, ip: str):
        _save_persisted_connection(ip, self._spin_port.value(), self._txt_push_ip.text().strip())

    def _collect_airline_catalog(self) -> list[tuple[str, str, str]]:
        """Build a stable airline catalog from the known DB plus current flights."""
        mw = self._main_window
        if not mw:
            return []

        try:
            from src.api.logos import collect_known_airline_catalog
        except ImportError:
            collect_known_airline_catalog = None

        result: list[tuple[str, str, str]] = []
        seen: set[str] = set()

        if collect_known_airline_catalog is not None:
            for icao, iata, name in collect_known_airline_catalog():
                if icao in seen:
                    continue
                seen.add(icao)
                result.append((icao, iata, name))

        flights = getattr(mw, '_flights', []) or []
        for flight in flights:
            raw = (getattr(flight, 'airline_icao', '') or "").strip()
            if not raw and len(flight.callsign or "") >= 3:
                raw = flight.callsign[:3]
            icao = raw.upper()
            if len(icao) != 3 or not icao.isalpha() or icao in seen:
                continue
            seen.add(icao)
            result.append(
                (
                    icao,
                    (getattr(flight, 'airline_iata', '') or "").strip().upper(),
                    (getattr(flight, 'airline_name', '') or "").strip(),
                )
            )
        return result

    def _collect_flight_airlines(self) -> list[tuple[str, str, str]]:
        """Airlines from the currently displayed flights only (no catalog)."""
        mw = self._main_window
        if not mw:
            return []
        result: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for flight in getattr(mw, '_flights', []) or []:
            raw = (getattr(flight, 'airline_icao', '') or "").strip()
            if not raw and len(flight.callsign or "") >= 3:
                raw = flight.callsign[:3]
            icao = raw.upper()
            if len(icao) != 3 or not icao.isalpha() or icao in seen:
                continue
            seen.add(icao)
            result.append(
                (
                    icao,
                    (getattr(flight, 'airline_iata', '') or "").strip().upper(),
                    (getattr(flight, 'airline_name', '') or "").strip(),
                )
            )
        return result

    def _current_logo_size(self) -> int:
        """Pixel size (w=h) of the layout's logo block, matching the Python
        preview exactly — e.g. 40 for the "sq40" format. Falls back to 24
        (the smallest/default format) if there's no enabled logo block."""
        mw = self._main_window
        if not mw:
            return 24
        try:
            blocks = mw._editor.get_layout()
        except Exception:
            return 24
        for b in blocks:
            if b.key == "logo" and b.enabled:
                return b.width
        return 24

    def _encode_logos(self) -> dict[str, str]:
        """Return {ICAO: hex_string} for currently displayed flights, sized
        to match the layout's logo block exactly (same pixels the Python app
        renders — see src/core/renderer.py's _paste_pil).

        The hex string is the raw pixel bytes (size*size*3) encoded as
        lowercase hex. The ESP32 decodes this and saves it to LittleFS.

        Scoped to the current flights (not the full airline catalog): the
        POST /config body is parsed into a 64 KB PSRAM buffer on the device
        (see ft_webserver.cpp), and the full catalog's logos alone hex-encode
        to ~288 KB — pushing them here would blow that budget and either
        fail to parse or make the device hang writing ~80+ logo files inside
        a single request. The full catalog still reaches the device, just
        via _push_all_logos()'s small batched POST /logos calls afterward.
        """
        mw = self._main_window
        if not mw:
            return {}
        try:
            from src.api.logos import get_logo
        except ImportError:
            return {}

        size = self._current_logo_size()
        result: dict[str, str] = {}
        for icao, iata, _ in self._collect_flight_airlines():
            try:
                img = get_logo(iata, size, size, icao)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                result[icao] = img.tobytes().hex()
            except Exception:
                continue
        return result

    def _collect_airline_names(self) -> dict[str, str]:
        """Return {ICAO: name} for the airline catalog used by the display."""
        result: dict[str, str] = {}
        for icao, _, name in self._collect_airline_catalog():
            if name:
                result[icao] = name
        return result

    def _build_config_payload(self) -> dict:
        mw = self._main_window
        if mw is None:
            raise RuntimeError("No main window reference")

        loc = mw._location
        if loc is None:
            raise RuntimeError("Location not set — fetch location first")

        st = mw._settings.get_state()

        from src.core.displays import get_display_size
        display_w, display_h = get_display_size()

        blocks = mw._editor.get_layout()
        layout = [
            {
                "key":          b.key,
                "x":            b.x,
                "y":            b.y,
                "enabled":      b.enabled,
                "fmt":          b.fmt,
                "color":        list(b.color),
                # Resolved text, not the raw nullable fields: custom_label/
                # custom_unit are None whenever the user hasn't typed into
                # those boxes, which is the common case. The ESP32 has no
                # concept of "fall back to this format's default label" —
                # it just prints whatever string it's given — so sending
                # the raw None (-> JSON null -> "") silently dropped labels
                # like "D:"/"km" that the Python preview shows via
                # effective_label/effective_unit's own fallback logic.
                "custom_label": b.effective_label,
                "custom_unit":  b.effective_unit,
                "font_scale":   b.font_scale,
                "custom_width": b.custom_width,
            }
            for b in blocks
        ]

        logos         = self._encode_logos()
        airline_names = self._collect_airline_names()

        return {
            "lat":              float(loc.lat),
            "lon":              float(loc.lon),
            "radius_km":        float(st["radius"]),
            "fetch_interval_s": int(st["fetch_interval"]),
            "cycle_interval_s": int(st["cycle_interval"]),
            "opensky_user":     str(mw._os_user or ""),
            "opensky_pass":     str(mw._os_pass or ""),
            "hidden_categories": list(st["hidden_categories"]),
            "display_w":        int(display_w),
            "display_h":        int(display_h),
            "layout":           layout,
            "logos":            logos,          # {ICAO: hex_string} sized to the logo block's format
            "airline_names":    airline_names,  # {ICAO: name}
        }

    def _push_config(self):
        ip = self._txt_push_ip.text().strip()
        if not ip:
            self._log("Enter a device IP address first.")
            return

        try:
            payload = self._build_config_payload()
        except RuntimeError as e:
            self._log(f"Push aborted: {e}")
            return

        self._btn_push.setEnabled(False)
        host, http_port = _parse_host_port(ip, 80)
        n_logos = len(payload.get('logos', {}))
        n_names = len(payload.get('airline_names', {}))
        self._log(f"Pushing config to http://{host}:{http_port}/config "
                  f"({n_logos} logos, {n_names} airline names) …")
        logo_size = self._current_logo_size()

        def _run():
            try:
                import requests as req
                resp = req.post(
                    f"http://{host}:{http_port}/config",
                    json=payload,
                    # clearLogoCache() (device-side) walks and deletes every
                    # cached logo file before applying the new config — with
                    # a lot of accumulated files that alone can take longer
                    # than a typical request. 30s gives it room; a healthy
                    # device with a small cache still responds in a couple
                    # of seconds either way.
                    timeout=30,
                )
                ok  = resp.status_code == 200
                msg = f"HTTP {resp.status_code}: {resp.text[:200].strip()}"
                self._sig.push_done.emit(ok, msg)
                if ok:
                    self._push_all_logos(host, logo_size)
            except Exception as exc:
                self._sig.push_done.emit(False, str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def _push_all_logos(self, ip: str, logo_size: int = 24, batch_size: int = 6):
        """Stream the full known airline catalog to the device in small batches.

        POST /config only carries logos for airlines in the currently
        displayed flights (see _encode_logos) to stay under the ESP32's
        64 KB JSON buffer. This follows up with everything else via
        POST /logos, a handful of airlines per request, so the device ends
        up with the complete catalog without ever needing a single payload
        large enough to overflow that buffer. Runs on the caller's thread —
        call from a background thread, not the GUI thread.
        """
        try:
            from src.api.logos import collect_known_airline_catalog, get_logo
            import requests as req
        except ImportError:
            return

        catalog = collect_known_airline_catalog()
        total = len(catalog)
        sent = 0
        self._sig.log_msg.emit(f"Pushing full logo catalog ({total} airlines) in batches…")

        for i in range(0, total, batch_size):
            batch = catalog[i:i + batch_size]
            logos = {}
            for icao, iata, _ in batch:
                try:
                    img = get_logo(iata, logo_size, logo_size, icao)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    logos[icao] = img.tobytes().hex()
                except Exception:
                    continue
            if not logos:
                continue
            try:
                resp = req.post(f"http://{ip}/logos", json={"logos": logos}, timeout=10)
                if resp.status_code == 200:
                    sent += len(logos)
                else:
                    self._sig.log_msg.emit(
                        f"Logo batch failed: HTTP {resp.status_code}"
                    )
            except Exception as exc:
                self._sig.log_msg.emit(f"Logo catalog push aborted: {exc}")
                return

        self._sig.log_msg.emit(f"Logo catalog push complete — {sent}/{total} airlines sent.")

    def _on_push_done(self, success: bool, message: str):
        self._btn_push.setEnabled(True)
        if success:
            ip = self._txt_push_ip.text().strip()
            self._save_device_ip(ip)
            self._log(f"Config pushed successfully — {message}")
        else:
            self._log(f"Push failed: {message}")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_view.append(f"[{ts}] {msg}")
        # Keep at most 200 lines
        doc = self._log_view.document()
        while doc.blockCount() > 200:
            cur = self._log_view.textCursor()
            cur.movePosition(cur.MoveOperation.Start)
            cur.select(cur.SelectionType.LineUnderCursor)
            cur.removeSelectedText()
            cur.deleteChar()
