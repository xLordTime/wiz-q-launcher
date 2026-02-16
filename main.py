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
import sys
import time
import psutil
from pathlib import Path

import PySimpleGUI as sg

from config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CONFIG,
    REGION_META,
    load_config,
    save_config,
)
from crypto import (
    Account,
    account_display,
    add_edit_account,
    load_accounts,
    load_master_password,
    save_accounts,
)
from launcher import (
    WIZWALKER_AVAILABLE,
    launch_with_login,
    start_instance,
    track_session_start,
    track_session_end,
    get_wizard_handles_safe,
)
from logging_utils import setup_logging
from playtime_tracker import PlaytimeTracker
from ui import apply_theme, build_window
from performance_monitor import PerformanceMonitor
from discord_integration import DiscordIntegration
from log_viewer import LogViewer
from update_checker import UpdateChecker
from issue_reporter import IssueReporter
from window_manager import WindowManager


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
        root = Path(__file__).resolve().parent
    
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


def start_and_track_sessions(
    config: dict,
    selected_accounts: list,
    count: int,
    tracker: PlaytimeTracker,
    active_sessions: dict,
    paths: dict,
    master_password: str,
    accounts: list,
    discord: DiscordIntegration = None,
) -> None:
    """
    Start game instances with auto-login and track playtime sessions.
    
    Process:
    1. Get current Wizard101 process handles before launch
    2. Launch instances with auto-login
    3. Detect new processes
    4. Start tracking each session
    5. Send Discord notification (if configured)
    
    Args:
        config: Application configuration
        selected_accounts: List of Account objects to start
        count: Number of instances to start
        tracker: PlaytimeTracker instance
        active_sessions: Dict to store {handle: account_name}
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
    
    # Wait a bit for new instances to appear
    time.sleep(3)
    
    # Track new handles
    after_handles = set(get_wizard_handles_safe())
    new_handles = after_handles.difference(before_handles)
    
    for handle, account in zip(sorted(new_handles), selected_accounts[:count]):
        track_session_start(tracker, handle, account.username)
        active_sessions[handle] = account.name
        logger.debug(f"Tracking playtime for {account.name} (handle {handle})")
        
        # Send Discord notification if configured
        if discord and config.get("discord_notifications"):
            discord.send_session_started(account.name, account.username, config.get("current_region", "de"))



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
    active_sessions = {}  # {handle: account_name}
    
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
        updater = UpdateChecker(current_version=APP_VERSION, repo="oliwi/q-launcher")
    except Exception as e:
        logger.warning(f"Failed to initialize update checker: {e}")
        updater = None
    
    # Initialize error reporter
    try:
        reporter = IssueReporter(
            github_repo=config.get("github_repo", "oliwi/q-launcher"),
            discord_webhook=config.get("discord_webhook_url")
        )
    except Exception as e:
        logger.warning(f"Failed to initialize issue reporter: {e}")
        reporter = None
    
    # Initialize log viewer
    try:
        log_file = paths["log_dir"] / "launcher.log"
        log_viewer = LogViewer(log_file) if log_file.exists() else None
    except Exception as e:
        logger.warning(f"Failed to initialize log viewer: {e}")
        log_viewer = None
    
    # Initialize window manager
    try:
        win_manager = WindowManager()
    except Exception as e:
        logger.warning(f"Failed to initialize window manager: {e}")
        win_manager = None
    
    # Build and display window
    try:
        window = build_window(config, accounts, log_file_path=str(log_file))
    except Exception as e:
        logger.exception(f"Failed to build window: {e}")
        sg.popup_error(f"Failed to build window:\n{str(e)}", title=APP_NAME)
        return 1
    logger = logging.getLogger("launcher")

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
                # Check for closed handles and end sessions
                if active_sessions:
                    current_handles = set(get_wizard_handles_safe())
                    closed_handles = [h for h in active_sessions if h not in current_handles]
                    for handle in closed_handles:
                        acc_name = active_sessions.pop(handle)
                        acc = next((a for a in accounts if a.name == acc_name), None)
                        if acc:
                            track_session_end(tracker, handle, acc, accounts)
                            save_accounts(paths["accounts_file"], master_password, accounts)
            except Exception as e:
                logger.exception(f"CRASH in TIMEOUT_EVENT handler: {e}")
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

        # ================== EXTENSIONS / WIZWALL ==================
        # Toggle Wizwall Extension
        if event == "-WIZWALL-ENABLED-":
            wizwall_enabled = values["-WIZWALL-ENABLED-"]
            config["wizwall_enabled"] = wizwall_enabled
            
            # Enable/disable all wizwall controls
            window["-WIZWALL-LAYOUT-"].update(disabled=not wizwall_enabled)
            window["-WIZWALL-AUTO-RESOLUTION-"].update(disabled=not wizwall_enabled)
            window["-ARRANGE-WINDOWS-"].update(disabled=not wizwall_enabled)
            window["-REFRESH-WINDOWS-"].update(disabled=not wizwall_enabled)
            window["-SAVE-LAYOUT-"].update(disabled=not wizwall_enabled)
            window["-RESTORE-LAYOUT-"].update(disabled=not wizwall_enabled)
            window["-SET-RESOLUTION-"].update(disabled=not wizwall_enabled)
            
            status = "enabled" if wizwall_enabled else "disabled"
            window["-STATUS-"].update(f"Wizwall extension {status}")
            save_config(paths["config_file"], config)
        
        # Set Resolution for Layout
        if event == "-SET-RESOLUTION-" and win_manager:
            try:
                layout = values.get("-WIZWALL-LAYOUT-", "2x2")
                width, height = win_manager.get_optimal_resolution_for_layout(layout)
                
                # Get wizard install path
                from launcher import get_wiz_install
                wiz_path = get_wiz_install(config)
                
                # Confirm with user
                msg = (
                    f"This will set the game resolution to {width}x{height}\n"
                    f"for optimal {layout} grid layout.\n\n"
                    f"File: {wiz_path}/Bin/preferences.xml\n\n"
                    f"⚠️  All running Wizard101 clients must be RESTARTED\n"
                    f"for this change to take effect!\n\n"
                    f"Continue?"
                )
                
                if sg.popup_yes_no(msg, title="Set Game Resolution") == "Yes":
                    success = win_manager.set_game_resolution(width, height, str(wiz_path))
                    if success:
                        sg.popup_ok(
                            f"✓ Resolution set to {width}x{height}\n\n"
                            f"Please RESTART all Wizard101 clients now!",
                            title="Success"
                        )
                        window["-STATUS-"].update(f"Set resolution: {width}x{height} (restart clients!)")
                    else:
                        sg.popup_error("Failed to set resolution. Check logs.", title=APP_NAME)
            except Exception as e:
                logger.exception(f"Set resolution failed: {e}")
                sg.popup_error(f"Failed to set resolution:\n{str(e)}", title=APP_NAME)
        
        # Arrange Windows - Multi-window grid layout
        if event == "-ARRANGE-WINDOWS-" and win_manager:
            try:
                layout = values.get("-WIZWALL-LAYOUT-", "2x2")
                
                # Build account mapping for window identification
                account_map = {handle: name for handle, name in active_sessions.items()}
                
                # Get all wizard windows
                windows = win_manager.get_wizard_windows(account_map)
                
                if not windows:
                    sg.popup("No Wizard101 windows found.\nStart some instances first!", title=APP_NAME)
                else:
                    # Arrange in selected grid layout
                    arranged = win_manager.arrange_grid(windows, layout=layout, padding=10)
                    
                    # Update window list display
                    window_info = "\n".join([
                        f"[{i+1}] {w.account_name} - Handle: {w.handle}"
                        for i, w in enumerate(windows)
                    ])
                    window["-WIZWALL-WINDOWS-"].update(window_info)
                    
                    window["-STATUS-"].update(f"✓ Arranged {arranged} windows in {layout} layout")
                    logger.info(f"Arranged {arranged} windows in {layout} layout")
            except Exception as e:
                logger.exception(f"Window arrangement failed: {e}")
                sg.popup_error(f"Failed to arrange windows:\n{str(e)}", title=APP_NAME)

        # Refresh Window List - Show current windows
        if event == "-REFRESH-WINDOWS-" and win_manager:
            try:
                account_map = {handle: name for handle, name in active_sessions.items()}
                windows = win_manager.get_wizard_windows(account_map)
                
                if windows:
                    window_info = "\n".join([
                        f"[{i+1}] {w.account_name} - Handle: {w.handle} - {w.title}"
                        for i, w in enumerate(windows)
                    ])
                    window["-WIZWALL-WINDOWS-"].update(window_info)
                    window["-STATUS-"].update(f"Found {len(windows)} active windows")
                else:
                    window["-WIZWALL-WINDOWS-"].update("No Wizard101 windows detected.")
                    window["-STATUS-"].update("No active windows found")
                    
            except Exception as e:
                logger.exception(f"Window refresh failed: {e}")
                sg.popup_error(f"Failed to refresh windows:\n{str(e)}", title=APP_NAME)
        
        # Save Current Layout
        if event == "-SAVE-LAYOUT-" and win_manager:
            try:
                account_map = {handle: name for handle, name in active_sessions.items()}
                windows = win_manager.get_wizard_windows(account_map)
                
                if not windows:
                    sg.popup("No windows to save layout for.", title=APP_NAME)
                else:
                    layout_data = win_manager.save_current_layout(windows)
                    # Store in config for persistence
                    config["saved_window_layout"] = layout_data
                    save_config(paths["config_file"], config)
                    window["-STATUS-"].update(f"✓ Saved layout for {len(layout_data)} windows")
                    sg.popup_ok(f"Saved positions for {len(layout_data)} windows", title="Layout Saved")
            except Exception as e:
                logger.exception(f"Save layout failed: {e}")
                sg.popup_error(f"Failed to save layout:\n{str(e)}", title=APP_NAME)
        
        # Restore Saved Layout
        if event == "-RESTORE-LAYOUT-" and win_manager:
            try:
                layout_data = config.get("saved_window_layout", {})
                if not layout_data:
                    sg.popup("No saved layout found.\nUse 'Save Current Layout' first.", title=APP_NAME)
                else:
                    restored = win_manager.restore_layout(layout_data)
                    window["-STATUS-"].update(f"✓ Restored {restored} windows")
                    sg.popup_ok(f"Restored {restored} windows to saved positions", title="Layout Restored")
            except Exception as e:
                logger.exception(f"Restore layout failed: {e}")
                sg.popup_error(f"Failed to restore layout:\n{str(e)}", title=APP_NAME)

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

        # Stats: Refresh - rebuild window with updated stats
        if event == "Refresh":
            window.close()
            window = build_window(config, accounts, log_file_path=str(log_file))
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

        # Stats: Reset All - clear all playtime data
        if event == "Reset All Stats":
            if sg.popup_yes_no("Reset ALL playtime stats? This cannot be undone!", title=APP_NAME) == "Yes":
                for account in accounts:
                    account.total_playtime = 0.0
                    account.sessions_count = 0
                    account.last_session_start = 0.0
                save_accounts(paths["accounts_file"], master_password, accounts)
                window.close()
                window = build_window(config, accounts, log_file_path=str(log_file))
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
                selected_accounts = [
                    acc for acc in accounts if account_display(acc) in selected
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
                selected_accounts = [
                    acc for acc in accounts if account_display(acc) in selected
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

        # F4 - Minimize to tray (or toggle window visibility)
        if event == "F4":
            if window.is_hidden():
                window.un_hide()
                window["-STATUS-"].update("Window restored (F4)")
            else:
                window.hide()
                window["-STATUS-"].update("Minimized to background (F4)")

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
        for handle, acc_name in list(active_sessions.items()):
            acc = next((a for a in accounts if a.name == acc_name), None)
            if acc:
                track_session_end(tracker, handle, acc, accounts)
        # Save final playtime data
        save_accounts(paths["accounts_file"], master_password, accounts)
        logger.info("Playtime sessions saved")

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
