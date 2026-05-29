# Changelog

## v5.2.0 (2026-05-29) - Discord, Tray, Playtime & UI Overhaul

### ✨ New Features

#### Discord Integration
- **Discord Rich Presence** — Live status with account name, region, session time, and 24 h playtime; auto-updates every N seconds (configurable)
- **discord_rpc_yield_to_game** — Checkbox to let Discord auto-detect the game instead of showing the launcher status when a session is active
- **Discord Webhook Notifications** — Full webhook URL input + enable/disable toggle in Settings; separate toggles for session-start, session-end, and error notifications
- **Webhook Test Button** — One-click test ping to verify the webhook URL is working
- **discord_errors** — Optionally posts a webhook message when the launcher crashes in the TIMEOUT handler

#### System Tray (F4)
- **Tray icon via pystray + Pillow** — F4 now minimizes to a wizard-hat tray icon instead of just hiding; right-click menu with Restore and Exit; graceful fallback when pystray/Pillow are not installed
- `services/tray_icon.py` — New module with `TrayIcon` class and `TRAY_AVAILABLE` flag
- Startup log hint when pystray is missing

#### Playtime Tracking Improvements
- **auto_playtime_tracking toggle** — Enable/disable session tracking globally; Discord presence still works when disabled
- **track_without_autologin** — Auto-detects externally started Wizard101 windows and adds them to the session tracker even when not launched via the launcher
- **Live Stats table** — Stats tab auto-refreshes every second; active accounts show a 🟢 indicator and live `(+Xm)` session time; externally tracked windows appear as `🟢 External #N` rows
- **Reset Selected Account** — New button in Stats tab resets playtime for a single selected account (with confirmation); no window rebuild needed
- **Reset All Stats** now updates the table in-place instead of rebuilding the window

#### UI & Settings
- **10 Themes** — WizDark, WizLight, Midnight, Nord, Dracula, Catppuccin, Monokai, Emerald, Slate, Sunset; theme applies immediately without restart
- **Account Reorder (↑/↓)** — New buttons in Accounts tab to move accounts up/down in the list
- **extra_args** — Space-separated launch arguments field in Settings passed directly to the game executable
- **check_for_updates toggle** — Checkbox to enable/disable automatic update checks on startup
- **save_window_state** — Saves and restores the window position on next launch
- **Performance Monitor Enable/Disable** — Checkbox at the top of the Performance tab; takes effect within 1 second; persisted in config

### 🔧 Improvements
- `send_session_ended` was never being called — fixed; duration is now correctly passed to Discord and stats
- `discord_session_start` / `discord_session_end` toggles are now actually checked before sending notifications
- Stats "Refresh" button no longer rebuilds the entire window; updates the table in-place
- All new settings are saved by both the "Save settings" button and the Ctrl+S shortcut
- `window_x` / `window_y` saved on exit and restored via `sg.Window(location=...)` on next start
- Ctrl+S shortcut wires all the same keys as the Save button (previously they diverged)

### 🐛 Bug Fixes
- **Pylance `DiscordIntegration` is unbound** — redundant local import inside the webhook-test handler caused Python to treat `DiscordIntegration` as a local variable throughout `main()`, making any earlier usage an `UnboundLocalError`; removed the duplicate import
- `track_session_start` was called unconditionally even when `auto_playtime_tracking = False`
- `get_wizard_handles_safe()` was only called inside the `if active_sessions:` guard, making `track_without_autologin` effectively a no-op — hoisted the call outside the guard
- Theme tooltip said "Restart the launcher to apply" — theme now rebuilds the window immediately

### 📦 Dependencies
- Added `pystray>=0.19.0` and `Pillow>=10.0.0` to `requirements.txt` (optional, graceful fallback)

---

## v5.1.0 (2026-03-15) - Version Alignment
### 🔧 Changes
- Unified project version to 5.1.0 across application code and documentation.
- Added this release entry and preserved historical release numbering.

---

## v0.3.0 (2026-02-16) - Multi-Window Manager & App Icon
### ✨ New Features
- **Multi-Window Manager**: Arrange multiple Wizard101 windows in grid layouts
  - Support for 7 preset layouts: 2x1, 1x2, 2x2, 3x2, 3x3, 4x2, 4x3
  - **wizwalker Integration**: Enhanced window detection via `get_all_wizard_handles()`
  - **Smart Fallback**: Auto-falls back to win32gui if wizwalker unavailable
  - **Window Info**: Uses wizwalker's `get_window_rectangle()` and `get_window_title()`
  - **Layout Saving**: Save and restore custom window arrangements
  - **Position Query**: Get current position/size of any window
  - Automatic window detection with account mapping
  - One-click window arrangement with configurable padding
  - "Refresh Window List" to view all active windows
  - Integration with auto-login session tracking
- **App Icon**: Added Wizard101-themed icon (icon.png)
  - Automatic PNG to ICO conversion (with Pillow if available)
  - Configurable via `app_icon_path` in config.json
  - Window icon displayed in taskbar and window frame
- **Enhanced Launch Tab**: New "Multi-Window Management" section
  - Grid layout dropdown selector
  - "Arrange Windows" and "Refresh Window List" buttons
  - Compact account selection layout (size optimized)
- **Dependencies**: Added `pywin32>=307` for window management

