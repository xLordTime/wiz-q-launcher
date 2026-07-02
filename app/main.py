"""
Wizard101 Launcher - Main Application Entry Point

This is the main event loop and application controller. It handles:
- User interactions and events from the UI
- Account management (add, edit, delete accounts)
- Launcher operations (quicklaunch, multi-instance, auto-login)
- Region switching and configuration
- Playtime tracking
- Configuration persistence

Architecture:
- ui.py: UI components and layouts
- config.py: Configuration management
- crypto.py: Account encryption/decryption
- launcher.py: Game launching logic
- playtime_tracker.py: Session tracking
- logging_utils.py: Logger setup
- performance_monitor.py: System monitoring
- discord_integration.py: Discord webhook notifications
- log_viewer.py: Live log file reading
- update_checker.py: Version checking
- issue_reporter.py: Error reporting

"""

import logging
import os
import queue
import shutil
import sys
import time
import webbrowser
from urllib.parse import quote
from pathlib import Path
from typing import Any, Optional

import PySimpleGUI as sg

from core.config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CONFIG,
    REGION_META,
    load_config,
    save_config,
)
from security.crypto import (
    Account,
    MASTER_PASSWORD_RESET,
    account_display,
    add_edit_account,
    change_master_password,
    invalidate_stored_master_secret,
    load_accounts,
    load_master_password,
    save_accounts,
    suspend_master_password,
)
from services.launcher import (
    WIZWALKER_AVAILABLE,
    auto_detect_wiz_install,
    launch_with_login,
    start_instance,
    track_session_start,
    track_session_end,
    get_wizard_handles_safe,
)
from core.logging_utils import setup_logging
from services.playtime_tracker import PlaytimeTracker
from app.ui import apply_theme, build_window, bind_mousewheel_scroll
from services.performance_monitor import PerformanceMonitor
from integrations.discord_integration import DiscordIntegration
from integrations.discord_presence import DEFAULT_CLIENT_ID, DiscordRichPresence, RollingActivity24h
from services.log_viewer import LogViewer
from services.update_checker import UpdateChecker, GITHUB_RELEASES_PAGE as _RELEASES_PAGE
from services.issue_reporter import IssueReporter
from services.backup_manager import create_profile_backup, inspect_backup_file, restore_profile_backup
import services.wizwall as wizwall
import extensions.window_capture as window_capture
from services.tray_icon import TrayIcon, TRAY_AVAILABLE


def get_paths() -> dict:
    """
    Get all important application directory paths.
    
    Handles both:
    - Release mode: When running as frozen .exe (PyInstaller)
    - Development mode: When running as .py script
    
    Returns:
        Dictionary with application paths:
            - root: AppData profile root directory
            - legacy_root: Legacy executable/source root for migration
            - data_dir: For encrypted account storage
            - log_dir: For log files
            - backups_dir: For profile backup archives
            - config_file: config.json path
            - accounts_file: accounts.enc.json path
    """
    if getattr(sys, "frozen", False):
        legacy_root = Path(sys.executable).resolve().parent
    else:
        legacy_root = Path(__file__).resolve().parent.parent

    appdata_base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    root = appdata_base / "WizQLauncher"
    data_dir = root / "data"
    log_dir = root / "logs"
    backups_dir = root / "backups"
    
    return {
        "root": root,
        "legacy_root": legacy_root,
        "data_dir": data_dir,
        "log_dir": log_dir,
        "backups_dir": backups_dir,
        "config_file": root / "config.json",
        "accounts_file": data_dir / "accounts.enc.json",
    }


def ensure_dirs(paths: dict) -> None:
    """
    Create required application directories if they don't exist.
    
    Args:
        paths: Dictionary from get_paths()
    """
    paths["data_dir"].mkdir(parents=True, exist_ok=True)
    paths["log_dir"].mkdir(parents=True, exist_ok=True)
    paths["backups_dir"].mkdir(parents=True, exist_ok=True)


def migrate_legacy_storage(paths: dict, dry_run: bool = False) -> dict:
    """Migrate config/data/logs from legacy root to AppData.

    Returns a diagnostics dict with status, planned files and copied files.
    """
    result = {
        "status": "nothing_to_migrate",
        "dry_run": bool(dry_run),
        "planned_files": [],
        "copied_files": [],
        "errors": [],
    }

    target_root = Path(paths["root"])
    legacy_root = Path(paths["legacy_root"])
    target_config = Path(paths["config_file"])

    if not legacy_root.exists() or legacy_root == target_root:
        return result

    planned_ops = []

    def _plan_missing_tree(src_dir: Path, dst_dir: Path, bucket: str) -> None:
        if not src_dir.exists() or not src_dir.is_dir():
            return
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            if dst_file.exists():
                continue
            planned_ops.append((src_file, dst_file, f"{bucket}/{rel.as_posix()}"))

    legacy_config = legacy_root / "config.json"
    legacy_data = legacy_root / "data"
    legacy_logs = legacy_root / "logs"

    if legacy_config.exists() and (not target_config.exists() or target_config.stat().st_size == 0):
        planned_ops.append((legacy_config, target_config, "config.json"))

    target_data = Path(paths["data_dir"])
    _plan_missing_tree(legacy_data, target_data, "data")

    target_logs = Path(paths["log_dir"])
    _plan_missing_tree(legacy_logs, target_logs, "logs")

    result["planned_files"] = [label for _, _, label in planned_ops]
    if not planned_ops:
        return result

    if dry_run:
        result["status"] = "would_migrate"
        return result

    for src_file, dst_file, label in planned_ops:
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            result["copied_files"].append(label)
        except Exception as exc:
            result["errors"].append(f"{label}: {exc}")

    if result["errors"]:
        result["status"] = "error"
    elif result["copied_files"]:
        result["status"] = "migrated"

    return result


def get_region_accounts(accounts: list, current_region: str) -> list:
    """
    Filter accounts by region.
    
    Args:
        accounts: List of all Account objects
        current_region: Current region code (e.g., 'de', 'us')
        
    Returns:
        List of Account objects for the current region
    """
    return [acc for acc in accounts if acc.region == current_region]


def get_account_by_username(accounts: list, username: str) -> Optional[Account]:
    """Find account object by username."""
    return next((acc for acc in accounts if acc.username == username), None)


