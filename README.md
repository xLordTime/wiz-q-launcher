# Wiz Q Launcher v5.2.0

Open source Wizard101 launcher with quick start, multi-instance, auto-login, playtime tracking, multi-window management, and extensible wizwalker integrations.

##  Features

### Core Launcher
-  **Quicklaunch** - Start instance instantly with one click
-  **Multi-Instance** - Launch multiple instances simultaneously (up to 8 regions)
-  **Auto-Login** - Automatic account injection via wizwalker
-  **Region Support** - 8 configurable regions (DE, US, FR, IT, GB, PL, ES, GR)
-  **Account Management** - Add, edit, delete encrypted accounts with master password protection

### Extensions System
-  **Wizwall** - Multi-window management with borderless windows
  -  **Grid Layouts** - 7 preset layouts (2x1, 2x2, 3x3, 4x3, 4x4, 2x3, 3x2)
  -  **Borderless Windows** - Pixel-perfect rendering without title bars
  -  **Auto-Resolution** - Automatically sets game resolution for window size
  -  **Save/Restore Layouts** - Persist window arrangements
  -  **Account Selection** - Select which accounts to launch via checkboxes
-  **Extensible Architecture** - Easy to add new wizwalker-based extensions
-  **Toggle Extensions** - Enable/disable features via config

### Playtime Tracking
-  **Session Tracking** - Automatically track playtime when using auto-login
-  **External Session Detection** - Optionally auto-track Wizard101 windows started outside the launcher (`track_without_autologin`)
-  **Live Stats** - Stats tab refreshes every second; active accounts show a 🟢 indicator with live session time
-  **Statistics** - View total playtime, session count, and average session duration per account
-  **Reset Selected** - Reset playtime for a single account without affecting others
-  **Export Stats** - Save playtime statistics to file
-  **Reset All Stats** - Clear all playtime data (with confirmation)

### Discord Integration
-  **Rich Presence** - Shows account, region, session time, and 24 h playtime in Discord status
-  **Yield to Game** - Let Discord auto-detect the game instead of showing launcher status during active sessions
-  **Webhook Notifications** - Post session-start, session-end, and error notifications to a Discord webhook
-  **Granular Toggles** - Enable/disable each notification type independently
-  **Test Button** - Verify webhook URL with one click

### User Interface
-  **10 Themes** - WizDark, WizLight, Midnight, Nord, Dracula, Catppuccin, Monokai, Emerald, Slate, Sunset (applies immediately)
-  **System Tray (F4)** - Minimize to a wizard-hat tray icon; restore or exit from right-click menu (requires pystray + Pillow)
-  **Account Reorder** - Move accounts up/down with ↑/↓ buttons in the Accounts tab
-  **Window Position Save** - Remembers and restores the window position between sessions
-  **Performance Monitor** - Live CPU, RAM, and Wizard memory usage with enable/disable toggle

### Region Management
-  **Per-Region Configuration** - Custom install paths, servers, and ports per region
-  **Live Region Toggle** - Show/hide region tabs without restart
-  **One-Click Region Switch** - Change current region instantly
-  **Default Settings** - Reset regions to factory defaults

### User Interface
-  **App Icon** - Wizard101 themed icon in window and taskbar
-  **Modern Dark Theme** - WizDark theme with color-coded UI elements (10 themes total)
-  **Tabbed Interface** - Launch, Accounts, Extensions, Regions, Performance, Stats, Settings, Logs tabs
-  **Configurable Options** - Window title template, foreground behavior, logging level, extra launch args
-  **Log Viewer** - Quick access to application logs
-  **Keyboard Shortcuts** - F1 Quicklaunch, F2 Multi-launch, F3 Auto-login, F4 Tray, Ctrl+S Save settings

## Requirements
- Windows 10+
- Python 3.11 or 3.12 (3.12 recommended)
- (Optional) EU wizwalker fork for auto-login and extensions (recommended for DE/EU servers)
- (Optional) pywin32 for window management (auto-installed)
- (Optional) pystray + Pillow for system tray icon (`pip install pystray Pillow`)

## Download

