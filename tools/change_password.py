"""
Standalone master-password changer for Wiz Q Launcher.

Works entirely in the console — no PySimpleGUI required.
Supports:
  - Current format  (salt + iterations + data)
  - Legacy v1       (salt + data, no iterations field  → default 390000)
  - Legacy v0       (base64-only data, no salt/iterations → simple Fernet key)

Run via: change_master_password.bat
Or:      python tools/change_password.py [accounts_file]
"""

import argparse
import base64
import getpass
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check — only stdlib + cryptography needed
# ---------------------------------------------------------------------------
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("[ERROR] 'cryptography' package not installed.")
    print("        Run:  pip install cryptography")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_ITERATIONS = 390000
CURRENT_ITERATIONS = 390000
BANNER = "=" * 60


# ---------------------------------------------------------------------------
# Crypto helpers (self-contained, no dependency on security/crypto.py)
# ---------------------------------------------------------------------------

def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _is_plaintext(raw: object) -> bool:
    """
    Return True if raw JSON looks like an unencrypted accounts file
    (a list of account dicts, or a dict with an 'accounts' list).
    Old versions had no master password and stored data in plain JSON.
    """
    if isinstance(raw, list):
        return bool(raw) and isinstance(raw[0], dict) and "username" in raw[0]
    if isinstance(raw, dict):
        accs = raw.get("accounts")
        if isinstance(accs, list):
            return bool(accs) and isinstance(accs[0], dict) and "username" in accs[0]
    return False


