"""Encryption and account management module."""

import base64
import ctypes
import ctypes.wintypes
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import PySimpleGUI as sg
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.config import APP_NAME

# Sentinel returned by change_master_password() when the user chose
# a full reset instead of changing the password.
MASTER_PASSWORD_RESET = "__RESET__"
MASTER_PASSWORD_PLACEHOLDER = "0"
AccountSecret = Union[str, bytes]


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPT32 = ctypes.windll.crypt32
_KERNEL32 = ctypes.windll.kernel32


@dataclass
class Account:
    """Account data structure."""

    name: str
    username: str
    password: str
    region: str = "de"  # Region code (de, us, fr, etc.)
    last_used: float = 0.0
    total_playtime: float = 0.0  # Sekunden
    last_session_start: float = 0.0  # Zeitstempel
    sessions_count: int = 0  # Anzahl der Spielsessions


def derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derive encryption key from password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _secret_to_bytes(secret: AccountSecret) -> bytes:
    if isinstance(secret, bytes):
        return secret
    return secret.encode("utf-8")


def _protect_secret(secret: bytes) -> str:
    """Protect a secret with Windows DPAPI for the current user."""
    if not secret:
        return ""

    in_blob = _DATA_BLOB()
    secret_buffer = ctypes.create_string_buffer(secret)
    in_blob.cbData = len(secret)
    in_blob.pbData = ctypes.cast(secret_buffer, ctypes.POINTER(ctypes.c_byte))

    out_blob = _DATA_BLOB()
    if not _CRYPT32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")

    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(protected).decode("ascii")
    finally:
        if out_blob.pbData:
            _KERNEL32.LocalFree(out_blob.pbData)


def _unprotect_secret(blob_b64: str) -> Optional[bytes]:
    """Recover a DPAPI-protected secret."""
    if not blob_b64:
        return None

    protected = base64.b64decode(blob_b64.encode("ascii"))
    in_blob = _DATA_BLOB()
    protected_buffer = ctypes.create_string_buffer(protected)
    in_blob.cbData = len(protected)
    in_blob.pbData = ctypes.cast(protected_buffer, ctypes.POINTER(ctypes.c_byte))

    out_blob = _DATA_BLOB()
    if not _CRYPT32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        return None

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            _KERNEL32.LocalFree(out_blob.pbData)


def _store_secret(config: dict, secret: bytes, mode: str, expires_at: int = 0) -> None:
    config["master_password_mode"] = mode
    config["master_password_enabled"] = mode == "password" and bool(config.get("master_password_enabled", True))
    config["master_password_secret_b64"] = _protect_secret(secret)
    config["master_password_secret_expires"] = int(expires_at)


def _load_stored_secret(config: dict) -> Optional[AccountSecret]:
    mode = str(config.get("master_password_mode", "password"))
    secret_blob = str(config.get("master_password_secret_b64", "")).strip()
    expires_at = int(config.get("master_password_secret_expires", 0) or 0)

    if not secret_blob:
        return None
    if expires_at and time.time() >= expires_at:
        config["master_password_secret_b64"] = ""
        config["master_password_secret_expires"] = 0
        config["master_password_enabled"] = True
        return None

    secret = _unprotect_secret(secret_blob)
    if secret is None:
        return None

    if mode == "local":
        return secret
    return secret.decode("utf-8")


def encrypt_accounts(secret: AccountSecret, accounts: List[Account]) -> dict:
    """Encrypt accounts with master password."""
    secret_bytes = _secret_to_bytes(secret)
    if isinstance(secret, bytes):
        key = secret_bytes
        salt = None
        iterations = None
    else:
        salt = os.urandom(16)
        iterations = 390000
        key = derive_key(secret, salt, iterations)
    fernet = Fernet(key)

    payload = [account.__dict__ for account in accounts]
    token = fernet.encrypt(json.dumps(payload).encode("utf-8"))

    encrypted = {
        "data": token.decode("ascii"),
        "mode": "local" if isinstance(secret, bytes) else "password",
    }
    if salt is not None and iterations is not None:
        encrypted["salt"] = base64.b64encode(salt).decode("ascii")
        encrypted["iterations"] = iterations
    return encrypted


