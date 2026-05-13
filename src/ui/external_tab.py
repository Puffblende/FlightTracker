"""External LED matrix display tab.

Lets the user discover ESP32 devices on the local network (UDP broadcast)
or via Bluetooth LE, connect, and stream live frames to them.
"""
from __future__ import annotations

import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QSpinBox, QTextEdit, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont

from src.external.discovery import scan_wifi, scan_ble, MatrixDevice, DATA_PORT
from src.external.protocol import UDPSender


class _Sig(QObject):
    """Cross-thread signals for the tab."""
    device_found = pyqtSignal(object)   # MatrixDevice
    scan_done    = pyqtSignal(str)      # "wifi" | "ble"
    ble_error    = pyqtSignal(str)


class ExternalDisplayTab(QWidget):
    """Tab for connecting to ESP32-based LED matrix displays."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices: list[MatrixDevice] = []
        self._sender:  UDPSender | None   = None
        self._frame_count = 0
        self._auto_send   = True

        self._sig = _Sig()
        self._sig.device_found.connect(self._on_device_found)
        self._sig.scan_done.connect(self._on_scan_done)
        self._sig.ble_error.connect(lambda e: self._log(f"Bluetooth error: {e}"))

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_discovery())
        root.addWidget(self._build_connection())
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
        row1.addWidget(self._txt_ip)

        row1.addSpacing(8)
        row1.addWidget(QLabel("Port:"))
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1024, 65535)
        self._spin_port.setValue(DATA_PORT)
        self._spin_port.setMaximumWidth(80)
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
            "ℹ  Your ESP32 must listen on UDP port 4211 and respond to discovery "
            "broadcasts on port 4210.  Frame packets begin with magic bytes 'FTLD' "
            "(4 B) + width (2 B) + height (2 B) + raw RGB data.  "
            "See src/external/protocol.py for a sample Arduino sketch."
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
            self._spin_port.setValue(dev.port)
            self._connect(dev)

    # ── Connection ────────────────────────────────────────────────────────────

    def _toggle_connect(self):
        if self._sender and self._sender.is_open:
            self._disconnect()
        else:
            ip = self._txt_ip.text().strip()
            if not ip:
                self._log("Enter an IP address first.")
                return
            dev = MatrixDevice(
                name=ip, transport="wifi",
                address=ip, port=self._spin_port.value(),
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
            self._spin_port.setValue(dev.port)
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

    # ── Frame streaming (called by main_window on every redraw) ───────────────

    def send_frame(self, buf: list) -> None:
        if not self._auto_send or self._sender is None or not self._sender.is_open:
            return
        sent = self._sender.send(buf)
        if sent > 0:
            self._frame_count += 1
            if self._frame_count % 30 == 0:
                self._lbl_frames.setText(f"Frames sent: {self._frame_count:,}")

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
