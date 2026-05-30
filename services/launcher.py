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


# Map folder-name suffix → region code (lowercase, including parentheses)
_FOLDER_SUFFIX_TO_REGION: dict = {
    "(de)": "de",
    "(fr)": "fr",
    "(it)": "it",
    "(gb)": "gb",
    "(pl)": "pl",
    "(es)": "es",
    "(gr)": "gr",
}

# Common install root directories to scan
_INSTALL_SEARCH_ROOTS: list = [
    Path(r"C:\ProgramData\KingsIsle Entertainment"),
    Path(r"C:\Program Files (x86)\KingsIsle Entertainment"),
    Path(r"C:\Program Files\KingsIsle Entertainment"),
]


def find_wiz_installs() -> dict:
    """
    Scan common directories and the Windows registry for Wizard101 installs.

    Returns a dict ``{region_code: install_path_str}`` for each found region.
    Verifies that ``Bin\\WizardGraphicalClient.exe`` exists before including
    a candidate.
    """
    found: dict = {}

    # ── 1. File-system scan ───────────────────────────────────────────────
    for root in _INSTALL_SEARCH_ROOTS:
        if not root.exists():
            continue
        try:
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                name_lower = entry.name.lower()
                if not name_lower.startswith("wizard101"):
                    continue
                exe = entry / "Bin" / "WizardGraphicalClient.exe"
                if not exe.exists():
                    continue
                region = "us"  # no suffix → US
                for suffix, code in _FOLDER_SUFFIX_TO_REGION.items():
                    if name_lower.endswith(suffix):
                        region = code
                        break
                if region not in found:
                    found[region] = str(entry)
        except PermissionError:
            pass

    # ── 2. Registry scan ─────────────────────────────────────────────────
    if winreg is not None:
        _REG_ROOTS = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, uninstall_key in _REG_ROOTS:
            try:
                with winreg.OpenKey(hive, uninstall_key) as uk:
                    idx = 0
                    while True:
                        try:
                            sub_key = winreg.EnumKey(uk, idx)
                            idx += 1
                            with winreg.OpenKey(uk, sub_key) as sk:
                                try:
                                    display_name = winreg.QueryValueEx(sk, "DisplayName")[0]
                                    if "wizard101" not in display_name.lower():
                                        continue
                                    install_loc = winreg.QueryValueEx(sk, "InstallLocation")[0]
                                    candidate = Path(install_loc)
                                    exe = candidate / "Bin" / "WizardGraphicalClient.exe"
                                    if not exe.exists():
                                        continue
                                    name_lower = display_name.lower()
                                    region = "us"
                                    for suffix, code in _FOLDER_SUFFIX_TO_REGION.items():
                                        bare = suffix.strip("()")
                                        if bare in name_lower:
                                            region = code
                                            break
                                    if region not in found:
                                        found[region] = str(candidate)
                                except (FileNotFoundError, OSError):
                                    pass
                        except OSError:
                            break
            except OSError:
                pass

    return found


def auto_detect_wiz_install(config: dict) -> bool:
    """
    Scan for Wizard101 installs and fill any *empty* ``region_install_*``
    config keys.  Returns ``True`` if at least one path was newly stored.
    """
    found = find_wiz_installs()
    if not found:
        return False
    changed = False
    for region_code, install_path in found.items():
        key = f"region_install_{region_code}"
        if not config.get(key, "").strip():
            config[key] = install_path
            changed = True
            logging.getLogger("launcher").info(
                "Auto-detected Wizard101 install for %s: %s", region_code, install_path
            )
    return changed


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
        except OSError:
            pass

    # Last resort: full filesystem + registry scan
    current_region = config.get("current_region", "de")
    scanned = find_wiz_installs()
    if current_region in scanned:
        return Path(scanned[current_region]).absolute()
    # Any install is better than none
    if scanned:
        return Path(next(iter(scanned.values()))).absolute()

    raise Exception(
        "Wizard101 install not found. "
        "Set the install path in Settings → Regions or click 'Auto-Detect'."
    )


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
    try:
        subprocess.Popen(args, cwd=str(location / "Bin"))
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot start Wizard101 — permission denied: {exc}"
        ) from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Wizard101 executable not found: {exc}"
        ) from exc
    except OSError as exc:
        raise OSError(f"Failed to start Wizard101: {exc}") from exc


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
