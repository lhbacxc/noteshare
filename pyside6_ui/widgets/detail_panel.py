from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from pyside6_ui.theme import STORAGE_LIMIT_BYTES
from pyside6_ui.widgets.storage_ring import StorageRingWidget


class DetailPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.info_card = QGroupBox("当前对象详情")
        self.info_card.setObjectName("SurfaceCard")
        info_layout = QFormLayout(self.info_card)
        info_layout.setLabelAlignment(Qt.AlignLeft)
        info_layout.setFormAlignment(Qt.AlignTop)
        info_layout.setContentsMargins(16, 18, 16, 16)
        info_layout.setSpacing(10)

        self.key_label = self._value_label("未选择对象")
        self.size_label = self._value_label("-")
        self.modified_label = self._value_label("-")
        self.storage_class_label = self._value_label("-")
        self.expire_label = self._value_label("-")
        self.url_status_label = self._value_label("-")
        info_layout.addRow("Key", self.key_label)
        info_layout.addRow("Size", self.size_label)
        info_layout.addRow("Last Modified", self.modified_label)
        info_layout.addRow("Storage Class", self.storage_class_label)
        info_layout.addRow("默认过期秒数", self.expire_label)
        info_layout.addRow("URL 状态", self.url_status_label)

        self.url_card = QGroupBox("链接与分享")
        self.url_card.setObjectName("SurfaceCard")
        url_layout = QVBoxLayout(self.url_card)
        url_layout.setContentsMargins(16, 18, 16, 16)
        url_layout.setSpacing(10)

        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        self.share_edit = QLineEdit()
        self.share_edit.setReadOnly(True)

        self.copy_url_button = QPushButton("复制 URL")
        self.copy_share_button = QPushButton("复制分享链接")

        url_layout.addWidget(QLabel("当前有效预签名 URL"))
        url_layout.addWidget(self.url_edit)
        url_layout.addWidget(self.copy_url_button, alignment=Qt.AlignRight)
        url_layout.addWidget(QLabel("当前有效分享链接"))
        url_layout.addWidget(self.share_edit)
        url_layout.addWidget(self.copy_share_button, alignment=Qt.AlignRight)

        self.storage_card = QGroupBox("Bucket 容量概览")
        self.storage_card.setObjectName("SurfaceCard")
        storage_layout = QVBoxLayout(self.storage_card)
        storage_layout.setContentsMargins(16, 18, 16, 16)
        storage_layout.setSpacing(10)

        self.ring = StorageRingWidget()
        self.storage_bucket_label = self._value_label("当前 bucket：未选择")
        self.storage_usage_label = self._value_label("已用空间：0 B / 10.00 GB")
        self.storage_percent_label = self._value_label("已用比例：0.0%")
        self.storage_hint_label = self._value_label("所有 bucket 合计：暂未统计")

        storage_layout.addWidget(self.ring, alignment=Qt.AlignHCenter)
        storage_layout.addWidget(self.storage_bucket_label)
        storage_layout.addWidget(self.storage_usage_label)
        storage_layout.addWidget(self.storage_percent_label)
        storage_layout.addWidget(self.storage_hint_label)
        self.ring.set_usage(0, STORAGE_LIMIT_BYTES)

        layout.addWidget(self.info_card)
        layout.addWidget(self.url_card)
        layout.addWidget(self.storage_card)
        layout.addStretch(1)

    def set_object_details(self, details: dict[str, str] | None) -> None:
        details = details or {}
        self.key_label.setText(details.get("key", "未选择对象"))
        self.size_label.setText(details.get("size", "-"))
        self.modified_label.setText(details.get("last_modified", "-"))
        self.storage_class_label.setText(details.get("storage_class", "-"))
        self.expire_label.setText(details.get("expire_seconds", "-"))
        self.url_status_label.setText(details.get("url_status", "-"))

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def set_share_url(self, share_url: str) -> None:
        self.share_edit.setText(share_url)

    def set_storage_summary(
        self,
        bucket_text: str,
        usage_text: str,
        percent_text: str,
        hint_text: str,
        used_bytes: int,
        total_bytes: int,
    ) -> None:
        self.storage_bucket_label.setText(bucket_text)
        self.storage_usage_label.setText(usage_text)
        self.storage_percent_label.setText(percent_text)
        self.storage_hint_label.setText(hint_text)
        self.ring.set_usage(used_bytes, total_bytes)

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label
