from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


DARK_QSS = """
QWidget { background: #232629; color: #dcdcdc; }
QMenuBar, QMenu { background: #2b2b2b; color: #dcdcdc; }
QMenu::item:selected, QMenuBar::item:selected { background: #3a5a40; }
QTableWidget { gridline-color: #555; background: #1e1e1e; }
QHeaderView::section { background: #2b2b2b; color: #dcdcdc; padding: 4px; border: 1px solid #444; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget, QListView, QTableView {
    background: #1e1e1e; color: #dcdcdc; border: 1px solid #444; padding: 2px;
}
QPushButton { background: #3a5a40; color: white; border: 1px solid #2d4730; padding: 5px 12px; border-radius: 3px; }
QPushButton:disabled { background: #444; color: #888; }
QDockWidget::title { background: #2b2b2b; padding: 4px; }
QStatusBar { background: #2b2b2b; color: #dcdcdc; }
QToolBar { background: #2b2b2b; border: none; }
QTabBar::tab { background: #2b2b2b; color: #dcdcdc; padding: 6px 12px; border: 1px solid #444; }
QTabBar::tab:selected { background: #3a5a40; }
"""


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Audi EDC17 map editor")
    app.setStyleSheet(DARK_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