def detect_new_handles(
    before_handles: set,
    expected_count: int,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.5,
) -> list:
    """Poll for newly started Wizard101 handles until timeout or expected count is reached."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        new_handles = sorted(set(get_wizard_handles_safe()).difference(before_handles))
        if len(new_handles) >= expected_count:
            return new_handles
        time.sleep(poll_interval_seconds)

    return sorted(set(get_wizard_handles_safe()).difference(before_handles))


def get_selected_account_for_presence(
    values: dict,
    accounts: list,
    config: dict,
    active_sessions: dict,
) -> Optional[Account]:
    """Resolve the currently selected account for Discord presence session display."""
    current_region = config.get("current_region", "de")
    region_accounts = get_region_accounts(accounts, current_region)

    launch_selected = values.get("-AUTO-ACCOUNTS-", []) if values else []
    if launch_selected:
        account = next(
            (acc for acc in region_accounts if account_display(acc) in launch_selected),
            None,
        )
        if account:
            return account

    accounts_selected = values.get("-ACCOUNTS-", []) if values else []
    if accounts_selected:
        account = next(
            (acc for acc in region_accounts if account_display(acc) in accounts_selected),
            None,
        )
        if account:
            return account

    if active_sessions:
        first_username = next(iter(active_sessions.values()))
        return get_account_by_username(accounts, first_username)

    return None


def get_active_username_session_seconds(tracker: PlaytimeTracker, username: str) -> float:
    """Get current active session duration for username (max if multiple handles exist)."""
    if not username:
        return 0.0

    now = time.time()
    durations = [
        max(0.0, now - start_time)
        for start_time, session_username in tracker.active_sessions.values()
        if session_username == username
    ]
    return max(durations) if durations else 0.0


def sync_discord_presence_config(
    discord_presence: DiscordRichPresence,
    config: dict,
) -> None:
    """Apply runtime config updates to the Discord Rich Presence client."""
    discord_presence.enabled = bool(config.get("discord_rich_presence", True))

    try:
        discord_presence.update_interval_seconds = max(
            5,
            int(config.get("discord_rpc_update_interval", 15)),
        )
    except (TypeError, ValueError):
        discord_presence.update_interval_seconds = 15

    discord_presence.rpc_yield_to_game = bool(config.get("discord_rpc_yield_to_game", True))
def start_and_track_sessions(
    config: dict,
    selected_accounts: list,
    count: int,
    tracker: PlaytimeTracker,
    active_sessions: dict,
    paths: dict,
    master_password: str,
    accounts: list,
    discord: Optional[DiscordIntegration] = None,
) -> None:
    """
    Start game instances with auto-login and track playtime sessions.

    Process:
    1. Get current Wizard101 process handles before launch
    2. Launch instances with auto-login
    3. Detect new processes (with retry polling)
    4. Start tracking each session
    5. Send Discord notification (if configured)

    Args:
        config: Application configuration
        selected_accounts: List of Account objects to start
        count: Number of instances to start
        tracker: PlaytimeTracker instance
        active_sessions: Dict to store {handle: account_username}
        paths: Dictionary from get_paths()
        master_password: Master password for account decryption
        accounts: All available accounts
        discord: DiscordIntegration instance (optional)
    """
    logger = logging.getLogger("launcher")

    # Get current handles before starting
    before_handles = set(get_wizard_handles_safe())

    # Start the instances
    launch_with_login(selected_accounts[:count], count, config)

    # Poll for new handles because client startup time can vary significantly.
    detection_timeout = float(config.get("handle_detect_timeout_seconds", 15))
    new_handles = detect_new_handles(before_handles, count, detection_timeout)

    if not new_handles:
        logger.warning("No new Wizard101 handles detected for playtime tracking")
        return

    if len(new_handles) < count:
        logger.warning(
            "Detected only %s/%s new handles; tracking available sessions only",
            len(new_handles),
            count,
        )

    for handle, account in zip(new_handles, selected_accounts[:count]):
        if config.get("auto_playtime_tracking", True):
            track_session_start(tracker, handle, account.username)
        active_sessions[handle] = account.username
        logger.info(
            "Playtime session started: account=%s username=%s handle=%s",
            account.name,
            account.username,
            handle,
        )

        if discord and config.get("discord_notifications") and config.get("discord_session_start", True):
            discord.send_session_started(
                account.name,
                account.username,
                config.get("current_region", "de"),
            )

def main() -> int:
    """
    Main application entry point and event loop controller.
    
    Initializes:
    - Configuration system
    - Logging
    - UI theme
    - Accounts and master password
    - Playtime tracking
    - Performance monitoring
    - Discord integration
    - Update checking
    
    Event loop handles:
    - Account management (add/edit/delete)
    - Launcher operations (quicklaunch, multi-instance, auto-login)
    - Region switching
    - UI interactions (log viewer, theme toggle, etc.)
    - Playtime tracking
    - Discord notifications
    
    Returns:
        Exit code (0 for success)
    """
    # Initialize paths and directories
    paths = get_paths()
    ensure_dirs(paths)
    migration_report = migrate_legacy_storage(paths)
    
    # Load configuration
    config = load_config(paths["config_file"])

    # Setup logging system early so startup diagnostics are captured
    setup_logging(paths["log_dir"], config)

    # Get logger for this module
    logger = logging.getLogger("launcher")
    logger.info("Launcher startup initialized")
    logger.info("Using profile storage at %s", paths["root"])
    if migration_report["status"] == "migrated":
        logger.info("Migrated legacy profile files into AppData storage (%s files)", len(migration_report["copied_files"]))
        for rel_path in migration_report["copied_files"]:
            logger.info("Migration copied: %s", rel_path)
    elif migration_report["status"] == "error":
        logger.warning("Legacy migration finished with errors: %s", "; ".join(migration_report["errors"]))

    migration_status = migration_report.get("status", "unknown")
    if migration_status in ("migrated", "nothing_to_migrate", "error"):
        config["migration_last_status"] = migration_status
    if migration_status == "migrated":
        config["migration_last_detail"] = (
            f"Migrated {len(migration_report.get('copied_files', []))} file(s) from legacy profile."
        )
    elif migration_status == "nothing_to_migrate":
        config["migration_last_detail"] = "No legacy files needed migration."
    elif migration_status == "error":
        config["migration_last_detail"] = "; ".join(migration_report.get("errors", [])) or "Migration failed."
    config["migration_last_run"] = int(time.time())

    # Auto-detect Wizard101 installations for any region that has no path set yet
    if auto_detect_wiz_install(config):
        save_config(paths["config_file"], config)
    
    # Apply UI theme
    apply_theme(config)

    logger.info("Configuration loaded and UI theme applied")
    
    # Load master password and accounts
    master_password = load_master_password(paths["accounts_file"], config)
    if not master_password:
        return 1

    save_config(paths["config_file"], config)

    try:
        accounts = load_accounts(paths["accounts_file"], master_password)
    except Exception as exc:
        sg.popup(f"Failed to load accounts: {exc}", title=APP_NAME)
        accounts = []

    # Initialize core systems
    tracker = PlaytimeTracker()
    active_sessions = {}  # {handle: account_username}

    # Initialize rolling 24h activity tracker + Discord Rich Presence
    activity_24h = RollingActivity24h(paths["data_dir"] / "activity_24h.json")
    discord_presence = DiscordRichPresence(
        client_id=DEFAULT_CLIENT_ID,
        enabled=bool(config.get("discord_rich_presence", True)),
        update_interval_seconds=int(config.get("discord_rpc_update_interval", 15)),
        rpc_yield_to_game=bool(config.get("discord_rpc_yield_to_game", True)),
    )
    sync_discord_presence_config(discord_presence, config)
    
    # Initialize performance monitor
    try:
        perf_monitor = PerformanceMonitor(max_history=100)
        perf_monitor.logger.setLevel(config.get("log_level", "INFO"))
    except Exception as e:
        logger.warning(f"Failed to initialize performance monitor: {e}")
        perf_monitor = None
    
    # Initialize Discord integration
    try:
        discord = DiscordIntegration(webhook_url=config.get("discord_webhook_url"))
        discord.enabled = config.get("discord_notifications", False)
    except Exception as e:
        logger.warning(f"Failed to initialize Discord integration: {e}")
        discord = None
    
    # Initialize update checker
    try:
        updater = UpdateChecker(current_version=APP_VERSION)
    except Exception as e:
        logger.warning(f"Failed to initialize update checker: {e}")
        updater = None
    
    # Initialize error reporter
    try:
        reporter = IssueReporter(
            github_repo=config.get("github_repo", "xLordTime/wiz-q-launcher"),
            discord_webhook=config.get("discord_webhook_url")
        )
    except Exception as e:
        logger.warning(f"Failed to initialize issue reporter: {e}")
        reporter = None
    
    log_file = paths["log_dir"] / "launcher.log"

    # Initialize log viewer
    try:
        log_viewer = LogViewer(log_file) if log_file.exists() else None
    except Exception as e:
        logger.warning(f"Failed to initialize log viewer: {e}")
        log_viewer = None

    # Wizwall state (no game hooks; lazy wizwalker usage)
    _ww_windows: list = []          # last scanned WizWindow list
    # JSON stores dict keys as strings; restore_positions() expects int handles.
    _ww_saved_layout: dict = {
        int(k): tuple(v)
        for k, v in config.get("wizwall_saved_layout", {}).items()
        if str(k).lstrip("-").isdigit() and isinstance(v, (list, tuple)) and len(v) == 4
    }

    # Clip & Record state
    _cap_windows: list = []         # last scanned CaptureWindow list

    # Build and display window
    try:
        window: Any = build_window(config, accounts, log_file_path=str(log_file))
    except Exception as e:
        logger.exception(f"Failed to build window: {e}")
        sg.popup_error(f"Failed to build window:\n{str(e)}", title=APP_NAME)
        return 1
    logger = logging.getLogger("launcher")

    # Enable mousewheel scrolling in all scrollable tab columns
    bind_mousewheel_scroll(window)

    latest_update_info: Optional[dict] = None
    log_output_text = ""
    last_perf_snapshot_ts = 0.0
    last_stats_refresh_ts = 0.0        # throttle: update stats table every 5 s
    last_handles_ts = 0.0              # throttle: Win32 handle enumeration every 2 s
    _update_result_queue: queue.Queue = queue.Queue()
    _download_queue: queue.Queue = queue.Queue()   # progress/complete/error from download thread
    _pending_update_path: Optional[Path] = None    # path to downloaded .exe ready to install

    # System tray (optional — needs pystray + Pillow in requirements)
    tray = TrayIcon(title=APP_NAME)
    if not TRAY_AVAILABLE:
        logger.info(
            "Tray icon unavailable — install pystray and Pillow for system tray support "
            "(pip install pystray Pillow). F4 will minimize to taskbar instead."
        )

    settings_search_items = [
        ("Login wait seconds", "login_wait_seconds", "-WAIT-"),
        ("Window title template", "window_title_template", "-TITLE-"),
        ("Log level", "log_level", "-LOGLEVEL-"),
        ("Discord webhook URL", "discord_webhook_url", "-DISCORD-WEBHOOK-URL-"),
        ("Discord notifications", "discord_notifications", "-DISCORD-NOTIFY-"),
        ("Theme", "ui_theme", "-THEME-"),
        ("Check for updates", "check_for_updates", "-CHECK-FOR-UPDATES-"),
        ("Backup scope", "backup_scope", "-BACKUP-SCOPE-"),
        ("Restore scope", "backup_restore_scope", "-BACKUP-RESTORE-SCOPE-"),
        ("Master password enabled", "master_password_enabled", "-MASTER-PW-ENABLED-"),
        ("Master password suspend days", "master_password_suspend_days", "-MASTER-PW-DAYS-"),
        ("Tools tab visibility", "show_tools_tab", "-SHOW-TOOLS-TAB-"),
        ("Extensions tab visibility", "show_extensions_tab", "-SHOW-EXTENSIONS-TAB-"),
        ("Performance tab visibility", "show_performance_tab", "-SHOW-PERFORMANCE-TAB-"),
        ("Auto playtime tracking", "auto_playtime_tracking", "-AUTO-PLAYTIME-"),
    ]

    def _run_settings_search(values: dict) -> None:
        """Search settings by label/config key/UI key and show matching entries."""
        query = str(values.get("-SETTINGS-SEARCH-", "")).strip().lower()
        if not query:
            if "-SETTINGS-SEARCH-STATUS-" in window.AllKeysDict:
                window["-SETTINGS-SEARCH-STATUS-"].update("Enter text to search settings.")
            window["-STATUS-"].update("Settings search: enter query")
            return

        results = []
        matched_config_keys = set()

        for label, config_key, ui_key in settings_search_items:
            hay = f"{label} {config_key} {ui_key}".lower()
            if query in hay:
                current_val = values.get(ui_key, config.get(config_key, ""))
                results.append(f"- {label} | config={config_key} | ui={ui_key} | value={current_val}")
                matched_config_keys.add(config_key)

        for config_key in sorted(config.keys()):
            if config_key in matched_config_keys:
                continue
            if query in config_key.lower():
                results.append(f"- config={config_key} | value={config.get(config_key)}")

        if results:
            if "-SETTINGS-SEARCH-STATUS-" in window.AllKeysDict:
                window["-SETTINGS-SEARCH-STATUS-"].update(f"{len(results)} match(es) found.")
            window["-STATUS-"].update(f"Settings search: {len(results)} match(es)")
            sg.popup_scrolled("\n".join(results), title=APP_NAME, size=(110, 30))
        else:
            if "-SETTINGS-SEARCH-STATUS-" in window.AllKeysDict:
                window["-SETTINGS-SEARCH-STATUS-"].update("No matching settings found.")
            window["-STATUS-"].update("Settings search: no matches")

    def _sync_reporter_config() -> None:
        """Keep issue-reporter targets in sync with current runtime config."""
        if reporter is None:
            return
        reporter.github_repo = str(config.get("github_repo", reporter.github_repo))
        reporter.github_api_url = f"https://api.github.com/repos/{reporter.github_repo}/issues"
        reporter.discord_webhook = str(config.get("discord_webhook_url", "")).strip() or None

    _sync_reporter_config()

    def _stats_table_rows() -> list:
        """Build stats table row data from current accounts + tracker (for in-place updates).
        Active sessions are marked with 🟢 and show the live session time in parentheses.
        Externally-tracked instances (unknown account) appear as extra rows at the bottom.
        """
        try:
            stats = tracker.get_accounts_stats_sorted(accounts, sort_by="playtime")
            active_usernames = {u for u in active_sessions.values() if u}
            rows = []
            for s in stats:
                name = s["name"]
                playtime = s["total_playtime"]
                if s["username"] in active_usernames:
                    live_secs = get_active_username_session_seconds(tracker, s["username"])
                    live_str = tracker.format_playtime(live_secs) if live_secs >= 60 else "<1m"
                    name = f"\U0001f7e2 {name}"
                    playtime = f"{playtime}  (+{live_str})"
                rows.append([name, playtime, str(s["sessions"]), s["avg_session"]])
            # Rows for externally-started Wizard101 windows (no linked account)
            ext_count = sum(1 for u in active_sessions.values() if u == "")
            for i in range(ext_count):
                rows.append([f"\U0001f7e2 External #{i + 1}", "(active)", "–", "–"])
            return rows
        except Exception:
            return []

    def _apply_settings_from_values(values: dict) -> bool:
        """Persist UI-related settings from the current widget values.

        Returns True when the window should be rebuilt because tab visibility
        or other structural UI settings changed.
        """
        ui_rebuild = False

        def _set(key: str, value) -> None:
            nonlocal ui_rebuild
            if config.get(key) != value:
                ui_rebuild = True
            config[key] = value

        try:
            config["login_wait_seconds"] = float(values.get("-WAIT-", 5))
        except ValueError:
            config["login_wait_seconds"] = 5
        config["window_title_template"] = values.get("-TITLE-", "{name} ({username})")
        config["log_level"] = values.get("-LOGLEVEL-", "INFO")
        config["discord_rich_presence"] = values.get("-DISCORD-RPC-", True)
        try:
            config["discord_rpc_update_interval"] = max(5, int(values.get("-DISCORD-RPC-INTERVAL-", 15)))
        except ValueError:
            config["discord_rpc_update_interval"] = 15
        config["discord_rpc_yield_to_game"] = values.get("-DISCORD-RPC-YIELD-", True)
        config["discord_webhook_url"] = values.get("-DISCORD-WEBHOOK-URL-", "").strip()
        config["discord_notifications"] = values.get("-DISCORD-NOTIFY-", False)
        config["discord_session_start"] = values.get("-DISCORD-NOTIFY-START-", True)
        config["discord_session_end"] = values.get("-DISCORD-NOTIFY-END-", True)
        config["discord_errors"] = values.get("-DISCORD-NOTIFY-ERRORS-", False)
        config["save_window_state"] = values.get("-SAVE-WINDOW-STATE-", False)
        config["check_for_updates"] = values.get("-CHECK-FOR-UPDATES-", True)
        config["enable_performance_monitor"] = values.get("-ENABLE-PERF-MONITOR-", True)
        config["auto_playtime_tracking"] = values.get("-AUTO-PLAYTIME-", True)
        config["track_without_autologin"] = values.get("-TRACK-WITHOUT-LOGIN-", False)
        config["backup_include_logs"] = values.get("-BACKUP-INCLUDE-LOGS-", True)
        config["backup_scope"] = str(values.get("-BACKUP-SCOPE-", config.get("backup_scope", "full"))).strip() or "full"
        config["backup_restore_scope"] = str(
            values.get("-BACKUP-RESTORE-SCOPE-", config.get("backup_restore_scope", "full"))
        ).strip() or "full"
        extra_args_str = values.get("-EXTRA-ARGS-", "").strip()
        config["extra_args"] = extra_args_str.split() if extra_args_str else []
        try:
            config["master_password_suspend_days"] = max(1, int(values.get("-MASTER-PW-DAYS-", 7)))
        except ValueError:
            config["master_password_suspend_days"] = 7
        config["master_password_enabled"] = bool(values.get("-MASTER-PW-ENABLED-", True))
        if config.get("master_password_mode") in ("local", "placeholder"):
            config["master_password_enabled"] = False

        _set("show_tools_tab", values.get("-SHOW-TOOLS-TAB-", False))
        _set("show_extensions_tab", values.get("-SHOW-EXTENSIONS-TAB-", False))
        _set("show_performance_tab", values.get("-SHOW-PERFORMANCE-TAB-", False))
        _set("show_extension_wizwall", values.get("-SHOW-EXT-WIZWALL-", True))
        _set("show_extension_capture", values.get("-SHOW-EXT-CAPTURE-", True))

        for region_code in REGION_META:
            _set(f"show_region_{region_code}", values.get(f"-SHOW-{region_code.upper()}-", False))

        return ui_rebuild

    def _apply_master_password_preferences(values: dict) -> None:
        """Persist master password UI preferences and apply suspension when requested."""
        requested_enabled = bool(values.get("-MASTER-PW-ENABLED-", True))
        try:
            requested_days = max(1, int(values.get("-MASTER-PW-DAYS-", 7)))
        except ValueError:
            requested_days = 7

        config["master_password_suspend_days"] = requested_days

        if str(config.get("master_password_mode", "password")) == "placeholder":
            config["master_password_enabled"] = False
            window["-MASTER-PW-ENABLED-"].update(value=False)
            return

        if isinstance(master_password, bytes):
            config["master_password_enabled"] = False
            config["master_password_mode"] = "local"
            return

        if not requested_enabled:
            suspend_master_password(config, master_password, requested_days)
            window["-MASTER-PW-ENABLED-"].update(value=False)
            return

        config["master_password_enabled"] = True
        config["master_password_mode"] = "password"
        config["master_password_secret_b64"] = ""
        config["master_password_secret_expires"] = 0

    def _refresh_master_password_ui() -> None:
        """Update security status text and control availability in Settings."""
        mode = str(config.get("master_password_mode", "password"))
        now = int(time.time())
        expires_at = int(config.get("master_password_secret_expires", 0) or 0)
        has_cache = bool(str(config.get("master_password_secret_b64", "")).strip())

        def _format_remaining(seconds_left: int) -> str:
            seconds_left = max(0, int(seconds_left))
            days = seconds_left // 86400
            hours = (seconds_left % 86400) // 3600
            minutes = (seconds_left % 3600) // 60
            seconds = seconds_left % 60
            if days > 0:
                return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
            return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

        if mode == "placeholder":
            status_text = "Status: Placeholder mode active (value '0' until real password is set)"
            status_color = "#FFCC99"
            suspend_disabled = True
            window["-MASTER-PW-ENABLED-"].update(value=False)
        elif mode == "local":
            status_text = "Status: Local mode active (no startup password)"
            status_color = "#FFB86C"
            suspend_disabled = True
            window["-MASTER-PW-ENABLED-"].update(value=False)
        elif has_cache and expires_at > now:
            remaining = _format_remaining(expires_at - now)
            status_text = f"Status: Temporarily unlocked ({remaining} remaining)"
            status_color = "#FFD700"
            suspend_disabled = False
            window["-MASTER-PW-ENABLED-"].update(value=False)
        elif bool(config.get("master_password_enabled", True)):
            status_text = "Status: Protected by master password"
            status_color = "#8FBC8F"
            suspend_disabled = False
            window["-MASTER-PW-ENABLED-"].update(value=True)
        else:
            status_text = "Status: Startup password off (not suspended yet)"
            status_color = "#FFCC99"
            suspend_disabled = False

        if "-MASTER-PW-STATUS-" in window.AllKeysDict:
            window["-MASTER-PW-STATUS-"].update(status_text, text_color=status_color)
        if "-MASTER-PW-SUSPEND-" in window.AllKeysDict:
            window["-MASTER-PW-SUSPEND-"].update(disabled=suspend_disabled)
        if "-MASTER-PW-DAYS-" in window.AllKeysDict:
            window["-MASTER-PW-DAYS-"].update(disabled=suspend_disabled)
        if "-MASTER-PW-LOCK-NOW-" in window.AllKeysDict:
            lock_disabled = mode in ("local", "placeholder") or not has_cache
            window["-MASTER-PW-LOCK-NOW-"].update(disabled=lock_disabled)

    def _refresh_migration_ui() -> None:
        """Update migration diagnostics widgets in Settings tab."""
        status = str(config.get("migration_last_status", "unknown"))
        detail = str(config.get("migration_last_detail", "No migration check run yet."))
        run_ts = int(config.get("migration_last_run", 0) or 0)

        if status == "migrated":
            label = "Migration status: migrated"
            color = "#8FBC8F"
        elif status == "nothing_to_migrate":
            label = "Migration status: nothing to migrate"
            color = "#87CEEB"
        elif status == "error":
            label = "Migration status: error"
            color = "#FF6B6B"
        else:
            label = "Migration status: unknown"
            color = "#FFD700"

        if run_ts > 0:
            label = f"{label} (last run {time.strftime('%Y-%m-%d %H:%M', time.localtime(run_ts))})"

        if "-MIGRATION-STATUS-" in window.AllKeysDict:
            window["-MIGRATION-STATUS-"].update(label, text_color=color)
        if "-MIGRATION-DETAIL-" in window.AllKeysDict:
            window["-MIGRATION-DETAIL-"].update(detail)

    def refresh_performance_ui() -> None:
        if not perf_monitor:
            return

        # Performance widgets may not exist when the tab is hidden.
        def _update_if_present(key: str, value: str) -> None:
            if key in window.AllKeysDict:
                window[key].update(value)

        latest = perf_monitor.history[-1] if perf_monitor.history else None
        avg = perf_monitor.get_average_metrics(last_n=10)
        peak = perf_monitor.get_peak_metrics()

        cpu_now = latest.cpu_percent if latest else 0.0
        ram_now = latest.memory_percent if latest else 0.0
        wizmem_now = latest.process_memory_mb if latest else 0.0

        _update_if_present("-PERF-CPU-", f"{cpu_now:.1f}%")
        _update_if_present("-PERF-RAM-", f"{ram_now:.1f}%")
        _update_if_present("-PERF-WIZMEM-", f"{wizmem_now:.1f} MB")
        _update_if_present("-PERF-AVG-CPU-", f"{avg.get('cpu_percent', 0.0):.1f}%")
        _update_if_present("-PERF-PEAK-CPU-", f"{peak.get('cpu_percent', 0.0):.1f}%")
        _update_if_present("-PERF-PEAK-WIZMEM-", f"{peak.get('wizard_memory_mb', 0.0):.1f} MB")

        history_lines = []
        for snap in perf_monitor.history[-12:]:
            history_lines.append(
                f"{snap.timestamp.strftime('%H:%M:%S')} | CPU {snap.cpu_percent:5.1f}% | "
                f"RAM {snap.memory_percent:5.1f}% | WIZ {snap.process_memory_mb:7.1f} MB"
            )
        _update_if_present("-PERF-HISTORY-", "\n".join(history_lines) if history_lines else "No snapshots yet.")

    _refresh_master_password_ui()
    _refresh_migration_ui()

    def _apply_update_result(update_info: Optional[dict], manual: bool = False) -> None:
        """Apply the result of a (possibly async) update check to the UI."""
        nonlocal latest_update_info
        nonlocal _pending_update_path
        latest_update_info = update_info
        config["last_update_check"] = int(time.time())
        save_config(paths["config_file"], config)

        def _staged_update_path(update_info_local: Optional[dict] = None) -> Optional[Path]:
            if not getattr(sys, "frozen", False):
                return None
            base_dir = Path(sys.executable).parent
            version_candidate = None
            if update_info_local:
                new_ver = str(update_info_local.get("new_version", "")).strip()
                if new_ver:
                    safe_ver = new_ver.replace("/", "_").replace("\\", "_")
                    version_candidate = base_dir / f"wiz-q-launcher_update_{safe_ver}.exe"
                    if version_candidate.exists():
                        return version_candidate

            legacy_candidate = base_dir / "wiz-q-launcher_update.exe"
            if legacy_candidate.exists():
                return legacy_candidate
            return None

        if update_info:
            status_text = (
                f"\u2B06 Update available: v{update_info['new_version']} "
                f"\u2014 click '\u2B07 Download Update' to install!"
            )
            window["-UPDATE-STATUS-"].update(status_text, text_color="#FFD700")
            window["-UPDATE-BANNER-"].update(
                f"Update available: v{update_info['new_version']}",
                visible=True,
            )
            staged = _staged_update_path(update_info)
            if staged is not None:
                _pending_update_path = staged
                window["-DOWNLOAD-UPDATE-"].update(disabled=False, text="\U0001f504 Restart & Apply")
                window["-UPDATE-STATUS-"].update(
                    "\u2705 Update already downloaded — click 'Restart & Apply' to install",
                    text_color="#87CEEB",
                )
            else:
                window["-DOWNLOAD-UPDATE-"].update(disabled=False, text="\u2B07 Download Update")
            if manual:
                if sg.popup_yes_no(
                    UpdateChecker.format_release_info(update_info),
                    title="Update Available — Download now?",
                    keep_on_top=True,
                ) == "Yes":
                    _start_download_update()
        else:
            status_text = f"\u2714 Up to date (v{APP_VERSION}) | Checked: {time.strftime('%Y-%m-%d %H:%M')}"
            window["-UPDATE-STATUS-"].update(status_text, text_color="#87CEEB")
            window["-UPDATE-BANNER-"].update(visible=False)
            window["-DOWNLOAD-UPDATE-"].update(disabled=True, text="\u2B07 Download Update")
            if manual:
                sg.popup("You are already on the latest version.", title=APP_NAME)

    def run_update_check(manual: bool = False) -> None:
        """Trigger an update check (async for background, sync for manual)."""
        if not updater:
            window["-UPDATE-STATUS-"].update("Update checker unavailable.")
            if manual:
                sg.popup("Update checker is not available.", title=APP_NAME)
            return

        if manual:
            # Manual: run synchronously so the user sees the result immediately
            window["-UPDATE-STATUS-"].update("Checking for updates...")
            update_info = updater.check_for_updates()
            _apply_update_result(update_info, manual=True)
        else:
            # Background: put result into queue; event loop picks it up
            window["-UPDATE-STATUS-"].update("Checking for updates in background...")

            def _bg_callback(result: Optional[dict]) -> None:
                _update_result_queue.put((result, False))

            updater.check_for_updates_async(_bg_callback)

    # Drain pending async update results in the event loop
    def _poll_update_queue() -> None:
        try:
            while True:
                result, manual = _update_result_queue.get_nowait()
                _apply_update_result(result, manual=manual)
        except queue.Empty:
            pass

    def _start_download_update() -> None:
        """Begin downloading the latest update in a background thread."""
        nonlocal _pending_update_path
        if not updater or not latest_update_info:
            return

        if getattr(sys, "frozen", False):
            staged = _staged_update_path(latest_update_info)
            if staged is not None:
                _pending_update_path = staged
                window["-DOWNLOAD-UPDATE-"].update(disabled=False, text="\U0001f504 Restart & Apply")
                window["-UPDATE-STATUS-"].update(
                    "\u2705 Update already downloaded — click 'Restart & Apply' to install",
                    text_color="#87CEEB",
                )
                return

        if not getattr(sys, "frozen", False):
            # Dev mode — no self-replace possible, open browser instead
            webbrowser.open(
                latest_update_info.get("download_url")
                or latest_update_info.get("release_page", _RELEASES_PAGE)
            )
            return
        window["-DOWNLOAD-UPDATE-"].update(disabled=True, text="Downloading... 0%")
        window["-UPDATE-STATUS-"].update("Downloading update...", text_color="#FFD700")

        def _on_progress(pct: int) -> None:
            _download_queue.put(("progress", pct))

        def _on_complete(path: Path) -> None:
            _download_queue.put(("complete", path))

        def _on_error(msg: str) -> None:
            _download_queue.put(("error", msg))

        updater.download_update_async(latest_update_info, _on_progress, _on_complete, _on_error)

    def _poll_download_queue() -> None:
        """Drain download progress/complete/error events and update the UI."""
        nonlocal _pending_update_path
        try:
            while True:
                item = _download_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    pct = item[1]
                    window["-DOWNLOAD-UPDATE-"].update(text=f"Downloading... {pct}%")
                    window["-UPDATE-STATUS-"].update(
                        f"Downloading update... {pct}%", text_color="#FFD700"
                    )
                elif kind == "complete":
                    _pending_update_path = item[1]
                    window["-DOWNLOAD-UPDATE-"].update(
                        disabled=False, text="\U0001f504 Restart & Apply"
                    )
                    window["-UPDATE-STATUS-"].update(
                        "\u2705 Update downloaded — click 'Restart & Apply' to install",
                        text_color="#87CEEB",
                    )
                    logger.info("Update ready at %s", _pending_update_path)
                elif kind == "error":
                    msg = item[1]
                    window["-DOWNLOAD-UPDATE-"].update(disabled=False, text="\u2B07 Download Update")
                    window["-UPDATE-STATUS-"].update(
                        f"\u274C Download failed: {msg}", text_color="#FF6B6B"
                    )
                    logger.error("Update download error: %s", msg)
        except queue.Empty:
            pass

    if config.get("check_for_updates", True):
        now_ts = int(time.time())
        interval = int(config.get("update_check_interval", 86400))
        last_check = int(config.get("last_update_check", 0))
        if now_ts - last_check >= interval:
            run_update_check(manual=False)   # async background check on startup
        else:
            last_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(last_check))
            window["-UPDATE-STATUS-"].update(
                f"\u2714 Up to date (v{APP_VERSION}) | Last check: {last_str}",
                text_color="#87CEEB",
            )
    else:
        window["-UPDATE-STATUS-"].update("Automatic update checks are disabled in settings.")

    while True:
        try:
            event, values = window.read(timeout=2000)  # 2 second timeout for periodic checks
        except Exception as e:
            logger.exception(f"CRASH in window.read(): {e}")
            sg.popup_error(f"Window Error:\n{str(e)}", title=APP_NAME)
            break
        
        # Handle playtime polling (timeout events)
        if event == sg.TIMEOUT_EVENT:
            try:
                _track_auto = config.get("auto_playtime_tracking", True)
                _track_ext = _track_auto and config.get("track_without_autologin", True)

                # Fetch current handles — throttled to every 2 s to reduce Win32 overhead
                current_handles: Optional[set] = None
                now_handles = time.time()
                if (active_sessions or _track_ext) and now_handles - last_handles_ts >= 2.0:
                    current_handles = set(get_wizard_handles_safe())
                    last_handles_ts = now_handles

                # End sessions for windows that have been closed
                if active_sessions and current_handles is not None:
                    closed_handles = [h for h in active_sessions if h not in current_handles]
                    for handle in closed_handles:
                        acc_username = active_sessions.pop(handle)
                        acc = get_account_by_username(accounts, acc_username)
                        if acc:
                            duration_secs = track_session_end(
                                tracker,
                                handle,
                                acc,
                                accounts,
                                reason="window_closed",
                            )
                            save_accounts(paths["accounts_file"], master_password, accounts)
                            if discord and config.get("discord_notifications") and config.get("discord_session_end", True) and duration_secs:
                                discord.send_session_ended(acc.name, duration_secs / 60.0)
                        else:
                            logger.warning(
                                "Playtime session ended for unknown username=%s handle=%s",
                                acc_username,
                                handle,
                            )

                # Auto-detect externally-started Wizard101 windows (track_without_autologin)
                if _track_ext and current_handles is not None:
                    for h in current_handles:
                        if h not in active_sessions:
                            if _track_auto:
                                track_session_start(tracker, h, "")
                            active_sessions[h] = ""  # empty = externally started, account unknown
                            logger.info("Auto-tracking externally-started wizard101 handle=%s", h)
                activity_24h.set_active(bool(active_sessions))

                # Only compute presence data when the RPC throttle period has elapsed
                _now_rpc = time.time()
                if discord_presence.enabled and (
                    _now_rpc - discord_presence._last_update >= discord_presence.update_interval_seconds
                ):
                    selected_account = get_selected_account_for_presence(
                        values,
                        accounts,
                        config,
                        active_sessions,
                    )
                    selected_name = selected_account.name if selected_account else None
                    selected_seconds = get_active_username_session_seconds(
                        tracker,
                        selected_account.username if selected_account else "",
                    )

                    discord_presence.update_presence(
                        total_24h_seconds=activity_24h.get_total_last_24h(),
                        selected_account_name=selected_name,
                        selected_session_seconds=selected_seconds,
                        active_sessions_count=len(active_sessions),
                        region=config.get("current_region", "de"),
                        total_account_playtime_seconds=(
                            selected_account.total_playtime if selected_account else 0.0
                        ),
                    )

                if perf_monitor and config.get("enable_performance_monitor", True):
                    poll_interval = max(1.0, float(config.get("performance_poll_interval", 5)))
                    now_perf = time.time()
                    if now_perf - last_perf_snapshot_ts >= poll_interval:
                        perf_monitor.take_snapshot()
                        refresh_performance_ui()
                        last_perf_snapshot_ts = now_perf

                # Auto-refresh Stats table in-place — throttled to once every 5 s
                now_stats = time.time()
                if now_stats - last_stats_refresh_ts >= 5.0:
                    window["-STATS-TABLE-"].update(values=_stats_table_rows())
                    last_stats_refresh_ts = now_stats

                # Drain async update-check results
                _poll_update_queue()
                # Drain download progress / complete / error
                _poll_download_queue()
                _refresh_master_password_ui()

            except Exception as e:
                logger.exception(f"CRASH in TIMEOUT_EVENT handler: {e}")
                if discord and config.get("discord_notifications") and config.get("discord_errors", False):
                    try:
                        discord.send_custom_message("⚠ Launcher Error", str(e), color=0xE74C3C)
                    except Exception:
                        pass
            continue

        if event in (sg.WIN_CLOSED, "Exit"):
            break

        # Apply Region - switch current region from dropdown
        if event == "-APPLY-REGION-":
            try:
                selected_region_display = values.get("-REGION-SELECT-", "")
                if selected_region_display:
                    # Extract region code from display (e.g., "DE - Deutschland" -> "de")
                    region_code = selected_region_display.split(" - ")[0].lower()
                    if region_code in REGION_META:
                        config["current_region"] = region_code
                        save_config(paths["config_file"], config)

                        window.close()
                        window = build_window(config, accounts)
                        bind_mousewheel_scroll(window)
                        _refresh_master_password_ui()
                        _refresh_migration_ui()
                        region_name = REGION_META[region_code]["name"]
                        window["-STATUS-"].update(f"✓ Switched to {region_name}")
                        logger.info(f"Region switched to {region_code}")
            except Exception as e:
                logger.exception(f"CRASH in APPLY-REGION: {e}")
                sg.popup_error(f"Region switch failed:\n{str(e)}", title=APP_NAME)
        
        # Update selected accounts counter
        if event == "-AUTO-ACCOUNTS-":
            try:
                selected_count = len(values.get("-AUTO-ACCOUNTS-", []))
                plural = "account" if selected_count == 1 else "accounts"
                window["-SELECTED-COUNT-"].update(f"{selected_count} {plural} selected")
            except Exception as e:
                logger.exception(f"Failed to update selected count: {e}")
        
        if event == "Quicklaunch":
            try:
                start_instance(config)
                window["-STATUS-"].update("Quicklaunch started")
            except Exception as exc:
                sg.popup(f"Launch failed: {exc}", title=APP_NAME)

        # Start Instances - start one instance for each selected account (without login)
        if event == "Start Instances":
            try:
                selected = values.get("-AUTO-ACCOUNTS-", [])
                region_accounts = get_region_accounts(accounts, config.get("current_region", "de"))
                selected_accounts = [
                    acc for acc in region_accounts if account_display(acc) in selected
                ]
                if not selected_accounts:
                    sg.popup("Select at least one account to start instances", title=APP_NAME)
                    continue
                
                count = len(selected_accounts)
                for _ in range(count):
                    start_instance(config)
                window["-STATUS-"].update(f"Started {count} instance(s) (no login)")
            except Exception as exc:
                sg.popup(f"Launch failed: {exc}", title=APP_NAME)

        # Start + Auto Login - start all selected accounts with auto-login
        if event == "Start + Auto Login":
            if not WIZWALKER_AVAILABLE:
                sg.popup("wizwalker not installed", title=APP_NAME)
                continue

            selected = values.get("-AUTO-ACCOUNTS-", [])
            region_accounts = get_region_accounts(accounts, config.get("current_region", "de"))
            selected_accounts = [
                acc for acc in region_accounts if account_display(acc) in selected
            ]
            if not selected_accounts:
                sg.popup("Select at least one account to start with auto-login", title=APP_NAME)
                continue

            count = len(selected_accounts)
            config["foreground_on_login"] = values.get("-FOREGROUND-", True)
            config["set_window_title"] = values.get("-SETTITLE-", True)
            start_and_track_sessions(
                config,
                selected_accounts,
                count,
                tracker,
                active_sessions,
                paths,
                master_password,
                accounts,
                discord,
            )
            window["-STATUS-"].update(f"Started {count} account(s) with auto-login + tracking")

        # Add account
        if event == "Add":
            current_region = config.get("current_region", "de")
            new_account = add_edit_account(current_region=current_region)
            if new_account:
                accounts.append(new_account)
                save_accounts(paths["accounts_file"], master_password, accounts)
                
                # Update UI with region-filtered accounts
                region_accounts = get_region_accounts(accounts, current_region)
                _acct_display = [account_display(a) for a in region_accounts]
                window["-ACCOUNTS-"].update(_acct_display)
                window["-AUTO-ACCOUNTS-"].update(_acct_display)
                window["-SELECTED-COUNT-"].update("0 accounts selected")

        # Edit account
        if event == "Edit":
            current_region = config.get("current_region", "de")
            region_accounts = get_region_accounts(accounts, current_region)
            selected = values.get("-ACCOUNTS-", [])
            if not selected:
                sg.popup("Select an account", title=APP_NAME)
                continue
            current = next(
                (acc for acc in region_accounts if account_display(acc) in selected),
                None,
            )
            if not current:
                continue
            updated = add_edit_account(current, current_region=current_region)
            if updated:
                idx = accounts.index(current)
                accounts[idx] = updated
                save_accounts(paths["accounts_file"], master_password, accounts)
                
                # Update UI with region-filtered accounts
                region_accounts = get_region_accounts(accounts, current_region)
                _acct_display = [account_display(a) for a in region_accounts]
                window["-ACCOUNTS-"].update(_acct_display)
                window["-AUTO-ACCOUNTS-"].update(_acct_display)
                window["-SELECTED-COUNT-"].update("0 accounts selected")

        # Delete account
        if event == "Delete":
            current_region = config.get("current_region", "de")
            region_accounts = get_region_accounts(accounts, current_region)
            selected = values.get("-ACCOUNTS-", [])
            if not selected:
                sg.popup("Select an account", title=APP_NAME)
                continue
            if sg.popup_yes_no("Delete selected account?", title=APP_NAME) != "Yes":
                continue
            
            # Delete from all accounts (not just region_accounts)
            accounts = [acc for acc in accounts if account_display(acc) not in selected]
            save_accounts(paths["accounts_file"], master_password, accounts)
            
            # Update UI with region-filtered accounts
            region_accounts = get_region_accounts(accounts, current_region)
            _acct_display = [account_display(a) for a in region_accounts]
            window["-ACCOUNTS-"].update(_acct_display)
            window["-AUTO-ACCOUNTS-"].update(_acct_display)
            window["-SELECTED-COUNT-"].update("0 accounts selected")

        # Move account up
        if event == "-ACCT-UP-":
            current_region = config.get("current_region", "de")
            region_accounts = get_region_accounts(accounts, current_region)
            selected = values.get("-ACCOUNTS-", [])
            if selected:
                sel_acc = next(
                    (acc for acc in region_accounts if account_display(acc) in selected), None
                )
                if sel_acc is not None:
                    idx = next((i for i, a in enumerate(accounts) if a.username == sel_acc.username), -1)
                    if idx > 0:
                        accounts[idx - 1], accounts[idx] = accounts[idx], accounts[idx - 1]
                        save_accounts(paths["accounts_file"], master_password, accounts)
                        region_accounts = get_region_accounts(accounts, current_region)
                        new_display = [account_display(a) for a in region_accounts]
                        new_idx = next((i for i, a in enumerate(region_accounts) if a.username == sel_acc.username), 0)
                        window["-ACCOUNTS-"].update(new_display, set_to_index=new_idx)
                        window["-AUTO-ACCOUNTS-"].update(new_display)

        # Move account down
        if event == "-ACCT-DOWN-":
            current_region = config.get("current_region", "de")
            region_accounts = get_region_accounts(accounts, current_region)
            selected = values.get("-ACCOUNTS-", [])
            if selected:
                sel_acc = next(
                    (acc for acc in region_accounts if account_display(acc) in selected), None
                )
                if sel_acc is not None:
                    idx = next((i for i, a in enumerate(accounts) if a.username == sel_acc.username), -1)
                    if idx != -1 and idx < len(accounts) - 1:
                        accounts[idx], accounts[idx + 1] = accounts[idx + 1], accounts[idx]
                        save_accounts(paths["accounts_file"], master_password, accounts)
                        region_accounts = get_region_accounts(accounts, current_region)
                        new_display = [account_display(a) for a in region_accounts]
                        new_idx = next((i for i, a in enumerate(region_accounts) if a.username == sel_acc.username), 0)
                        window["-ACCOUNTS-"].update(new_display, set_to_index=new_idx)
                        window["-AUTO-ACCOUNTS-"].update(new_display)

        # Handle region visibility toggle
        if event == "-SETTINGS-SEARCH-BTN-":
            _run_settings_search(values)

        if event == "-SETTINGS-SEARCH-CLEAR-":
            if "-SETTINGS-SEARCH-" in window.AllKeysDict:
                window["-SETTINGS-SEARCH-"].update("")
            if "-SETTINGS-SEARCH-STATUS-" in window.AllKeysDict:
                window["-SETTINGS-SEARCH-STATUS-"].update("Search by label, config key, or UI key.")
            window["-STATUS-"].update("Settings search cleared")

        region_visibility_changed = False
        for region_code in REGION_META:
            toggle_key = f"-SHOW-{region_code.upper()}-"
            if event == toggle_key:
                config[f"show_region_{region_code}"] = values.get(toggle_key, False)
                region_visibility_changed = True

        # Save settings and handle region changes
        if event == "Save settings" or region_visibility_changed:
            ui_rebuild = _apply_settings_from_values(values)
            _apply_master_password_preferences(values)

            # Apply discord integration settings at runtime
            if discord is not None:
                discord.set_webhook_url(config["discord_webhook_url"])
                discord.enabled = config["discord_notifications"]
            _sync_reporter_config()
            sync_discord_presence_config(discord_presence, config)
            
            save_config(paths["config_file"], config)
            
            if ui_rebuild:
                window.close()
                window = build_window(config, accounts, log_file_path=str(log_file))
                bind_mousewheel_scroll(window)
                _refresh_master_password_ui()
                _refresh_migration_ui()
                window["-STATUS-"].update("UI settings updated, window refreshed")
            else:
                _refresh_master_password_ui()
                _refresh_migration_ui()
                window["-STATUS-"].update("Settings saved")

        # ================== WIZWALL — Window Tiling Extension ==================
        # Scan: find all running Wizard101 windows (no game hooks)
        if event == "-WW-SCAN-":
            _ww_windows = wizwall.scan_windows()
            display = wizwall.format_window_list(_ww_windows)
            window["-WW-WINDOWS-"].update(display)
            window["-WW-OUTPUT-"].update(f"Scanned: {len(_ww_windows)} window(s) found.")
            window["-STATUS-"].update(f"Wizwall: {len(_ww_windows)} window(s) found")

        # Arrange: tile windows in the selected grid layout
        if event == "-WW-ARRANGE-":
            if not _ww_windows:
                _ww_windows = wizwall.scan_windows()
                window["-WW-WINDOWS-"].update(wizwall.format_window_list(_ww_windows))
            layout_str  = str(values.get("-WW-LAYOUT-", "2x2"))
            try:
                padding = int(str(values.get("-WW-PADDING-", "4")).strip())
            except ValueError:
                padding = 4
            borderless = bool(values.get("-WW-BORDERLESS-", True))
            # Save preference
            config["wizwall_layout"]    = layout_str
            config["wizwall_padding"]   = padding
            config["wizwall_borderless"] = borderless
            save_config(paths["config_file"], config)

            count, lines = wizwall.arrange_grid(
                _ww_windows,
                layout=layout_str,
                padding=padding,
                borderless=borderless,
            )
            window["-WW-OUTPUT-"].update("\n".join(lines))
            window["-WW-WINDOWS-"].update(wizwall.format_window_list(_ww_windows))
            window["-STATUS-"].update(f"Wizwall: arranged {count}/{len(_ww_windows)} window(s)")
            logger.info("Wizwall arranged %d windows in %s layout", count, layout_str)

        # Save: snapshot current window positions
        if event == "-WW-SAVE-":
            if not _ww_windows:
                _ww_windows = wizwall.scan_windows()
                window["-WW-WINDOWS-"].update(wizwall.format_window_list(_ww_windows))
            _ww_saved_layout = wizwall.snapshot_positions(_ww_windows)
            # Persist: convert int keys to str for JSON
            config["wizwall_saved_layout"] = {str(k): list(v) for k, v in _ww_saved_layout.items()}
            save_config(paths["config_file"], config)
            window["-WW-OUTPUT-"].update(f"Saved positions for {len(_ww_saved_layout)} window(s).")
            window["-STATUS-"].update(f"Wizwall: saved {len(_ww_saved_layout)} positions")

        # Restore: move windows back to saved positions
        if event == "-WW-RESTORE-":
            if not _ww_saved_layout:
                window["-WW-OUTPUT-"].update("No saved layout found.\nUse 'Save Positions' first.")
            else:
                if not _ww_windows:
                    _ww_windows = wizwall.scan_windows()
                    window["-WW-WINDOWS-"].update(wizwall.format_window_list(_ww_windows))
                count, lines = wizwall.restore_positions(_ww_saved_layout, _ww_windows)
                window["-WW-OUTPUT-"].update("\n".join(lines))
                window["-WW-WINDOWS-"].update(wizwall.format_window_list(_ww_windows))
                window["-STATUS-"].update(f"Wizwall: restored {count} window(s)")

        # ================== CLIP & RECORD Extension ==================

        def _cap_output_dir() -> Path:
            raw = str(values.get("-CAP-OUTPUT-DIR-", "") or config.get("capture_output_dir", "recordings")).strip()
            p = Path(raw)
            return p if p.is_absolute() else (paths["root"] / p)

        def _cap_fps() -> int:
            try:
                return int(values.get("-CAP-FPS-", config.get("capture_fps", 20)))
            except (TypeError, ValueError):
                return 20

        def _cap_clip_secs() -> int:
            try:
                return int(values.get("-CAP-CLIP-SECS-", config.get("clip_buffer_seconds", 30)))
            except (TypeError, ValueError):
                return 30

        def _cap_selected_window():
            """Return the selected CaptureWindow or None."""
            sel = values.get("-CAP-WINDOWS-") or []
            if not sel or not _cap_windows:
                return None
            label = sel[0].split("  (hwnd=")[0]
            return next((w for w in _cap_windows if w.label == label), None)

        def _cap_refresh_list():
            window["-CAP-WINDOWS-"].update(
                [f"{w.label}  (hwnd={w.handle})" for w in _cap_windows]
            )

        def _cap_update_rec_status():
            sel = _cap_selected_window()
            if sel and window_capture.is_recording(sel.handle):
                info = window_capture.active_recording_info(sel.handle) or ""
                window["-CAP-REC-STATUS-"].update(info)
            else:
                window["-CAP-REC-STATUS-"].update("")

        # Scan
        if event == "-CAP-SCAN-":
            _cap_windows = window_capture.scan_windows(
                account_map={h: u for h, u in active_sessions.items() if u}
            )
            _cap_refresh_list()
            window["-CAP-OUTPUT-"].update(f"Found {len(_cap_windows)} window(s).\n", append=True)
            window["-STATUS-"].update(f"Capture: {len(_cap_windows)} window(s) found")

        # Screenshot selected
        if event == "-CAP-SCREENSHOT-":
            sel = _cap_selected_window()
            if sel is None:
                window["-CAP-OUTPUT-"].update("⚠ Select a window first.\n", append=True)
            else:
                path_saved = window_capture.take_screenshot(sel.handle, sel.label, _cap_output_dir())
                if path_saved:
                    window["-CAP-OUTPUT-"].update(f"📸 {path_saved}\n", append=True)
                    window["-STATUS-"].update(f"Screenshot saved: {path_saved.name}")
                else:
                    window["-CAP-OUTPUT-"].update("❌ Screenshot failed — is the window open?\n", append=True)

        # Screenshot all
        if event == "-CAP-SCREENSHOT-ALL-":
            if not _cap_windows:
                _cap_windows = window_capture.scan_windows(
                    account_map={h: u for h, u in active_sessions.items() if u}
                )
                _cap_refresh_list()
            saved_paths = window_capture.screenshot_all(_cap_windows, _cap_output_dir())
            for p in saved_paths:
                window["-CAP-OUTPUT-"].update(f"📸 {p}\n", append=True)
            window["-STATUS-"].update(f"Screenshots: {len(saved_paths)} saved")

        # Start recording
        if event == "-CAP-REC-START-":
            sel = _cap_selected_window()
            if sel is None:
                window["-CAP-OUTPUT-"].update("⚠ Select a window first.\n", append=True)
            elif window_capture.is_recording(sel.handle):
                window["-CAP-OUTPUT-"].update(f"⚠ Already recording {sel.label}\n", append=True)
            else:
                state = window_capture.start_recording(
                    sel, _cap_output_dir(), fps=_cap_fps(), clip_buffer_seconds=_cap_clip_secs()
                )
                window["-CAP-REC-START-"].update(disabled=True)
                window["-CAP-REC-STOP-"].update(disabled=False)
                enc = "MP4 (cv2)" if window_capture.CV2_AVAILABLE else "PNG frames"
                window["-CAP-OUTPUT-"].update(
                    f"⏺ Recording {sel.label} → {state.output_path.name}  [{enc}]\n", append=True
                )
                window["-STATUS-"].update(f"Recording: {sel.label}")

        # Stop recording
        if event == "-CAP-REC-STOP-":
            sel = _cap_selected_window()
            handle = sel.handle if sel else None
            if handle is None and _cap_windows:
                # Stop first active recording if nothing selected
                for w in _cap_windows:
                    if window_capture.is_recording(w.handle):
                        handle = w.handle
                        break
            if handle is not None:
                out_path = window_capture.stop_recording(handle)
                window["-CAP-REC-START-"].update(disabled=False)
                window["-CAP-REC-STOP-"].update(disabled=True)
                window["-CAP-REC-STATUS-"].update("")
                if out_path:
                    window["-CAP-OUTPUT-"].update(f"⏹ Saved: {out_path}\n", append=True)
                    window["-STATUS-"].update(f"Recording saved: {out_path.name}")
                else:
                    window["-CAP-OUTPUT-"].update("⏹ Recording stopped (no frames captured).\n", append=True)

        # Save clip from ring buffer
        if event == "-CAP-CLIP-SAVE-":
            sel = _cap_selected_window()
            if sel is None:
                window["-CAP-OUTPUT-"].update("⚠ Select a window first.\n", append=True)
            else:
                clip_path = window_capture.save_clip(sel.handle, sel.label, _cap_output_dir(), _cap_fps())
                if clip_path:
                    window["-CAP-OUTPUT-"].update(f"💾 Clip saved: {clip_path}\n", append=True)
                    window["-STATUS-"].update(f"Clip saved: {Path(clip_path).name}")
                else:
                    window["-CAP-OUTPUT-"].update(
                        "⚠ No clip data yet — start recording first to fill the buffer.\n", append=True
                    )

        # Save capture settings
        if event == "-CAP-SAVE-SETTINGS-":
            config["capture_output_dir"] = str(values.get("-CAP-OUTPUT-DIR-", "recordings")).strip()
            config["capture_fps"] = _cap_fps()
            config["clip_buffer_seconds"] = _cap_clip_secs()
            save_config(paths["config_file"], config)
            window["-CAP-OUTPUT-"].update("✅ Settings saved.\n", append=True)
            window["-STATUS-"].update("Capture settings saved")

        # Keep rec status refreshed on each tick
        if event == sg.TIMEOUT_EVENT and _cap_windows:
            _cap_update_rec_status()

        # Handle region-specific save and set as current
        for region_code in REGION_META:
            set_region_key = f"-SET-REGION-{region_code.upper()}-"
            reset_region_key = f"-RESET-{region_code.upper()}-"
            auto_detect_key = f"-AUTO-DETECT-{region_code.upper()}-"

            # Auto-detect install path for this region
            if event == auto_detect_key:
                from services.launcher import find_wiz_installs
                found = find_wiz_installs()
                install_key = f"-INSTALL-{region_code.upper()}-"
                if region_code in found:
                    window[install_key].update(found[region_code])
                    config[f"region_install_{region_code}"] = found[region_code]
                    save_config(paths["config_file"], config)
                    window["-STATUS-"].update(
                        f"✓ Auto-detected {REGION_META[region_code]['name']}: {found[region_code]}"
                    )
                    logger.info("Auto-detected install for %s: %s", region_code, found[region_code])
                elif found:
                    # Offer the first found install of any region
                    first_path = next(iter(found.values()))
                    window[install_key].update(first_path)
                    window["-STATUS-"].update(
                        f"⚠ No exact match for {region_code.upper()}, suggested: {first_path}"
                    )
                else:
                    sg.popup(
                        "No Wizard101 installation found.\n"
                        "Please install Wizard101 or set the path manually.",
                        title=APP_NAME,
                    )
                    window["-STATUS-"].update("Auto-detect: no install found")
            
            # Set region as current
            if event == set_region_key:
                # Save region-specific settings
                install_key = f"-INSTALL-{region_code.upper()}-"
                server_key = f"-SERVER-{region_code.upper()}-"
                port_key = f"-PORT-{region_code.upper()}-"
                
                config[f"region_install_{region_code}"] = values.get(install_key, "").strip()
                config[f"region_server_{region_code}"] = values.get(server_key, "").strip()
                try:
                    config[f"region_port_{region_code}"] = int(values.get(port_key, 12000))
                except ValueError:
                    config[f"region_port_{region_code}"] = 12000
                
                # Set as current region
                config["current_region"] = region_code
                save_config(paths["config_file"], config)
                

                window.close()
                window = build_window(config, accounts)
                bind_mousewheel_scroll(window)
                _refresh_master_password_ui()
                _refresh_migration_ui()
                region_name = REGION_META[region_code]["name"]
                window["-STATUS-"].update(f"✓ Switched to {region_name}")
            
            # Reset region to defaults
            if event == reset_region_key:
                region_info = REGION_META.get(region_code, {})
                config[f"region_install_{region_code}"] = ""
                config[f"region_server_{region_code}"] = region_info.get("server", "")
                config[f"region_port_{region_code}"] = 12000
                save_config(paths["config_file"], config)
                
                # Rebuild window to reflect defaults

                window.close()
                window = build_window(config, accounts)
                bind_mousewheel_scroll(window)
                _refresh_master_password_ui()
                _refresh_migration_ui()
                region_name = REGION_META[region_code]["name"]
                window["-STATUS-"].update(f"Reset {region_name} to defaults")

        # Open log folder
        if event == "Open log folder":
            os.startfile(str(paths["log_dir"]))

        # ================== UPDATE BANNER CLICK ==================
        if event == "-UPDATE-BANNER-":
            if latest_update_info:
                if sg.popup_yes_no(
                    UpdateChecker.format_release_info(latest_update_info),
                    title="Update Available — Download now?",
                    keep_on_top=True,
                ) == "Yes":
                    _start_download_update()

        # ================== SETTINGS: UPDATE CHECKER ==================
        if event == "-CHECK-UPDATES-":
            run_update_check(manual=True)

        if event == "-DOWNLOAD-UPDATE-":
            if _pending_update_path is not None:
                # Update already downloaded — launch relay and exit
                ok = UpdateChecker.apply_update_on_restart(_pending_update_path)
                if ok:
                    window.close()
                    sys.exit(0)
                else:
                    # Frozen exe not available (dev mode) — open browser
                    webbrowser.open(
                        latest_update_info.get("download_url", _RELEASES_PAGE)
                        if latest_update_info else _RELEASES_PAGE
                    )
            else:
                _start_download_update()

        # ================== SETTINGS: CHANGE MASTER PASSWORD ==================
        if event == "-CHANGE-PASSWORD-":
            if sg.popup_yes_no(
                "Critical action: password change/reset can lock account access if interrupted or forgotten.\n\n"
                "Do you want to continue?",
                title=APP_NAME,
            ) != "Yes":
                continue
            result = change_master_password(
                paths["accounts_file"], master_password, accounts, config=config
            )
            if result == MASTER_PASSWORD_RESET:
                # Full reset: wipe in-memory state, re-run first-time setup
                accounts = []
                master_password = load_master_password(paths["accounts_file"], config)
                if not master_password:
                    sg.popup("No master password set. Launcher will exit.", title=APP_NAME)
                    break
                save_config(paths["config_file"], config)
                accounts = load_accounts(paths["accounts_file"], master_password)
                logger.info("Master password reset. New password set, accounts reloaded.")
                _refresh_master_password_ui()
                window["-STATUS-"].update("Master password reset. Fresh start.")
            elif result:
                master_password = result
                save_config(paths["config_file"], config)
                logger.info("Master password changed successfully.")
                _refresh_master_password_ui()
                window["-STATUS-"].update("Master password changed.")

        if event == "-MASTER-PW-SUSPEND-":
            _apply_master_password_preferences(values)
            save_config(paths["config_file"], config)
            suspend_days = int(config.get("master_password_suspend_days", 7))
            _refresh_master_password_ui()
            window["-STATUS-"].update(f"Master password suspended for {suspend_days} day(s)")

        if event == "-MASTER-PW-LOCK-NOW-":
            if str(config.get("master_password_mode", "password")) == "local":
                sg.popup(
                    "Local passwordless mode cannot be locked instantly.\n"
                    "Switch back to password mode first.",
                    title=APP_NAME,
                )
            else:
                invalidate_stored_master_secret(config)
                save_config(paths["config_file"], config)
                _refresh_master_password_ui()
                window["-STATUS-"].update("Temporary unlock cleared. Master password required on next unlock.")

        if event == "-MIGRATION-DRYRUN-":
            preview = migrate_legacy_storage(paths, dry_run=True)
            planned = preview.get("planned_files", [])
            if planned:
                logger.info("Migration dry-run found %s pending file(s)", len(planned))
                for rel_path in planned:
                    logger.info("Migration dry-run pending: %s", rel_path)
                detail = "Would migrate:\n" + "\n".join(f"- {p}" for p in planned[:80])
                if len(planned) > 80:
                    detail += f"\n... and {len(planned) - 80} more"
                config["migration_last_detail"] = f"Dry-run: {len(planned)} file(s) pending migration."
                config["migration_last_run"] = int(time.time())
                _refresh_migration_ui()
                save_config(paths["config_file"], config)
                sg.popup_scrolled(detail, title=APP_NAME, size=(100, 30))
                window["-STATUS-"].update(f"Migration dry-run: {len(planned)} file(s) pending")
            else:
                config["migration_last_status"] = "nothing_to_migrate"
                config["migration_last_detail"] = "Dry-run: no files pending migration."
                config["migration_last_run"] = int(time.time())
                _refresh_migration_ui()
                save_config(paths["config_file"], config)
                window["-STATUS-"].update("Migration dry-run: nothing to migrate")

        # ================== SETTINGS: BACKUP & RESTORE ==================
        if event == "-BACKUP-CREATE-":
            try:
                backup_file = create_profile_backup(
                    paths,
                    scope=str(values.get("-BACKUP-SCOPE-", config.get("backup_scope", "full"))),
                )
                window["-STATUS-"].update(f"Backup created: {backup_file.name}")
                logger.info("Profile backup created: %s", backup_file)
            except Exception as exc:
                logger.exception("Backup creation failed")
                sg.popup(f"Backup creation failed:\n{exc}", title=APP_NAME)

        if event == "-BACKUP-OPEN-FOLDER-":
            try:
                os.startfile(str(paths["backups_dir"]))
            except Exception as exc:
                logger.warning("Failed to open backup folder: %s", exc)
                sg.popup(f"Could not open backup folder:\n{exc}", title=APP_NAME)

        if event == "-BACKUP-RESTORE-":
            if active_sessions:
                sg.popup(
                    "Please end all active sessions before restoring a backup.",
                    title=APP_NAME,
                )
            else:
                restore_file_raw = str(values.get("-BACKUP-RESTORE-FILE-", "")).strip()
                if not restore_file_raw:
                    sg.popup("Select a backup file first.", title=APP_NAME)
                else:
                    restore_file = Path(restore_file_raw)
                    if not restore_file.exists():
                        sg.popup("Selected backup file does not exist.", title=APP_NAME)
                    else:
                        confirm = sg.popup_yes_no(
                            "CRITICAL ACTION: Restore backup now?\n\n"
                            "Current config/data/logs will be replaced by backup contents.\n"
                            "A rollback snapshot will be created first.",
                            title=APP_NAME,
                        )
                        if confirm == "Yes":
                            pre_restore = None
                            try:
                                backup_meta = inspect_backup_file(restore_file)
                                logger.info(
                                    "Backup integrity check passed: scope=%s files=%s",
                                    backup_meta.get("scope"),
                                    backup_meta.get("file_count"),
                                )

                                pre_restore = create_profile_backup(paths, scope="full")
                                logger.info("Created pre-restore snapshot: %s", pre_restore)

                                restore_scope = str(
                                    values.get(
                                        "-BACKUP-RESTORE-SCOPE-",
                                        config.get("backup_restore_scope", "full"),
                                    )
                                )
                                restore_profile_backup(restore_file, paths, restore_scope=restore_scope)

                                config = load_config(paths["config_file"])
                                apply_theme(config)
                                save_config(paths["config_file"], config)

                                master_password = load_master_password(paths["accounts_file"], config)
                                if not master_password:
                                    sg.popup(
                                        "Backup restored, but unlocking accounts was cancelled.\n"
                                        "Please restart launcher and unlock manually.",
                                        title=APP_NAME,
                                    )
                                    break

                                accounts = load_accounts(paths["accounts_file"], master_password)
                                sync_discord_presence_config(discord_presence, config)
                                if discord is not None:
                                    discord.set_webhook_url(config.get("discord_webhook_url", ""))
                                    discord.enabled = config.get("discord_notifications", False)
                                _sync_reporter_config()

                                window.close()
                                window = build_window(config, accounts, log_file_path=str(log_file))
                                bind_mousewheel_scroll(window)
                                _refresh_master_password_ui()
                                _refresh_migration_ui()
                                window["-STATUS-"].update(f"Backup restored: {restore_file.name}")
                                logger.info("Backup restored successfully: %s", restore_file)
                            except Exception as exc:
                                logger.exception("Backup restore failed")
                                rollback_note = ""
                                if pre_restore and Path(pre_restore).exists():
                                    try:
                                        restore_profile_backup(pre_restore, paths, restore_scope="full")
                                        rollback_note = "\n\nRollback completed from pre-restore snapshot."
                                        logger.info("Restore rollback successful from %s", pre_restore)
                                    except Exception as rollback_exc:
                                        rollback_note = (
                                            "\n\nRollback failed. Please restore manually from:\n"
                                            f"{pre_restore}\nError: {rollback_exc}"
                                        )
                                        logger.exception("Restore rollback failed")

                                sg.popup(f"Backup restore failed:\n{exc}{rollback_note}", title=APP_NAME)

        # ================== SETTINGS: ISSUE REPORTER ==================
        if event == "-REPORT-ISSUE-":
            title = str(values.get("-ISSUE-TITLE-", "")).strip()
            context = str(values.get("-ISSUE-CONTEXT-", "")).strip()

            if not title:
                sg.popup("Please enter an issue title.", title=APP_NAME)
            elif not reporter:
                sg.popup("Issue reporter is not available.", title=APP_NAME)
            else:
                context_block = (
                    f"App Version: {APP_VERSION}\n"
                    f"Current Region: {config.get('current_region', 'de')}\n"
                    f"\n{context}"
                )
                success = reporter.report_error(
                    title=title,
                    error=Exception("Manual issue report from UI"),
                    context=context_block,
                )
                if success:
                    sg.popup("Issue report sent successfully.", title=APP_NAME)
                    window["-STATUS-"].update("Issue reported")
                else:
                    repo = str(config.get("github_repo", "xLordTime/wiz-q-launcher"))
                    fallback_title = f"[MANUAL] {title}"
                    fallback_body = (
                        "## Manual Issue Report\n\n"
                        f"**Created:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"{context_block}\n"
                    )
                    issue_url = (
                        f"https://github.com/{repo}/issues/new"
                        f"?title={quote(fallback_title)}"
                        f"&body={quote(fallback_body[:7000])}"
                    )
                    try:
                        window.TKroot.clipboard_clear()
                        window.TKroot.clipboard_append(fallback_body)
                    except Exception:
                        pass
                    webbrowser.open(issue_url)
                    sg.popup(
                        "Auto-report failed. Opened a pre-filled GitHub issue in your browser.\n"
                        "Issue details were also copied to clipboard.",
                        title=APP_NAME,
                    )
                    window["-STATUS-"].update("Issue fallback opened in browser")

        # ================== PERFORMANCE TAB ==================
        if event == "-ENABLE-PERF-MONITOR-":
            config["enable_performance_monitor"] = bool(values.get("-ENABLE-PERF-MONITOR-", True))
            save_config(paths["config_file"], config)
            state = "enabled" if config["enable_performance_monitor"] else "disabled"
            window["-STATUS-"].update(f"Performance monitoring {state}")
            logger.info("Performance monitoring %s", state)

        if event == "-PERF-REFRESH-":
            if perf_monitor:
                perf_monitor.take_snapshot()
                refresh_performance_ui()
                window["-STATUS-"].update("Performance metrics refreshed")

        if event == "-PERF-CLEAR-HISTORY-":
            if perf_monitor:
                perf_monitor.clear_history()
                refresh_performance_ui()
                window["-STATUS-"].update("Performance history cleared")

        # ================== LIVE LOG VIEWER HANDLERS ==================
        # Refresh logs - reload log file
        if event == "-LOG-REFRESH-" and log_viewer:
            try:
                latest_logs = log_viewer.get_latest_logs(num_lines=100)
                log_text = "\n".join(latest_logs)
                log_output_text = log_text
                window["-LOG-OUTPUT-"].update(log_text)
                window["-STATUS-"].update("✓ Logs refreshed")
            except Exception as e:
                logger.warning(f"Log refresh failed: {e}")

        # Search logs
        if event == "-LOG-SEARCH-BTN-" and log_viewer:
            search_query = values.get("-LOG-SEARCH-", "")
            if search_query:
                try:
                    results = log_viewer.search_logs(search_query, case_sensitive=False)
                    log_text = "\n".join(results) if results else "No matches found"
                    log_output_text = log_text
                    window["-LOG-OUTPUT-"].update(log_text)
                    window["-STATUS-"].update(f"✓ Found {len(results)} matches")
                except Exception as e:
                    logger.warning(f"Log search failed: {e}")

        # Clear log search
        if event == "-LOG-CLEAR-BTN-" and log_viewer:
            window["-LOG-SEARCH-"].update("")
            try:
                latest_logs = log_viewer.get_latest_logs(num_lines=100)
                log_text = "\n".join(latest_logs)
                log_output_text = log_text
                window["-LOG-OUTPUT-"].update(log_text)
                window["-STATUS-"].update("✓ Log view cleared")
            except Exception as e:
                logger.warning(f"Log clear failed: {e}")

        # Filter logs by level
        if event == "-LOG-LEVEL-" and log_viewer:
            selected_level = values.get("-LOG-LEVEL-", "All")
            try:
                if selected_level == "All":
                    logs = log_viewer.get_latest_logs(num_lines=100)
                else:
                    logs = log_viewer.filter_by_level(selected_level)
                log_text = "\n".join(logs)
                log_output_text = log_text
                window["-LOG-OUTPUT-"].update(log_text)
                window["-STATUS-"].update(f"✓ Filtered to {selected_level}")
            except Exception as e:
                logger.warning(f"Log filter failed: {e}")

        # Filter logs by recent time window
        if event == "-LOG-LAST15-" and log_viewer:
            try:
                recent = log_viewer.filter_last_minutes(15)
                log_text = "\n".join(recent) if recent else "No log lines in the last 15 minutes"
                log_output_text = log_text
                window["-LOG-OUTPUT-"].update(log_text)
                window["-STATUS-"].update(f"✓ Showing last 15 minutes ({len(recent)} lines)")
            except Exception as e:
                logger.warning(f"Log last-15 filter failed: {e}")

        # Copy current log view to clipboard
        if event == "-LOG-COPY-":
            try:
                window.TKroot.clipboard_clear()
                window.TKroot.clipboard_append(log_output_text or "")
                window["-STATUS-"].update("✓ Log view copied to clipboard")
            except Exception as e:
                logger.warning(f"Log clipboard copy failed: {e}")

        # Export full log to file
        if event == "-LOG-EXPORT-" and log_viewer:
            try:
                all_logs = log_viewer.get_all_logs()
                export_file = paths["root"] / f"launcher_export_{int(time.time())}.txt"
                with open(export_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(all_logs))
                window["-STATUS-"].update(f"✓ Log exported to {export_file.name}")
                logger.info(f"Log exported to {export_file}")
            except Exception as e:
                logger.warning(f"Log export failed: {e}")
                sg.popup(f"Export failed: {e}", title=APP_NAME)

        # ================== DISCORD WEBHOOK TEST ==================
        if event == "-DISCORD-WEBHOOK-TEST-":
            test_url = values.get("-DISCORD-WEBHOOK-URL-", "").strip()
            if not test_url:
                sg.popup("Enter a webhook URL first.", title=APP_NAME)
            else:
                try:
                    _test_discord = DiscordIntegration(webhook_url=test_url)
                    ok = _test_discord.test_connection()
                    if ok:
                        sg.popup("✓ Webhook test successful!", title=APP_NAME)
                    else:
                        sg.popup("✗ Webhook test failed — check the URL and try again.", title=APP_NAME)
                except Exception as e:
                    sg.popup(f"Webhook test error: {e}", title=APP_NAME)

        # ================== THEME TOGGLE HANDLER ==================
        # Switch between Dark and Light themes
        if event == "-THEME-":
            new_theme = values.get("-THEME-", "WizDark")
            if new_theme != config.get("ui_theme", "WizDark"):
                config["ui_theme"] = new_theme
                save_config(paths["config_file"], config)
                
                # Apply theme and rebuild window
                apply_theme(config)

                window.close()
                window = build_window(config, accounts, log_file_path=str(log_file))
                bind_mousewheel_scroll(window)
                _refresh_master_password_ui()
                _refresh_migration_ui()
                window["-STATUS-"].update(f"✓ Theme changed to {new_theme}")
                logger.info(f"Theme changed to {new_theme}")

        # Stats: Refresh - update table in-place (no window rebuild)
        if event == "Refresh":
            window["-STATS-TABLE-"].update(values=_stats_table_rows())
            window["-STATUS-"].update("Stats refreshed")

        # Stats: Export - save playtime stats to file
        if event == "Export Stats":
            try:
                stats_list = tracker.get_accounts_stats_sorted(accounts, sort_by="playtime")
                export_file = paths["root"] / "playtime_stats.txt"
                with open(export_file, "w", encoding="utf-8") as f:
                    f.write("=== Wizard101 Playtime Statistics ===\n\n")
                    for stat in stats_list:
                        f.write(f"Name: {stat['name']}\n")
                        f.write(f"Username: {stat['username']}\n")
                        f.write(f"Total Playtime: {stat['total_playtime']}\n")
                        f.write(f"Sessions: {stat['sessions']}\n")
                        f.write(f"Avg Session: {stat['avg_session']}\n")
                        f.write("-" * 40 + "\n\n")
                window["-STATUS-"].update(f"✓ Stats exported to {export_file.name}")
                logger.info(f"Stats exported to {export_file}")
            except Exception as exc:
                sg.popup(f"Export failed: {exc}", title=APP_NAME)
                logger.exception("Stats export failed")

        # Stats: Reset Selected - clear playtime for the selected account
        if event == "-RESET-SELECTED-STATS-":
            selected_rows = values.get("-STATS-TABLE-", [])
            if not selected_rows:
                sg.popup("Select an account row first.", title=APP_NAME)
            else:
                if sg.popup_yes_no(
                    "Critical action: reset selected account playtime now?\n"
                    "This cannot be undone.",
                    title=APP_NAME,
                ) != "Yes":
                    continue
                idx = selected_rows[0]
                stats_snapshot = tracker.get_accounts_stats_sorted(accounts, sort_by="playtime")
                if idx < len(stats_snapshot):
                    target_username = stats_snapshot[idx]["username"]
                    acc = get_account_by_username(accounts, target_username)
                    if acc:
                        acc.total_playtime = 0.0
                        acc.sessions_count = 0
                        acc.last_session_start = 0.0
                        save_accounts(paths["accounts_file"], master_password, accounts)
                        window["-STATS-TABLE-"].update(values=_stats_table_rows())
                        window["-STATUS-"].update(f"✓ Stats cleared for {acc.name}")
                        logger.info("Playtime reset for account=%s", acc.username)

        # Stats: Reset All - clear all playtime data
        if event == "Reset All Stats":
            if sg.popup_yes_no(
                "CRITICAL ACTION: Reset ALL playtime stats now?\n"
                "This cannot be undone.",
                title=APP_NAME,
            ) == "Yes":
                for account in accounts:
                    account.total_playtime = 0.0
                    account.sessions_count = 0
                    account.last_session_start = 0.0
                save_accounts(paths["accounts_file"], master_password, accounts)
                window["-STATS-TABLE-"].update(values=_stats_table_rows())
                window["-STATUS-"].update("✓ All stats cleared")
                logger.info("All playtime stats reset")

        # ================== KEYBOARD SHORTCUTS ==================
        # F1 - Quicklaunch
        if event == "F1":
            try:
                start_instance(config)
                window["-STATUS-"].update("Quicklaunch started (F1)")
            except Exception as exc:
                sg.popup(f"Launch failed: {exc}", title=APP_NAME)

        # F2 - Start Selected Instances
        if event == "F2":
            try:
                selected = values.get("-AUTO-ACCOUNTS-", [])
                region_accounts = get_region_accounts(accounts, config.get("current_region", "de"))
                selected_accounts = [
                    acc for acc in region_accounts if account_display(acc) in selected
                ]
                if not selected_accounts:
                    sg.popup("Select at least one account to start instances (F2)", title=APP_NAME)
                else:
                    count = len(selected_accounts)
                    for _ in range(count):
                        start_instance(config)
                    window["-STATUS-"].update(f"Started {count} instance(s) (F2)")
            except Exception as exc:
                sg.popup(f"Launch failed: {exc}", title=APP_NAME)

        # F3 - Start with Auto-Login (all selected accounts)
        if event == "F3":
            if not WIZWALKER_AVAILABLE:
                sg.popup("wizwalker not installed", title=APP_NAME)
            else:
                selected = values.get("-AUTO-ACCOUNTS-", [])
                region_accounts = get_region_accounts(accounts, config.get("current_region", "de"))
                selected_accounts = [
                    acc for acc in region_accounts if account_display(acc) in selected
                ]
                if not selected_accounts:
                    sg.popup("Select at least one account for auto-login (F3)", title=APP_NAME)
                else:
                    count = len(selected_accounts)
                    config["foreground_on_login"] = values.get("-FOREGROUND-", True)
                    config["set_window_title"] = values.get("-SETTITLE-", True)
                    start_and_track_sessions(
                        config,
                        selected_accounts,
                        count,
                        tracker,
                        active_sessions,
                        paths,
                        master_password,
                        accounts,
                        discord,
                    )
                    window["-STATUS-"].update(f"Started {count} account(s) with auto-login (F3)")

        # F4 - Minimize to tray (or restore)
        if event == "F4":
            if window.is_hidden():
                window.un_hide()
                tray.stop()
                window["-STATUS-"].update("Window restored (F4)")
            else:
                window.hide()
                if tray.available:
                    tray.start(window.write_event_value)
                    window["-STATUS-"].update("Minimized to tray — right-click tray icon to restore (F4)")
                else:
                    window["-STATUS-"].update("Minimized (install pystray+Pillow for tray icon) (F4)")

        # Tray icon — restore
        if event == "-TRAY-RESTORE-":
            window.un_hide()
            tray.stop()
            window["-STATUS-"].update("Restored from tray")

        # Tray icon — exit
        if event == "-TRAY-EXIT-":
            break

        # Ctrl+E - Export Stats shortcut
        if event == "Ctrl+E":
            try:
                stats_list = tracker.get_accounts_stats_sorted(accounts, sort_by="playtime")
                export_file = paths["root"] / "playtime_stats.txt"
                with open(export_file, "w", encoding="utf-8") as f:
                    f.write("=== Wizard101 Playtime Statistics ===\n\n")
                    for stat in stats_list:
                        f.write(f"Name: {stat['name']}\n")
                        f.write(f"Username: {stat['username']}\n")
                        f.write(f"Total Playtime: {stat['total_playtime']}\n")
                        f.write(f"Sessions: {stat['sessions']}\n")
                        f.write(f"Avg Session: {stat['avg_session']}\n")
                        f.write("-" * 40 + "\n\n")
                window["-STATUS-"].update(f"✓ Stats exported (Ctrl+E)")
                logger.info(f"Stats exported via shortcut")
            except Exception as exc:
                logger.exception("Stats export failed")

        # Ctrl+S - Save Settings shortcut
        if event == "Ctrl+S":
            ui_rebuild = _apply_settings_from_values(values)
            _apply_master_password_preferences(values)

            # Apply discord integration settings at runtime
            if discord is not None:
                discord.set_webhook_url(config["discord_webhook_url"])
                discord.enabled = config["discord_notifications"]
            _sync_reporter_config()
            sync_discord_presence_config(discord_presence, config)
            
            save_config(paths["config_file"], config)
            if ui_rebuild:
                window.close()
                window = build_window(config, accounts, log_file_path=str(log_file))
                bind_mousewheel_scroll(window)
                _refresh_master_password_ui()
                _refresh_migration_ui()
                window["-STATUS-"].update("UI settings updated (Ctrl+S)")
            else:
                _refresh_master_password_ui()
                _refresh_migration_ui()
                window["-STATUS-"].update("✓ Settings saved (Ctrl+S)")
            logger.info("Settings saved via shortcut")

    # Cleanup: End all active sessions before closing
    if active_sessions:
        logger.info(f"Ending {len(active_sessions)} active playtime sessions...")
        for handle, acc_username in list(active_sessions.items()):
            acc = get_account_by_username(accounts, acc_username)
            if acc:
                track_session_end(
                    tracker,
                    handle,
                    acc,
                    accounts,
                    reason="app_shutdown",
                )
            else:
                logger.warning(
                    "Skipping shutdown playtime finalize for unknown username=%s handle=%s",
                    acc_username,
                    handle,
                )
        # Save final playtime data
        if master_password is not None:
            save_accounts(paths["accounts_file"], master_password, accounts)
            logger.info("Playtime sessions saved")
        else:
            logger.warning("Skipping final save — no master password set")



    activity_24h.close()
    discord_presence.close()
    tray.stop()

    # Save window position if requested
    if config.get("save_window_state", False):
        try:
            loc = window.current_location()
            if loc and loc[0] is not None and loc[1] is not None:
                config["window_x"] = loc[0]
                config["window_y"] = loc[1]
                save_config(paths["config_file"], config)
        except Exception:
            pass

    window.close()
    logger.info("Launcher closed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        import PySimpleGUI as sg
        sg.popup_error(f"FATAL ERROR:\n{str(e)}\n\nCheck console for details.", title="Launcher Fatal Error")
        raise SystemExit(1)














