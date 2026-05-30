"""
Window Capture — Clip & Record Extension for Wiz Q Launcher
===========================================================
Records individual Wizard101 windows or all windows at once.

Features:
  - Clip mode: rolling ring-buffer of the last N seconds; save on demand
  - Record mode: start/stop full recording per window
  - Screenshot: single-frame PNG, one window or all windows
  - Output: MP4 via OpenCV when available, PNG-frame-sequence fallback
  - Each output is named  <AccountLabel>_<YYYYMMDD_HHMMSS>.<ext>

Win32 only — captures the game window rectangle, not the full screen.
No game hooks are used.

Optional dependencies:
  - opencv-python (cv2)  — MP4 encoding  (pip install opencv-python)
  - Pillow (PIL)         — frame capture  (already in requirements.txt)
  - pywin32              — GetWindowRect  (already in requirements.txt)
"""

from __future__ import annotations

import collections
import ctypes
import ctypes.wintypes
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("window_capture")

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------

try:
    import cv2 as _cv2          # type: ignore
    CV2_AVAILABLE = True
except ImportError:
    _cv2 = None                 # type: ignore
    CV2_AVAILABLE = False

try:
    from PIL import ImageGrab as _ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    _ImageGrab = None           # type: ignore
    PIL_AVAILABLE = False

_user32 = ctypes.windll.user32

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CaptureWindow:
    """A discovered Wizard101 window available for capture."""
    handle: int
    title: str
    label: str          # account name or window title fallback

    def __str__(self) -> str:
        return f"{self.label}  (hwnd={self.handle})"


@dataclass
class RecordingState:
    """Tracks an active per-window recording session."""
    handle: int
    label: str
    output_path: Path
    fps: int
    started_at: float = field(default_factory=time.time)
    frame_count: int = 0
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = field(default=None)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at


# Active recordings: handle → RecordingState
_active_recordings: Dict[int, RecordingState] = {}

# Rolling ring-buffers: handle → Deque[(timestamp, PIL.Image)]
# Populated continuously while recording; used by save_clip().
_ring_buffers: Dict[int, Deque] = {}

# ---------------------------------------------------------------------------
# Win32 helpers
# ---------------------------------------------------------------------------

def _get_wiz_handles() -> List[int]:
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


