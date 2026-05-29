# Update Guide — v5.1.0 → v5.2.0

## What's New

### Discord Integration
The launcher now has full Discord support — both Rich Presence and Webhook notifications.

**Rich Presence** shows your current status in Discord:  
- Active account name and region  
- Current session duration  
- Total playtime in the last 24 h  

**Webhook Notifications** post messages to a Discord channel:  
- Session started / session ended (with duration)  
- Launcher errors (optional)  

Configure everything in **Settings → Discord Rich Presence** and **Settings → Discord Webhook Notifications**.  
Use the **Test** button to verify your webhook URL before saving.

> **New config keys:** `discord_rich_presence`, `discord_rpc_client_id`, `discord_rpc_update_interval`, `discord_rpc_yield_to_game`, `discord_webhook_url`, `discord_notifications`, `discord_session_start`, `discord_session_end`, `discord_errors`

---

### System Tray (F4)
Press **F4** to minimize the launcher to a wizard-hat icon in the system tray.  
Right-click the tray icon → **Restore** or **Exit**.

Requires optional packages:
```
pip install pystray Pillow
```
Without them the launcher simply minimizes to the taskbar (a hint is logged on startup).

---

### 10 UI Themes
Go to **Settings → UI Theme** and pick one of ten themes:

| Theme | Style |
|---|---|
| WizDark | Default dark wizard theme |
| WizLight | Light variant |
| Midnight | Deep blue-black |
| Nord | Arctic blue palette |
| Dracula | Purple/pink dark |
| Catppuccin | Pastel mocha |
| Monokai | Classic code-editor |
| Emerald | Green dark |
| Slate | Cool grey |
| Sunset | Warm orange/red |

Theme applies immediately — no restart needed.

---

### Playtime Tracking Improvements

**auto_playtime_tracking** (Settings → Playtime Tracking)  
Toggle session recording on/off. Discord Presence continues working even when disabled.

**track_without_autologin** (Settings → Playtime Tracking)  
When enabled the launcher auto-detects any Wizard101 window that was started outside the launcher and adds it to the active session list. These appear in the Stats tab as `🟢 External #N`.

**Live Stats tab**  
The Stats table now refreshes every second automatically.  
Active accounts are highlighted with 🟢 and show the live session time: e.g. `2h 15m  (+23m)`.

**Reset Selected**  
New button in the Stats tab — select a row, click **Reset Selected**, confirm → only that account's playtime is cleared.

---

### Account Reorder (↑ / ↓)
In the **Accounts** tab, use the new **↑** and **↓** buttons to change the order of accounts in the list. The new order is saved immediately.

---

### Extra Launch Arguments
**Settings → Launch Options** now has an **Extra Args** field.  
Enter space-separated arguments (e.g. `-nosound -windowed`) that will be appended to the game executable command on every launch.

> Config key: `extra_args` (stored as a list)

---

### Performance Monitor Toggle
The **Performance** tab now has an **Enable Performance Monitoring** checkbox at the top.  
Toggle it on/off at any time — takes effect within one second. State is persisted in config.

---

### Window Position Save
Enable **Settings → UI Theme → Save Window State** to have the launcher remember its screen position and restore it on next launch.

---

### Other Improvements
- **check_for_updates** toggle in Settings disables the automatic update check on startup
- **Ctrl+S** shortcut now saves all the same fields as the Save button (they were previously out of sync)
- Stats "Refresh" button no longer rebuilds the entire window (much faster)

---

## Migration from v5.1.0

No manual migration required. The launcher automatically adds missing config keys with sensible defaults on startup:

| New Key | Default | Meaning |
|---|---|---|
| `discord_rich_presence` | `true` | Enable Rich Presence |
| `discord_rpc_yield_to_game` | `true` | Let Discord detect the game when a session is active |
| `discord_notifications` | `false` | Webhook notifications off by default |
| `discord_webhook_url` | `""` | No webhook configured |
| `discord_session_start` | `true` | Notify on session start |
| `discord_session_end` | `true` | Notify on session end |
| `discord_errors` | `false` | Don't post errors by default |
| `save_window_state` | `true` | Saves window position |
| `check_for_updates` | `true` | Checks for updates on startup |
| `auto_playtime_tracking` | `true` | Playtime tracking enabled |
| `track_without_autologin` | `true` | External session detection enabled |
| `extra_args` | `[]` | No extra launch arguments |
| `enable_performance_monitor` | `true` | Performance tab polling on |

---

## Optional Packages

Install for full feature support:

```bash
pip install pystray Pillow   # System tray (F4)
```

All other new features work without additional packages.
