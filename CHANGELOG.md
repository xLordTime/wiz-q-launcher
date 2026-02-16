# Changelog

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
