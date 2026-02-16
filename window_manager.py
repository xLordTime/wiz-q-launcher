"""
Window Manager - Multi-Window Grid Layout and Positioning

Provides tools to arrange multiple Wizard101 windows in configurable grid layouts.
Supports selective window arrangement, custom monitor selection, and preset layouts.

Integrates with wizwalker for enhanced window detection and manipulation.
"""

import logging
import ctypes
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

try:
    import win32gui  # type: ignore
    import win32con  # type: ignore
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    from wizwalker.utils import (
        get_all_wizard_handles,
        get_window_rectangle,
        get_window_title,
        set_foreground_window as wizwalker_set_foreground,
        Rectangle as WizwalkerRectangle,
    )
    WIZWALKER_AVAILABLE = True
except ImportError:
    WIZWALKER_AVAILABLE = False


@dataclass
class WindowInfo:
    """Information about a window to be managed."""
    handle: int
    title: str
    account_name: str
    
    def __repr__(self):
        return f"Window(handle={self.handle}, title='{self.title}', account='{self.account_name}')"


@dataclass
class MonitorInfo:
    """Screen/monitor dimensions."""
    x: int
    y: int
    width: int
    height: int
    
    @classmethod
    def get_primary(cls) -> "MonitorInfo":
        """Get primary monitor dimensions."""
        if WIN32_AVAILABLE:
            import ctypes
            user32 = ctypes.windll.user32
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            return cls(x=0, y=0, width=width, height=height)
        # Fallback for non-Windows or missing win32
        return cls(x=0, y=0, width=1920, height=1080)


