import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, app, launch, clip):
        super().__init__()
        self.app = app
        self.actions = {0x6A01: launch, 0x6A02: clip}
        self.registered = []
        if sys.platform == "win32":
            for ident, key in ((0x6A01, ord("L")), (0x6A02, ord("C"))):
                if ctypes.windll.user32.RegisterHotKey(None, ident, 0x0001 | 0x0002 | 0x4000, key):
                    self.registered.append(ident)
            app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32" and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.actions:
                self.actions[msg.wParam]()
                return True, 0
        return False, 0

    def close(self):
        if sys.platform == "win32":
            self.app.removeNativeEventFilter(self)
            for ident in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, ident)
