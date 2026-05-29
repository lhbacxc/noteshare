from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


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
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSortingEnabled(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.setShowGrid(False)

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
        self.setRowCount(0)

        for row, item in enumerate(objects):
            self.insertRow(row)
            key = str(item.get("key", ""))
            values = [
                key,
                format_size(int(item.get("size", 0))),
                str(item.get("last_modified", "")),
                str(item.get("storage_class", "")),
                str(get_expire_seconds(bucket, key)),
                get_url_status_display(bucket, key),
            ]
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                if column in {1, 4}:
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    table_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                table_item.setData(Qt.UserRole, key)
                self.setItem(row, column, table_item)

        if not selected_keys:
            return

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
