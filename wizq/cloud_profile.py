"""Project the local SQLite profile into portable records and apply changes in a transaction."""

from __future__ import annotations

import json
import time

from .settings import BY_KEY, REGIONS, set_value
from .storage import STEAM_ACCOUNT_PREFIX

CHECKPOINT = "cloud_checkpoint"
LOCAL_SETTINGS = {
    "addon:cloud-sync",
    "borderless",
    "capture_audio_device",
    "ffmpeg_path",
    "launch_split",
    "desktop_split",
    "window_size",
    "window_account_links",
    "window_originals",
    "window_undo",
    "tutorial_seen",
}
NAMED_SETTINGS = {"launch_profiles", "window_profiles", "window_placements"}
COLUMNS = {
    "groups": ("name", "position"),
    "accounts": (
        "nickname",
        "region",
        "group_id",
        "position",
        "favorite",
        "legacy_seconds",
        "legacy_sessions",
    ),
    "sessions": ("account_id", "region", "started", "seen", "elapsed", "ended"),
    "activity": ("started", "ended"),
}


def portable_setting(key):
    return key not in LOCAL_SETTINGS and not key.startswith(("region_install_", "cloud_"))


def profile_records(store, vault):
    result = {}
    for row in store.query("SELECT key,value FROM settings"):
        key = row["key"]
        if portable_setting(key):
            value = json.loads(row["value"])
            if key in NAMED_SETTINGS:
                result.update({f"{key}/{name}": {"value": item} for name, item in value.items()})
            else:
                result["settings/" + key] = {"value": value}
    if "settings/window_mode" not in result and store.get("borderless") is not None:
        result["settings/window_mode"] = {"value": "borderless" if store.get("borderless") else "windowed"}
    for table, fields in COLUMNS.items():
        query = "SELECT * FROM " + table
        args = ()
        if table == "activity":
            query += " WHERE ended >= ?"
            args = (time.time() - 172800,)
        for row in store.query(query, args):
            ident = row["id"]
            record = {field: row[field] for field in fields}
            if table == "accounts":
                # Keep frequently changing playtime metadata separate from credentials.
                record["credentials"] = vault.decrypt(row["credentials"], ident)
                result["recent/" + ident] = {"value": row["last_used"]}
            if table == "sessions" and record["ended"] is None:
                record["ended"] = record["seen"]
            result[table + "/" + ident] = record
    webhook = store.get("discord_webhook", meta=True)
    if webhook:
        result["meta/discord_webhook"] = {"value": vault.decrypt(webhook, "discord-webhook")}
    return result


def apply_profile(store, vault, current, desired, backups, checkpoint):
    # Foreign keys are enforced locally even when the group/account was removed
    # on another device while a different device edited the referencing record.
    desired = dict(desired)
    for key, value in tuple(desired.items()):
        if key.startswith("settings/" + STEAM_ACCOUNT_PREFIX):
            ident = key.removeprefix("settings/" + STEAM_ACCOUNT_PREFIX)
            if "accounts/" + ident not in desired:
                desired.pop(key)
        if key.startswith("accounts/") and "groups/" + str(value["group_id"]) not in desired:
            desired[key] = {**value, "group_id": None}
        if key.startswith("sessions/") and "accounts/" + str(value["account_id"]) not in desired:
            desired[key] = {**value, "account_id": None}
        if key.startswith("recent/") and "accounts/" + key.split("/", 1)[1] not in desired:
            desired.pop(key)
    changes = {
        key: desired.get(key)
        for key in current.keys() | desired.keys()
        if current.get(key) != desired.get(key)
    }
    if not changes and checkpoint is None:
        return set()
    if any(
        key in current and key.split("/", 1)[0] in {"accounts", "groups", "settings", "meta", *NAMED_SETTINGS}
        for key in changes
    ):
        store.backup(backups, keep=5)
    with store.transaction() as db:
        for table in ("activity", "sessions", "accounts", "groups"):
            for key, value in changes.items():
                if key.startswith(table + "/") and value is None:
                    condition = " AND ended IS NOT NULL" if table == "sessions" else ""
                    db.execute(f"DELETE FROM {table} WHERE id=?{condition}", (key.split("/", 1)[1],))
        for table, fields in COLUMNS.items():
            for key, value in changes.items():
                if not key.startswith(table + "/") or value is None:
                    continue
                ident = key.split("/", 1)[1]
                row = {field: value[field] for field in fields}
                if table == "accounts":
                    if row["region"] not in REGIONS:
                        raise ValueError("Ungültige Accountregion im Cloud-Profil.")
                    row["credentials"] = vault.encrypt(value["credentials"], ident)
                columns = ("id", *row)
                values = (ident, *row.values())
                if table == "sessions":
                    # Imported history has no local process or HWND. Live rows
                    # keep their existing process state and remain open locally.
                    columns += ("pid", "created")
                    values += (0, 0)
                assignments = [
                    "ended=CASE WHEN sessions.ended IS NULL THEN NULL ELSE excluded.ended END"
                    if table == "sessions" and field == "ended"
                    else f"{field}=excluded.{field}"
                    for field in row
                ]
                placeholders = ",".join("?" for _ in columns)
                db.execute(
                    f"INSERT INTO {table}({','.join(columns)}) VALUES ({placeholders}) "
                    f"ON CONFLICT(id) DO UPDATE SET {','.join(assignments)}",
                    values,
                )
        named = {}
        for key, value in changes.items():
            kind, _, ident = key.partition("/")
            if kind == "settings" and portable_setting(ident):
                if value is None:
                    db.execute("DELETE FROM settings WHERE key=?", (ident,))
                    if ident == "window_mode":
                        db.execute("DELETE FROM settings WHERE key='borderless'")
                elif ident in BY_KEY:
                    set_value(store, ident, value["value"])
                else:
                    store.set(ident, value["value"])
            if kind in NAMED_SETTINGS:
                if kind not in named:
                    named[kind] = store.get(kind, {})
                if value is None:
                    named[kind].pop(ident, None)
                else:
                    named[kind][ident] = value["value"]
            if kind == "recent" and value is not None:
                db.execute("UPDATE accounts SET last_used=? WHERE id=?", (value["value"], ident))
            if key == "meta/discord_webhook":
                secret = vault.encrypt(value["value"], "discord-webhook") if value is not None else None
                store.set("discord_webhook", secret, meta=True)
        for key, value in named.items():
            store.set(key, value)
        if checkpoint is not None:
            store.set(CHECKPOINT, checkpoint, meta=True)
    return set(changes)