def _extract_plaintext_accounts(raw: object) -> list:
    """Extract the account list from an unencrypted file."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "accounts" in raw:
        return raw["accounts"]
    return []


def _try_decrypt(password: str, enc: dict) -> list:
    """
    Attempt to decrypt with all known format variants.
    Returns the raw account list on success, raises InvalidToken on failure.
    """
    # ── Format: current / legacy-v1  (has 'salt' field) ────────────────────
    if "salt" in enc:
        salt = base64.b64decode(enc["salt"])
        iterations = int(enc.get("iterations", DEFAULT_ITERATIONS))
        key = _derive_key(password, salt, iterations)
        fernet = Fernet(key)
        payload = fernet.decrypt(enc["data"].encode("ascii"))
        return json.loads(payload.decode("utf-8"))

    # ── Format: legacy-v0  (raw Fernet token, password used directly) ───────
    #   Some very early builds encoded the password as the raw Fernet key.
    #   This tries to use the password as a base-64 key directly.
    try:
        key = base64.urlsafe_b64encode(
            password.encode("utf-8").ljust(32, b"\x00")[:32]
        )
        fernet = Fernet(key)
        payload = fernet.decrypt(enc["data"].encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        pass

    # Nothing worked
    raise InvalidToken


def _encrypt(password: str, accounts: list) -> dict:
    """Always re-encrypt with the current (secure) format."""
    salt = os.urandom(16)
    key = _derive_key(password, salt, CURRENT_ITERATIONS)
    fernet = Fernet(key)
    token = fernet.encrypt(json.dumps(accounts).encode("utf-8"))
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": CURRENT_ITERATIONS,
        "data": token.decode("ascii"),
    }


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _ask_password(prompt: str) -> str:
    """Read a password from stdin (hidden input where possible)."""
    try:
        return getpass.getpass(prompt)
    except Exception:
        # Fallback for environments where getpass doesn't hide input
        return input(prompt)


def _confirm(question: str) -> bool:
    return input(f"{question} [j/n]: ").strip().lower() in ("j", "y", "ja", "yes")


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def find_accounts_file(start: Path) -> Path:
    """Walk up from start looking for the accounts file."""
    candidates = [
        start / "data" / "accounts.enc.json",
        start / "accounts.enc.json",
        start.parent / "data" / "accounts.enc.json",
        start.parent / "accounts.enc.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # Return default path even if missing (caller handles it)


def change_password(accounts_file: Path) -> int:
    """
    Interactive master-password change workflow.
    Returns 0 on success, 1 on failure/abort.
    """
    print(BANNER)
    print("  Wiz Q Launcher — Master Password Change Tool")
    print(BANNER)
    print(f"  Accounts file: {accounts_file}")
    print()

    if not accounts_file.exists():
        print("[ERROR] Accounts file not found.")
        print(f"        Expected: {accounts_file}")
        print("        Start the launcher at least once to create it.")
        return 1

    # ── Load encrypted blob ──────────────────────────────────────────────────
    try:
        with accounts_file.open("r", encoding="utf-8") as fh:
            enc = json.load(fh)
    except Exception as e:
        print(f"[ERROR] Could not read accounts file: {e}")
        return 1

    # ── Detect format ────────────────────────────────────────────────────────
    is_plain = _is_plaintext(enc)

    if is_plain:
        fmt = "plaintext (no encryption — legacy version without master password)"
    elif isinstance(enc, dict) and "salt" in enc and "iterations" in enc:
        fmt = f"current (PBKDF2, {enc['iterations']} iterations)"
    elif isinstance(enc, dict) and "salt" in enc:
        fmt = f"legacy-v1 (PBKDF2, default {DEFAULT_ITERATIONS} iterations)"
    else:
        fmt = "legacy-v0 (raw Fernet)"
    print(f"  Detected format : {fmt}")
    print()

    # ── Plaintext path: no current password needed ───────────────────────────
    if is_plain:
        accounts = _extract_plaintext_accounts(enc)
        print(f"  Found {len(accounts)} unencrypted account(s).")
        print("  [MIGRATION] This file has NO master password yet.")
        print("              A new password will be set and the file will be")
        print("              re-encrypted in the current secure format.")
        print()
        # Skip current-password verification — there is none
    else:
        # ── Encrypted path: verify current password ──────────────────────────
        for attempt in range(1, 4):
            current_pw = _ask_password(f"Current master password (attempt {attempt}/3): ")
            if not current_pw:
                print("[ABORT] No password entered.")
                return 1
            try:
                accounts = _try_decrypt(current_pw, enc)
                break
            except InvalidToken:
                print("[WRONG] Password incorrect.")
                if attempt == 3:
                    print("[ERROR] Too many failed attempts. Aborting.")
                    return 1
        else:
            return 1

    print(f"  Unlocked {len(accounts)} account(s).")
    print()

    # ── New password ─────────────────────────────────────────────────────────
    while True:
        new_pw = _ask_password("New master password: ")
        if not new_pw:
            print("[ABORT] No password entered.")
            return 1
        if len(new_pw) < 4:
            print("[WARN] Password must be at least 4 characters. Try again.")
            continue
        confirm_pw = _ask_password("Confirm new master password: ")
        if new_pw != confirm_pw:
            print("[WARN] Passwords do not match. Try again.")
            continue
        break

    # ── Backup ───────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = accounts_file.with_suffix(f".bak_{ts}.json")
    try:
        shutil.copy2(accounts_file, backup_path)
        print(f"\n  Backup saved: {backup_path.name}")
    except Exception as e:
        print(f"\n[WARN] Could not create backup: {e}")
        if not _confirm("  Continue without backup?"):
            print("[ABORT]")
            return 1

    # ── Re-encrypt and save ───────────────────────────────────────────────────
    try:
        new_enc = _encrypt(new_pw, accounts)
        with accounts_file.open("w", encoding="utf-8") as fh:
            json.dump(new_enc, fh, indent=2, sort_keys=True)
        print("  Master password changed successfully.")
        print(f"  New format: current (PBKDF2, {CURRENT_ITERATIONS} iterations)")
        print()
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to save new password: {e}")
        print(f"        Your original file is still intact.")
        try:
            shutil.copy2(backup_path, accounts_file)
        except Exception:
            pass
        return 1


def reset_password(accounts_file: Path) -> int:
    """
    Delete the accounts file so the launcher starts completely fresh
    (emulates a new install — no accounts, no master password).
    Returns 0 on success, 1 on abort/failure.
    """
    print(BANNER)
    print("  Wiz Q Launcher \u2014 Master Password RESET Tool")
    print(BANNER)
    print(f"  Accounts file: {accounts_file}")
    print()

    if not accounts_file.exists():
        print("  No accounts file found \u2014 already a fresh state.")
        return 0

    print("  WARNING: This will permanently DELETE all saved accounts.")
    print("           The launcher will behave as if starting for the first time.")
    print()
    confirm1 = input("  Type YES to confirm reset: ").strip()
    if confirm1 != "YES":
        print("[ABORT] Reset cancelled.")
        return 1
    confirm2 = input("  Type YES again to confirm: ").strip()
    if confirm2 != "YES":
        print("[ABORT] Reset cancelled.")
        return 1

    # Create timestamped backup before deleting
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = accounts_file.with_suffix(f".bak_{ts}.json")
    try:
        shutil.copy2(accounts_file, backup_path)
        print(f"\n  Backup saved : {backup_path.name}")
    except Exception as e:
        print(f"[WARN] Could not create backup: {e}")

    try:
        accounts_file.unlink()
        print("  Accounts file deleted.")
        print("  Next launcher start will prompt for a new master password.")
        print()
        return 0
    except Exception as e:
        print(f"[ERROR] Could not delete accounts file: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Change or reset the Wiz Q Launcher master password."
    )
    parser.add_argument(
        "accounts_file",
        nargs="?",
        help="Path to accounts.enc.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all accounts and start completely fresh (new install simulation)",
    )
    args = parser.parse_args()

    if args.accounts_file:
        accounts_file = Path(args.accounts_file).resolve()
    else:
        accounts_file = find_accounts_file(Path(__file__).resolve().parent.parent)

    try:
        if args.reset:
            return reset_password(accounts_file)
        return change_password(accounts_file)
    except KeyboardInterrupt:
        print("\n[ABORT] Cancelled by user.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
