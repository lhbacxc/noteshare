from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pyside6_ui.main_window import NoteShareMainWindow


def _resolve_runtime_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / relative_path


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("NoteShare R2 管理工具")

    icon_path = _resolve_runtime_path("cf_cloud.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = NoteShareMainWindow(icon_path=icon_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
