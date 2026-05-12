"""Tetris-style drag-and-drop layout editor for the 80×40 LED matrix."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsRectItem, QGraphicsTextItem, QLabel, QPushButton, QGroupBox,
    QScrollArea, QCheckBox, QComboBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPen, QBrush, QFont

from src.core.models import (
    LayoutBlock, BLOCK_TYPES, BLOCK_TYPE_MAP, BLOCK_FORMATS,
    BLOCK_DEFAULT_FORMAT, default_layout,
)

GRID_SCALE = 7          # display pixels per LED pixel
PANEL_W = 80 * GRID_SCALE
PANEL_H = 40 * GRID_SCALE


class BlockItem(QGraphicsRectItem):
    """A draggable, snap-to-grid block for one data element."""

    def __init__(self, block: LayoutBlock):
        self.block = block
        w = block.width * GRID_SCALE
        h = block.height * GRID_SCALE
        super().__init__(0, 0, w, h)
        r, g, b = block.color
        self.setBrush(QBrush(QColor(r, g, b, 150)))
        self.setPen(QPen(QColor(min(255, r + 40), min(255, g + 40), min(255, b + 40)), 1))
        self.setPos(block.x * GRID_SCALE, block.y * GRID_SCALE)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f"{block.label}  ({block.width}×{block.height} px)")

        # Scale font to block height: small text for 7px rows, bigger for logo
        pt = max(7, min(11, h // 8))
        font = QFont("Courier New", pt)
        font.setBold(True)

        # Size label: show px dimensions
        lbl_text = f"{block.label}\n{block.width}×{block.height}px"
        lbl = QGraphicsTextItem(lbl_text, self)
        lbl.setDefaultTextColor(QColor(0, 0, 0))
        lbl.setFont(font)
        # Vertically center
        text_h = lbl.boundingRect().height()
        lbl.setPos(3, max(1, (h - text_h) / 2))

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            x = round(value.x() / GRID_SCALE) * GRID_SCALE
            y = round(value.y() / GRID_SCALE) * GRID_SCALE
            x = max(0, min(x, (80 - self.block.width) * GRID_SCALE))
            y = max(0, min(y, (40 - self.block.height) * GRID_SCALE))
            return QPointF(x, y)
        return super().itemChange(change, value)

    def grid_pos(self) -> tuple:
        p = self.scenePos()
        return (round(p.x() / GRID_SCALE), round(p.y() / GRID_SCALE))


# ── Per-block control row ─────────────────────────────────────────────────────

class BlockControlRow(QWidget):
    """One row in the left panel: checkbox + format dropdown."""
    toggled = pyqtSignal(str, bool)         # key, enabled
    format_changed = pyqtSignal(str, str)   # key, format_id

    def __init__(self, block: LayoutBlock, parent=None):
        super().__init__(parent)
        self.key = block.key
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        # Row 1: checkbox with colored label
        r, g, b = block.color
        bright = (min(255, r + 60), min(255, g + 60), min(255, b + 60))
        self.cb = QCheckBox(block.label)
        self.cb.setChecked(block.enabled)
        self.cb.setStyleSheet(
            f"QCheckBox {{ color: rgb{bright}; font-weight: bold; }}"
        )
        self.cb.stateChanged.connect(
            lambda s: self.toggled.emit(self.key, bool(s))
        )
        layout.addWidget(self.cb)

        # Row 2: format combo
        fmt_list = BLOCK_FORMATS.get(block.key, [])
        self.combo = QComboBox()
        self.combo.setMaximumHeight(20)
        for fid, flabel, fw, fh in fmt_list:
            self.combo.addItem(flabel, fid)
        # Select current format
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == block.fmt:
                self.combo.setCurrentIndex(i)
                break
        self.combo.setEnabled(block.enabled)
        self.combo.currentIndexChanged.connect(self._on_format)
        layout.addWidget(self.combo)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        layout.addWidget(line)

    def _on_format(self, _idx: int):
        fid = self.combo.currentData()
        if fid:
            self.format_changed.emit(self.key, fid)

    def set_enabled(self, enabled: bool):
        self.cb.setChecked(enabled)
        self.combo.setEnabled(enabled)

    def current_format(self) -> str:
        return self.combo.currentData() or ""


# ── Main editor widget ────────────────────────────────────────────────────────

class LayoutEditorWidget(QWidget):
    layout_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list[LayoutBlock] = default_layout()
        self._items: dict[str, BlockItem] = {}
        self._rows: dict[str, BlockControlRow] = {}
        self._init_ui()
        self._populate()

    def _init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # ── Left: scrollable control panel ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(220)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.setSpacing(0)

        ctrl_layout.addWidget(QLabel("Drag blocks on the grid →"))
        ctrl_layout.addSpacing(6)

        for key, label, color in BLOCK_TYPES:
            block = next((b for b in self._blocks if b.key == key), None)
            if block is None:
                block = LayoutBlock(key, 0, 0, False)
                self._blocks.append(block)
            row = BlockControlRow(block)
            row.toggled.connect(self._on_toggle)
            row.format_changed.connect(self._on_format)
            ctrl_layout.addWidget(row)
            self._rows[key] = row

        ctrl_layout.addStretch()

        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset)
        ctrl_layout.addWidget(reset_btn)

        scroll.setWidget(ctrl_widget)
        root.addWidget(scroll)

        # ── Right: graphics scene ────────────────────────────────────────────
        self._scene = QGraphicsScene(0, 0, PANEL_W, PANEL_H)
        self._draw_grid()

        self._view = QGraphicsView(self._scene)
        self._view.setBackgroundBrush(QBrush(QColor(12, 12, 12)))
        self._view.setFrameShape(QGraphicsView.Shape.Box)
        self._view.setFixedSize(PANEL_W + 4, PANEL_H + 4)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Forward mouse release to sync positions
        self._view.mouseReleaseEvent = self._view_mouse_release

        root.addWidget(self._view)
        root.addStretch()

    def _draw_grid(self):
        pen_major = QPen(QColor(45, 45, 45), 0.5)
        pen_minor = QPen(QColor(28, 28, 28), 0.3)
        for x in range(0, PANEL_W + 1, GRID_SCALE):
            pen = pen_major if (x // GRID_SCALE) % 8 == 0 else pen_minor
            self._scene.addLine(x, 0, x, PANEL_H, pen)
        for y in range(0, PANEL_H + 1, GRID_SCALE):
            pen = pen_major if (y // GRID_SCALE) % 8 == 0 else pen_minor
            self._scene.addLine(0, y, PANEL_W, y, pen)
        self._scene.addRect(0, 0, PANEL_W, PANEL_H, QPen(QColor(90, 90, 90), 1.5))

        font = QFont("Courier New", 4)
        for x in range(0, 81, 10):
            t = self._scene.addText(str(x), font)
            t.setDefaultTextColor(QColor(55, 55, 55))
            t.setPos(x * GRID_SCALE - 5, -10)
        for y in range(0, 41, 10):
            t = self._scene.addText(str(y), font)
            t.setDefaultTextColor(QColor(55, 55, 55))
            t.setPos(-18, y * GRID_SCALE - 5)

    def _populate(self):
        for item in list(self._items.values()):
            self._scene.removeItem(item)
        self._items.clear()
        for block in self._blocks:
            if block.enabled:
                item = BlockItem(block)
                self._scene.addItem(item)
                self._items[block.key] = item

    def _on_toggle(self, key: str, enabled: bool):
        for b in self._blocks:
            if b.key == key:
                b.enabled = enabled
                break
        if enabled:
            block = next(b for b in self._blocks if b.key == key)
            item = BlockItem(block)
            self._scene.addItem(item)
            self._items[key] = item
        else:
            if key in self._items:
                self._scene.removeItem(self._items.pop(key))
        if key in self._rows:
            self._rows[key].combo.setEnabled(enabled)
        self._emit()

    def _on_format(self, key: str, fmt_id: str):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None:
            return
        # Remember position before recreating
        old_item = self._items.get(key)
        if old_item:
            gx, gy = old_item.grid_pos()
            block.x, block.y = gx, gy
            self._scene.removeItem(old_item)
            del self._items[key]

        block.fmt = fmt_id

        if block.enabled:
            item = BlockItem(block)
            self._scene.addItem(item)
            self._items[key] = item
        self._emit()

    def _reset(self):
        self._blocks = default_layout()
        for row in self._rows.values():
            block = next((b for b in self._blocks if b.key == row.key), None)
            if block:
                row.set_enabled(block.enabled)
                # Reset combo to block's default format
                for i in range(row.combo.count()):
                    if row.combo.itemData(i) == block.fmt:
                        row.combo.setCurrentIndex(i)
                        break
        self._populate()
        self._emit()

    def _view_mouse_release(self, event):
        QGraphicsView.mouseReleaseEvent(self._view, event)
        self._emit()

    def _sync_positions(self):
        for block in self._blocks:
            item = self._items.get(block.key)
            if item:
                gx, gy = item.grid_pos()
                block.x = gx
                block.y = gy

    def _emit(self):
        self._sync_positions()
        self.layout_changed.emit(list(self._blocks))

    def get_layout(self):
        self._sync_positions()
        return list(self._blocks)
