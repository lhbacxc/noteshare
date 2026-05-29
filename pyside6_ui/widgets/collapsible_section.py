from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")

        self.toggle_button = QToolButton(text=title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.content_widget = QWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_widget)

    def set_content_layout(self, layout) -> None:
        self.content_widget.setLayout(layout)

    def set_collapsed(self, collapsed: bool) -> None:
        self.toggle_button.setChecked(not collapsed)
        self.content_widget.setVisible(not collapsed)
        self.toggle_button.setArrowType(Qt.RightArrow if collapsed else Qt.DownArrow)

    def is_collapsed(self) -> bool:
        return not self.toggle_button.isChecked()

    def _on_toggle_clicked(self, checked: bool) -> None:
        self.content_widget.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
