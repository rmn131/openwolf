from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from .binfile import BinFile, DTYPE_FORMATS
from .mapdef import AxisDef, MapDef
from .scanner import AxisHit, MapHit, scan


def _hex_field(value: int = 0) -> QLineEdit:
    field = QLineEdit(f"0x{value:X}")
    field.setPlaceholderText("0x340000")
    return field


def _parse_int(text: str, default: int = 0) -> int:
    text = text.strip().replace("_", "")
    if not text:
        return default
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text)
    except ValueError:
        return default


class AxisForm(QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.address = _hex_field(0)
        self.count = QLineEdit("0")
        self.count.setValidator(QIntValidator(0, 1024))
        self.dtype = QComboBox()
        for name in DTYPE_FORMATS:
            self.dtype.addItem(name)
        self.dtype.setCurrentText("uint16")
        self.be = QCheckBox("big-endian")
        self.factor = QLineEdit("1.0")
        self.offset = QLineEdit("0.0")
        self.units = QLineEdit("")

        form = QFormLayout(self)
        form.addRow("address", self.address)
        form.addRow("count", self.count)
        form.addRow("type", self.dtype)
        form.addRow("", self.be)
        form.addRow("factor", self.factor)
        form.addRow("offset", self.offset)
        form.addRow("units", self.units)

    def load(self, axis: AxisDef) -> None:
        self.address.setText(f"0x{axis.address:X}")
        self.count.setText(str(axis.count))
        self.dtype.setCurrentText(axis.dtype)
        self.be.setChecked(axis.big_endian)
        self.factor.setText(str(axis.factor))
        self.offset.setText(str(axis.offset))
        self.units.setText(axis.units)

    def to_axis(self) -> AxisDef:
        return AxisDef(
            address=_parse_int(self.address.text()),
            count=_parse_int(self.count.text()),
            dtype=self.dtype.currentText(),
            big_endian=self.be.isChecked(),
            factor=float(self.factor.text().replace(",", ".") or "1") or 1.0,
            offset=float(self.offset.text().replace(",", ".") or "0"),
            units=self.units.text(),
        )


class MapDefDialog(QDialog):
    def __init__(self, mapdef: MapDef | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Map definition")
        self.resize(700, 520)

        self.name = QLineEdit()
        self.address = _hex_field(0)
        self.rows = QLineEdit("1")
        self.cols = QLineEdit("1")
        self.dtype = QComboBox()
        for name in DTYPE_FORMATS:
            self.dtype.addItem(name)
        self.dtype.setCurrentText("uint16")
        self.be = QCheckBox("big-endian")
        self.factor = QLineEdit("1.0")
        self.offset = QLineEdit("0.0")
        self.units = QLineEdit()
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)

        body = QFormLayout()
        body.addRow("name", self.name)
        body.addRow("data address", self.address)
        body.addRow("rows (Y)", self.rows)
        body.addRow("cols (X)", self.cols)
        body.addRow("data type", self.dtype)
        body.addRow("", self.be)
        body.addRow("factor", self.factor)
        body.addRow("offset", self.offset)
        body.addRow("units", self.units)
        body.addRow("notes", self.notes)

        self.x_form = AxisForm("X axis")
        self.y_form = AxisForm("Y axis")

        axes_layout = QHBoxLayout()
        axes_layout.addWidget(self.x_form)
        axes_layout.addWidget(self.y_form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(body)
        root.addLayout(axes_layout)
        root.addWidget(btns)

        if mapdef is not None:
            self.load(mapdef)

    def load(self, m: MapDef) -> None:
        self.name.setText(m.name)
        self.address.setText(f"0x{m.address:X}")
        self.rows.setText(str(m.rows))
        self.cols.setText(str(m.cols))
        self.dtype.setCurrentText(m.dtype)
        self.be.setChecked(m.big_endian)
        self.factor.setText(str(m.factor))
        self.offset.setText(str(m.offset))
        self.units.setText(m.units)
        self.notes.setPlainText(m.notes)
        self.x_form.load(m.x_axis)
        self.y_form.load(m.y_axis)

    def to_mapdef(self) -> MapDef:
        return MapDef(
            name=self.name.text() or "unnamed",
            address=_parse_int(self.address.text()),
            rows=max(1, _parse_int(self.rows.text(), 1)),
            cols=max(1, _parse_int(self.cols.text(), 1)),
            dtype=self.dtype.currentText(),
            big_endian=self.be.isChecked(),
            factor=float(self.factor.text().replace(",", ".") or "1") or 1.0,
            offset=float(self.offset.text().replace(",", ".") or "0"),
            units=self.units.text(),
            notes=self.notes.toPlainText(),
            x_axis=self.x_form.to_axis(),
            y_axis=self.y_form.to_axis(),
        )


class ScannerDialog(QDialog):
    """Range-scan dialog: pick a region, scan, browse axis/map candidates."""

    mapAccepted = Signal(MapDef)
    axisAccepted = Signal(AxisDef, str)   # axis + which (x/y)

    def __init__(self, binf: BinFile, default_range: tuple[int, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Map / axis scanner")
        self.resize(900, 600)
        self._binf = binf
        self._axes: list[AxisHit] = []
        self._maps: list[MapHit] = []

        self.start = _hex_field(default_range[0])
        self.end = _hex_field(default_range[1])
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._do_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Start"))
        controls.addWidget(self.start)
        controls.addWidget(QLabel("End"))
        controls.addWidget(self.end)
        controls.addWidget(self.scan_btn)
        controls.addStretch(1)

        self.maps_table = QTableWidget(0, 6)
        self.maps_table.setHorizontalHeaderLabels(["data addr", "rows", "cols", "type", "score", "axes"])
        self.maps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.maps_table.setSelectionBehavior(self.maps_table.SelectionBehavior.SelectRows)

        self.axes_list = QListWidget()

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(120)
        self.preview.setStyleSheet("font-family: monospace;")

        add_map_btn = QPushButton("Add selected map to project")
        add_map_btn.clicked.connect(self._emit_map)
        add_x_btn = QPushButton("Use axis as X axis")
        add_x_btn.clicked.connect(lambda: self._emit_axis("x"))
        add_y_btn = QPushButton("Use axis as Y axis")
        add_y_btn.clicked.connect(lambda: self._emit_axis("y"))

        action_row = QHBoxLayout()
        action_row.addWidget(add_map_btn)
        action_row.addWidget(add_x_btn)
        action_row.addWidget(add_y_btn)
        action_row.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(controls)
        root.addWidget(self.progress)
        root.addWidget(QLabel("Map candidates:"))
        root.addWidget(self.maps_table, 2)
        root.addWidget(QLabel("Axis candidates (also useful by themselves):"))
        root.addWidget(self.axes_list, 1)
        root.addWidget(QLabel("Preview:"))
        root.addWidget(self.preview)
        root.addLayout(action_row)

        self.maps_table.itemSelectionChanged.connect(self._on_map_selected)
        self.axes_list.itemSelectionChanged.connect(self._on_axis_selected)

    def _do_scan(self) -> None:
        self.progress.setVisible(True)
        self.scan_btn.setEnabled(False)
        s = _parse_int(self.start.text())
        e = _parse_int(self.end.text())
        if e <= s:
            e = min(self._binf.size, s + 0x10000)
        self._axes, self._maps = scan(self._binf, s, e)
        self._populate()
        self.scan_btn.setEnabled(True)
        self.progress.setVisible(False)

    def _populate(self) -> None:
        self.maps_table.setRowCount(0)
        for m in self._maps[:300]:
            row = self.maps_table.rowCount()
            self.maps_table.insertRow(row)
            self.maps_table.setItem(row, 0, QTableWidgetItem(f"0x{m.address:06X}"))
            self.maps_table.setItem(row, 1, QTableWidgetItem(str(m.rows)))
            self.maps_table.setItem(row, 2, QTableWidgetItem(str(m.cols)))
            self.maps_table.setItem(row, 3, QTableWidgetItem(m.dtype))
            self.maps_table.setItem(row, 4, QTableWidgetItem(f"{m.score:.2f}"))
            xa = f"X@0x{m.x_axis.address:06X}/{m.x_axis.count}" if m.x_axis else ""
            ya = f"Y@0x{m.y_axis.address:06X}/{m.y_axis.count}" if m.y_axis else ""
            self.maps_table.setItem(row, 5, QTableWidgetItem(f"{xa}  {ya}"))

        self.axes_list.clear()
        for a in self._axes[:600]:
            item = QListWidgetItem(a.describe())
            item.setData(Qt.ItemDataRole.UserRole, a)
            self.axes_list.addItem(item)

    def _selected_map(self) -> MapHit | None:
        row = self.maps_table.currentRow()
        if 0 <= row < len(self._maps):
            return self._maps[row]
        return None

    def _selected_axis(self) -> AxisHit | None:
        item = self.axes_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_map_selected(self) -> None:
        m = self._selected_map()
        if not m:
            return
        try:
            arr = self._binf.read_array(m.address, m.rows * m.cols, m.dtype)
            sample = arr[: min(arr.size, 12)]
        except Exception as exc:
            self.preview.setPlainText(f"read error: {exc}")
            return
        x_vals = m.x_axis.values if m.x_axis else None
        y_vals = m.y_axis.values if m.y_axis else None
        lines = [
            f"data @ 0x{m.address:06X}  {m.rows}x{m.cols}  {m.dtype}",
            f"first cells: {sample.tolist()}",
        ]
        if x_vals is not None:
            lines.append(f"X axis @ 0x{m.x_axis.address:06X}: {x_vals.tolist()}")
        if y_vals is not None:
            lines.append(f"Y axis @ 0x{m.y_axis.address:06X}: {y_vals.tolist()}")
        self.preview.setPlainText("\n".join(lines))

    def _on_axis_selected(self) -> None:
        a = self._selected_axis()
        if a is None:
            return
        self.preview.setPlainText(f"axis @ 0x{a.address:06X} ({a.count} {a.dtype}): {a.values.tolist()}")

    def _emit_map(self) -> None:
        m = self._selected_map()
        if not m:
            return
        x_ax = AxisDef(
            address=m.x_axis.address,
            count=m.x_axis.count,
            dtype=m.x_axis.dtype,
            big_endian=m.x_axis.big_endian,
        ) if m.x_axis else AxisDef()
        y_ax = AxisDef(
            address=m.y_axis.address,
            count=m.y_axis.count,
            dtype=m.y_axis.dtype,
            big_endian=m.y_axis.big_endian,
        ) if m.y_axis else AxisDef()
        mapdef = MapDef(
            name=f"map_{m.address:06X}",
            address=m.address,
            rows=m.rows,
            cols=m.cols,
            dtype=m.dtype,
            big_endian=m.big_endian,
            x_axis=x_ax,
            y_axis=y_ax,
            notes=f"auto-detected, score {m.score:.2f}",
        )
        self.mapAccepted.emit(mapdef)

    def _emit_axis(self, which: str) -> None:
        a = self._selected_axis()
        if a is None:
            return
        ax = AxisDef(
            address=a.address,
            count=a.count,
            dtype=a.dtype,
            big_endian=a.big_endian,
        )
        self.axisAccepted.emit(ax, which)
