from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pyside6_ui.theme import STORAGE_LIMIT_BYTES
from pyside6_ui.widgets.storage_ring import StorageRingWidget


class DetailPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._details: dict[str, str] = {}
        self._current_url = ""
        self._current_share_url = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        self.link_card = QFrame()
        self.link_card.setObjectName("InsetPanel")
        self.link_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        link_layout = QVBoxLayout(self.link_card)
        link_layout.setContentsMargins(18, 16, 18, 18)
        link_layout.setSpacing(10)

        link_layout.addWidget(self._label("链接操作", "SectionLabel"))

        self.url_status_label = self._label("预签名 URL 状态：未生成", "BodyValue")
        self.share_status_label = self._label("分享状态：未创建", "BodyValue")
        self.object_meta_label = self._label("当前未选中文件。", "MutedValue")
        self.object_meta_label.setWordWrap(True)

        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        self.url_edit.setPlaceholderText("当前有效预签名 URL")
        self.share_edit = QLineEdit()
        self.share_edit.setReadOnly(True)
        self.share_edit.setPlaceholderText("当前有效分享链接")

        self.copy_url_button = QPushButton("复制 URL")
        self.copy_share_button = QPushButton("复制分享链接")

        link_layout.addWidget(self.url_status_label)
        link_layout.addWidget(self.url_edit)
        link_layout.addWidget(self.copy_url_button, alignment=Qt.AlignRight)
        link_layout.addWidget(self.share_status_label)
        link_layout.addWidget(self.share_edit)
        link_layout.addWidget(self.copy_share_button, alignment=Qt.AlignRight)
        link_layout.addWidget(self.object_meta_label)

        self.storage_card = QFrame()
        self.storage_card.setObjectName("InsetPanel")
        self.storage_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        storage_layout = QVBoxLayout(self.storage_card)
        storage_layout.setContentsMargins(18, 16, 18, 18)
        storage_layout.setSpacing(10)

        storage_layout.addWidget(self._label("容量概览", "SectionLabel"))
        self.ring = StorageRingWidget()
        self.storage_bucket_label = self._label("当前 bucket：未选择", "BodyValue")
        self.storage_usage_label = self._label("已用空间：0 B / 10.00 GB", "BodyValue")
        self.storage_percent_label = self._label("已用比例：0.0%", "BodyValue")
        self.storage_hint_label = self._label("所有 bucket 合计：暂未统计", "MutedValue")
        self.storage_hint_label.setWordWrap(True)

        storage_layout.addWidget(self.ring, alignment=Qt.AlignHCenter)
        storage_layout.addWidget(self.storage_bucket_label)
        storage_layout.addWidget(self.storage_usage_label)
        storage_layout.addWidget(self.storage_percent_label)
        storage_layout.addWidget(self.storage_hint_label)
        self.ring.set_usage(0, STORAGE_LIMIT_BYTES)

        layout.addWidget(self.link_card, 1)
        layout.addWidget(self.storage_card, 0)

    def _label(self, text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def set_object_details(self, details: dict[str, str] | None) -> None:
        self._details = details or {}
        if not self._details:
            self.object_meta_label.setText("当前未选中文件。")
            return

        metadata = [
            f"大小：{self._details.get('size', '-')}",
            f"修改时间：{self._details.get('last_modified', '-')}",
            f"默认过期秒数：{self._details.get('expire_seconds', '-')}",
        ]
        self.object_meta_label.setText(" · ".join(metadata))

    def set_url(self, url: str) -> None:
        self._current_url = url.strip()
        self.url_edit.setText(self._current_url)
        self.url_status_label.setText(
            "预签名 URL 状态：已生成" if self._current_url else "预签名 URL 状态：未生成"
        )

    def set_share_url(self, share_url: str) -> None:
        self._current_share_url = share_url.strip()
        self.share_edit.setText(self._current_share_url)
        self.share_status_label.setText(
            "分享状态：可访问" if self._current_share_url else "分享状态：未创建"
        )

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