def _get_title(handle: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(handle, buf, 256)
    return buf.value


def _get_window_rect(handle: int) -> Optional[Tuple[int, int, int, int]]:
    """Return (left, top, right, bottom) in screen coordinates."""
    rect = ctypes.wintypes.RECT()
    if _user32.GetWindowRect(handle, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return None


# ---------------------------------------------------------------------------
# Frame capture
# ---------------------------------------------------------------------------

def _capture_frame(handle: int):
    """Grab one frame from the window's bounding rect. Returns PIL Image or None."""
    if not PIL_AVAILABLE:
        return None
    rect = _get_window_rect(handle)
    if rect is None:
        return None
    left, top, right, bottom = rect
    if right - left < 4 or bottom - top < 4:
        return None
    try:
        return _ImageGrab.grab(bbox=(left, top, right, bottom))
    except Exception as exc:
        logger.debug("Frame capture failed hwnd=%d: %s", handle, exc)
        return None


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _safe_name(label: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. ")
    return "".join(c if c in keep else "_" for c in label).strip() or "window"


def _output_path(output_dir: Path, label: str, ext: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{_safe_name(label)}_{ts}.{ext}"


# ---------------------------------------------------------------------------
# Public API — window discovery
# ---------------------------------------------------------------------------

def scan_windows(account_map: Optional[Dict[int, str]] = None) -> List[CaptureWindow]:
    """Return all currently open Wizard101 windows."""
    account_map = account_map or {}
    return [
        CaptureWindow(
            handle=h,
            title=_get_title(h),
            label=account_map.get(h) or _get_title(h) or f"Window-{h}",
        )
        for h in _get_wiz_handles()
    ]


# ---------------------------------------------------------------------------
# Public API — screenshot
# ---------------------------------------------------------------------------

def take_screenshot(handle: int, label: str, output_dir: Path) -> Optional[Path]:
    """Save a single PNG screenshot of the window. Returns path or None."""
    img = _capture_frame(handle)
    if img is None:
        logger.warning("Screenshot: could not capture hwnd=%d", handle)
        return None
    path = _output_path(output_dir, label, "png")
    try:
        img.save(path)
        logger.info("Screenshot saved: %s", path)
        return path
    except Exception as exc:
        logger.warning("Screenshot save failed: %s", exc)
        return None


def screenshot_all(windows: List[CaptureWindow], output_dir: Path) -> List[Path]:
    """Screenshot every window. Returns list of saved paths."""
    paths = []
    for w in windows:
        p = take_screenshot(w.handle, w.label, output_dir)
        if p:
            paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Public API — recording
# ---------------------------------------------------------------------------

def start_recording(
    win: CaptureWindow,
    output_dir: Path,
    fps: int = 20,
    clip_buffer_seconds: int = 30,
) -> RecordingState:
    """
    Begin recording a window in a background thread.

    Frames are written to an MP4 (if cv2 available) or PNG sequence.
    A rolling ring-buffer of the last ``clip_buffer_seconds`` frames is
    maintained in parallel for save_clip().

    Returns the RecordingState (already running).
    """
    # Stop any previous recording for this handle
    if win.handle in _active_recordings:
        stop_recording(win.handle)

    ext = "mp4" if CV2_AVAILABLE else ""
    out = _output_path(output_dir, win.label, ext) if CV2_AVAILABLE else (
        output_dir / f"{_safe_name(win.label)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    state = RecordingState(handle=win.handle, label=win.label, output_path=out, fps=fps)

    max_frames = fps * clip_buffer_seconds
    ring: Deque = collections.deque(maxlen=max_frames)
    _ring_buffers[win.handle] = ring
    _active_recordings[win.handle] = state

    def _loop():
        writer = None
        frame_interval = 1.0 / fps

        while not state._stop_event.is_set():
            t0 = time.monotonic()
            img = _capture_frame(win.handle)
            if img is not None:
                ring.append((time.time(), img))
                if CV2_AVAILABLE:
                    try:
                        import numpy as np                   # lazy
                        bgr = _cv2.cvtColor(np.array(img.convert("RGB")), _cv2.COLOR_RGB2BGR)
                        if writer is None:
                            h_px, w_px = bgr.shape[:2]
                            fourcc = _cv2.VideoWriter_fourcc(*"mp4v")
                            writer = _cv2.VideoWriter(str(state.output_path), fourcc, fps, (w_px, h_px))
                        writer.write(bgr)
                    except Exception as exc:
                        logger.debug("cv2 write: %s", exc)
                else:
                    # PNG sequence
                    try:
                        state.output_path.mkdir(parents=True, exist_ok=True)
                        img.save(state.output_path / f"frame_{state.frame_count:06d}.png")
                    except Exception as exc:
                        logger.debug("PNG write: %s", exc)
                state.frame_count += 1

            elapsed = time.monotonic() - t0
            sleep_for = max(0.0, frame_interval - elapsed)
            if sleep_for:
                time.sleep(sleep_for)

        if writer is not None:
            writer.release()
        logger.info(
            "Recording stopped: %s (%d frames, %.1fs)",
            state.output_path, state.frame_count, state.elapsed_seconds(),
        )

    state._stop_event.clear()
    state._thread = threading.Thread(target=_loop, daemon=True, name=f"capture-{win.handle}")
    state._thread.start()
    logger.info("Recording started: hwnd=%d label=%s fps=%d", win.handle, win.label, fps)
    return state


def stop_recording(handle: int) -> Optional[Path]:
    """Stop an active recording. Returns output path if frames were captured."""
    state = _active_recordings.pop(handle, None)
    if state is None:
        return None
    state._stop_event.set()
    if state._thread:
        state._thread.join(timeout=4.0)
    return state.output_path if state.frame_count > 0 else None


def stop_all_recordings() -> List[Path]:
    """Stop every active recording."""
    handles = list(_active_recordings.keys())
    paths = []
    for h in handles:
        p = stop_recording(h)
        if p:
            paths.append(p)
    return paths


def is_recording(handle: int) -> bool:
    """Return True if a recording is active for the given handle."""
    state = _active_recordings.get(handle)
    return state is not None and state.is_running


def active_recording_info(handle: int) -> Optional[str]:
    """Return a short status string for the UI, or None."""
    state = _active_recordings.get(handle)
    if state is None or not state.is_running:
        return None
    elapsed = state.elapsed_seconds()
    mins, secs = divmod(int(elapsed), 60)
    return f"⏺ {mins:02d}:{secs:02d}  {state.frame_count} frames"


# ---------------------------------------------------------------------------
# Public API — clip (save ring-buffer snapshot)
# ---------------------------------------------------------------------------

def save_clip(handle: int, label: str, output_dir: Path, fps: int = 20) -> Optional[Path]:
    """
    Write the current ring-buffer for ``handle`` to disk as a video clip.
    Works even while recording is still running (non-destructive snapshot).
    Returns saved path or None.
    """
    ring = _ring_buffers.get(handle)
    if not ring:
        logger.warning("save_clip: no ring-buffer for hwnd=%d", handle)
        return None

    frames = [img for _, img in list(ring)]   # snapshot — does not drain the deque
    if not frames:
        return None

    if CV2_AVAILABLE:
        return _write_mp4(frames, label, output_dir, fps)
    return _write_png_sequence(frames, label, output_dir)


# ---------------------------------------------------------------------------
# Private video/image writers
# ---------------------------------------------------------------------------

def _write_mp4(pil_frames: list, label: str, output_dir: Path, fps: int) -> Optional[Path]:
    try:
        import numpy as np      # type: ignore
        path = _output_path(output_dir, label + "_clip", "mp4")
        first_bgr = _cv2.cvtColor(np.array(pil_frames[0].convert("RGB")), _cv2.COLOR_RGB2BGR)
        h_px, w_px = first_bgr.shape[:2]
        fourcc = _cv2.VideoWriter_fourcc(*"mp4v")
        writer = _cv2.VideoWriter(str(path), fourcc, fps, (w_px, h_px))
        for img in pil_frames:
            writer.write(_cv2.cvtColor(np.array(img.convert("RGB")), _cv2.COLOR_RGB2BGR))
        writer.release()
        logger.info("Clip saved: %s (%d frames)", path, len(pil_frames))
        return path
    except Exception as exc:
        logger.warning("MP4 clip write failed: %s", exc)
        return None


def _write_png_sequence(pil_frames: list, label: str, output_dir: Path) -> Optional[Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = output_dir / f"{_safe_name(label)}_clip_{ts}"
    folder.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(pil_frames):
        try:
            img.save(folder / f"frame_{i:06d}.png")
        except Exception:
            pass
    logger.info("Clip saved (PNG sequence): %s (%d frames)", folder, len(pil_frames))
    return folder
