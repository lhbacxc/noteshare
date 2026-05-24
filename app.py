from __future__ import annotations

from tkinter import Tk

from gui import R2GuiApp


def main() -> None:
    root = Tk()
    R2GuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
