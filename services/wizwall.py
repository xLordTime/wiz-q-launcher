"""
Wizwall — Window-Tiling Extension for Wiz Q Launcher
=====================================================

Provides grid-tiling of Wizard101 windows using only Win32 window-management
APIs.  **No game hooks are activated.**

wizwalker is imported lazily at call-time so that:
  - The launcher still starts if wizwalker is not installed.
  - Updating wizwalker (venv / requirements change) never requires touching
    this file.

If wizwalker's ``get_all_wizard_handles()`` is unavailable we fall back to a
pure-ctypes Win32 enumeration that checks for the ``"Wizard Graphical Client"``
window class — the same logic wizwalker itself uses.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("wizwall")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class WizWindow:
    """A discovered Wizard101 window."""
    handle: int
    title: str
    label: str          # account name supplied by caller, or title as fallback

    def __str__(self) -> str:
        return f"{self.label}  (hwnd={self.handle})"


# Saved layout: handle → (x, y, w, h)
SavedLayout = Dict[int, Tuple[int, int, int, int]]


# ---------------------------------------------------------------------------
# Lazy wizwalker import helper
# ---------------------------------------------------------------------------

def _ww():
    """
    Lazily return the ``wizwalker.utils`` module, or *None* if unavailable.

    Importing here (not at module level) means:
      - No import error when wizwalker is missing.
      - Picking up a freshly-installed / updated wizwalker without restarting.
    """
    try:
        import wizwalker.utils as _u  # noqa: PLC0415
        return _u
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Win32 helpers (pure ctypes — no wizwalker dependency)
# ---------------------------------------------------------------------------

_user32 = ctypes.windll.user32

# Window-style constants
_GWL_STYLE       = -16
_WS_OVERLAPPEDWINDOW = 0x00CF0000   # title-bar + borders + system-menu + ...
_WS_VISIBLE      = 0x10000000
_SWP_FRAMECHANGED = 0x0020          # re-query style after SetWindowLongW
_SWP_SHOWWINDOW   = 0x0040
_SWP_NOZORDER     = 0x0004
_HWND_TOP         = 0
_SW_RESTORE       = 9


def _ctypes_get_handles() -> List[int]:
    """Enumerate Wizard101 windows by class name via ctypes (fallback)."""
    TARGET = "Wizard Graphical Client"
    found: List[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _cb(hwnd: int, _: int) -> bool:
        buf = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, buf, 64)
        if buf.value == TARGET:
            found.append(hwnd)
        return True

    _user32.EnumWindows(_cb, 0)
    return found


def _get_title_ctypes(handle: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(handle, buf, 256)
    return buf.value


def _get_rect_ctypes(handle: int) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) via GetWindowRect."""
    rect = ctypes.wintypes.RECT()
    if _user32.GetWindowRect(handle, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return None


def _screen_size() -> Tuple[int, int]:
    return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_windows(
    account_map: Optional[Dict[int, str]] = None,
) -> List[WizWindow]:
    """
    Return all currently open Wizard101 windows.

    Uses ``wizwalker.utils.get_all_wizard_handles()`` when available (same
    logic, but kept in wizwalker).  Falls back to the ctypes version.

    **No game hooks are activated.**  This is a pure window-enumeration call.

    Args:
        account_map: Optional ``{hwnd: account_name}`` mapping.  When a handle
                     appears in the map its account name is used as the label;
                     otherwise the window title is used.
    Returns:
        List of :class:`WizWindow` objects.
    """
    utils = _ww()
    if utils is not None:
        try:
            handles = utils.get_all_wizard_handles()
            logger.debug("wizwalker found %d handle(s)", len(handles))
        except Exception as exc:
            logger.warning("wizwalker.get_all_wizard_handles failed (%s) — using ctypes fallback", exc)
            handles = _ctypes_get_handles()
    else:
        logger.debug("wizwalker not available, using ctypes fallback")
        handles = _ctypes_get_handles()

    result: List[WizWindow] = []
    am = account_map or {}
    for h in handles:
        # Title via wizwalker if available, else ctypes
        if utils is not None:
            try:
                title = utils.get_window_title(h)
            except Exception:
                title = _get_title_ctypes(h)
        else:
            title = _get_title_ctypes(h)
        label = am.get(h, title or f"hwnd:{h}")
        result.append(WizWindow(handle=h, title=title, label=label))

    logger.info("scan_windows: found %d Wizard101 window(s)", len(result))
    return result


def parse_layout(layout: str) -> Tuple[int, int]:
    """Parse ``"COLSxROWS"`` string → ``(cols, rows)``.  Defaults to 2×2."""
    try:
        c, r = layout.lower().split("x", 1)
        return max(1, int(c)), max(1, int(r))
    except Exception:
        logger.warning("Could not parse layout %r, falling back to 2x2", layout)
        return 2, 2


def calc_grid_positions(
    count: int,
    cols: int,
    rows: int,
    screen_w: int,
    screen_h: int,
    padding: int = 4,
) -> List[Tuple[int, int, int, int]]:
    """
    Calculate ``(x, y, w, h)`` for *count* cells in a cols×rows grid.

    Windows that exceed ``cols * rows`` are silently omitted.
    """
    cell_w = max(1, (screen_w - padding * (cols + 1)) // cols)
    cell_h = max(1, (screen_h - padding * (rows + 1)) // rows)
    positions: List[Tuple[int, int, int, int]] = []
    for i in range(min(count, cols * rows)):
        c = i % cols
        r = i // cols
        x = padding + c * (cell_w + padding)
        y = padding + r * (cell_h + padding)
        positions.append((x, y, cell_w, cell_h))
    return positions


def _move_window(
    handle: int,
    x: int, y: int, w: int, h: int,
    borderless: bool = True,
) -> bool:
    """Move *and* optionally de-decorate a window (pure Win32 / ctypes)."""
    try:
        _user32.ShowWindow(handle, _SW_RESTORE)

        if borderless:
            style = _user32.GetWindowLongW(handle, _GWL_STYLE)
            new_style = (style & ~_WS_OVERLAPPEDWINDOW) | _WS_VISIBLE
            _user32.SetWindowLongW(handle, _GWL_STYLE, new_style)

        _user32.SetWindowPos(
            handle,
            _HWND_TOP,
            x, y, w, h,
            _SWP_FRAMECHANGED | _SWP_SHOWWINDOW | _SWP_NOZORDER,
        )
        return True
    except Exception as exc:
        logger.warning("Failed to move hwnd %d: %s", handle, exc)
        return False


def arrange_grid(
    windows: List[WizWindow],
    layout: str = "2x2",
    padding: int = 4,
    borderless: bool = True,
) -> Tuple[int, List[str]]:
    """
    Tile *windows* in a grid on the primary monitor.

    Args:
        windows:    Windows to arrange (from :func:`scan_windows`).
        layout:     Grid spec, e.g. ``"2x2"``, ``"3x2"``.
        padding:    Pixel gap between cells.
        borderless: Strip title-bar / borders for seamless tiling.

    Returns:
        ``(arranged_count, info_lines)`` — info_lines can be shown in the UI.
    """
    if not windows:
        return 0, ["No Wizard101 windows found."]

    cols, rows = parse_layout(layout)
    sw, sh = _screen_size()
    positions = calc_grid_positions(len(windows), cols, rows, sw, sh, padding)

    arranged = 0
    lines: List[str] = []
    for win, (x, y, w, h) in zip(windows, positions):
        if _move_window(win.handle, x, y, w, h, borderless):
            arranged += 1
            lines.append(f"[OK]   {win.label}  →  ({x}, {y})  {w}×{h}")
            logger.info("Arranged '%s' hwnd=%d at (%d,%d) %dx%d", win.label, win.handle, x, y, w, h)
            time.sleep(0.03)
        else:
            lines.append(f"[FAIL] {win.label}")

    lines.append(f"\nArranged {arranged}/{len(windows)} window(s) in {layout} layout.")
    return arranged, lines


def snapshot_positions(windows: List[WizWindow]) -> SavedLayout:
    """
    Capture current geometry of *windows*.

    Returns a ``{handle: (x, y, w, h)}`` dict that can be stored in config.
    """
    result: SavedLayout = {}
    for win in windows:
        pos = _get_rect_ctypes(win.handle)
        if pos:
            result[win.handle] = pos
            logger.debug("Snapshot hwnd=%d → %s", win.handle, pos)
    return result


def restore_positions(
    saved: SavedLayout,
    windows: List[WizWindow],
) -> Tuple[int, List[str]]:
    """
    Restore windows to previously snapshotted positions (with decorations).

    Only windows whose handle appears in *saved* are moved.

    Returns ``(restored_count, info_lines)``.
    """
    live = {win.handle: win for win in windows}
    restored = 0
    lines: List[str] = []
    for handle, (x, y, w, h) in saved.items():
        win = live.get(handle)
        if win is None:
            lines.append(f"[SKIP] hwnd:{handle}  (not running)")
            continue
        if _move_window(handle, x, y, w, h, borderless=False):
            restored += 1
            lines.append(f"[OK]   {win.label}  →  ({x}, {y})  {w}×{h}")
        else:
            lines.append(f"[FAIL] {win.label}")

    lines.append(f"\nRestored {restored}/{len(saved)} window(s).")
    return restored, lines


def format_window_list(windows: List[WizWindow]) -> str:
    """Format window list for display in the UI multiline widget."""
    if not windows:
        return "No Wizard101 windows detected."
    lines = []
    for i, win in enumerate(windows, 1):
        pos = _get_rect_ctypes(win.handle)
        geo = f"  @({pos[0]},{pos[1]}) {pos[2]}×{pos[3]}" if pos else ""
        lines.append(f"[{i}]  {win.label}{geo}")
    return "\n".join(lines)
