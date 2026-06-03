from __future__ import annotations

WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 620
WINDOW_DEFAULT_WIDTH = 1320
WINDOW_DEFAULT_HEIGHT = 820
STORAGE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024
COUNTDOWN_REFRESH_MS = 5000
AUTO_REFRESH_DELAY_MS = 200
RESPONSIVE_VERTICAL_SPLIT_WIDTH = 1180

COLOR_BG = "#f5f5f7"
COLOR_SURFACE = "#ffffff"
COLOR_SURFACE_ALT = "#fbfbfd"
COLOR_SURFACE_SUBTLE = "#f7f8fb"
COLOR_BORDER = "#e4e4ea"
COLOR_BORDER_SOFT = "#eff0f4"
COLOR_TEXT = "#1d1d1f"
COLOR_TEXT_MUTED = "#6e6e73"
COLOR_TEXT_SUBTLE = "#8d8d92"
COLOR_PRIMARY = "#0066cc"
COLOR_PRIMARY_SOFT = "#e8f1ff"
COLOR_PRIMARY_PRESSED = "#0058b0"
COLOR_DANGER = "#c43c2f"
COLOR_DANGER_SOFT = "#fff3f2"
COLOR_DANGER_BORDER = "#f1c7c2"
COLOR_DARK_CARD = "#1d1d1f"
COLOR_DARK_BORDER = "#2d2d30"
COLOR_DARK_TEXT_MUTED = "#c7c7cc"


APP_STYLESHEET = f"""
QWidget {{
    background: transparent;
    color: {COLOR_TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI Variable", "Segoe UI";
    font-size: 13px;
}}
QMainWindow {{
    background: {COLOR_BG};
}}
QWidget#AppCanvas {{
    background: {COLOR_BG};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollArea {{
    border: none;
}}
QFrame#SurfaceCard,
QGroupBox#SurfaceCard,
QWidget#SurfaceCard {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 24px;
}}
QFrame#InsetPanel,
QWidget#InsetPanel {{
    background-color: {COLOR_SURFACE_SUBTLE};
    border: 1px solid {COLOR_BORDER_SOFT};
    border-radius: 20px;
}}
QDialog,
QFileDialog,
QInputDialog,
QMessageBox {{
    background: {COLOR_BG};
}}
QDialog QWidget,
QFileDialog QWidget,
QInputDialog QWidget,
QMessageBox QWidget {{
    background: {COLOR_BG};
    color: {COLOR_TEXT};
}}
QFrame#StatusHeroCard,
QWidget#StatusHeroCard {{
    background-color: {COLOR_DARK_CARD};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 24px;
}}
QLabel#SectionLabel {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#PaneTitle {{
    color: {COLOR_TEXT_MUTED};
    font-size: 13px;
    font-weight: 600;
    padding-left: 18px;
}}
QLabel#SectionTitle {{
    color: {COLOR_TEXT};
    font-size: 16px;
    font-weight: 600;
}}
QLabel#FieldLabel {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
    padding-left: 2px;
}}
QLabel#BodyValue {{
    color: {COLOR_TEXT};
    font-size: 13px;
}}
QLabel#MutedValue {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
}}
QLabel#HeroEyebrow {{
    color: {COLOR_DARK_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#HeroTitle {{
    color: #ffffff;
    font-size: 18px;
    font-weight: 600;
}}
QLabel#HeroSubtle {{
    color: {COLOR_DARK_TEXT_MUTED};
    font-size: 12px;
}}
QLabel#MetaBadge {{
    background-color: #f1f2f6;
    border: 1px solid {COLOR_BORDER};
    border-radius: 999px;
    color: {COLOR_TEXT_MUTED};
    padding: 5px 10px;
    font-size: 12px;
}}
QLabel#MetaBadge[accent="true"] {{
    background-color: {COLOR_DARK_CARD};
    border: 1px solid {COLOR_DARK_BORDER};
    color: #ffffff;
}}
QToolButton#SectionToggle {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT};
    font-size: 18px;
    font-weight: 600;
    padding: 0;
    text-align: left;
}}
QToolButton#SectionToggle:hover {{
    color: {COLOR_PRIMARY};
}}
QGroupBox#SurfaceCard {{
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    color: {COLOR_TEXT};
}}
QGroupBox#SurfaceCard::title {{
    subcontrol-origin: margin;
    left: 18px;
    padding: 0 6px;
    color: {COLOR_TEXT_MUTED};
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background-color: {COLOR_SURFACE_ALT};
    border: 1px solid #e2e3e8;
    border-radius: 16px;
    padding: 9px 14px;
    selection-background-color: {COLOR_PRIMARY};
    min-height: 18px;
}}
QLineEdit[readOnly="true"],
QPlainTextEdit[readOnly="true"] {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 16px;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_PRIMARY};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
}}
QPushButton {{
    background-color: #fafafc;
    border: 1px solid {COLOR_BORDER};
    border-radius: 16px;
    padding: 7px 16px;
    color: {COLOR_TEXT};
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: #f2f3f7;
}}
QPushButton:pressed {{
    background-color: #eceef3;
}}
QPushButton:disabled {{
    color: {COLOR_TEXT_SUBTLE};
    background-color: #f3f4f7;
    border: 1px solid #e9eaf0;
}}
QPushButton#PrimaryButton {{
    background-color: {COLOR_PRIMARY};
    color: #ffffff;
    border: 1px solid {COLOR_PRIMARY};
}}
QPushButton#PrimaryButton:hover {{
    background-color: #0b70d3;
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {COLOR_PRIMARY_PRESSED};
}}
QPushButton#DangerButton {{
    background-color: {COLOR_DANGER_SOFT};
    color: {COLOR_DANGER};
    border: 1px solid {COLOR_DANGER_BORDER};
}}
QPushButton#DangerButton:hover {{
    background-color: #ffe9e6;
}}
QPushButton#DangerButton:pressed {{
    background-color: #ffdfdb;
}}
QHeaderView::section {{
    background-color: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER_SOFT};
    padding: 12px 10px;
    font-weight: 600;
}}
QHeaderView::section:first {{
    border-top-left-radius: 24px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 24px;
}}
QTableCornerButton::section {{
    background-color: {COLOR_SURFACE_ALT};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER_SOFT};
    border-top-left-radius: 24px;
}}
QTableWidget#ObjectTable {{
    background-color: {COLOR_SURFACE};
    alternate-background-color: {COLOR_SURFACE_ALT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 24px;
    selection-background-color: {COLOR_PRIMARY_SOFT};
    selection-color: {COLOR_TEXT};
    gridline-color: transparent;
    outline: none;
}}
QTableWidget#ObjectTable::item {{
    padding: 8px 10px;
    border-bottom: 1px solid #f2f2f5;
    background-color: {COLOR_SURFACE};
}}
QTableWidget#ObjectTable::item:selected {{
    background-color: {COLOR_PRIMARY_SOFT};
}}
QStatusBar {{
    background-color: {COLOR_SURFACE_ALT};
    border-top: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
    padding-left: 10px;
}}
QSplitter::handle {{
    background: transparent;
    width: 10px;
    height: 10px;
}}
QScrollBar:vertical {{
    width: 10px;
    background: transparent;
    margin: 8px 0;
}}
QScrollBar::handle:vertical {{
    background-color: #d7d8de;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0;
}}
"""
