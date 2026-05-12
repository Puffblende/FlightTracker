"""Layout editor with live preview and contextual customization panel.

The preview rectangles render the actual LED bitmap font (1:1 with the LED
panel output) so they grow correctly with font scale. Sample values are
the *current* flight's values when one is selected.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsRectItem, QGraphicsPixmapItem, QLabel, QPushButton,
    QScrollArea, QCheckBox, QComboBox, QFrame, QSpinBox, QColorDialog,
    QLineEdit, QGroupBox, QGraphicsItem,
)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPixmap, QImage

from src.core.models import (
    LayoutBlock, BLOCK_TYPES, BLOCK_FORMATS, default_layout, Flight,
    render_block_text, _format_for,
)
from src.core.displays import get_display_size, get_window_hint
from src.core.font import (
    FONT_5X7, CHAR_W, CHAR_H, CHAR_SPACING, draw_text, text_width,
)

MAX_CANVAS_W = 880
MAX_CANVAS_H = 460


def _grid_scale_for(W: int, H: int) -> int:
    win_w, win_h = get_window_hint()
    budget_w = win_w if win_w else MAX_CANVAS_W
    budget_h = win_h if win_h else MAX_CANVAS_H
    for s in (32, 24, 16, 12, 10, 8, 7, 6, 5, 4, 3, 2, 1):
        if W * s <= budget_w and H * s <= budget_h:
            return s
    return 1


# ── Bitmap font → QPixmap (so the preview matches the LED render exactly) ────

def _render_text_to_pixmap(text: str, color: tuple, scale: int,
                           grid_scale: int) -> QPixmap:
    """Render text using the LED bitmap font, upscaled to grid_scale."""
    if not text:
        return QPixmap()
    w_chars = max(1, len(text))
    px_w = (w_chars * (CHAR_W + CHAR_SPACING) - CHAR_SPACING) * scale
    px_h = CHAR_H * scale
    if px_w <= 0 or px_h <= 0:
        return QPixmap()
    buf = [[(0, 0, 0, 0)] * px_w for _ in range(px_h)]
    cx = 0
    for ch in text:
        rows = FONT_5X7.get(ch, FONT_5X7.get(' '))
        for ry, bits in enumerate(rows):
            for bx in range(5):
                if not (bits & (1 << (4 - bx))):
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        x = cx + bx * scale + dx
                        y = ry * scale + dy
                        if 0 <= x < px_w and 0 <= y < px_h:
                            buf[y][x] = (color[0], color[1], color[2], 255)
        cx += (CHAR_W + CHAR_SPACING) * scale

    # Up-scale to screen pixels (grid_scale × per font pixel)
    img = QImage(px_w * grid_scale, px_h * grid_scale, QImage.Format.Format_ARGB32)
    img.fill(0)
    for y in range(px_h):
        for x in range(px_w):
            r, g, b, a = buf[y][x]
            if a == 0:
                continue
            qc = QColor(r, g, b, a)
            for dy in range(grid_scale):
                for dx in range(grid_scale):
                    img.setPixelColor(x * grid_scale + dx, y * grid_scale + dy, qc)
    return QPixmap.fromImage(img)


# Same plane glyph as the renderer — keep in sync
_PLANE_GLYPH = [
    "...X...",
    "...X...",
    "..XXX..",
    "XXXXXXX",
    "..XXX..",
    "...X...",
    ".XX.XX.",
]


def _render_progress_to_pixmap(block: LayoutBlock, grid_scale: int) -> QPixmap:
    """Render a sample progress bar (50% progress) matching renderer semantics."""
    w = max(4, block.width)
    h = max(1, block.height)
    img = QImage(w * grid_scale, h * grid_scale, QImage.Format.Format_ARGB32)
    img.fill(0)
    color    = QColor(*block.color)
    plane_qc = QColor(*(block.plane_color if block.plane_color is not None else block.color))
    dim      = QColor(block.color[0] // 2, block.color[1] // 2, block.color[2] // 2)

    bar_block_h = 7 if block.show_plane else 3
    bar_y = bar_block_h // 2
    pos   = (w - 1) // 2  # 50 % for preview

    def put(x, y, qc):
        if not (0 <= x < w and 0 <= y < h):
            return
        for dy in range(grid_scale):
            for dx in range(grid_scale):
                img.setPixelColor(x * grid_scale + dx, y * grid_scale + dy, qc)

    # Bar — dotted remaining (every 2nd pixel) matches renderer
    if block.show_remaining:
        for i in range(w):
            if i <= pos:
                put(i, bar_y, color)
            elif i % 2 == 0:
                put(i, bar_y, dim)
    else:
        for i in range(pos + 1):
            put(i, bar_y, color)

    # Endpoints
    if block.show_endpoints:
        for ex in (0, w - 1):
            for dy_ in (-1, 0):
                for dx_ in (-1, 0, 1):
                    put(ex + dx_, bar_y + dy_, color)

    # Marker / plane — put() already clips to [0, w) so no overflow
    if block.show_plane:
        for gy, row in enumerate(_PLANE_GLYPH):
            for gx, ch in enumerate(row):
                if ch == "X":
                    put(pos + gx - 3, bar_y + gy - 3, plane_qc)
    else:
        for dx in (-1, 0, 1):
            put(pos + dx, bar_y, plane_qc)
        put(pos, bar_y - 1, plane_qc)

    return QPixmap.fromImage(img)


# ── Canvas block item ─────────────────────────────────────────────────────────

class BlockItem(QGraphicsRectItem):
    """Draggable rectangle on the canvas, with the actual bitmap-font preview."""

    def __init__(self, block: LayoutBlock, flight: Flight | None,
                 grid_scale: int, panel_w: int, panel_h: int, on_select):
        self.block = block
        self._gs = grid_scale
        self._pw = panel_w
        self._ph = panel_h
        self._on_select = on_select

        w = max(1, block.width) * grid_scale
        h = max(1, block.height) * grid_scale
        super().__init__(0, 0, w, h)

        r, g, b = block.color
        # Background tint, low opacity so the preview text is fully visible
        self.setBrush(QBrush(QColor(r, g, b, 50)))
        self.setPen(QPen(QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60)), 1))
        self.setPos(block.x * grid_scale, block.y * grid_scale)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f"{block.label}  ({block.width}×{block.height} px)")

        # Pixmap of the actual rendered content
        pixmap = self._build_pixmap(flight)
        if not pixmap.isNull():
            self._pix = QGraphicsPixmapItem(pixmap, self)
            self._pix.setPos(0, 0)

    def _build_pixmap(self, flight: Flight | None) -> QPixmap:
        block = self.block
        gs = self._gs
        if block.key == "logo":
            # No flight-dependent preview for the logo — fill with a flat box
            return QPixmap()
        if block.key == "progress":
            return _render_progress_to_pixmap(block, gs)
        if flight is None:
            text = block.effective_label + "----" + block.effective_unit
        else:
            try:
                text = render_block_text(block, flight)
            except Exception:
                text = block.effective_label + "----" + block.effective_unit
        return _render_text_to_pixmap(text, block.color, block.font_scale, gs)

    def mousePressEvent(self, event):
        if self._on_select:
            self._on_select(self.block.key)
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            x = round(value.x() / self._gs) * self._gs
            y = round(value.y() / self._gs) * self._gs
            max_x = (self._pw // self._gs - self.block.width) * self._gs
            max_y = (self._ph // self._gs - self.block.height) * self._gs
            x = max(0, min(x, max(0, max_x)))
            y = max(0, min(y, max(0, max_y)))
            return QPointF(x, y)
        return super().itemChange(change, value)

    def grid_pos(self) -> tuple:
        p = self.scenePos()
        return (round(p.x() / self._gs), round(p.y() / self._gs))


# ── Left-side row: just a checkbox you can click to select ────────────────────

class BlockRow(QWidget):
    toggled = pyqtSignal(str, bool)
    selected = pyqtSignal(str)

    def __init__(self, block: LayoutBlock, parent=None):
        super().__init__(parent)
        self.key = block.key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self.cb = QCheckBox(block.label)
        self.cb.setChecked(block.enabled)
        self._apply_color(block.color)
        self.cb.stateChanged.connect(
            lambda s: self.toggled.emit(self.key, bool(s))
        )
        self.cb.clicked.connect(lambda *_: self.selected.emit(self.key))
        lay.addWidget(self.cb)
        lay.addStretch()

    def _apply_color(self, rgb: tuple):
        r, g, b = rgb
        br = (min(255, r + 60), min(255, g + 60), min(255, b + 60))
        self.cb.setStyleSheet(
            f"QCheckBox {{ color: rgb{br}; font-weight: bold; }}"
        )

    def refresh_color(self, rgb: tuple):
        self._apply_color(rgb)

    def set_enabled(self, enabled: bool):
        self.cb.setChecked(enabled)


# ── Customization panel (below the canvas) ────────────────────────────────────

class CustomizationPanel(QGroupBox):
    color_changed   = pyqtSignal(str, tuple)
    font_changed    = pyqtSignal(str, int)
    label_changed   = pyqtSignal(str, str)
    unit_changed    = pyqtSignal(str, str)
    fmt_changed     = pyqtSignal(str, str)
    width_changed   = pyqtSignal(str, int)
    show_remaining_changed = pyqtSignal(str, bool)
    show_plane_changed     = pyqtSignal(str, bool)
    show_endpoints_changed = pyqtSignal(str, bool)
    plane_color_changed    = pyqtSignal(str, tuple)

    def __init__(self, parent=None):
        super().__init__("Customize — (select a block)", parent)
        self._block: LayoutBlock | None = None
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Row 1: format + color + font size
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        row1.addWidget(QLabel("Format:"))
        self.fmt = QComboBox()
        self.fmt.setMinimumWidth(220)
        self.fmt.currentIndexChanged.connect(self._on_fmt)
        row1.addWidget(self.fmt)

        row1.addSpacing(8)
        row1.addWidget(QLabel("Color:"))
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(28, 22)
        self.color_btn.clicked.connect(self._pick_color)
        row1.addWidget(self.color_btn)

        row1.addSpacing(8)
        row1.addWidget(QLabel("Font scale:"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(1, 10)
        self.font_spin.setSuffix("×")
        self.font_spin.valueChanged.connect(
            lambda v: self._emit(self.font_changed, int(v))
        )
        row1.addWidget(self.font_spin)
        row1.addStretch()
        root.addLayout(row1)

        # Row 2: label + unit
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Label:"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("(none)")
        self.label_edit.setMaximumWidth(140)
        self.label_edit.editingFinished.connect(self._on_label)
        row2.addWidget(self.label_edit)

        self.unit_lbl = QLabel("Unit:")
        row2.addWidget(self.unit_lbl)
        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText("(none)")
        self.unit_edit.setMaximumWidth(80)
        self.unit_edit.editingFinished.connect(self._on_unit)
        row2.addWidget(self.unit_edit)
        row2.addStretch()
        root.addLayout(row2)

        # Row 3: progress controls
        prog = QHBoxLayout()
        prog.setSpacing(8)
        prog.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(4, 256)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(
            lambda v: self._emit(self.width_changed, int(v))
        )
        prog.addWidget(self.width_spin)

        self.cb_remaining = QCheckBox("Remaining distance")
        self.cb_remaining.toggled.connect(
            lambda v: self._emit(self.show_remaining_changed, bool(v))
        )
        prog.addWidget(self.cb_remaining)

        self.cb_plane = QCheckBox("Plane marker")
        self.cb_plane.toggled.connect(
            lambda v: self._emit(self.show_plane_changed, bool(v))
        )
        prog.addWidget(self.cb_plane)

        self.plane_color_btn = QPushButton()
        self.plane_color_btn.setFixedSize(22, 18)
        self.plane_color_btn.setToolTip("Plane glyph color")
        self.plane_color_btn.clicked.connect(self._pick_plane_color)
        prog.addWidget(self.plane_color_btn)

        self.cb_endpoints = QCheckBox("Endpoint dots")
        self.cb_endpoints.toggled.connect(
            lambda v: self._emit(self.show_endpoints_changed, bool(v))
        )
        prog.addWidget(self.cb_endpoints)
        prog.addStretch()
        self._prog_widget = QWidget()
        self._prog_widget.setLayout(prog)
        root.addWidget(self._prog_widget)

    def _emit(self, signal, value):
        if self._building or self._block is None:
            return
        signal.emit(self._block.key, value)

    # ── public ────────────────────────────────────────────────────────────────

    def show_block(self, block: LayoutBlock | None):
        self._block = block
        self._building = True
        try:
            if block is None:
                self.setTitle("Customize — (select a block)")
                self.fmt.clear()
                self.label_edit.clear()
                self.unit_edit.clear()
                self._prog_widget.setVisible(False)
                return

            self.setTitle(f"Customize — {block.label}")

            self.fmt.clear()
            for spec in BLOCK_FORMATS.get(block.key, []):
                self.fmt.addItem(spec.label, spec.id)
            for i in range(self.fmt.count()):
                if self.fmt.itemData(i) == block.fmt:
                    self.fmt.setCurrentIndex(i)
                    break

            self._set_swatch(block.color)
            self.font_spin.setValue(block.font_scale)

            # Show label/unit fields only for blocks that render text
            has_label = block.has_label
            self.label_edit.parentWidget()  # no-op
            self.label_edit.setVisible(has_label)
            self.label_edit.setText(block.effective_label if has_label else "")
            # parent label widget visibility handled by layout naturally

            self.unit_lbl.setVisible(block.has_unit)
            self.unit_edit.setVisible(block.has_unit)
            self.unit_edit.setText(block.effective_unit if block.has_unit else "")

            is_prog = block.key == "progress"
            self._prog_widget.setVisible(is_prog)
            if is_prog:
                self.width_spin.setValue(block.custom_width or block.width)
                self.cb_remaining.setChecked(block.show_remaining)
                self.cb_plane.setChecked(block.show_plane)
                self.cb_endpoints.setChecked(block.show_endpoints)
                # Plane color swatch — defaults to the bar color when unset
                pc = block.plane_color if block.plane_color is not None else block.color
                self._set_plane_swatch(pc)
                self.font_spin.setEnabled(False)
            else:
                self.font_spin.setEnabled(True)
        finally:
            self._building = False

    # ── handlers ──────────────────────────────────────────────────────────────

    def _set_swatch(self, rgb: tuple):
        r, g, b = rgb
        self.color_btn.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 1px solid #555;"
        )

    def _pick_color(self):
        if self._block is None:
            return
        c = QColorDialog.getColor(QColor(*self._block.color), self, "Choose color")
        if c.isValid():
            rgb = (c.red(), c.green(), c.blue())
            self._set_swatch(rgb)
            self.color_changed.emit(self._block.key, rgb)

    def _set_plane_swatch(self, rgb: tuple):
        r, g, b = rgb
        self.plane_color_btn.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 1px solid #555;"
        )

    def _pick_plane_color(self):
        if self._block is None:
            return
        current = (self._block.plane_color
                   if self._block.plane_color is not None
                   else self._block.color)
        c = QColorDialog.getColor(QColor(*current), self, "Plane color")
        if c.isValid():
            rgb = (c.red(), c.green(), c.blue())
            self._set_plane_swatch(rgb)
            self.plane_color_changed.emit(self._block.key, rgb)

    def _on_fmt(self, _idx: int):
        fid = self.fmt.currentData()
        if fid:
            self._emit(self.fmt_changed, fid)

    def _on_label(self):
        self._emit(self.label_changed, self.label_edit.text())

    def _on_unit(self):
        self._emit(self.unit_changed, self.unit_edit.text())


# ── Main editor widget ────────────────────────────────────────────────────────

class LayoutEditorWidget(QWidget):
    layout_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list[LayoutBlock] = default_layout()
        self._items: dict[str, BlockItem] = {}
        self._rows: dict[str, BlockRow] = {}
        self._selected_key: str | None = None
        self._flight: Flight | None = None
        self._init_ui()
        self._build_canvas()
        self._populate()

    # ── public ────────────────────────────────────────────────────────────────

    def set_flight(self, flight: Flight | None):
        """Live flight whose values feed the preview rectangles."""
        self._flight = flight
        # Rebuild all canvas items so they pick up new values
        for block in self._blocks:
            if block.enabled:
                self._rebuild_item(block)

    def apply_display_size(self):
        self._build_canvas()
        for b in self._blocks:
            b.x = max(0, min(b.x, max(0, self._W - b.width)))
            b.y = max(0, min(b.y, max(0, self._H - b.height)))
        self._populate()
        self._emit()

    def get_layout(self):
        self._sync_positions()
        return list(self._blocks)

    # ── construction ──────────────────────────────────────────────────────────

    def _init_ui(self):
        self._root = QHBoxLayout(self)
        self._root.setContentsMargins(8, 8, 8, 8)
        self._root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(220)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.setSpacing(0)
        ctrl_layout.addWidget(QLabel("Enable + click to customize:"))
        ctrl_layout.addSpacing(4)

        for key, _label, _color in BLOCK_TYPES:
            block = next((b for b in self._blocks if b.key == key), None)
            if block is None:
                block = LayoutBlock(key, 0, 0, False)
                self._blocks.append(block)
            row = BlockRow(block)
            row.toggled.connect(self._on_toggle)
            row.selected.connect(self._on_select)
            ctrl_layout.addWidget(row)
            self._rows[key] = row

        ctrl_layout.addStretch()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset)
        ctrl_layout.addWidget(reset_btn)
        scroll.setWidget(ctrl_widget)
        self._root.addWidget(scroll)

        right = QVBoxLayout()
        right.setSpacing(10)
        self._canvas_container = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self._canvas_container)

        self._custom = CustomizationPanel()
        self._custom.color_changed.connect(self._on_color)
        self._custom.font_changed.connect(self._on_font)
        self._custom.label_changed.connect(self._on_label)
        self._custom.unit_changed.connect(self._on_unit)
        self._custom.fmt_changed.connect(self._on_format)
        self._custom.width_changed.connect(self._on_width)
        self._custom.show_remaining_changed.connect(self._on_show_remaining)
        self._custom.show_plane_changed.connect(self._on_show_plane)
        self._custom.show_endpoints_changed.connect(self._on_show_endpoints)
        self._custom.plane_color_changed.connect(self._on_plane_color)
        right.addWidget(self._custom)

        right_container = QWidget()
        right_container.setLayout(right)
        self._root.addWidget(right_container, 1)

        self._scene = None
        self._view = None

    def _build_canvas(self):
        W, H = get_display_size()
        self._W, self._H = W, H
        self._GS = _grid_scale_for(W, H)
        self._PW = W * self._GS
        self._PH = H * self._GS

        if self._view is not None:
            self._canvas_layout.removeWidget(self._view)
            self._view.deleteLater()
            self._view = None
            self._scene = None
            self._items.clear()

        self._scene = QGraphicsScene(0, 0, self._PW, self._PH)
        self._draw_grid()
        self._view = QGraphicsView(self._scene)
        self._view.setBackgroundBrush(QBrush(QColor(12, 12, 12)))
        self._view.setFrameShape(QGraphicsView.Shape.Box)
        self._view.setFixedSize(self._PW + 4, self._PH + 4)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.mouseReleaseEvent = self._view_mouse_release
        self._canvas_layout.addWidget(self._view)

    def _draw_grid(self):
        pen_major = QPen(QColor(45, 45, 45), 0.5)
        pen_minor = QPen(QColor(28, 28, 28), 0.3)
        for x in range(0, self._PW + 1, self._GS):
            pen = pen_major if (x // self._GS) % 8 == 0 else pen_minor
            self._scene.addLine(x, 0, x, self._PH, pen)
        for y in range(0, self._PH + 1, self._GS):
            pen = pen_major if (y // self._GS) % 8 == 0 else pen_minor
            self._scene.addLine(0, y, self._PW, y, pen)
        self._scene.addRect(0, 0, self._PW, self._PH, QPen(QColor(90, 90, 90), 1.5))

        font = QFont("Courier New", 4)
        step = 10 if self._W <= 128 else 20
        for x in range(0, self._W + 1, step):
            t = self._scene.addText(str(x), font)
            t.setDefaultTextColor(QColor(55, 55, 55))
            t.setPos(x * self._GS - 5, -10)
        for y in range(0, self._H + 1, step):
            t = self._scene.addText(str(y), font)
            t.setDefaultTextColor(QColor(55, 55, 55))
            t.setPos(-18, y * self._GS - 5)

    def _populate(self):
        for item in list(self._items.values()):
            self._scene.removeItem(item)
        self._items.clear()
        for block in self._blocks:
            if block.enabled:
                item = BlockItem(block, self._flight, self._GS, self._PW, self._PH,
                                 self._on_select)
                self._scene.addItem(item)
                self._items[block.key] = item

    def _rebuild_item(self, block: LayoutBlock):
        old = self._items.get(block.key)
        if old:
            gx, gy = old.grid_pos()
            block.x, block.y = gx, gy
            self._scene.removeItem(old)
            del self._items[block.key]
        # Clamp position to new dimensions
        block.x = max(0, min(block.x, max(0, self._W - block.width)))
        block.y = max(0, min(block.y, max(0, self._H - block.height)))
        if block.enabled:
            item = BlockItem(block, self._flight, self._GS, self._PW, self._PH,
                             self._on_select)
            self._scene.addItem(item)
            self._items[block.key] = item

    # ── handlers: from left list ──────────────────────────────────────────────

    def _on_toggle(self, key: str, enabled: bool):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None:
            return
        block.enabled = enabled
        if enabled:
            self._rebuild_item(block)
            self._on_select(key)
        else:
            if key in self._items:
                self._scene.removeItem(self._items.pop(key))
            if self._selected_key == key:
                self._selected_key = None
                self._custom.show_block(None)
        self._emit()

    def _on_select(self, key: str):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None or not block.enabled:
            return
        self._selected_key = key
        self._custom.show_block(block)

    # ── handlers: from customization panel ────────────────────────────────────

    def _on_color(self, key: str, rgb: tuple):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.custom_color = rgb
        if key in self._rows:
            self._rows[key].refresh_color(rgb)
        self._rebuild_item(block)
        self._emit()

    def _on_font(self, key: str, scale: int):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.font_scale = max(1, int(scale))
        self._rebuild_item(block)
        self._emit()

    def _on_label(self, key: str, text: str):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.custom_label = text
        self._rebuild_item(block)
        self._emit()

    def _on_unit(self, key: str, text: str):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.custom_unit = text
        self._rebuild_item(block)
        self._emit()

    def _on_format(self, key: str, fmt_id: str):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.fmt = fmt_id
        # If the user hasn't customized label/unit, repaint the inputs with the
        # new format's natural defaults
        spec = _format_for(key, fmt_id)
        if spec is not None and self._selected_key == key:
            # Pull current effective values into the input fields
            self._custom.show_block(block)
        self._rebuild_item(block)
        self._emit()

    def _on_width(self, key: str, w: int):
        block = next((b for b in self._blocks if b.key == key), None)
        if block is None: return
        block.custom_width = w
        self._rebuild_item(block)
        self._emit()

    def _on_show_remaining(self, key: str, v: bool):
        b = next((b for b in self._blocks if b.key == key), None)
        if b is None: return
        b.show_remaining = v
        self._rebuild_item(b)
        self._emit()

    def _on_show_plane(self, key: str, v: bool):
        b = next((b for b in self._blocks if b.key == key), None)
        if b is None: return
        b.show_plane = v
        self._rebuild_item(b)
        self._emit()

    def _on_show_endpoints(self, key: str, v: bool):
        b = next((b for b in self._blocks if b.key == key), None)
        if b is None: return
        b.show_endpoints = v
        self._rebuild_item(b)
        self._emit()

    def _on_plane_color(self, key: str, rgb: tuple):
        b = next((b for b in self._blocks if b.key == key), None)
        if b is None: return
        b.plane_color = rgb
        self._rebuild_item(b)
        self._emit()

    # ── reset / shared ────────────────────────────────────────────────────────

    def set_layout(self, blocks: list[LayoutBlock]) -> None:
        """Restore an external layout without emitting layout_changed."""
        from src.core.models import BLOCK_TYPES
        self._blocks = list(blocks)
        # Ensure every known block type is present (add disabled stubs for missing ones)
        existing = {b.key for b in self._blocks}
        for key, _label, _color in BLOCK_TYPES:
            if key not in existing:
                self._blocks.append(LayoutBlock(key, 0, 0, False))
        for key, row in self._rows.items():
            block = next((b for b in self._blocks if b.key == key), None)
            if block:
                row.set_enabled(block.enabled)
                row.refresh_color(block.color)
        self._selected_key = None
        self._custom.show_block(None)
        self._populate()

    def _reset(self):
        self._blocks = default_layout()
        for row in self._rows.values():
            block = next((b for b in self._blocks if b.key == row.key), None)
            if block:
                row.set_enabled(block.enabled)
                row.refresh_color(block.color)
        self._selected_key = None
        self._custom.show_block(None)
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
