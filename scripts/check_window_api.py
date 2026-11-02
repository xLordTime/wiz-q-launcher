"""Exercise actual Windows HWND operations against a disposable Qt test window."""

import sys

from PySide6.QtWidgets import QApplication, QWidget

from wizq.win32_windows import CAPTION, FRAME_BITS, THICKFRAME, Win32Windows


def main():
    app = QApplication([])
    widget = QWidget()
    widget.setWindowTitle("WizQ native window test")
    widget.resize(500, 300)
    widget.show()
    app.processEvents()
    hwnd = int(widget.winId())
    api = Win32Windows()
    original = api.snapshot(hwnd)
    try:
        monitors = api.monitors()
        assert monitors and any(m.primary for m in monitors)
        x, y = monitors[0].work[:2]
        api.apply(hwnd, [x + 20, y + 20, 640, 360], "borderless", True)
        app.processEvents()
        state = api.snapshot(hwnd)
        assert state["style"] & FRAME_BITS == 0, state
        assert state["topmost"]
        assert state["rect"][2:] == [640, 360], state
        api.apply(hwnd, [x + 30, y + 30, 640, 360], "windowed", False, "client", original["style"])
        app.processEvents()
        state = api.snapshot(hwnd)
        assert state["style"] & CAPTION and state["style"] & THICKFRAME
        assert not state["topmost"]
        assert api.rect(hwnd, client=True)[2:] == [640, 360], state
        before_minimize = api.rect(hwnd)
        api.show(hwnd, "minimize")
        app.processEvents()
        minimized = api.snapshot(hwnd)
        assert minimized["placement"]["show"] in (2, 7)
        assert minimized["layout_rect"] == before_minimize, (minimized, before_minimize)
        api.show(hwnd, "restore")
        app.processEvents()
        api.restore(hwnd, original)
        app.processEvents()
        restored = api.snapshot(hwnd)
        assert restored["style"] & FRAME_BITS == original["style"] & FRAME_BITS
        assert restored["topmost"] == original["topmost"]
        assert restored["rect"] == original["rect"], (restored, original)
        # The controller must never accept a Qt HWND as a Wizard101 instance.
        assert not api.valid({"hwnd": hwnd, "pid": __import__("os").getpid(), "created": 0})
        print("Win32 monitors, borderless/frame restore, client-size DPI conversion, minimize and topmost OK")
    finally:
        widget.close()


if __name__ == "__main__":
    sys.exit(main())