def decrypt_accounts(secret: AccountSecret, encrypted: dict) -> List[Account]:
    """Decrypt accounts with master password."""
    if isinstance(secret, bytes):
        key = secret
    else:
        salt = base64.b64decode(encrypted["salt"].encode("ascii"))
        iterations = int(encrypted.get("iterations", 390000))
        key = derive_key(secret, salt, iterations)
    fernet = Fernet(key)

    payload = fernet.decrypt(encrypted["data"].encode("ascii"))
    accounts = json.loads(payload.decode("utf-8"))
    return [Account(**item) for item in accounts]


def load_accounts(accounts_file: Path, secret: AccountSecret) -> List[Account]:
    """Load encrypted accounts from file."""
    if not accounts_file.exists():
        return []

    with accounts_file.open("r", encoding="utf-8") as handle:
        encrypted = json.load(handle)

    if isinstance(encrypted, list):
        return [Account(**item) for item in encrypted]

    return decrypt_accounts(secret, encrypted)


def save_accounts(
    accounts_file: Path, secret: AccountSecret, accounts: List[Account]
) -> None:
    """Save accounts encrypted to file."""
    encrypted = encrypt_accounts(secret, accounts)
    with accounts_file.open("w", encoding="utf-8") as handle:
        json.dump(encrypted, handle, indent=2, sort_keys=True)


def prompt_master_password(first_time: bool) -> Optional[str]:
    """Prompt user for master password (create on first run)."""
    if first_time:
        pw1 = sg.popup_get_text(
            "Create master password",
            title=APP_NAME,
            password_char="*",
        )
        if not pw1:
            return None
        pw2 = sg.popup_get_text(
            "Confirm master password",
            title=APP_NAME,
            password_char="*",
        )
        if pw1 != pw2:
            sg.popup("Passwords do not match", title=APP_NAME)
            return None
        return pw1

    pw = sg.popup_get_text(
        "Enter master password",
        title=APP_NAME,
        password_char="*",
    )
    return pw or None


def load_master_password(accounts_file: Path, config: Optional[dict] = None) -> Optional[AccountSecret]:
    """Prompt, validate, or restore the master secret used for accounts."""
    first_time = not accounts_file.exists()

    if config is not None:
        stored_secret = _load_stored_secret(config)
        if stored_secret is not None:
            return stored_secret

    if config is not None and config.get("master_password_mode") == "local":
        sg.popup(
            "Master password is disabled for this launcher profile.\n"
            "Accounts will be unlocked automatically on this Windows user.",
            title=APP_NAME,
        )
        return None

    if config is not None and config.get("master_password_mode") == "placeholder":
        return MASTER_PASSWORD_PLACEHOLDER

    if first_time:
        choice = sg.popup_yes_no(
            "Would you like to use a master password to protect your accounts?\n\n"
            "Yes = require a password at startup\n"
            "No = use a local Windows-protected secret instead",
            title=APP_NAME,
        )
        if choice is None:
            return None
        if choice == "No":
            if config is not None:
                config["master_password_mode"] = "placeholder"
                config["master_password_enabled"] = False
                config["master_password_secret_b64"] = ""
                config["master_password_secret_expires"] = 0
            sg.popup(
                "No master password selected.\n"
                "Placeholder '0' is active until you set a real master password.",
                title=APP_NAME,
            )
            return MASTER_PASSWORD_PLACEHOLDER

        password = prompt_master_password(True)
        if password is None:
            return None
        if config is not None:
            config["master_password_mode"] = "password"
            config["master_password_enabled"] = True
            config["master_password_secret_b64"] = ""
            config["master_password_secret_expires"] = 0
        return password

    while True:
        password = prompt_master_password(False)
        if password is None:
            return None

        try:
            load_accounts(accounts_file, password)
            if config is not None:
                config["master_password_mode"] = "password"
                config["master_password_enabled"] = True
                config["master_password_secret_b64"] = ""
                config["master_password_secret_expires"] = 0
            return password
        except InvalidToken:
            choice = sg.popup_yes_no(
                "Master password invalid.\n\n"
                "Do you want to reset saved accounts and continue with placeholder '0'?\n"
                "The old accounts file will be kept as a backup.",
                title=APP_NAME,
            )
            if choice == "Yes":
                try:
                    if accounts_file.exists():
                        backup_name = (
                            f"{accounts_file.stem}.invalid-{int(time.time())}{accounts_file.suffix}.bak"
                        )
                        backup_path = accounts_file.with_name(backup_name)
                        accounts_file.replace(backup_path)
                except Exception as exc:
                    sg.popup(f"Failed to create accounts backup:\n{exc}", title=APP_NAME)
                    continue

                if config is not None:
                    config["master_password_mode"] = "placeholder"
                    config["master_password_enabled"] = False
                    config["master_password_secret_b64"] = ""
                    config["master_password_secret_expires"] = 0

                sg.popup(
                    "Accounts were reset and backed up.\n"
                    "Launcher continues with placeholder '0'.\n"
                    "Set a real master password in Settings afterwards.",
                    title=APP_NAME,
                )
                return MASTER_PASSWORD_PLACEHOLDER

            sg.popup("Master password invalid", title=APP_NAME)
        except Exception as exc:
            sg.popup(f"Failed to unlock: {exc}", title=APP_NAME)


