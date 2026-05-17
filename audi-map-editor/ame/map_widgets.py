from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .binfile import BinFile
from .mapdef import MapDef


def _value_to_color(v: float, lo: float, hi: float) -> QColor:
    if hi <= lo:
        return QColor("#2b2b2b")
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    # blue -> green -> yellow -> red, dimmed
    if t < 0.5:
        f = t / 0.5
        r = int(40 + f * (180 - 40))
        g = int(120 + f * (200 - 120))
        b = int(180 - f * (180 - 80))
    else:
        f = (t - 0.5) / 0.5
        r = int(180 + f * (220 - 180))
        g = int(200 - f * (200 - 80))
        b = int(80 - f * (80 - 40))
    return QColor(r, g, b)


class MapTable(QWidget):
    """Editable table widget with heatmap colouring and axis headers."""

    valueChanged = Signal(int, int, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(self)
        self.table.itemChanged.connect(self._on_item_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        self._suspend = False
        self._values: np.ndarray | None = None

    def load(self, values: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray, fmt: str = "{:.2f}") -> None:
        self._suspend = True
        self._values = values.astype(np.float64, copy=True)
        rows, cols = self._values.shape
        self.table.clear()
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        if x_axis.size == cols:
            self.table.setHorizontalHeaderLabels([fmt.format(float(v)) for v in x_axis])
        if y_axis.size == rows:
            self.table.setVerticalHeaderLabels([fmt.format(float(v)) for v in y_axis])
        lo, hi = float(self._values.min()), float(self._values.max())
        for r in range(rows):
            for c in range(cols):
                v = float(self._values[r, c])
                item = QTableWidgetItem(fmt.format(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(QBrush(_value_to_color(v, lo, hi)))
                item.setForeground(QBrush(QColor("#111")))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self._suspend = False

    def values(self) -> np.ndarray | None:
        return None if self._values is None else self._values.copy()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend or self._values is None:
            return
        try:
            v = float(item.text().replace(",", "."))
        except ValueError:
            r, c = item.row(), item.column()
            item.setText(f"{self._values[r, c]:.2f}")
            return
        r, c = item.row(), item.column()
        self._values[r, c] = v
        lo, hi = float(self._values.min()), float(self._values.max())
        self._suspend = True
        for rr in range(self._values.shape[0]):
            for cc in range(self._values.shape[1]):
                it = self.table.item(rr, cc)
                if it is not None:
                    it.setBackground(QBrush(_value_to_color(float(self._values[rr, cc]), lo, hi)))
        self._suspend = False
        self.valueChanged.emit(r, c, v)


class MapSurface(QWidget):
    """3D surface plot (matplotlib) — read-only visual aid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 4), facecolor="#1e1e1e")
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self._ax = None

    def plot(self, values: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray, title: str = "") -> None:
        self.figure.clear()
        rows, cols = values.shape
        if rows <= 1 or cols <= 1:
            ax = self.figure.add_subplot(111, facecolor="#1e1e1e")
            xs = x_axis if cols > 1 else y_axis
            ys = values.flatten()
            if xs.size != ys.size:
                xs = np.arange(ys.size)
            ax.plot(xs, ys, color="#f0a060", marker="o")
            ax.set_title(title, color="#dcdcdc")
            ax.tick_params(colors="#dcdcdc")
            for spine in ax.spines.values():
                spine.set_color("#888")
        else:
            ax = self.figure.add_subplot(111, projection="3d", facecolor="#1e1e1e")
            xa = x_axis if x_axis.size == cols else np.arange(cols)
            ya = y_axis if y_axis.size == rows else np.arange(rows)
            X, Y = np.meshgrid(xa, ya)
            ax.plot_surface(X, Y, values, cmap="viridis", edgecolor="none", alpha=0.95)
            ax.set_title(title, color="#dcdcdc")
            ax.tick_params(colors="#dcdcdc")
            for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
                axis.label.set_color("#dcdcdc")
        self.figure.tight_layout()
        self.canvas.draw_idle()


class MapEditor(QWidget):
    """Top-level widget combining heatmap table and 3D plot for one map."""

    valuesChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._map: MapDef | None = None
        self._binf: BinFile | None = None
        self._cached_x: np.ndarray | None = None
        self._cached_y: np.ndarray | None = None

        self.title = QLabel("(no map selected)")
        self.title.setStyleSheet("font-weight: bold; padding: 4px;")
        self.table = MapTable(self)
        self.surface = MapSurface(self)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self.table)
        splitter.addWidget(self.surface)
        splitter.setSizes([260, 280])

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.addWidget(self.title)
        root.addWidget(splitter, 1)

        self.table.valueChanged.connect(self._on_cell_edited)

    def load(self, binf: BinFile, mapdef: MapDef) -> None:
        self._binf = binf
        self._map = mapdef
        values = mapdef.read(binf)
        x = mapdef.x_axis.read(binf) if mapdef.x_axis.count else np.arange(values.shape[1])
        y = mapdef.y_axis.read(binf) if mapdef.y_axis.count else np.arange(values.shape[0])
        self._cached_x = x
        self._cached_y = y
        fmt = "{:.0f}" if mapdef.dtype.startswith(("uint", "int")) and mapdef.factor == 1.0 else "{:.2f}"
        self.title.setText(
            f"{mapdef.name}  @ 0x{mapdef.address:06X}  "
            f"({mapdef.rows}x{mapdef.cols} {mapdef.dtype}, factor {mapdef.factor})"
        )
        self.table.load(values, x, y, fmt=fmt)
        self.surface.plot(values, x, y, title=mapdef.name)

    def refresh_plot(self) -> None:
        if self._map is None or self._binf is None:
            return
        values = self.table.values()
        if values is None:
            return
        self.surface.plot(values, self._cached_x, self._cached_y, title=self._map.name)

    def _on_cell_edited(self, row: int, col: int, value: float) -> None:
        if self._binf is None or self._map is None:
            return
        cell_index = row * self._map.cols + col
        item_size = self._map.cols * self._map.rows
        if cell_index >= item_size:
            return
        # write a single cell back
        from .binfile import dtype_size
        addr = self._map.address + cell_index * dtype_size(self._map.dtype)
        raw = (value - self._map.offset) / (self._map.factor if self._map.factor else 1.0)
        self._binf.write_value(addr, raw, self._map.dtype, self._map.big_endian)
        self.refresh_plot()
        self.valuesChanged.emit()
