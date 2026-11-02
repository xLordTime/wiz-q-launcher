"""Win32 window geometry in physical desktop pixels, independent of Qt DPI units."""

from __future__ import annotations

import ctypes
import sys
from contextlib import contextmanager
from ctypes import wintypes

from .windowing import Monitor, recover_rect, rectangle

CAPTION, THICKFRAME, MINBOX, MAXBOX, SYSMENU = 0x00C00000, 0x00040000, 0x00020000, 0x00010000, 0x00080000
FRAME_BITS = CAPTION | THICKFRAME | MINBOX | MAXBOX | SYSMENU
NOZORDER, NOACTIVATE, FRAMECHANGED = 0x0004, 0x0010, 0x0020


class WindowPlacement(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def as_rect(rect):
    return [rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top]


class Win32Windows:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Die Spielfenstersteuerung benötigt Windows.")
        self.user = ctypes.WinDLL("user32", use_last_error=True)

    def fn(self, name, args, result=wintypes.BOOL):
        function = getattr(self.user, name)
        function.argtypes, function.restype = args, result
        return function

    @staticmethod
    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    @contextmanager
    def physical(self):
        # Restore the caller's context: Qt and worker threads must retain their
        # own DPI handling after an operation. Windows 10 PMv1 is a fallback.
        setter, previous = None, None
        try:
            setter = self.fn("SetThreadDpiAwarenessContext", [ctypes.c_void_p], ctypes.c_void_p)
            previous = setter(ctypes.c_void_p(-4)) or setter(ctypes.c_void_p(-3))
        except AttributeError:
            pass
        try:
            yield
        finally:
            if previous and setter:
                setter(previous)

    def valid(self, instance):
        from . import backend

        return (
            backend.alive(instance["pid"], instance["created"])
            and (instance["hwnd"], instance["pid"]) in backend.window_handles()
        )

    def monitors(self):
        result = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
        )
        error = []

        @callback_type
        def visit(handle, _dc, _rect, _data):
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if not self.fn("GetMonitorInfoW", [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)])(
                handle, ctypes.byref(info)
            ):
                error.append(ctypes.get_last_error())
                return False
            result.append(
                Monitor(
                    info.szDevice,
                    tuple(as_rect(info.rcMonitor)),
                    tuple(as_rect(info.rcWork)),
                    bool(info.dwFlags & 1),
                )
            )
            return True

        with self.physical():
            self.check(
                self.fn(
                    "EnumDisplayMonitors",
                    [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM],
                )(None, None, visit, 0)
            )
        if error:
            raise ctypes.WinError(error[0])
        if not result:
            raise RuntimeError("Windows meldet keinen Bildschirm.")
        return sorted(result, key=lambda m: (not m.primary, m.rect[0], m.rect[1], m.id))

    def long(self, hwnd, index):
        ctypes.set_last_error(0)
        value = self.fn("GetWindowLongPtrW", [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t)(hwnd, index)
        if value == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        return value & 0xFFFFFFFF

    def set_long(self, hwnd, index, value):
        ctypes.set_last_error(0)
        result = self.fn(
            "SetWindowLongPtrW", [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t
        )(hwnd, index, value)
        if result == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())

    def rect(self, hwnd, client=False):
        rect = wintypes.RECT()
        with self.physical():
            self.check(
                self.fn(
                    "GetClientRect" if client else "GetWindowRect",
                    [wintypes.HWND, ctypes.POINTER(wintypes.RECT)],
                )(hwnd, ctypes.byref(rect))
            )
        return as_rect(rect)

    def placement(self, hwnd):
        placement = WindowPlacement()
        placement.length = ctypes.sizeof(placement)
        self.check(
            self.fn("GetWindowPlacement", [wintypes.HWND, ctypes.POINTER(WindowPlacement)])(
                hwnd, ctypes.byref(placement)
            )
        )
        return placement

    def snapshot(self, hwnd):
        with self.physical():
            placement = self.placement(hwnd)
            return {
                "style": self.long(hwnd, -16),
                "exstyle": self.long(hwnd, -20),
                "rect": self.rect(hwnd),
                "topmost": bool(self.long(hwnd, -20) & 8),
                "placement": {
                    "flags": placement.flags,
                    "show": placement.showCmd,
                    "min": [placement.ptMinPosition.x, placement.ptMinPosition.y],
                    "max": [placement.ptMaxPosition.x, placement.ptMaxPosition.y],
                    "normal": as_rect(placement.rcNormalPosition),
                },
            }

    def position(self, hwnd, rect, topmost=None, flags=0):
        x, y, w, h = rect
        after = None if topmost is None else ctypes.c_void_p(-1 if topmost else -2)
        self.check(
            self.fn(
                "SetWindowPos",
                [
                    wintypes.HWND,
                    wintypes.HWND,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    wintypes.UINT,
                ],
            )(hwnd, after, x, y, w, h, flags | NOACTIVATE | (NOZORDER if topmost is None else 0))
        )

    def apply(self, hwnd, rect, mode="unchanged", topmost=None, size_kind="outer", original_style=None):
        rect = rectangle(rect)
        with self.physical():
            current = self.long(hwnd, -16)
            desired = current
            if mode == "windowed":
                baseline = current if original_style is None else original_style
                desired = (
                    (current & ~FRAME_BITS)
                    | (baseline & FRAME_BITS)
                    | CAPTION
                    | THICKFRAME
                    | MINBOX
                    | MAXBOX
                    | SYSMENU
                )
            elif mode == "borderless":
                desired = current & ~FRAME_BITS
            elif mode != "unchanged":
                raise ValueError("Unbekannter Fenstermodus.")
            if desired != current:
                self.set_long(hwnd, -16, desired)
            # Normalize a minimized/maximized client without stealing focus.
            placement = self.placement(hwnd)
            if placement.showCmd in (2, 3, 6, 7, 11):
                placement.showCmd = 4  # SW_SHOWNOACTIVATE
                self.check(
                    self.fn("SetWindowPlacement", [wintypes.HWND, ctypes.POINTER(WindowPlacement)])(
                        hwnd, ctypes.byref(placement)
                    )
                )
            if size_kind == "client":
                # Move first so GetDpiForWindow reflects the destination display.
                self.position(hwnd, [rect[0], rect[1], 0, 0], flags=0x0001 | FRAMECHANGED)
                try:
                    dpi = self.fn("GetDpiForWindow", [wintypes.HWND], wintypes.UINT)(hwnd) or 96
                    adjust = self.fn(
                        "AdjustWindowRectExForDpi",
                        [
                            ctypes.POINTER(wintypes.RECT),
                            wintypes.DWORD,
                            wintypes.BOOL,
                            wintypes.DWORD,
                            wintypes.UINT,
                        ],
                    )
                    area = wintypes.RECT(0, 0, rect[2], rect[3])
                    self.check(adjust(ctypes.byref(area), desired, False, self.long(hwnd, -20), dpi))
                except AttributeError:
                    area = wintypes.RECT(0, 0, rect[2], rect[3])
                    self.check(
                        self.fn(
                            "AdjustWindowRectEx",
                            [ctypes.POINTER(wintypes.RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
                        )(ctypes.byref(area), desired, False, self.long(hwnd, -20))
                    )
                rect[2:] = as_rect(area)[2:]
            elif size_kind != "outer":
                raise ValueError("Unbekannter Größentyp.")
            self.position(hwnd, rect, topmost, FRAMECHANGED | 0x0040)

    def restore(self, hwnd, state):
        with self.physical():
            current = self.long(hwnd, -16)
            # Only reverse frame bits we manage; unrelated live game state bits
            # (visibility/minimized/maximized etc.) are handled by placement.
            self.set_long(hwnd, -16, (current & ~FRAME_BITS) | (state["style"] & FRAME_BITS))
            self.position(hwnd, state["rect"], state["topmost"], FRAMECHANGED)
            saved = state.get("placement")
            if saved:
                placement = WindowPlacement()
                placement.length = ctypes.sizeof(placement)
                placement.flags, placement.showCmd = saved["flags"], saved["show"]
                placement.ptMinPosition = wintypes.POINT(*saved["min"])
                placement.ptMaxPosition = wintypes.POINT(*saved["max"])
                x, y, w, h = saved["normal"]
                placement.rcNormalPosition = wintypes.RECT(x, y, x + w, y + h)
                self.check(
                    self.fn("SetWindowPlacement", [wintypes.HWND, ctypes.POINTER(WindowPlacement)])(
                        hwnd, ctypes.byref(placement)
                    )
                )
            reachable = recover_rect(state["rect"], self.monitors())
            if reachable != state["rect"]:
                self.position(hwnd, reachable, state["topmost"], FRAMECHANGED)

    def show(self, hwnd, action):
        commands = {"minimize": 7, "maximize": 3, "restore": 4}
        if action not in commands:
            raise ValueError("Unbekannte Fensteraktion.")
        with self.physical():
            placement = self.placement(hwnd)
            placement.showCmd = commands[action]
            self.check(
                self.fn("SetWindowPlacement", [wintypes.HWND, ctypes.POINTER(WindowPlacement)])(
                    hwnd, ctypes.byref(placement)
                )
            )
