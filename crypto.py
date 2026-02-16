"""Encryption and account management module."""

import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import PySimpleGUI as sg
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config import APP_NAME


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


def encrypt_accounts(password: str, accounts: List[Account]) -> dict:
    """Encrypt accounts with master password."""
    salt = os.urandom(16)
    iterations = 390000
    key = derive_key(password, salt, iterations)
    fernet = Fernet(key)

    payload = [account.__dict__ for account in accounts]
    token = fernet.encrypt(json.dumps(payload).encode("utf-8"))

    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": iterations,
        "data": token.decode("ascii"),
    }


def decrypt_accounts(password: str, encrypted: dict) -> List[Account]:
    """Decrypt accounts with master password."""
    salt = base64.b64decode(encrypted["salt"].encode("ascii"))
    iterations = int(encrypted.get("iterations", 390000))
    key = derive_key(password, salt, iterations)
    fernet = Fernet(key)

    payload = fernet.decrypt(encrypted["data"].encode("ascii"))
    accounts = json.loads(payload.decode("utf-8"))
    return [Account(**item) for item in accounts]


def load_accounts(accounts_file: Path, password: str) -> List[Account]:
    """Load encrypted accounts from file."""
    if not accounts_file.exists():
        return []

    with accounts_file.open("r", encoding="utf-8") as handle:
        encrypted = json.load(handle)
    return decrypt_accounts(password, encrypted)


def save_accounts(
    accounts_file: Path, password: str, accounts: List[Account]
) -> None:
    """Save accounts encrypted to file."""
    encrypted = encrypt_accounts(password, accounts)
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


def load_master_password(accounts_file: Path) -> Optional[str]:
    """Prompt and validate master password."""
    first_time = not accounts_file.exists()
    while True:
        password = prompt_master_password(first_time)
        if password is None:
            return None

        if first_time:
            return password

        try:
            load_accounts(accounts_file, password)
            return password
        except InvalidToken:
            sg.popup("Master password invalid", title=APP_NAME)
        except Exception as exc:
            sg.popup(f"Failed to unlock: {exc}", title=APP_NAME)


def account_display(account: Account) -> str:
    """Format account for display in UI."""
    return f"{account.name} ({account.username})"


def add_edit_account(account: Optional[Account] = None, current_region: str = "de") -> Optional[Account]:
    """Dialog to add or edit an account."""
    from config import REGION_META
    
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
