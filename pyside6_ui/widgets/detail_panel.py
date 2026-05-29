from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from pyside6_ui.theme import STORAGE_LIMIT_BYTES
from pyside6_ui.widgets.storage_ring import StorageRingWidget


class DetailPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

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

        layout.addWidget(self.url_card)
        layout.addWidget(self.storage_card)
        layout.addStretch(1)

    def set_object_details(self, details: dict[str, str] | None) -> None:
        del details

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
