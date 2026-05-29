from __future__ import annotations

WINDOW_MIN_WIDTH = 1260
WINDOW_MIN_HEIGHT = 760
WINDOW_DEFAULT_WIDTH = 1480
WINDOW_DEFAULT_HEIGHT = 900
STORAGE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024
COUNTDOWN_REFRESH_MS = 5000
AUTO_REFRESH_DELAY_MS = 200


APP_STYLESHEET = """
QWidget {
    background: #f4f7fb;
    color: #223043;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 13px;
}
QMainWindow {
    background: #f4f7fb;
}
QFrame#SurfaceCard, QGroupBox#SurfaceCard {
    background: #ffffff;
    border: 1px solid #dde5ef;
    border-radius: 16px;
}
QGroupBox#SurfaceCard {
    margin-top: 10px;
    padding-top: 12px;
    font-weight: 600;
}
QGroupBox#SurfaceCard::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 4px;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #ced7e3;
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: #2f7cf6;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #2f7cf6;
}
QPushButton {
    background: #edf3ff;
    border: 1px solid #d5e0f2;
    border-radius: 10px;
    padding: 8px 14px;
    color: #223043;
    font-weight: 600;
}
QPushButton:hover {
    background: #e3ecff;
}
QPushButton:pressed {
    background: #d7e5ff;
}
QPushButton#PrimaryButton {
    background: #2f7cf6;
    color: #ffffff;
    border: 1px solid #2f7cf6;
}
QPushButton#PrimaryButton:hover {
    background: #246ee3;
}
QPushButton#DangerButton {
    background: #fff2f1;
    color: #c0392b;
    border: 1px solid #f0c5c1;
}
QPushButton#DangerButton:hover {
    background: #ffe6e2;
}
QHeaderView::section {
    background: #edf2f8;
    color: #4b5c70;
    border: none;
    border-bottom: 1px solid #dbe3ee;
    padding: 10px 8px;
    font-weight: 600;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #dde5ef;
    border-radius: 14px;
    gridline-color: #eef2f7;
    selection-background-color: #e8f1ff;
    selection-color: #223043;
}
QTableWidget::item {
    padding: 6px;
}
QTableWidget::item:selected {
    background: #e8f1ff;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #dde5ef;
}
QSplitter::handle {
    background: transparent;
    width: 8px;
}
"""
