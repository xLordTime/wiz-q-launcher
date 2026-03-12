"""Launcher logic and Wizard101 instance management."""

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

try:
    import winreg
except Exception:  # pragma: no cover - only for non-Windows
    winreg = None

try:
    from wizwalker.utils import (
        get_all_wizard_handles,
        instance_login,
        set_foreground_window,
        set_window_title,
    )

    WIZWALKER_AVAILABLE = True
except Exception:
    WIZWALKER_AVAILABLE = False

from core.config import REGISTRY_KEY
from security.crypto import Account
from services.playtime_tracker import PlaytimeTracker


def get_wiz_install(config: dict) -> Path:
    """Get Wizard101 installation path from config or registry."""
    override_path = os.getenv("WIZ_INSTALL_OVERRIDE", "").strip()
    if override_path:
        return Path(override_path).absolute()

    # Check current region's custom install path first
    current_region = config.get("current_region", "de")
    region_install = config.get(f"region_install_{current_region}", "").strip()
    if region_install:
        candidate = Path(region_install)
        if candidate.exists():
            return candidate.absolute()

    # Fall back to old install_path field
    install_path = config.get("install_path", "").strip()
    if install_path:
        candidate = Path(install_path)
        if candidate.exists():
            return candidate.absolute()

    region = str(config.get("region", "de")).lower()
    default_install = config.get("default_install", "")
    if region == "us":
        default_install = config.get("default_install_us", default_install)
    default_install_path = Path(default_install)
    if default_install_path.exists():
        return default_install_path

    if winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY,
                0,
                winreg.KEY_READ,
            ) as key:
                install_location = Path(
                    winreg.QueryValueEx(key, "InstallLocation")[0]
                ).absolute()
                return install_location
        except OSError as exc:
            raise Exception("Wizard101 install not found") from exc

    raise Exception("Wizard101 install not found")


def build_launch_args(config: dict, install_dir: Path) -> List[str]:
    """Build command-line arguments for Wizard101 client."""
    exe = install_dir / "Bin" / "WizardGraphicalClient.exe"
    if not exe.exists():
        raise FileNotFoundError(f"WizardGraphicalClient.exe missing in {exe}")

    # Get region-specific server and port
    current_region = config.get("current_region", "de")
    login_server = config.get(f"region_server_{current_region}", "login-de.eu.wizard101.com")
    login_port = config.get(f"region_port_{current_region}", 12000)

    args = [
        str(exe),
        "-L",
        str(login_server),
        str(login_port),
        "-A",
        str(current_region),
    ]
    extra_args = config.get("extra_args", [])
    if isinstance(extra_args, list):
        args.extend([str(arg) for arg in extra_args])
    return args


def start_instance(config: dict) -> None:
    """Start a single Wizard101 instance."""
    location = get_wiz_install(config)
    args = build_launch_args(config, location)
    subprocess.Popen(args, cwd=str(location / "Bin"))


def get_wizard_handles_safe() -> List[int]:
    """Safely get all active Wizard101 handles."""
    if not WIZWALKER_AVAILABLE:
        return []
    try:
        return list(get_all_wizard_handles())
    except Exception as exc:
        logging.getLogger("wizwalker").warning(
            "Failed to get wizard handles: %s", exc
        )
        return []


def apply_window_options(config: dict, handle: int, account: Account) -> None:
    """Apply window title and foreground options after login."""
    if not WIZWALKER_AVAILABLE:
        return
    if config.get("set_window_title"):
        template = config.get("window_title_template", "{name} ({username})")
        try:
            title = template.format(
                name=account.name, username=account.username
            )
            set_window_title(handle, title)
        except Exception as exc:
            logging.getLogger("launcher").warning(
                "Failed to format window title: %s", exc
            )
    if config.get("foreground_on_login"):
        set_foreground_window(handle)


async def start_instances_with_login(
    instance_number: int, accounts: List[Account], config: dict
) -> None:
    """Start N instances and auto-login selected accounts."""
    start_handles = set(get_wizard_handles_safe())

    for _ in range(instance_number):
        start_instance(config)

    await asyncio.sleep(float(config.get("login_wait_seconds", 5)))

    new_handles = set(get_wizard_handles_safe()).difference(start_handles)

    for handle, account in zip(sorted(new_handles), accounts):
        instance_login(handle, account.username, account.password)
        apply_window_options(config, handle, account)


def launch_with_login(accounts: List[Account], count: int, config: dict) -> None:
    """Start launcher thread with auto-login."""
    logger = logging.getLogger("launcher")

    def runner() -> None:
        try:
            asyncio.run(start_instances_with_login(count, accounts, config))
            logger.info("Auto-login finished for %s instances", count)
        except Exception as exc:
            logger.exception("Auto-login failed: %s", exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()



def track_session_start(tracker: PlaytimeTracker, handle: int, username: str) -> None:
    """Start tracking a playtime session."""
    tracker.start_session(handle, username)
    logging.getLogger("launcher").info(
        "Playtime session started: username=%s handle=%s",
        username,
        handle,
    )


def track_session_end(
    tracker: PlaytimeTracker,
    handle: int,
    account: Account,
    accounts: List[Account],
    reason: str = "process_exit",
) -> Optional[float]:
    """End tracking and update account playtime."""
    duration = tracker.end_session(handle)
    if duration > 0:
        account = tracker.update_account_playtime(account, duration)
        # Update account in list
        for i, acc in enumerate(accounts):
            if acc.username == account.username:
                accounts[i] = account
                break
        logging.getLogger("launcher").info(
            "Playtime session ended (%s): account=%s username=%s handle=%s duration=%s",
            reason,
            account.name,
            account.username,
            handle,
            tracker.format_playtime(duration),
        )
        return duration
    return None
