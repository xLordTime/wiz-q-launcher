"""
System-tray icon for Wiz-Q Launcher.

Requires pystray and Pillow.  Both are optional — if missing, TRAY_AVAILABLE
is False and the tray feature is silently disabled (F4 falls back to minimize).

Thread model
------------
pystray runs its own message loop in a daemon thread.  To communicate events
back to the PySimpleGUI main thread the caller passes *window.write_event_value*
as ``notify_fn``; the tray callbacks are then picked up in the normal event loop.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw

    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


def _get_icon_path() -> Optional[Path]:
    """Resolve icon.ico from the bundled resources (frozen) or project root (dev)."""
    # PyInstaller frozen: files are extracted to sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "icon.ico"
        if p.exists():
            return p
    # Dev mode: walk up from this file to the project root
    for parent in Path(__file__).parents:
        p = parent / "icon.ico"
        if p.exists():
            return p
    return None


# ── event keys posted back to the PySimpleGUI window ──────────────────────────
RESTORE_EVENT = "-TRAY-RESTORE-"
EXIT_EVENT = "-TRAY-EXIT-"


def _make_tray_icon() -> "Image.Image":
    """Load icon.ico for the system tray, falling back to a drawn placeholder."""
    icon_path = _get_icon_path()
    if icon_path is not None:
        try:
            img = Image.open(icon_path)
            img = img.convert("RGBA")
            img = img.resize((64, 64), Image.LANCZOS)
            return img
        except Exception:
            pass
    # Fallback: draw a simple wizard-hat
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon(
        [(size // 2, 2), (4, size - 10), (size - 4, size - 10)],
        fill="#238636",
    )
    draw.rectangle([2, size - 12, size - 2, size - 2], fill="#1c6ea4")
    return img


class TrayIcon:
    """Wraps a pystray.Icon; starts/stops the tray icon as needed."""

    def __init__(self, title: str = "Wiz-Q Launcher") -> None:
        self._title = title
        self._icon: Optional["pystray.Icon"] = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return TRAY_AVAILABLE

    @property
    def running(self) -> bool:
        with self._lock:
            return self._icon is not None

    def start(self, notify_fn: Callable[[str, object], None]) -> bool:
        """
        Show the tray icon and wire it to *notify_fn* (window.write_event_value).
        Returns False if pystray is unavailable or already running.
        """
        if not TRAY_AVAILABLE:
            return False
        with self._lock:
            if self._icon is not None:
                return False  # already running

            def _on_restore(icon: "pystray.Icon", item: object = None) -> None:
                notify_fn(RESTORE_EVENT, None)

            def _on_exit(icon: "pystray.Icon", item: object = None) -> None:
                notify_fn(EXIT_EVENT, None)
                icon.stop()

            menu = pystray.Menu(
                pystray.MenuItem("Show Launcher", _on_restore, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", _on_exit),
            )
            self._icon = pystray.Icon(
                "wiz-q-launcher",
                _make_tray_icon(),
                self._title,
                menu,
            )

        t = threading.Thread(target=self._icon.run, daemon=True)
        t.start()
        return True

    def stop(self) -> None:
        """Remove the tray icon."""
        with self._lock:
            icon = self._icon
            self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