def create_local_master_secret(config: Optional[dict] = None) -> bytes:
    """Create and store a locally protected master secret (passwordless mode)."""
    secret = Fernet.generate_key()
    if config is not None:
        _store_secret(config, secret, mode="local", expires_at=0)
        config["master_password_enabled"] = False
    return secret


def suspend_master_password(config: dict, current_password: str, days: int) -> None:
    """Suspend password prompts by caching the current password locally for N days."""
    expires_at = int(time.time()) + max(1, days) * 86400
    _store_secret(config, current_password.encode("utf-8"), mode="password", expires_at=expires_at)
    config["master_password_enabled"] = False
    config["master_password_suspend_days"] = max(1, days)


def invalidate_stored_master_secret(config: dict) -> None:
    """Invalidate any locally cached unlock secret immediately."""
    config["master_password_secret_b64"] = ""
    config["master_password_secret_expires"] = 0
    config["master_password_enabled"] = True


def change_master_password(
    accounts_file: Path,
    current_password: AccountSecret,
    accounts: List[Account],
    config: Optional[dict] = None,
) -> Optional[str]:
    """
    Let the user change the master password.

    Verifies the current password, asks for a new one (with confirmation),
    re-encrypts all accounts with the new password, and saves the file.

    Args:
        accounts_file: Path to the encrypted accounts file.
        current_password: The currently active master password.
        accounts: Already-loaded list of Account objects.

    Returns:
        The new password string if changed successfully, None otherwise.
    """
    # ── Ask whether to change or fully reset ────────────────────────────────
    choice = sg.popup_yes_no(
        "What would you like to do?\n\n"
        "  YES  →  Change master password (keep accounts)\n"
        "  NO   →  RESET — delete all accounts and start fresh",
        title=APP_NAME,
    )
    if choice is None:
        return None

    # ── RESET branch ─────────────────────────────────────────────────────────
    if choice == "No":
        confirm = sg.popup_yes_no(
            "WARNING: This will permanently delete ALL saved accounts.\n"
            "The launcher will behave as if it is starting for the first time.\n\n"
            "Are you absolutely sure?",
            title=APP_NAME,
        )
        if confirm != "Yes":
            return None
        try:
            if accounts_file.exists():
                accounts_file.unlink()
        except Exception as exc:
            sg.popup(f"Failed to delete accounts file:\n{exc}", title=APP_NAME)
            return None
        sg.popup(
            "Accounts file deleted.\n"
            "On next action you will be prompted to create a new master password.",
            title=APP_NAME,
        )
        return MASTER_PASSWORD_RESET

    # ── CHANGE branch ────────────────────────────────────────────────────────
    skip_current_password_check = (
        config is not None and str(config.get("master_password_mode", "password")) == "placeholder"
    )

    if not isinstance(current_password, bytes) and not skip_current_password_check:
        entered = sg.popup_get_text(
            "Enter your CURRENT master password to continue:",
            title=APP_NAME,
            password_char="*",
        )
        if not entered:
            return None
        if entered != current_password:
            sg.popup("Current password is incorrect.", title=APP_NAME)
            return None

    new_pw = sg.popup_get_text(
        "Enter NEW master password:",
        title=APP_NAME,
        password_char="*",
    )
    if not new_pw:
        return None
    if len(new_pw) < 4:
        sg.popup("Password must be at least 4 characters.", title=APP_NAME)
        return None

    for attempt in range(3):
        label = "Confirm NEW master password:"
        if attempt > 0:
            label += f"\n\nPasswords did not match — attempt {attempt + 1}/3:"
        confirm_pw = sg.popup_get_text(
            label,
            title=APP_NAME,
            password_char="*",
        )
        if confirm_pw is None:
            return None
        if new_pw == confirm_pw:
            break
        if attempt < 2:
            sg.popup("Passwords do not match. Please try again.", title=APP_NAME)
    else:
        sg.popup("Passwords do not match — change cancelled.", title=APP_NAME)
        return None

    save_accounts(accounts_file, new_pw, accounts)
    if config is not None:
        config["master_password_mode"] = "password"
        config["master_password_enabled"] = True
        config["master_password_secret_b64"] = ""
        config["master_password_secret_expires"] = 0
    sg.popup("Master password changed successfully.", title=APP_NAME)
    return new_pw


