"""Merge versioned fields without re-stamping changes received from another device."""

from .cloud_files import CloudError, is_hex
from .cloud_profile import COLUMNS, NAMED_SETTINGS, portable_setting
from .storage import SCHEMA


def stamp(register):
    return register[0], register[1]


def fields(key, value):
    if key.startswith(("accounts/", "groups/")):
        return value
    return {"value": value}


def value_of(key, record):
    if record is None or not record["exists"][2]:
        return None
    value = {field: cell[2] for field, cell in record["fields"].items()}
    if key.startswith(("accounts/", "groups/")):
        return value
    return value["value"]


def revise(key, record, value, revision):
    previous = value_of(key, record)
    if value is None:
        return {"exists": [*revision, False], "fields": {}}
    if previous is None:
        return {
            "exists": [*revision, True],
            "fields": {name: [*revision, item] for name, item in fields(key, value).items()},
        }
    old, new = fields(key, previous), fields(key, value)
    edited = dict(record["fields"])
    for field, item in new.items():
        if old[field] != item:
            edited[field] = [*revision, item]
    return {"exists": record["exists"], "fields": edited}


def combine(left, right):
    if left is None or left == right:
        return right
    before, after = stamp(left["exists"]), stamp(right["exists"])
    if before != after:
        # A deletion or recreation takes precedence over edits to the old row.
        return left if before > after else right
    result = dict(left["fields"])
    for name, cell in right["fields"].items():
        if name not in result or stamp(cell) > stamp(result[name]):
            result[name] = cell
    return {"exists": left["exists"], "fields": result}


def validate_packet(packet, device):
    if not isinstance(packet, dict) or packet.get("format") != 1 or packet.get("device") != device:
        raise CloudError("Dieser Cloud-Stand verwendet ein anderes Format.")
    records, clock = packet.get("records"), packet.get("clock")
    if (
        packet.get("schema") != SCHEMA
        or not isinstance(records, dict)
        or len(records) > 750_000
        or type(clock) is not int
        or not 0 <= clock < 2**63 - 1
    ):
        raise CloudError("Dieser Cloud-Stand benötigt ein kompatibles Launcher-Profil.")
    for key, record in records.items():
        kind, sep, ident = key.partition("/")
        if not sep or not ident or len(key) > 1100 or not isinstance(record, dict):
            raise CloudError("Ungültiger Datensatz im Cloud-Profil.")
        if not (
            kind in COLUMNS
            or kind in ("recent", "files")
            or kind in NAMED_SETTINGS
            or kind == "settings"
            and portable_setting(ident)
            and ident not in NAMED_SETTINGS
            or key == "meta/discord_webhook"
        ):
            raise CloudError("Unbekannter Datensatz im Cloud-Profil.")
        exists, cells = record.get("exists"), record.get("fields")
        validate_cell(exists, clock)
        if type(exists[2]) is not bool or not isinstance(cells, dict) or (not exists[2] and cells):
            raise CloudError("Ungültiger Versionsstand im Cloud-Profil.")
        for cell in cells.values():
            validate_cell(cell, clock)
            if stamp(cell) < stamp(exists):
                raise CloudError("Ungültiger Versionsstand im Cloud-Profil.")
        if exists[2]:
            try:
                value = value_of(key, record)
                if not isinstance(value, dict):
                    raise ValueError
                if kind in COLUMNS and not set(COLUMNS[kind]).issubset(value):
                    raise ValueError
                if kind == "accounts":
                    credentials = value.get("credentials")
                    if not isinstance(credentials, dict) or set(credentials) != {"username", "password"}:
                        raise ValueError
                    if not all(isinstance(item, str) for item in credentials.values()):
                        raise ValueError
                if kind in {"settings", "recent", "meta", *NAMED_SETTINGS} and set(value) != {"value"}:
                    raise ValueError
                if kind == "files" and (
                    set(value) != {"sha256", "size"}
                    or not is_hex(value["sha256"], 64)
                    or type(value["size"]) is not int
                    or value["size"] < 0
                ):
                    raise ValueError
            except (KeyError, ValueError) as exc:
                raise CloudError("Ungültiger Inhalt im Cloud-Profil.") from exc


def validate_cell(cell, clock):
    if (
        not isinstance(cell, list)
        or len(cell) != 3
        or type(cell[0]) is not int
        or not 0 < cell[0] <= clock
        or not is_hex(cell[1], 32)
    ):
        raise CloudError("Ungültige Änderungsversion im Cloud-Profil.")
