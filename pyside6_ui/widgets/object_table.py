from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QPainter, QRegion, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class SortableTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str, sort_value) -> None:
        super().__init__(text)
        self.sort_value = sort_value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class ObjectTableWidget(QTableWidget):
    HEADERS = [
        "Key",
        "Size",
        "Last Modified",
        "Storage Class",
        "默认过期秒数",
        "URL 到期 / 剩余时间",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setObjectName("ObjectTable")
        self.viewport().setObjectName("ObjectTableViewport")
        self.verticalScrollBar().setObjectName("ObjectTableScrollBar")
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setFrameShape(QFrame.NoFrame)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        header = self.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.setShowGrid(False)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setFocusPolicy(Qt.StrongFocus)
        self.sortByColumn(0, Qt.AscendingOrder)
        self._apply_rounded_mask()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_rounded_mask()

    def _apply_rounded_mask(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        radius = 24
        mask = QBitmap(self.size())
        mask.fill(Qt.color0)
        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.color1)
        painter.drawRoundedRect(self.rect(), radius, radius)
        painter.end()
        self.setMask(QRegion(mask))

    def populate(
        self,
        objects: list[dict[str, object]],
        bucket: str,
        get_expire_seconds: Callable[[str, str], int],
        get_url_status_display: Callable[[str, str], str],
        format_size: Callable[[int], str],
        selected_keys: list[str] | None = None,
    ) -> None:
        selected_keys = selected_keys or []
        header = self.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()

        self.setSortingEnabled(False)
        self.setUpdatesEnabled(False)
        self.clearSelection()
        self.setRowCount(0)

        for row, item in enumerate(objects):
            self.insertRow(row)
            key = str(item.get("key", ""))
            size_value = int(item.get("size", 0))
            last_modified = str(item.get("last_modified", ""))
            storage_class = str(item.get("storage_class", ""))
            expire_seconds = get_expire_seconds(bucket, key)
            url_status = get_url_status_display(bucket, key)
            values = [
                key,
                format_size(size_value),
                last_modified,
                storage_class,
                str(expire_seconds),
                url_status,
            ]
            sort_values = [
                key.casefold(),
                size_value,
                last_modified,
                storage_class.casefold(),
                expire_seconds,
                url_status,
            ]
            for column, value in enumerate(values):
                table_item = SortableTableWidgetItem(value, sort_values[column])
                if column in {1, 4}:
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    table_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                table_item.setData(Qt.UserRole, key)
                self.setItem(row, column, table_item)

        self.setSortingEnabled(True)
        self.sortItems(sort_column, sort_order)

        if selected_keys:
            self._restore_selection(selected_keys)

        self.setUpdatesEnabled(True)

    def _restore_selection(self, selected_keys: list[str]) -> None:
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data(Qt.UserRole) in selected_keys:
                self.selectRow(row)

    def selected_keys(self) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for item in self.selectedItems():
            key = str(item.data(Qt.UserRole) or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys
