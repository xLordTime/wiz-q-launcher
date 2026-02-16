# Multi-Window Management Guide

## Overview

The **Window Manager** allows you to arrange multiple Wizard101 windows in configurable grid layouts with a single click. Enhanced with **wizwalker integration** for accurate window detection and manipulation.

## Features

### Wizwalker Integration 🆕
- **Enhanced Detection** - Uses wizwalker's `get_all_wizard_handles()` for 100% accurate window detection
- **Smart Fallback** - Falls back to win32gui if wizwalker unavailable
- **Window Info** - Leverages wizwalker's `get_window_rectangle()` and `get_window_title()`
- **Better Foreground** - Uses wizwalker's `set_foreground_window()` for reliable window focus

### Grid Layouts
- **2x1** - Two windows side-by-side
- **1x2** - Two windows stacked vertically
- **2x2** - Four windows in 2x2 grid
- **3x2** - Six windows in 3x2 grid
- **3x3** - Nine windows in 3x3 grid
- **4x2** - Eight windows in 4x2 grid
- **4x3** - Twelve windows in 4x3 grid

### Window Detection
- Automatically detects all active Wizard101 windows via **wizwalker** (primary) or win32gui (fallback)
- Maps windows to account names (when using auto-login)
- Shows window count and account mapping

### Layout Management 🆕
- **Save Current Layout** - Capture current window positions for all active windows
- **Restore Layout** - Restore previously saved window arrangement
- **Get Window Position** - Query current position/size of any window

## Usage

### Quick Start
1. Launch multiple Wizard101 instances (via "Start N" or "Start + Auto Login")
2. Go to **Launch** tab
3. Select grid layout from dropdown (e.g., "2x2")
4. Click **📐 Arrange Windows**
5. All detected windows will be positioned in the selected grid

### Refresh Window List
- Click **🔄 Refresh Window List** to see all currently active Wizard101 windows
- Shows account names and window titles
- Useful for verifying window detection before arranging

### Selective Arrangement
Coming soon: Select specific windows to include/exclude from arrangement.
`wizwalker` library (optional but recommended for enhanced detection)
- Windows operating system
- Admin privileges may be required for some window operations

### Window Detection
The manager detects Wizard101 windows using a two-tier approach:
1. **Primary**: wizwalker's `get_all_wizard_handles()` (most accurate, requires wizwalker installed)
2. **Fallback**: win32gui enumeration by class name `SDL_app` or title containing "Wizard101"

Wizwalker detection is preferred as it uses game-specific process detection for 100% accuracy. some window operations

### Window Detection
The manager detects Wizard101 windows by:
1. Class name: `SDL_app` (standard Wizard101 window class)
2. Window title containing "Wizard101"

### Layout Calculation
- Automatically calculates optimal window size based on screen resolution
- Applies 10px padding between windows by default
- Centres layout on primary monitor

### Account Mapping
When using **Start + Auto Login**, windows are tracked with their account names:
- Displayed in window refresh popup
- Logged for debugging
- Used for selective arrangement (future feature)

## Configuration

No manual configuration required. The window manager:
- Auto-detects screen resolution
- Uses primary monitor by default
- Calculates optimal cell sizes for selected layout

## Troubleshooting

### Windows not detected
- Ensure Wizard101 instances are fully loaded
- Try clicking **Refresh Window List** to verify detection
- Check logs for detection errors

### Arrangement fails
- Verify windows are not minimized
- Ensure sufficient screen space for selected layout
- Check if `pywin32` is installed: `pip list | findstr pywin32`

### Windows overlap or incorrect size
- Try a different layout (fewer cells)
- Check if multiple monitors are active
- Verify no third-party window managers are interfering
Programmatic Usage

```python
from window_manager import WindowManager

# Initialize manager
manager = WindowManager()

# Get all windows
windows = manager.get_wizard_windows()

# Arrange in 2x2 grid
manager.arrange_grid(windows, layout="2x2")

# Save current layout
saved_layout = manager.save_current_layout(windows)

# Later: restore that layout
manager.restore_layout(saved_layout)

# Get position of specific window
pos = manager.get_window_position(window_handle)  # Returns (x, y, width, height)
```

### 
## Advanced Usage

### Custom Layouts
To add custom layouts, edit `window_manager.py`:

```python
PRESET_LAYOUTS = {
    "1x1": "Single window (fullscreen)",
    "2x1": "Two windows (side-by-side)",
    # Add your custom layout here:
    "5x2": "Ten windows (5x2 grid)",
}
```

### Multi-Monitor Support
Coming soon: Select target monitor for arrangement.

### Saved Layouts
Coming soon: Save and load custom window arrangements per account set.

## Keyboard Shortcuts

Future feature: Quick-arrange hotkeys (e.g., `Ctrl+Shift+1` for 2x2 layout).

## See Also

- [Usage Guide](USAGE.md) - General launcher usage
- [Configuration](CONFIGURATION.md) - Config options
- [README](../README.md) - Main documentation
