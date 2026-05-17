from __future__ import annotations

from PySide6.QtCore import QAbstractScrollArea, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QAbstractScrollArea, QWidget


class HexView(QAbstractScrollArea):
    """A minimal read-only hex viewer with byte-level highlight support."""

    addressClicked = Signal(int)

    BYTES_PER_ROW = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: bytes = b""
        self._base_address: int = 0
        self._highlight: tuple[int, int] | None = None  # (start, length)

        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)

        self._update_metrics()
        self.viewport().setAutoFillBackground(True)
        pal = self.viewport().palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#dcdcdc"))
        self.viewport().setPalette(pal)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def set_data(self, data: bytes, base_address: int = 0) -> None:
        self._data = bytes(data) if not isinstance(data, (bytes, bytearray)) else bytes(data)
        self._base_address = base_address
        self._highlight = None
        self._update_scroll()
        self.viewport().update()

    def set_highlight(self, address: int, length: int) -> None:
        self._highlight = (address - self._base_address, length)
        self.scroll_to_address(address)
        self.viewport().update()

    def clear_highlight(self) -> None:
        self._highlight = None
        self.viewport().update()

    def scroll_to_address(self, address: int) -> None:
        rel = max(0, address - self._base_address)
        row = rel // self.BYTES_PER_ROW
        first_visible = self.verticalScrollBar().value()
        rows_on_screen = max(1, self.viewport().height() // self._row_h)
        if row < first_visible or row >= first_visible + rows_on_screen:
            self.verticalScrollBar().setValue(max(0, row - 2))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll()

    def _update_metrics(self) -> None:
        fm = QFontMetrics(self.font())
        self._char_w = fm.horizontalAdvance("0")
        self._row_h = fm.height() + 2
        self._addr_w = self._char_w * 9      # "00000000 "
        self._byte_w = self._char_w * 3      # "FF "
        self._ascii_x = self._addr_w + self._byte_w * self.BYTES_PER_ROW + self._char_w * 2

    def _update_scroll(self) -> None:
        total_rows = (len(self._data) + self.BYTES_PER_ROW - 1) // self.BYTES_PER_ROW
        rows_on_screen = max(1, self.viewport().height() // self._row_h)
        self.verticalScrollBar().setRange(0, max(0, total_rows - rows_on_screen))
        self.verticalScrollBar().setPageStep(rows_on_screen)

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        painter.fillRect(event.rect(), self.viewport().palette().color(QPalette.ColorRole.Base))
        text_color = self.viewport().palette().color(QPalette.ColorRole.Text)
        addr_color = QColor("#7a9cc6")
        hl_color = QColor("#3a5a40")

        first_row = self.verticalScrollBar().value()
        rows_on_screen = max(1, self.viewport().height() // self._row_h + 1)
        total_rows = (len(self._data) + self.BYTES_PER_ROW - 1) // self.BYTES_PER_ROW
        last_row = min(total_rows, first_row + rows_on_screen)

        hl_start = hl_end = -1
        if self._highlight:
            hl_start, length = self._highlight
            hl_end = hl_start + length

        for row in range(first_row, last_row):
            y = (row - first_row) * self._row_h
            offset = row * self.BYTES_PER_ROW
            painter.setPen(addr_color)
            painter.drawText(2, y + self._row_h - 4,
                             f"{self._base_address + offset:08X}")

            for i in range(self.BYTES_PER_ROW):
                idx = offset + i
                if idx >= len(self._data):
                    break
                byte = self._data[idx]
                x = self._addr_w + i * self._byte_w
                if hl_start <= idx < hl_end:
                    painter.fillRect(QRect(x - 2, y, self._byte_w, self._row_h), hl_color)
                painter.setPen(text_color)
                painter.drawText(x, y + self._row_h - 4, f"{byte:02X}")

                ax = self._ascii_x + i * self._char_w
                ch = chr(byte) if 32 <= byte < 127 else "."
                if hl_start <= idx < hl_end:
                    painter.fillRect(QRect(ax - 1, y, self._char_w, self._row_h), hl_color)
                painter.drawText(ax, y + self._row_h - 4, ch)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(self._ascii_x + self._char_w * self.BYTES_PER_ROW + 24, 400)