**Pre-built Executable** (no Python required):
- Download `Q-Launcher.exe` from the [Releases](https://github.com/oliwi/q-launcher/releases) page
- Run directly - no installation needed
- All dependencies included

**From Source** (for developers):
See Installation section below

## Installation

### Option 1: Pre-built Executable (Recommended)
```bash
# Download Q-Launcher.exe from releases
# Double-click to run - that's it!
```

### Option 2: From Source
```bash
# Clone or download the repository
cd q-launcher

# Create virtual environment (optional but recommended)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Option 3: Build Your Own Executable
```bash
# After installing from source
python build.py
# Executable will be in dist/Q-Launcher.exe
```

## Quick Start

```bash
# Launch the application
python main.py
```

1. Create or unlock your master password on first run
2. Add accounts in the **Accounts** tab
3. Select region from **Launch** tab (shows current region)
4. Choose between:
   - **Quicklaunch** - Start one instance
   - **Start N** - Start multiple plain instances
   - **Start + Auto Login** - Start with automatic login and playtime tracking
## Documentation

- [Usage Guide](documentation/USAGE.md) - How to use all features
- [Configuration Reference](documentation/CONFIGURATION.md) - All config options
- [UI Overview](documentation/UI_UPDATE.md) - Region management and UI features
- [Playtime Tracker](PLAYTIME_TRACKER.md) - Session tracking details
- [Code Structure](documentation/REFACTORING.md) - Module organization

## Project Structure

```text
q-launcher/
  main.py                      # Root run entry point
  build.py                     # Root build entry point
  app/                         # App runtime modules
    main.py                    # Event loop and app controller
    ui.py                      # UI components and theme
  core/                        # Core config and logging
    config.py
    logging_utils.py
  security/                    # Encryption and account management
    crypto.py
  services/                    # Launching, tracking, utilities
    launcher.py
    playtime_tracker.py
    performance_monitor.py
    tray_icon.py
    log_viewer.py
    update_checker.py
    issue_reporter.py
    wizwall.py
  integrations/                # External integrations
    discord_integration.py     # Webhook notifications
    discord_presence.py        # Rich Presence
  scripts/                     # Build/maintenance scripts
    build.py
  documentation/               # Extended documentation
```
## Configuration

The launcher creates config.json automatically. Common settings:

```json
{
  "current_region": "de",
  "show_region_de": true,
  "show_region_us": true,
  "region_install_de": "",
  "region_server_de": "login-de.eu.wizard101.com",
  "region_port_de": 12000,
  "login_wait_seconds": 5,
  "window_title_template": "{name} ({username})",
  "foreground_on_login": true,
  "log_level": "INFO"
}
```

See [Configuration Guide](documentation/CONFIGURATION.md) for all options.

## Usage Examples

### Quick Launch
1. Go to **Launch** tab
2. Click **Quicklaunch** to start one instance
3. Wizard101 launches with current region settings

### Multi-Instance Launch with Wizwall
1. Go to **Extensions** -> **Wizwall** tab
2. Select accounts from the list (shows live counter)
3. Choose grid layout (2x2, 3x3, etc.)
4. Enable "Auto Set Resolution" for pixel-perfect windows
5. Click **Start Instances** or **Start + Auto Login**
6. Windows are automatically arranged in borderless grid layout

### Region Switching
1. Click on region tab (DE, US, FR, etc.)
2. (Optional) Edit install path, server, port
3. Click **Set as Current** button
4. Launcher switches to that region instantly

### Playtime Tracking
1. Select accounts in Launch tab
2. Click **Start + Auto Login**
3. Sessions are tracked automatically
4. View stats in **Stats** tab
5. Export or reset as needed

## Notes

- The UI uses PySimpleGUI OSS package (PySimpleGUI-4-foss). You can upgrade to the Hobbyist build if desired.
- Auto-login feature requires wizwalker package installed.
- Playtime tracking only works with **Start + Auto Login** feature.
- Account passwords are AES-256 encrypted with a master password.
- All configuration persists in config.json and is human-readable.

## Troubleshooting

**Auto-login not working?**
- Install EU fork: pip install git+https://github.com/Lapridox/wizwalker.git@2cab70d98c41ad53aef1d38e3caf3be208eeea1c
- Check logs in **Logs** tab for error messages

**Playtime not tracking?**
- Only tracks with **Start + Auto Login** by default
- Enable `track_without_autologin` in Settings > Playtime Tracking to also track externally started instances
- Ensure instances launched through the launcher
- Close instances normally (don't force-close)

**Region settings resetting?**
- Check that config.json is writable
- Verify region code matches REGION_META in config.py

## License

MIT License - See LICENSE file for details

## Version History

- **v5.2.0** (2026-05-29) - Discord integration, system tray, 10 themes, playtime overhaul, UI improvements
- **v5.1.0** (2026-03-15) - Version alignment and release numbering cleanup
- **v0.4.0** (2026-02-16) - Extensions system, Wizwall, borderless windows, region-specific accounts, .exe builds
- **v0.3.0** (2026-02-15) - Multi-window manager, grid layouts
- **v0.2.0** (2026-02-14) - Playtime tracking, region management, stats
- **v0.1.0** (2026-02-13) - Initial release with quicklaunch and auto-login




