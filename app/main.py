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
import sys
import time
import webbrowser
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
    load_accounts,
    load_master_password,
    save_accounts,
)
from services.launcher import (
    WIZWALKER_AVAILABLE,
    launch_with_login,
    start_instance,
    track_session_start,
    track_session_end,
    get_wizard_handles_safe,
)
from core.logging_utils import setup_logging
from services.playtime_tracker import PlaytimeTracker
from app.ui import apply_theme, build_window
from services.performance_monitor import PerformanceMonitor
from integrations.discord_integration import DiscordIntegration
from integrations.discord_presence import DEFAULT_CLIENT_ID, DiscordRichPresence, RollingActivity24h
from services.log_viewer import LogViewer
from services.update_checker import UpdateChecker
from services.issue_reporter import IssueReporter
import services.wizwall as wizwall
from services.tray_icon import TrayIcon, TRAY_AVAILABLE


def get_paths() -> dict:
    """
    Get all important application directory paths.
    
    Handles both:
    - Release mode: When running as frozen .exe (PyInstaller)
    - Development mode: When running as .py script
    
    Returns:
        Dictionary with application paths:
            - root: Application root directory
            - data_dir: For encrypted account storage
            - log_dir: For log files
            - config_file: config.json path
            - accounts_file: accounts.enc.json path
    """
    if getattr(sys, "frozen", False):
        # Running as compiled .exe (PyInstaller)
        root = Path(sys.executable).resolve().parent
    else:
        # Running as Python script
        root = Path(__file__).resolve().parent.parent
    
    data_dir = root / "data"
    log_dir = root / "logs"
    
    return {
        "root": root,
        "data_dir": data_dir,
        "log_dir": log_dir,
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
    
    # Load configuration
    config = load_config(paths["config_file"])
    
    # Setup logging system
    setup_logging(paths["log_dir"], config)
    
    # Apply UI theme
    apply_theme(config)
    
    # Get logger for this module
    logger = logging.getLogger("launcher")
    
    # Load master password and accounts
    master_password = load_master_password(paths["accounts_file"])
    if not master_password:
        return 1

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

    # Build and display window
    try:
        window: Any = build_window(config, accounts, log_file_path=str(log_file))
    except Exception as e:
        logger.exception(f"Failed to build window: {e}")
        sg.popup_error(f"Failed to build window:\n{str(e)}", title=APP_NAME)
        return 1
    logger = logging.getLogger("launcher")

    latest_update_info: Optional[dict] = None
    last_perf_snapshot_ts = 0.0
    _update_result_queue: queue.Queue = queue.Queue()

    # System tray (optional — needs pystray + Pillow in requirements)
    tray = TrayIcon(title=APP_NAME)
    if not TRAY_AVAILABLE:
        logger.info(
            "Tray icon unavailable — install pystray and Pillow for system tray support "
            "(pip install pystray Pillow). F4 will minimize to taskbar instead."
        )

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

    def refresh_performance_ui() -> None:
        if not perf_monitor:
            return

        latest = perf_monitor.history[-1] if perf_monitor.history else None
        avg = perf_monitor.get_average_metrics(last_n=10)
        peak = perf_monitor.get_peak_metrics()

        cpu_now = latest.cpu_percent if latest else 0.0
        ram_now = latest.memory_percent if latest else 0.0
        wizmem_now = latest.process_memory_mb if latest else 0.0

        window["-PERF-CPU-"].update(f"{cpu_now:.1f}%")
        window["-PERF-RAM-"].update(f"{ram_now:.1f}%")
        window["-PERF-WIZMEM-"].update(f"{wizmem_now:.1f} MB")
        window["-PERF-AVG-CPU-"].update(f"{avg.get('cpu_percent', 0.0):.1f}%")
        window["-PERF-PEAK-CPU-"].update(f"{peak.get('cpu_percent', 0.0):.1f}%")
        window["-PERF-PEAK-WIZMEM-"].update(f"{peak.get('wizard_memory_mb', 0.0):.1f} MB")

        history_lines = []
        for snap in perf_monitor.history[-12:]:
            history_lines.append(
                f"{snap.timestamp.strftime('%H:%M:%S')} | CPU {snap.cpu_percent:5.1f}% | "
                f"RAM {snap.memory_percent:5.1f}% | WIZ {snap.process_memory_mb:7.1f} MB"
            )
        window["-PERF-HISTORY-"].update("\n".join(history_lines) if history_lines else "No snapshots yet.")

    def _apply_update_result(update_info: Optional[dict], manual: bool = False) -> None:
        """Apply the result of a (possibly async) update check to the UI."""
        nonlocal latest_update_info
        latest_update_info = update_info
        config["last_update_check"] = int(time.time())
        save_config(paths["config_file"], config)

        if update_info:
            status_text = (
                f"\u2B06 Update available: v{update_info['new_version']} "
                f"\u2014 click 'Open Download Page' to get it!"
            )
            window["-UPDATE-STATUS-"].update(status_text, text_color="#FFD700")
            window["-UPDATE-BANNER-"].update(
                f"Update available: v{update_info['new_version']}",
                visible=True,
            )
            if manual:
                if sg.popup_yes_no(
                    UpdateChecker.format_release_info(update_info),
                    title="Update Available",
                    keep_on_top=True,
                ) == "Yes":
                    webbrowser.open(update_info["download_url"])
        else:
            status_text = f"\u2714 Up to date (v{APP_VERSION}) | Checked: {time.strftime('%Y-%m-%d %H:%M')}"
            window["-UPDATE-STATUS-"].update(status_text, text_color="#87CEEB")
            window["-UPDATE-BANNER-"].update(visible=False)
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
            event, values = window.read(timeout=1000)  # 1 second timeout for periodic checks
        except Exception as e:
            logger.exception(f"CRASH in window.read(): {e}")
            sg.popup_error(f"Window Error:\n{str(e)}", title=APP_NAME)
            break
        
        # Handle playtime polling (timeout events)
        if event == sg.TIMEOUT_EVENT:
            try:
                _track_auto = config.get("auto_playtime_tracking", True)
                _track_ext = _track_auto and config.get("track_without_autologin", True)

                # Fetch current handles once (used for end-detection and auto-tracking)
                current_handles: set = set()
                if active_sessions or _track_ext:
                    current_handles = set(get_wizard_handles_safe())

                # End sessions for windows that have been closed
                if active_sessions:
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
                if _track_ext:
                    for h in current_handles:
                        if h not in active_sessions:
                            if _track_auto:
                                track_session_start(tracker, h, "")
                            active_sessions[h] = ""  # empty = externally started, account unknown
                            logger.info("Auto-tracking externally-started wizard101 handle=%s", h)
                sync_discord_presence_config(discord_presence, config)
                activity_24h.set_active(bool(active_sessions))

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

                # Auto-refresh Stats table in-place (no window rebuild needed)
                window["-STATS-TABLE-"].update(values=_stats_table_rows())

                # Drain async update-check results
                _poll_update_queue()

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
                window["-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
                window["-AUTO-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
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
                window["-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
                window["-AUTO-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
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
            window["-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
            window["-AUTO-ACCOUNTS-"].update([account_display(a) for a in region_accounts])
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
        region_visibility_changed = False
        for region_code in REGION_META:
            toggle_key = f"-SHOW-{region_code.upper()}-"
            if event == toggle_key:
                config[f"show_region_{region_code}"] = values.get(toggle_key, False)
                region_visibility_changed = True

        # Save settings and handle region changes
        if event == "Save settings" or region_visibility_changed:
            # Save global settings
            try:
                config["login_wait_seconds"] = float(values.get("-WAIT-", 5))
            except ValueError:
                config["login_wait_seconds"] = 5
            config["window_title_template"] = values.get(
                "-TITLE-", "{name} ({username})"
            )
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
            extra_args_str = values.get("-EXTRA-ARGS-", "").strip()
            config["extra_args"] = extra_args_str.split() if extra_args_str else []

            # Apply discord integration settings at runtime
            if discord is not None:
                discord.set_webhook_url(config["discord_webhook_url"])
                discord.enabled = config["discord_notifications"]
            sync_discord_presence_config(discord_presence, config)

            # Save region visibility settings
            for region_code in REGION_META:
                toggle_key = f"-SHOW-{region_code.upper()}-"
                config[f"show_region_{region_code}"] = values.get(toggle_key, False)
            
            save_config(paths["config_file"], config)
            
            if region_visibility_changed:

                window.close()
                window = build_window(config, accounts)
                window["-STATUS-"].update("Regions updated, window refreshed")
            else:
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

        # Handle region-specific save and set as current
        for region_code in REGION_META:
            set_region_key = f"-SET-REGION-{region_code.upper()}-"
            reset_region_key = f"-RESET-{region_code.upper()}-"
            
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
                    title="Update Available",
                    keep_on_top=True,
                ) == "Yes":
                    webbrowser.open(
                        latest_update_info.get("download_url")
                        or latest_update_info.get("release_page", "")
                    )

        # ================== SETTINGS: UPDATE CHECKER ==================
        if event == "-CHECK-UPDATES-":
            run_update_check(manual=True)

        if event == "-OPEN-UPDATE-URL-":
            try:
                from services.update_checker import GITHUB_RELEASES_PAGE
                url = GITHUB_RELEASES_PAGE
                if latest_update_info:
                    url = latest_update_info.get("download_url") or latest_update_info.get("release_page") or url
                webbrowser.open(str(url))
                window["-STATUS-"].update("Opened update download page")
            except Exception as exc:
                logger.warning("Failed to open update URL: %s", exc)
                sg.popup(f"Could not open update page: {exc}", title=APP_NAME)

        # ================== SETTINGS: CHANGE MASTER PASSWORD ==================
        if event == "-CHANGE-PASSWORD-":
            result = change_master_password(
                paths["accounts_file"], master_password, accounts
            )
            if result == MASTER_PASSWORD_RESET:
                # Full reset: wipe in-memory state, re-run first-time setup
                accounts = []
                master_password = load_master_password(paths["accounts_file"])
                if not master_password:
                    sg.popup("No master password set. Launcher will exit.", title=APP_NAME)
                    break
                accounts = load_accounts(paths["accounts_file"], master_password)
                logger.info("Master password reset. New password set, accounts reloaded.")
                window["-STATUS-"].update("Master password reset. Fresh start.")
            elif result:
                master_password = result
                logger.info("Master password changed successfully.")
                window["-STATUS-"].update("Master password changed.")

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
                    sg.popup("Failed to report issue. Check network/settings.", title=APP_NAME)

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
                window["-LOG-OUTPUT-"].update(log_text)
                window["-STATUS-"].update(f"✓ Filtered to {selected_level}")
            except Exception as e:
                logger.warning(f"Log filter failed: {e}")

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
                idx = selected_rows[0]
                stats_snapshot = tracker.get_accounts_stats_sorted(accounts, sort_by="playtime")
                if idx < len(stats_snapshot):
                    target_username = stats_snapshot[idx]["username"]
                    acc = get_account_by_username(accounts, target_username)
                    if acc and sg.popup_yes_no(
                        f"Reset playtime for '{acc.name}'? This cannot be undone!", title=APP_NAME
                    ) == "Yes":
                        acc.total_playtime = 0.0
                        acc.sessions_count = 0
                        acc.last_session_start = 0.0
                        save_accounts(paths["accounts_file"], master_password, accounts)
                        window["-STATS-TABLE-"].update(values=_stats_table_rows())
                        window["-STATUS-"].update(f"✓ Stats cleared for {acc.name}")
                        logger.info("Playtime reset for account=%s", acc.username)

        # Stats: Reset All - clear all playtime data
        if event == "Reset All Stats":
            if sg.popup_yes_no("Reset ALL playtime stats? This cannot be undone!", title=APP_NAME) == "Yes":
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
            extra_args_str = values.get("-EXTRA-ARGS-", "").strip()
            config["extra_args"] = extra_args_str.split() if extra_args_str else []

            # Apply discord integration settings at runtime
            if discord is not None:
                discord.set_webhook_url(config["discord_webhook_url"])
                discord.enabled = config["discord_notifications"]
            sync_discord_presence_config(discord_presence, config)

            # Save region visibility settings
            for region_code in REGION_META:
                toggle_key = f"-SHOW-{region_code.upper()}-"
                config[f"show_region_{region_code}"] = values.get(toggle_key, False)
            
            save_config(paths["config_file"], config)
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