def account_display(account: Account) -> str:
    """Format account for display in UI."""
    return f"{account.name} ({account.username})"


def add_edit_account(account: Optional[Account] = None, current_region: str = "de") -> Optional[Account]:
    """Dialog to add or edit an account."""
    from core.config import REGION_META
    
    # Build region options
    region_options = []
    for region_code, region_info in REGION_META.items():
        region_display = f"{region_code.upper()} - {region_info['name']}"
        region_options.append(region_display)
    
    # Get default region
    if account:
        default_region = f"{account.region.upper()} - {REGION_META.get(account.region, {}).get('name', account.region.upper())}"
    else:
        default_region = f"{current_region.upper()} - {REGION_META.get(current_region, {}).get('name', current_region.upper())}"
    
    layout = [
        [sg.Text("Name"), sg.Input(account.name if account else "", key="-NAME-")],
        [
            sg.Text("Username"),
            sg.Input(account.username if account else "", key="-USER-"),
        ],
        [
            sg.Text("Password"),
            sg.Input(
                account.password if account else "",
                key="-PASS-",
                password_char="*",
            ),
        ],
        [
            sg.Text("Region"),
            sg.Combo(
                region_options,
                default_value=default_region,
                key="-REGION-",
                readonly=True,
                size=(30, 1)
            )
        ],
        [sg.Button("Save"), sg.Button("Cancel")],
    ]

    window = sg.Window("Account", layout, modal=True)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, "Cancel"):
            window.close()
            return None
        if event == "Save":
            name = values["-NAME-"].strip()
            username = values["-USER-"].strip()
            password = values["-PASS-"].strip()
            region_display = values["-REGION-"]
            
            # Extract region code from display (e.g., "DE - Deutschland" -> "de")
            region_code = region_display.split(" - ")[0].lower() if region_display else current_region
            
            if not name or not username or not password:
                sg.popup("Please fill all fields", title=APP_NAME)
                continue
            window.close()
            
            # Preserve existing account data if editing
            if account:
                return Account(
                    name=name,
                    username=username,
                    password=password,
                    region=region_code,
                    last_used=account.last_used,
                    total_playtime=account.total_playtime,
                    last_session_start=account.last_session_start,
                    sessions_count=account.sessions_count
                )
            else:
                return Account(name=name, username=username, password=password, region=region_code)

