from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")

        self.toggle_button = QToolButton(text=title)
        self.toggle_button.setObjectName("SectionToggle")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.bucket_badge = self._make_badge("未选择 bucket")
        self.status_badge = self._make_badge("待补全")

        self.content_widget = QWidget()

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        header_layout.addWidget(self.toggle_button, 1)
        header_layout.addWidget(self.bucket_badge, 0, Qt.AlignRight)
        header_layout.addWidget(self.status_badge, 0, Qt.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)
        layout.addLayout(header_layout)
        layout.addWidget(self.content_widget)

    def _make_badge(self, text: str) -> QLabel:
        badge = QLabel(text)
        badge.setObjectName("MetaBadge")
        return badge

    def set_content_layout(self, layout) -> None:
        self.content_widget.setLayout(layout)

    def set_meta_texts(self, bucket_text: str, status_text: str, status_accent: bool = False) -> None:
        self.bucket_badge.setText(bucket_text)
        self.status_badge.setText(status_text)
        self.status_badge.setProperty("accent", status_accent)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def set_collapsed(self, collapsed: bool) -> None:
        self.toggle_button.setChecked(not collapsed)
        self.content_widget.setVisible(not collapsed)
        self.toggle_button.setArrowType(Qt.RightArrow if collapsed else Qt.DownArrow)

    def is_collapsed(self) -> bool:
        return not self.toggle_button.isChecked()

    def _on_toggle_clicked(self, checked: bool) -> None:
        self.content_widget.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
