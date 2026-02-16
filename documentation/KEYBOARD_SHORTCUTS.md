"""
Keyboard Shortcuts & Integration Guide

=== KEYBOARD SHORTCUTS ===

F1  - Quicklaunch (Start one instance immediately)
F2  - Start Multi-Instance (Launch N instances based on count setting)
F3  - Start + Auto-Login (Launch with credentials + playtime tracking)
F4  - Minimize/Show Window (Toggle window visibility)

Ctrl+E - Export Playtime Statistics (Quick export shortcut)
Ctrl+S - Save Settings (Quick save configuration)

=== FEATURES ===

Live Log Viewer Tab
-------------------
The Logs tab now shows a live, interactive log viewer with:

- Refresh Button: Reload latest logs from file
- Search Box: Find specific text in logs  
- Filter by Level: Show only DEBUG/INFO/WARNING/ERROR
- Export Button: Save all logs to timestamped file
- Auto-reload: Logs update periodically

To use:
1. Click Logs tab
2. Enter search term and click Search
3. Or select log level to filter
4. Click Refresh to reload
5. Click Export to save logs


Dark/Light Theme Toggle
-----------------------
Switch between themes in Settings tab:

- WizDark (default): Dark theme optimized for gaming
- WizLight: Light theme for daytime use

Changes apply immediately with full window rebuild.


Discord Webhook Integration
---------------------------
Send notifications to Discord when sessions start/end:

1. Go to Settings tab
2. Configure in config.json:
   - "discord_webhook_url": "https://discord.com/api/webhooks/..."
   - "discord_notifications": true
   - "discord_session_start": true
   - "discord_session_end": true

Session notifications include:
- Account name and username
- Current region
- Session duration (on end)

To get webhook URL:
1. Open Discord server
2. Server Settings → Webhooks
3. Create New Webhook
4. Copy webhook URL


Performance Monitoring
---------------------
Monitor system and process performance:

- CPU usage (%)
- Memory usage (%)  
- Wizard101 process memory (MB)
- Historical data with averages and peaks

Enabled by default, toggle in config.json:
"enable_performance_monitor": true


Auto-Update Checking
-------------------
Check for new releases automatically:

Enabled by default. Connect to:
https://github.com/oliwi/q-launcher/releases

Checks weekly for new versions.
Manual update checking in Settings tab (future).


Error Reporting
---------------
Automatically report errors to GitHub or Discord:

- Crash reports sent to GitHub issues (if token configured)
- Fallback to Discord webhook  
- Stack traces and context included

Errors help identify and fix bugs faster!

=== CONFIGURATION ===

New config.json keys for advanced features:

Debug Mode
----------
"debug_mode": false                    # Enable verbose logging

Auto-Region-Switching  
----------------------
"auto_region_switch": false            # Auto-switch per account
"account_region_map": {}               # {account_name: region_code}

Auto-Playtime Tracking
----------------------
"auto_playtime_tracking": true         # Track all sessions
"track_without_autologin": true        # Detect process starts

Discord Integration
-------------------
"discord_webhook_url": ""              # Webhook for notifications
"discord_notifications": false         # Enable/disable
"discord_session_start": true          # Notify on start
"discord_session_end": true            # Notify on end
"discord_errors": true                 # Notify on errors

Performance Monitoring
---------------------
"enable_performance_monitor": true     # Monitor CPU/Memory
"performance_poll_interval": 5         # Poll every N seconds

Update Checking
---------------
"check_for_updates": true              # Auto-check for updates
"update_check_interval": 86400         # Check every 24h

Window State
-----------
"save_window_state": true              # Remember position/size
"window_width": 900                    # Window width
"window_height": 700                   # Window height
"window_x": null                       # X position
"window_y": null                       # Y position

=== TRAY ICON (Future) ===

F4 currently minimizes/shows window.
Full system tray support coming in next update with:
- Click to restore
- Right-click menu
- Notifications
- Background operation
