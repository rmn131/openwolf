from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QToolBar,
    QWidget,
)

from .binfile import BinFile, dtype_size
from .dialogs import MapDefDialog, ScannerDialog
from .edc17 import EcuInfo, identify
from .hex_view import HexView
from .map_widgets import MapEditor
from .mapdef import MapDef, Project


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Audi EDC17 map editor")
        self.resize(1400, 900)

        self.binf: BinFile | None = None
        self.project: Project = Project()
        self.project_path: Path | None = None
        self.ecu: EcuInfo | None = None

        self._build_central()
        self._build_docks()
        self._build_menu()
        self._refresh_actions()

    # --- UI construction -----------------------------------------------------

    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.map_editor = MapEditor()
        self.hex_view = HexView()
        self.tabs.addTab(self.map_editor, "Map editor")
        self.tabs.addTab(self.hex_view, "Hex view")
        self.setCentralWidget(self.tabs)
        self.map_editor.valuesChanged.connect(self._on_map_dirty)

    def _build_docks(self) -> None:
        self.map_list = QListWidget()
        self.map_list.itemActivated.connect(self._open_selected_map)
        self.map_list.itemSelectionChanged.connect(self._sync_hex_to_selection)

        dock = QDockWidget("Maps", self)
        dock.setWidget(self.map_list)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        self.info_view = QPlainTextEdit()
        self.info_view.setReadOnly(True)
        info_dock = QDockWidget("ECU info", self)
        info_dock.setWidget(self.info_view)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, info_dock)
        self.splitDockWidget(dock, info_dock, Qt.Orientation.Vertical)

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self.act_open_bin = QAction("Open .bin…", self, shortcut=QKeySequence.StandardKey.Open)
        self.act_open_bin.triggered.connect(self.open_bin)
        file_menu.addAction(self.act_open_bin)

        self.act_save_bin = QAction("Save .bin", self, shortcut=QKeySequence.StandardKey.Save)
        self.act_save_bin.triggered.connect(self.save_bin)
        file_menu.addAction(self.act_save_bin)

        self.act_save_bin_as = QAction("Save .bin as…", self)
        self.act_save_bin_as.triggered.connect(self.save_bin_as)
        file_menu.addAction(self.act_save_bin_as)

        file_menu.addSeparator()

        self.act_open_project = QAction("Open project…", self)
        self.act_open_project.triggered.connect(self.open_project)
        file_menu.addAction(self.act_open_project)

        self.act_save_project = QAction("Save project", self)
        self.act_save_project.triggered.connect(self.save_project)
        file_menu.addAction(self.act_save_project)

        self.act_save_project_as = QAction("Save project as…", self)
        self.act_save_project_as.triggered.connect(self.save_project_as)
        file_menu.addAction(self.act_save_project_as)

        file_menu.addSeparator()
        quit_act = QAction("Quit", self, shortcut=QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        map_menu = bar.addMenu("&Map")
        self.act_add_map = QAction("Add map…", self)
        self.act_add_map.triggered.connect(self.add_map)
        map_menu.addAction(self.act_add_map)
        self.act_edit_map = QAction("Edit selected…", self)
        self.act_edit_map.triggered.connect(self.edit_selected_map)
        map_menu.addAction(self.act_edit_map)
        self.act_del_map = QAction("Delete selected", self)
        self.act_del_map.triggered.connect(self.delete_selected_map)
        map_menu.addAction(self.act_del_map)

        tools_menu = bar.addMenu("&Tools")
        self.act_scan = QAction("Scan for maps / axes…", self)
        self.act_scan.triggered.connect(self.open_scanner)
        tools_menu.addAction(self.act_scan)
        self.act_identify = QAction("Re-identify ECU", self)
        self.act_identify.triggered.connect(self.identify_ecu)
        tools_menu.addAction(self.act_identify)

        toolbar = QToolBar()
        self.addToolBar(toolbar)
        toolbar.addAction(self.act_open_bin)
        toolbar.addAction(self.act_save_bin)
        toolbar.addSeparator()
        toolbar.addAction(self.act_scan)
        toolbar.addAction(self.act_add_map)
        toolbar.addAction(self.act_edit_map)

    # --- file ops ------------------------------------------------------------

    def open_bin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open firmware", "",
            "Firmware binaries (*.bin *.ori *.frf *.hex *.s19);;All files (*.*)",
        )
        if not path:
            return
        try:
            self.binf = BinFile.load(path)
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.project = Project(bin_path=path)
        self.project_path = None
        self.identify_ecu()
        self.hex_view.set_data(bytes(self.binf.data), 0)
        self._refresh_map_list()
        self._refresh_actions()
        self.statusBar().showMessage(f"Loaded {path} ({self.binf.size} bytes)")

    def save_bin(self) -> None:
        if self.binf is None:
            return
        try:
            target = self.binf.save()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {target}")

    def save_bin_as(self) -> None:
        if self.binf is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save firmware as", "", "Binary (*.bin);;All files (*.*)")
        if not path:
            return
        try:
            self.binf.save(path)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.project.bin_path = path
        self.statusBar().showMessage(f"Saved {path}")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "AME project (*.ame.json);;All (*.*)")
        if not path:
            return
        try:
            self.project = Project.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.project_path = Path(path)
        if self.project.bin_path and Path(self.project.bin_path).is_file():
            self.binf = BinFile.load(self.project.bin_path)
            self.identify_ecu()
            self.hex_view.set_data(bytes(self.binf.data), 0)
        self._refresh_map_list()
        self._refresh_actions()

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        try:
            self.project.save(self.project_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved project {self.project_path}")

    def save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", "project.ame.json", "AME project (*.ame.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.save_project()

    # --- map list ------------------------------------------------------------

    def _refresh_map_list(self) -> None:
        self.map_list.clear()
        for idx, m in enumerate(self.project.maps):
            label = f"{m.name}   [{m.rows}x{m.cols} {m.dtype} @ 0x{m.address:06X}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.map_list.addItem(item)

    def _selected_index(self) -> int | None:
        item = self.map_list.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _open_selected_map(self) -> None:
        idx = self._selected_index()
        if idx is None or self.binf is None:
            return
        try:
            self.map_editor.load(self.binf, self.project.maps[idx])
        except (IndexError, ValueError) as exc:
            QMessageBox.warning(self, "Bad map", f"could not load map: {exc}")
            return
        self.tabs.setCurrentWidget(self.map_editor)

    def _sync_hex_to_selection(self) -> None:
        idx = self._selected_index()
        if idx is None or self.binf is None:
            return
        m = self.project.maps[idx]
        size = m.rows * m.cols * dtype_size(m.dtype)
        self.hex_view.set_highlight(m.address, size)

    def add_map(self) -> None:
        if self.binf is None:
            return
        dlg = MapDefDialog(parent=self)
        if dlg.exec():
            self.project.maps.append(dlg.to_mapdef())
            self._refresh_map_list()

    def edit_selected_map(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        dlg = MapDefDialog(self.project.maps[idx], parent=self)
        if dlg.exec():
            self.project.maps[idx] = dlg.to_mapdef()
            self._refresh_map_list()
            self.map_list.setCurrentRow(idx)
            self._open_selected_map()

    def delete_selected_map(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self.project.maps[idx]
        self._refresh_map_list()

    # --- tools ---------------------------------------------------------------

    def identify_ecu(self) -> None:
        if self.binf is None:
            return
        self.ecu = identify(self.binf)
        self.project.ecu = self.ecu.variant
        self.info_view.setPlainText(self.ecu.summary() or "(no ECU markers found)")

    def open_scanner(self) -> None:
        if self.binf is None:
            return
        default = (0x340000, min(self.binf.size, 0x400000))
        if self.ecu and self.ecu.data_block:
            default = self.ecu.data_block
        dlg = ScannerDialog(self.binf, default, parent=self)
        dlg.mapAccepted.connect(self._on_scanner_map)
        dlg.axisAccepted.connect(self._on_scanner_axis)
        dlg.exec()

    def _on_scanner_map(self, mapdef: MapDef) -> None:
        self.project.maps.append(mapdef)
        self._refresh_map_list()
        self.map_list.setCurrentRow(len(self.project.maps) - 1)

    def _on_scanner_axis(self, axis, which: str) -> None:
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "No map selected", "Select a map in the list first.")
            return
        m = self.project.maps[idx]
        if which == "x":
            m.x_axis = axis
        else:
            m.y_axis = axis
        self._refresh_map_list()
        self.map_list.setCurrentRow(idx)

    # --- misc ----------------------------------------------------------------

    def _on_map_dirty(self) -> None:
        if self.binf is None:
            return
        self.hex_view.set_data(bytes(self.binf.data), 0)
        self._sync_hex_to_selection()
        title = "Audi EDC17 map editor"
        if self.binf.modified:
            title += " *"
        self.setWindowTitle(title)

    def _refresh_actions(self) -> None:
        has_bin = self.binf is not None
        for a in (self.act_save_bin, self.act_save_bin_as, self.act_add_map,
                  self.act_scan, self.act_identify):
            a.setEnabled(has_bin)
