"""Read-only legacy decoder; deliberately imports neither the old GUI nor Win32 hooks."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .settings import BY_KEY, REGIONS, set_value
from .vault import b64, dpapi


def read_json(path, default=None):
    if not path.exists():
        return default
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Alte Profildatei ist ungewöhnlich groß; Import wurde angehalten.")
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def legacy_sources(root, executable_dir):
    roots = []
    for folder in (Path(root), Path(executable_dir)):
        if folder not in roots and (
            (folder / "config.json").exists() or (folder / "data/accounts.enc.json").exists()
        ):
            roots.append(folder)
    return roots


def decode_accounts(source, password=None):
    config = read_json(source / "config.json", {})
    if not isinstance(config, dict):
        raise ValueError("Alte Konfiguration ist ungültig")
    payload = read_json(source / "data/accounts.enc.json", [])
    if isinstance(payload, list):
        return config, payload
    secret = password
    mode = config.get("master_password_mode", "password")
    cached = config.get("master_password_secret_b64")
    if secret is None and cached:
        expiry = config.get("master_password_secret_expires", 0) or 0
        if mode == "local" or not expiry or time.time() < float(expiry):
            raw = dpapi(base64.b64decode(cached, validate=True), decrypt=True)
            secret = raw if mode == "local" else raw.decode("utf-8")
    if secret is None and mode == "placeholder":
        secret = "0"  # Decode-only compatibility; never used for the new vault.
    if secret is None:
        raise PermissionError("Das bisherige Masterpasswort wird für die Übernahme benötigt.")
    if isinstance(secret, bytes):
        key = secret
    else:
        iterations = int(payload.get("iterations", 390000))
        if not 10000 <= iterations <= 2000000:
            raise ValueError("Unbekannte Legacy-KDF-Parameter")
        salt = base64.b64decode(payload["salt"], validate=True)
        key = base64.urlsafe_b64encode(
            PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(
                secret.encode("utf-8")
            )
        )
    accounts = json.loads(Fernet(key).decrypt(payload["data"].encode("ascii")))
    if not isinstance(accounts, list):
        raise ValueError("Ungültige alte Accountliste")
    return config, accounts


def number(value, name):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"Ungültiger historischer Statistikwert: {name}")
    return parsed


def migrate(store, vault, source: Path, password=None):
    if store.get("legacy_migrated", meta=True):
        return store.get("legacy_migrated", meta=True)
    config, accounts = decode_accounts(source, password)
    if store.query("SELECT id FROM accounts LIMIT 1"):
        raise ValueError("Das neue Profil enthält bereits Accounts. Kein automatisches Zusammenführen.")
    # Back up every source file used by the decoder, protected with the new vault.
    files = {}
    for rel in ("config.json", "data/accounts.enc.json", "data/activity_24h.json"):
        path = source / rel
        if path.exists():
            raw = path.read_bytes()
            files[rel] = {"sha256": hashlib.sha256(raw).hexdigest(), "data": b64(raw)}
    envelope = vault.encrypt({"files": files, "source": str(source)}, "legacy-backup")
    backup_dir = store.path.parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    destination = backup_dir / ("legacy-" + uuid.uuid4().hex + ".vault.json")
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(envelope)
        handle.flush()
        os.fsync(handle.fileno())
    report = {"accounts": len(accounts), "seconds": 0, "skipped_settings": [], "backup": destination.name}
    activity = read_json(source / "data/activity_24h.json", {})
    with store.transaction() as db:
        for index, old in enumerate(accounts):
            if not isinstance(old, dict) or old.get("region", "de") not in REGIONS:
                raise ValueError("Unbekannte Accountregion im Altprofil")
            total = number(old.get("total_playtime", 0), "total_playtime")
            count = number(old.get("sessions_count", 0), "sessions_count")
            if not count.is_integer():
                raise ValueError("Ungültige Sitzungsanzahl")
            ident = store.save_account(
                vault, old["name"], old["username"], old["password"], old.get("region", "de")
            )
            db.execute(
                "UPDATE accounts SET legacy_seconds=?,legacy_sessions=?,last_used=? WHERE id=?",
                (total, int(count), number(old.get("last_used", 0), "last_used"), ident),
            )
            report["seconds"] += total
        for key, value in config.items():
            if key in BY_KEY:
                try:
                    set_value(store, key, value)
                except (ValueError, TypeError):
                    report["skipped_settings"].append(key)
        # Compatibility aliases only when no explicit per-region value exists.
        for code, old_key in (("de", "default_install"), ("us", "default_install_us")):
            if not config.get("region_install_" + code) and config.get(old_key):
                store.set("region_install_" + code, config[old_key])
        if config.get("discord_webhook_url"):
            store.set(
                "discord_webhook", vault.encrypt(config["discord_webhook_url"], "discord-webhook"), meta=True
            )
        valid_intervals = activity.get("intervals", []) if isinstance(activity, dict) else []
        for pair in valid_intervals:
            if isinstance(pair, list) and len(pair) == 2:
                start, end = map(float, pair)
                if math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= time.time():
                    db.execute("INSERT INTO activity VALUES(?,?,?)", (str(uuid.uuid4()), start, end))
        # An unfinished legacy active_since is deliberately not extended to now.
        store.set("legacy_migrated", report, meta=True)
    return report
