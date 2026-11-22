"""Account launch methods with portable definitions and per-PC client paths."""

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from .game_install import CLIENT
from .settings import REGIONS

LAUNCH_METHOD_PREFIX = "launch_method:"
LAUNCH_METHOD_PATH_PREFIX = "launch_method_path:"
ACCOUNT_LAUNCH_METHOD_PREFIX = "launch_method_account:"
MODE_NAMES = {False: "Direkt (Wiz Q)", True: "Steam-Direktstart"}


@dataclass(frozen=True)
class LaunchMethod:
    id: str
    name: str
    region: str
    steam: bool


def read_method(method_id, value):
    if (
        isinstance(value, dict)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("region"), str)
        and value["region"] in REGIONS
        and type(value.get("steam")) is bool
    ):
        return LaunchMethod(method_id, value["name"], value["region"], value["steam"])
    return None


def launch_method(store, method_id):
    return read_method(method_id, store.get(LAUNCH_METHOD_PREFIX + method_id))


def launch_methods(store):
    records = store.query("SELECT key,value FROM settings WHERE key GLOB ?", (LAUNCH_METHOD_PREFIX + "*",))
    methods = {}
    for record in records:
        method_id = record["key"].removeprefix(LAUNCH_METHOD_PREFIX)
        method = read_method(method_id, json.loads(record["value"]))
        if method:
            methods[method_id] = method
    return methods


def client_path(value):
    path = Path(os.path.expandvars(value.strip().strip('"')))
    if not path.is_absolute() or path.name.casefold() != CLIENT.name.casefold():
        raise ValueError(f"Wähle den vollständigen Pfad zu {CLIENT.name}.")
    return path


def save_launch_method(store, name, region, steam, client, *, method_id=None):
    name = name.strip()
    if not name:
        raise ValueError("Gib der Startmethode einen Namen.")
    if region not in REGIONS:
        raise ValueError("Wähle ein gültiges Serverprofil.")
    path = str(client_path(client)) if client.strip() else ""
    with store.transaction() as db:
        methods = launch_methods(store)
        if method_id is not None and method_id not in methods:
            raise ValueError("Diese Startmethode ist nicht mehr vorhanden.")
        names = [*MODE_NAMES.values(), *(m.name for m in methods.values() if m.id != method_id)]
        if any(name.casefold() == existing.casefold() for existing in names):
            raise ValueError("Dieser Name wird bereits verwendet.")
        method_id = method_id or str(uuid.uuid4())
        store.set(LAUNCH_METHOD_PREFIX + method_id, {"name": name, "region": region, "steam": bool(steam)})
        path_key = LAUNCH_METHOD_PATH_PREFIX + method_id
        if path:
            store.set(path_key, path)
        else:
            db.execute("DELETE FROM settings WHERE key=?", (path_key,))
    return method_id


def delete_launch_method(store, method_id):
    with store.transaction() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM accounts a JOIN settings s ON s.key=?||a.id WHERE s.value=?",
            (ACCOUNT_LAUNCH_METHOD_PREFIX, json.dumps(method_id)),
        ).fetchone()[0]
        if count:
            raise ValueError(f"Ordne den verknüpften Accounts zuerst eine andere Startmethode zu ({count}).")
        db.execute(
            "DELETE FROM settings WHERE key IN (?,?)",
            (LAUNCH_METHOD_PREFIX + method_id, LAUNCH_METHOD_PATH_PREFIX + method_id),
        )