### 🔧 Improvements
- **wizwalker Integration Enhanced**: Window Manager now uses wizwalker APIs as primary method
- Fixed `requirements.txt` formatting
- Improved error handling in main event loop
- Better module initialization with try-except wrappers

### 🐛 Bug Fixes
- Fixed syntax errors in main.py event loop structure
- Fixed bind_all() AttributeError (changed to bind())
- Fixed IssueReporter backtick escape sequences
- Resolved indentation issues after error handling additions

---

## v0.2.0 (2026-02-14) - Playtime Tracking & Region Management
### ✨ New Features
- **Playtime Tracker**: Automatically track session time per account
- **Region Management**: Support for 8 regions with per-region configuration
- **Enhanced UI**: New Stats tab showing playtime statistics for all accounts
- **Refactored Architecture**: Modular code structure
- **Account Features**: Edit and delete existing accounts
- **Improved Logging**: Dedicated logging_utils module with rotating logs

### 🐛 Bug Fixes
- Fixed region switching with proper window rebuild
- Fixed playtime tracking for multiple concurrent sessions
- Improved handle detection for new instances

---

## v0.1.0 (2026-02-13) - Initial Release
### ✨ Initial Features
- Quicklaunch with configurable server, port, and region
- Multi-instance start with optional auto-login via wizwalker
- Encrypted account storage with master password
- Install path detection (config, default path, registry)
- Window title and foreground control for started clients
- Configurable logging with rotating logs
- PyInstaller and GitHub Actions build workflow


## v0.3.0 (2026-02-16) - Multi-Window Manager & App Icon
### ✨ New Features
- **Multi-Window Manager**: Arrange multiple Wizard101 windows in grid layouts
  - Support for 7 preset layouts: 2x1, 1x2, 2x2, 3x2, 3x3, 4x2, 4x3
  - **wizwalker Integration**: Enhanced window detection via `get_all_wizard_handles()`
  - **Smart Fallback**: Auto-falls back to win32gui if wizwalker unavailable
  - **Window Info**: Uses wizwalker's `get_window_rectangle()` and `get_window_title()`
  - **Layout Saving**: Save and restore custom window arrangements
  - **Position Query**: Get current position/size of any window
  - Automatic window detection with account mapping
  - One-click window arrangement with configurable padding
  - "Refresh Window List" to view all active windows
  - Integration with auto-login session tracking
- **App Icon**: Added Wizard101-themed icon (icon.png)
  - Automatic PNG to ICO conversion (with Pillow if available)
  - Configurable via `app_icon_path` in config.json
  - Window icon displayed in taskbar and window frame
- **Enhanced Launch Tab**: New "Multi-Window Management" section
  - Grid layout dropdown selector
  - "Arrange Windows" and "Refresh Window List" buttons
  - Compact account selection layout (size optimized)
- **Dependencies**: Added `pywin32>=307` for window management

### 🔧 Improvements
- **wizwalker Integration Enhanced**: Window Manager now uses wizwalker APIs as primary method
  - `get_all_wizard_handles()` for accurate window detection
  - `get_window_rectangle()` for precise position/size querying
  - `get_window_title()` for window information
  - `set_foreground_window()` for reliable window focusing
- Fixed `requirements.txt` formatting (wizwalker line break issue)
- Improved error handling in main event loop
- Better module initialization with try-except wrappers

### 📝 Documentation
- Added WINDOW_MANAGER.md with complete window management guide including wizwalker integration details
- Updated README.md with window manager feature and wizwalker enhancements

### 🐛 Bug Fixes
- Fixed syntax errors in main.py event loop structure
- Fixed bind_all() AttributeError (changed to bind())
- Fixed IssueReporter backtick escape sequences
- Resolved indentation issues after error handling additions

---

## v0.2.0 (2026-02-14) - Playtime Tracking & Region Management
### ✨ New Features
- **Playtime Tracker**: Automatically track session time per account
  - Total playtime, session count, and average session duration
  - Stats export to file
  - Reset all stats functionality
- **Region Management**: Support for 8 regions with per-region configuration
  - DE (Deutschland), US (United States), FR (France), IT (Italia), GB (United Kingdom), PL (Polska), ES (España), GR (Ελλάδα)
  - Per-region tabs with custom install paths, servers, and ports
  - Live region visibility toggle (no restart needed)
  - One-click region switching
- **Enhanced UI**: New Stats tab showing playtime statistics for all accounts
- **Refactored Architecture**: Modular code structure (config, crypto, launcher, ui, logging_utils, playtime_tracker)
- **Account Features**: Edit and delete existing accounts
- **Improved Logging**: Dedicated logging_utils module with rotating logs

### 🐛 Bug Fixes
- Fixed region switching with proper window rebuild
- Fixed playtime tracking for multiple concurrent sessions
- Improved handle detection for new instances

### 📝 Documentation
- Added PLAYTIME_TRACKER.md with full tracking documentation
- Updated UI_UPDATE.md with region management details
- Added REFACTORING.md documenting code structure
- Extended USAGE.md with new features
- Expanded CONFIGURATION.md with region-specific keys

---

## v0.1.0 (2026-02-13) - Initial Release
### ✨ Initial Features
- Quicklaunch with configurable server, port, and region
- Multi-instance start with optional auto-login via wizwalker
- Encrypted account storage with master password
- Install path detection (config, default path, registry)
- Window title and foreground control for started clients
- Configurable logging with rotating logs
- PyInstaller and GitHub Actions build workflow
