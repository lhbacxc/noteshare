from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class StorageRingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._used_bytes = 0
        self._total_bytes = 1
        self._base_color = QColor("#ececf1")
        self._used_color = QColor("#0066cc")
        self._text_color = QColor("#1d1d1f")
        self._sub_text_color = QColor("#6e6e73")
        self.setMinimumSize(150, 150)

    def set_usage(self, used_bytes: int, total_bytes: int) -> None:
        self._used_bytes = max(0, int(used_bytes))
        self._total_bytes = max(1, int(total_bytes))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = 18
        rect = QRectF(margin, margin, self.width() - (margin * 2), self.height() - (margin * 2))

        pen = QPen(self._base_color, 10)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        used_ratio = min(1.0, self._used_bytes / self._total_bytes)
        if used_ratio > 0:
            pen.setColor(self._used_color)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, int(-360 * used_ratio * 16))

        painter.setPen(self._text_color)
        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(0, -12, 0, 0), Qt.AlignCenter, self._format_size(self._used_bytes))

        painter.setPen(self._sub_text_color)
        sub_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(sub_font)
        sub_rect = QRectF(rect.left(), rect.center().y() + 2, rect.width(), 34)
        painter.drawText(sub_rect, Qt.AlignHCenter | Qt.AlignTop, f"/ {self._format_size(self._total_bytes)}")

    def _format_size(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{size} B"
