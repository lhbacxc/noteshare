from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Tk

from gui import R2GuiApp


def _resolve_runtime_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / relative_path


def main() -> None:
    root = Tk()
    icon_path = _resolve_runtime_path("cf_cloud.ico")
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except Exception:
            pass
    R2GuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