class WindowManager:
    """
    Manages multi-window layouts for Wizard101 instances.
    
    Features:
    - Grid layouts (1x1, 2x1, 2x2, 3x2, 3x3, 4x2, etc.)
    - Custom positioning per window
    - Monitor selection support
    - Selective window arrangement
    - wizwalker integration for enhanced detection
    
    Example:
        manager = WindowManager()
        windows = manager.get_wizard_windows()
        manager.arrange_grid(windows, layout="2x2")
    """
    
    def __init__(self):
        self.logger = logging.getLogger("window_manager")
        if WIZWALKER_AVAILABLE:
            self.logger.info("Window Manager initialized with wizwalker support")
        elif WIN32_AVAILABLE:
            self.logger.info("Window Manager initialized with win32gui only")
        else:
            self.logger.warning("Window management disabled - no wizwalker or win32gui")
    
    def get_wizard_windows(self, account_map: Optional[Dict[int, str]] = None) -> List[WindowInfo]:
        """
        Get all currently active Wizard101 windows.
        
        Uses wizwalker's get_all_wizard_handles for accurate detection if available,
        falls back to win32gui enumeration otherwise.
        
        Args:
            account_map: Optional dict mapping window handles to account names
            
        Returns:
            List of WindowInfo objects for all Wizard101 windows
        """
        windows = []
        
        # Prefer wizwalker for window detection (more accurate)
        if WIZWALKER_AVAILABLE:
            try:
                handles = get_all_wizard_handles()
                self.logger.debug(f"wizwalker found {len(handles)} handles")
                
                for handle in handles:
                    try:
                        title = get_window_title(handle)
                        account_name = account_map.get(handle, "Unknown") if account_map else "Unknown"
                        windows.append(WindowInfo(
                            handle=handle,
                            title=title,
                            account_name=account_name
                        ))
                    except Exception as e:
                        self.logger.warning(f"Failed to get info for handle {handle}: {e}")
                
                self.logger.info(f"Found {len(windows)} Wizard101 windows via wizwalker")
                return windows
            except Exception as e:
                self.logger.warning(f"wizwalker detection failed, falling back to win32gui: {e}")
        
        # Fallback to win32gui enumeration
        if not WIN32_AVAILABLE:
            self.logger.warning("Neither wizwalker nor win32gui available")
            return []
        
        def enum_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                
                # Detect Wizard101 windows by class name
                if class_name == "SDL_app" or "Wizard101" in title:
                    account_name = account_map.get(hwnd, "Unknown") if account_map else "Unknown"
                    windows.append(WindowInfo(
                        handle=hwnd,
                        title=title,
                        account_name=account_name
                    ))
            return True
        
        try:
            win32gui.EnumWindows(enum_callback, None)
            self.logger.info(f"Found {len(windows)} Wizard101 windows via win32gui")
        except Exception as e:
            self.logger.exception(f"Failed to enumerate windows: {e}")
        
        return windows
    
    def move_window(self, handle: int, x: int, y: int, width: int, height: int) -> bool:
        """
        Move and resize a window.
        
        Creates a borderless window with correct client area size for pixel-perfect rendering.
        This ensures mouse coordinates match the game rendering.
        
        Args:
            handle: Window handle
            x, y: Top-left position
            width, height: Window dimensions (client area)
            
        Returns:
            True if successful
        """
        if not WIN32_AVAILABLE:
            return False
        
        try:
            # Get user32 for advanced window manipulation
            user32 = ctypes.windll.user32
            
            # Window style constants
            GWL_STYLE = -16
            WS_OVERLAPPEDWINDOW = 0x00CF0000
            WS_POPUP = 0x80000000
            SWP_FRAMECHANGED = 0x0020
            SWP_SHOWWINDOW = 0x0040
            
            # Ensure window is in normal state
            win32gui.ShowWindow(handle, win32con.SW_SHOWNORMAL)
            
            # Change to borderless popup style for pixel-perfect rendering
            current_style = user32.GetWindowLongW(handle, GWL_STYLE)
            new_style = (current_style & ~WS_OVERLAPPEDWINDOW) | WS_POPUP
            user32.SetWindowLongW(handle, GWL_STYLE, new_style)
            
            # Set position and size with proper flags
            # Flags: SWP_FRAMECHANGED (apply style change) | SWP_SHOWWINDOW (show window)
            user32.SetWindowPos(
                handle,
                0,  # hwndInsertAfter (0 = HWND_TOP)
                x, y,
                width, height,
                SWP_FRAMECHANGED | SWP_SHOWWINDOW
            )
            
            # Update and activate
            win32gui.UpdateWindow(handle)
            win32gui.SetForegroundWindow(handle)
            
            self.logger.debug(f"Moved window {handle} to ({x}, {y}) size ({width}x{height}) [borderless]")
            return True
        except Exception as e:
            self.logger.exception(f"Failed to move window {handle}: {e}")
            return False
    
    def get_window_position(self, handle: int) -> Optional[Tuple[int, int, int, int]]:
        """
        Get current window position and size.
        
        Uses wizwalker's get_window_rectangle for accurate detection if available.
        
        Args:
            handle: Window handle
            
        Returns:
            Tuple of (x, y, width, height) or None if failed
        """
        # Prefer wizwalker's get_window_rectangle
        if WIZWALKER_AVAILABLE:
            try:
                rect = get_window_rectangle(handle)
                x = rect.x1
                y = rect.y1
                width = rect.x2 - rect.x1
                height = rect.y2 - rect.y1
                return (x, y, width, height)
            except Exception as e:
                self.logger.warning(f"wizwalker get_window_position failed: {e}")
        
        # Fallback to win32gui
        if WIN32_AVAILABLE:
            try:
                rect = win32gui.GetWindowRect(handle)
                x, y, right, bottom = rect
                width = right - x
                height = bottom - y
                return (x, y, width, height)
            except Exception as e:
                self.logger.exception(f"Failed to get window position for {handle}: {e}")
        
        return None
    
    def parse_layout(self, layout: str) -> Tuple[int, int]:
        """
        Parse layout string like "2x2" into (cols, rows).
        
        Args:
            layout: Layout string (e.g., "2x2", "3x3", "4x2")
            
        Returns:
            Tuple of (columns, rows)
        """
        try:
            parts = layout.lower().split("x")
            if len(parts) == 2:
                cols = int(parts[0])
                rows = int(parts[1])
                return (cols, rows)
        except ValueError:
            pass
        
        self.logger.warning(f"Invalid layout format '{layout}', defaulting to 2x2")
        return (2, 2)
    
    def calculate_grid_positions(
        self,
        num_windows: int,
        layout: str,
        monitor: Optional[MonitorInfo] = None,
        padding: int = 5
    ) -> List[Tuple[int, int, int, int]]:
        """
        Calculate grid positions for windows.
        
        Args:
            num_windows: Number of windows to arrange
            layout: Grid layout string (e.g., "2x2")
            monitor: Monitor to use (defaults to primary)
            padding: Padding between windows in pixels
            
        Returns:
            List of (x, y, width, height) tuples for each window
        """
        if monitor is None:
            monitor = MonitorInfo.get_primary()
        
        cols, rows = self.parse_layout(layout)
        
        # Calculate cell dimensions
        usable_width = monitor.width - (padding * (cols + 1))
        usable_height = monitor.height - (padding * (rows + 1))
        cell_width = usable_width // cols
        cell_height = usable_height // rows
        
        positions = []
        for i in range(min(num_windows, cols * rows)):
            col = i % cols
            row = i // cols
            
            x = monitor.x + padding + (col * (cell_width + padding))
            y = monitor.y + padding + (row * (cell_height + padding))
            
            positions.append((x, y, cell_width, cell_height))
        
        return positions
    
    def arrange_grid(
        self,
        windows: List[WindowInfo],
        layout: str = "2x2",
        monitor: Optional[MonitorInfo] = None,
        padding: int = 5
    ) -> int:
        """
        Arrange windows in a grid layout.
        
        Args:
            windows: List of WindowInfo objects to arrange
            layout: Grid layout (e.g., "2x2", "3x3", "4x2")
            monitor: Target monitor (defaults to primary)
            padding: Spacing between windows
            
        Returns:
            Number of windows successfully arranged
        """
        if not WIN32_AVAILABLE:
            self.logger.warning("win32gui not available - cannot arrange windows")
            return 0
        
        if not windows:
            self.logger.info("No windows to arrange")
            return 0
        
        positions = self.calculate_grid_positions(
            num_windows=len(windows),
            layout=layout,
            monitor=monitor,
            padding=padding
        )
        
        arranged_count = 0
        for window, (x, y, w, h) in zip(windows, positions):
            if self.move_window(window.handle, x, y, w, h):
                arranged_count += 1
                self.logger.info(
                    f"Arranged '{window.account_name}' at grid position "
                    f"({x}, {y}) size ({w}x{h})"
                )
                # Small delay to let Windows process the change
                import time
                time.sleep(0.05)  # 50ms between windows
        
        self.logger.info(f"Arranged {arranged_count}/{len(windows)} windows in {layout} layout")
        return arranged_count
    
    def arrange_custom(
        self,
        windows: List[WindowInfo],
        positions: List[Tuple[int, int, int, int]]
    ) -> int:
        """
        Arrange windows at custom positions.
        
        Args:
            windows: List of windows to arrange
            positions: List of (x, y, width, height) tuples
            
        Returns:
            Number of windows successfully arranged
        """
        if not WIN32_AVAILABLE:
            return 0
        
        arranged_count = 0
        for window, (x, y, w, h) in zip(windows, positions):
            if self.move_window(window.handle, x, y, w, h):
                arranged_count += 1
        
        return arranged_count
    
    def bring_to_front(self, handle: int) -> bool:
        """
        Bring a window to the foreground and ensure it's usable.
        
        Uses wizwalker's set_foreground_window if available for better compatibility.
        
        Args:
            handle: Window handle
            
        Returns:
            True if successful
        """
        if not WIN32_AVAILABLE and not WIZWALKER_AVAILABLE:
            return False
        
        try:
            # Ensure window is not minimized
            if WIN32_AVAILABLE:
                win32gui.ShowWindow(handle, win32con.SW_SHOWNORMAL)
            
            # Prefer wizwalker's implementation for bringing to front
            if WIZWALKER_AVAILABLE:
                try:
                    wizwalker_set_foreground(handle)
                except Exception as e:
                    self.logger.warning(f"wizwalker bring_to_front failed, trying win32gui: {e}")
                    if WIN32_AVAILABLE:
                        win32gui.SetForegroundWindow(handle)
            elif WIN32_AVAILABLE:
                win32gui.SetForegroundWindow(handle)
            
            return True
        except Exception as e:
            self.logger.exception(f"Failed to bring window {handle} to front: {e}")
            return False
    
    def minimize_window(self, handle: int) -> bool:
        """Minimize a window."""
        if not WIN32_AVAILABLE:
            return False
        
        try:
            win32gui.ShowWindow(handle, win32con.SW_MINIMIZE)
            return True
        except Exception as e:
            self.logger.exception(f"Failed to minimize window {handle}: {e}")
            return False
    
    def restore_window(self, handle: int) -> bool:
        """Restore a minimized or maximized window to normal state."""
        if not WIN32_AVAILABLE:
            return False
        
        try:
            # Use SW_SHOWNORMAL instead of SW_RESTORE for better usability
            win32gui.ShowWindow(handle, win32con.SW_SHOWNORMAL)
            win32gui.UpdateWindow(handle)
            return True
        except Exception as e:
            self.logger.exception(f"Failed to restore window {handle}: {e}")
            return False
    
    def save_current_layout(self, windows: Optional[List[WindowInfo]] = None) -> Dict[int, Tuple[int, int, int, int]]:
        """
        Save current window positions for all detected Wizard101 windows.
        
        Args:
            windows: Optional list of windows (if None, auto-detects all)
            
        Returns:
            Dict mapping window handles to (x, y, width, height) tuples
        """
        if windows is None:
            windows = self.get_wizard_windows()
        
        layout = {}
        for window in windows:
            pos = self.get_window_position(window.handle)
            if pos:
                layout[window.handle] = pos
                self.logger.debug(f"Saved position for {window.account_name}: {pos}")
        
        self.logger.info(f"Saved layout for {len(layout)} windows")
        return layout
    
    def restore_layout(self, layout: Dict[int, Tuple[int, int, int, int]]) -> int:
        """
        Restore windows to saved positions.
        
        Args:
            layout: Dict mapping window handles to (x, y, width, height) tuples
            
        Returns:
            Number of windows successfully restored
        """
        restored_count = 0
        for handle, (x, y, w, h) in layout.items():
            if self.move_window(handle, x, y, w, h):
                restored_count += 1
                self.logger.debug(f"Restored window {handle} to position ({x}, {y}) size ({w}x{h})")
        
        self.logger.info(f"Restored {restored_count}/{len(layout)} windows")
        return restored_count
    
    def get_optimal_resolution_for_layout(
        self,
        layout: str = "2x2",
        monitor: Optional[MonitorInfo] = None,
        padding: int = 5
    ) -> Tuple[int, int]:
        """
        Calculate optimal window resolution for a grid layout.
        
        This resolution should be set in Wizard101's preferences.xml BEFORE starting clients
        to ensure pixel-perfect mouse coordination.
        
        Args:
            layout: Grid layout (e.g., "2x2", "3x3")
            monitor: Monitor to use (defaults to primary)
            padding: Padding between windows in pixels
            
        Returns:
            Tuple of (width, height) for window resolution
        """
        if monitor is None:
            monitor = MonitorInfo.get_primary()
        
        cols, rows = self.parse_layout(layout)
        
        # Calculate cell dimensions
        usable_width = monitor.width - (padding * (cols + 1))
        usable_height = monitor.height - (padding * (rows + 1))
        cell_width = usable_width // cols
        cell_height = usable_height // rows
        
        return (cell_width, cell_height)
    
    def set_game_resolution(
        self,
        width: int,
        height: int,
        wiz_install_path: str
    ) -> bool:
        """
        Set the game resolution in preferences.xml.
        
        IMPORTANT: Wizard101 clients must be RESTARTED after this for changes to take effect!
        
        Args:
            width: Window width in pixels
            height: Window height in pixels
            wiz_install_path: Path to Wizard101 installation folder
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from pathlib import Path
            
            prefs_path = Path(wiz_install_path) / "Bin" / "preferences.xml"
            
            if not prefs_path.exists():
                self.logger.error(f"preferences.xml not found at {prefs_path}")
                return False
            
            # Read current preferences
            with open(prefs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Modify resolution lines
            # Line 56: IsFullscreen (set to 0 for windowed mode)
            # Line 57: Resolution string
            modified = False
            for i, line in enumerate(lines):
                if '<IsFullscreen TYPE="INT">' in line:
                    lines[i] = f'    <IsFullscreen TYPE="INT">0</IsFullscreen>\n'
                    modified = True
                    self.logger.debug(f"Set IsFullscreen to 0 at line {i}")
                elif '<Resolution TYPE="STR">' in line:
                    lines[i] = f'    <Resolution TYPE="STR">{width}x{height}</Resolution>\n'
                    modified = True
                    self.logger.debug(f"Set Resolution to {width}x{height} at line {i}")
            
            if not modified:
                self.logger.warning("Could not find Resolution/IsFullscreen tags in preferences.xml")
                return False
            
            # Write back
            with open(prefs_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            self.logger.info(f"Set game resolution to {width}x{height} in {prefs_path}")
            self.logger.warning("⚠️  Wizard101 clients must be RESTARTED for resolution changes to take effect!")
            return True
            
        except Exception as e:
            self.logger.exception(f"Failed to set game resolution: {e}")
            return False


# Preset layouts for quick selection
PRESET_LAYOUTS = {
    "1x1": "Single window (fullscreen)",
    "2x1": "Two windows (side-by-side)",
    "1x2": "Two windows (stacked)",
    "2x2": "Four windows (2x2 grid)",
    "3x2": "Six windows (3x2 grid)",
    "3x3": "Nine windows (3x3 grid)",
    "4x2": "Eight windows (4x2 grid)",
    "4x3": "Twelve windows (4x3 grid)",
}
