"""Synchronize portable launcher data in a user-owned cloud folder."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .cloud_files import (
    FILE_ROOTS,
    CloudError,
    CloudFiles,
    atomic_output,
    file_stamp,
    is_hex,
    linked,
    safe_file,
)
from .cloud_merge import combine, revise, validate_packet, value_of
from .cloud_profile import CHECKPOINT, apply_profile, profile_records
from .storage import SCHEMA
from .vault import Vault, b64, unb64

META = "cloud_sync"
MARKER = b"WizQ Cloud 1\n"
SETTLE_SECONDS = 8


@dataclass(frozen=True)
class SyncResult:
    devices: int
    uploaded: int
    downloaded: int
    pending: int
    changed: frozenset[str]


def new_code():
    return secrets.token_hex(32)


def decode_code(code):
    normalized = "".join(code.split()).replace("-", "").lower()
    if not is_hex(normalized, 64):
        raise CloudError("Der Cloud-Schlüssel besteht aus 64 Hex-Zeichen.")
    return bytes.fromhex(normalized)


class CloudSync:
    def __init__(self, paths, store, vault):
        self.paths, self.store, self.vault = paths, store, vault
        self.lock = threading.Lock()
        self.hashes = {}
        self.file_blocked = frozenset()
        # A database restored on another PC still has a separate writer identity.
        self.identity_file = paths.directory("data") / "cloud-device-id"

    def config(self):
        return self.store.get(META, meta=True)

    def device_id(self):
        if self.identity_file.is_file():
            ident = self.identity_file.read_text(encoding="ascii").strip()
            if not is_hex(ident, 32):
                raise CloudError("Die lokale Cloud-Geräte-ID ist beschädigt.")
            return ident
        ident = secrets.token_hex(16)
        with atomic_output(self.identity_file) as handle:
            handle.write(ident.encode("ascii"))
        return ident

    def unlocked(self):
        key = self.vault.key
        if key is None:
            raise CloudError("Entsperre den Tresor für den Cloud-Abgleich.")
        vault = Vault(self.store)
        vault.key = key
        return vault

    def validate_folder(self, folder):
        try:
            folder = Path(folder).resolve(strict=True)
        except FileNotFoundError as exc:
            raise CloudError("Der gewählte Cloud-Ordner ist gerade nicht erreichbar.") from exc
        local = self.paths.root.resolve()
        if not folder.is_dir() or folder.is_relative_to(local) or local.is_relative_to(folder):
            raise CloudError("Wähle einen Cloud-Ordner außerhalb des lokalen Launcher-Profils.")
        return folder

    def connect(self, folder, code, *, create):
        with self.lock:
            vault = self.unlocked()
            if self.config():
                raise CloudError("Trenne zuerst die vorhandene Cloud-Verknüpfung.")
            folder = self.validate_folder(folder)
            secret = decode_code(code)
            cloud = CloudFiles(folder, secret)
            marker = cloud.root / "profile.wq"
            if create:
                if marker.exists() and cloud.devices.exists():
                    raise CloudError("Für diesen Schlüssel existiert bereits ein Cloud-Profil.")
                with atomic_output(marker) as output:
                    output.write(MARKER)
            elif not marker.is_file():
                raise CloudError("Profil fehlt im gewählten Ordner. Prüfe Schlüssel und Cloud-Download.")
            config = {"folder": str(folder), "secret": vault.encrypt(b64(secret), META)}
            self.store.set(META, config, meta=True)
            try:
                return self._sync(vault, cloud, joining=not create)
            except Exception:
                self.store.set(META, None, meta=True)
                raise

    def code(self):
        config = self.config()
        if not config:
            raise CloudError("Zuerst ein Cloud-Profil verbinden.")
        return unb64(self.unlocked().decrypt(config["secret"], META)).hex()

    def disconnect(self):
        with self.lock:
            self.store.set(META, None, meta=True)
            self.hashes.clear()

    def sync(self, *, settle=SETTLE_SECONDS, profile_only=False):
        with self.lock:
            config = self.config()
            if not config:
                raise CloudError("Zuerst ein Cloud-Profil verbinden.")
            vault = self.unlocked()
            cloud = CloudFiles(
                self.validate_folder(config["folder"]), unb64(vault.decrypt(config["secret"], META))
            )
            previous = self.file_blocked
            if profile_only:
                self.file_blocked = frozenset(FILE_ROOTS)
            try:
                return self._sync(vault, cloud, settle=settle)
            finally:
                self.file_blocked = previous

    def scan(self, settle):
        files, pending = {}, set()
        now = time.time()

        def unreadable(error):
            raise error

        for name in FILE_ROOTS:
            if name in self.file_blocked:
                continue
            directory = self.paths.root / name
            if linked(directory):
                raise CloudError("Ein Profilordner verweist auf einen anderen Ordner.")
            if not directory.is_dir():
                continue
            for root, dirs, names in os.walk(directory, onerror=unreadable):
                root = Path(root)
                dirs[:] = [d for d in dirs if d != "__pycache__" and not linked(root / d)]
                for filename in names:
                    if filename.startswith((".wizq-part-", ".pending-")) or filename.endswith(
                        (".pyc", ".part")
                    ):
                        continue
                    path = root / filename
                    if linked(path) or not path.is_file():
                        continue
                    key = "files/" + path.relative_to(self.paths.root).as_posix()
                    safe_file(self.paths.root, key[6:])
                    try:
                        before = file_stamp(path)
                        cached = self.hashes.get(path)
                        if cached and cached[0] == before:
                            files[key] = cached[1]
                            continue
                        if now - before[3] / 1e9 < settle:
                            pending.add(key)
                            continue
                        with path.open("rb") as handle:
                            sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
                        if before != file_stamp(path):
                            pending.add(key)
                            continue
                        files[key] = {"sha256": sha256, "size": before[2]}
                        self.hashes[path] = before, files[key]
                    except (FileNotFoundError, PermissionError):
                        pending.add(key)
        return files, pending

    def blocked(self, key):
        return any(key.startswith("files/" + name + "/") for name in self.file_blocked)

    def collect(self, cloud, device):
        packets, own = [], None
        for path in sorted(cloud.devices.glob("*.wq")):
            # The filename may be changed by a sync provider creating a conflict copy.
            ident = path.stem[:32]
            if not is_hex(ident, 32) or not path.is_file() or linked(path):
                continue
            packet = cloud.read_packet(path, "device/" + ident)
            validate_packet(packet, ident)
            packets.append(packet)
            if path.stem == device:
                own = packet
        return packets, own

    def _sync(self, vault, cloud, *, joining=False, settle=SETTLE_SECONDS):
        marker = cloud.root / "profile.wq"
        if not marker.is_file() or linked(marker):
            raise CloudError("Das Cloud-Profil ist gerade offline.")
        with marker.open("rb") as handle:
            if handle.read(len(MARKER) + 1) != MARKER:
                raise CloudError("Dieses Cloud-Profil verwendet ein anderes Format.")
        device = self.device_id()
        scope = cloud.root.name + "/" + device
        saved = self.store.get(CHECKPOINT, {}, meta=True)
        state = (
            cloud.decode_packet(unb64(saved["packet"]), "local/" + scope)
            if saved.get("scope") == scope
            else {}
        )
        base = state.get("records", {})
        packets, own = self.collect(cloud, device)
        if joining and not packets:
            raise CloudError("Der erste Profilstand wird noch vom Cloud-Dienst übertragen.")
        clock = max([state.get("clock", 0), *(packet["clock"] for packet in packets)])
        if clock >= 2**63 - 2:
            raise CloudError("Der Versionszähler im Cloud-Profil ist ungültig.")
        effective = dict(base)
        for packet in packets:
            for key, record in packet["records"].items():
                effective[key] = combine(effective.get(key), record)
        with self.store.lock:
            local = profile_records(self.store, vault)
        local_files, pending = self.scan(settle)
        current = {**local, **local_files}
        revision = [clock + 1, device]
        uploaded, edits = 0, False
        for key in sorted(current.keys() | base.keys()):
            if key in pending or self.blocked(key):
                continue
            if joining and key not in base and key in effective:
                continue
            value = current.get(key)
            if value == value_of(key, base.get(key)) or value == value_of(key, effective.get(key)):
                continue
            if key.startswith("activity/") and value is None:
                continue
            if key.startswith("files/") and value is not None:
                cloud.put(safe_file(self.paths.root, key[6:]), value)
                uploaded += 1
            effective[key] = combine(effective.get(key), revise(key, base.get(key), value, revision))
            edits = True
        if edits:
            clock += 1
        cutoff = time.time() - 172800
        effective = {
            key: record
            for key, record in effective.items()
            if not key.startswith("activity/") or (value_of(key, record) or {}).get("ended", 0) >= cutoff
        }
        desired = {
            key: value for key, record in effective.items() if (value := value_of(key, record)) is not None
        }
        deferred = pending | {key for key in effective.keys() | base.keys() if self.blocked(key)}
        backups = self.paths.directory("backups") / "cloud"
        downloaded, applied, later = self.apply_files(cloud, local_files, desired, deferred, backups)
        with self.store.lock:
            current = profile_records(self.store, vault)
            profile = {key: value for key, value in desired.items() if not key.startswith("files/")}
            for key in current.keys() | local.keys():
                if current.get(key) != local.get(key):
                    later.add(key)
                    if key in current:
                        profile[key] = current[key]
                    else:
                        profile.pop(key, None)
            checkpoint = dict(effective)
            for key in deferred | later:
                checkpoint.pop(key, None)
                if key in base:
                    checkpoint[key] = base[key]
            checkpoint_doc = {"clock": clock, "records": checkpoint}
            saved = None
            if checkpoint_doc != state:
                sealed = cloud.encode_packet(checkpoint_doc, "local/" + scope)
                saved = {"scope": scope, "packet": b64(sealed)}
            applied.update(apply_profile(self.store, vault, current, profile, backups, saved))
        doc = {"format": 1, "schema": SCHEMA, "device": device, "clock": clock, "records": effective}
        if doc != own:
            cloud.write_packet(cloud.devices / (device + ".wq"), "device/" + device, doc)
        devices = {device, *(packet["device"] for packet in packets)}
        return SyncResult(
            len(devices),
            uploaded,
            downloaded,
            sum(key.startswith("files/") for key in deferred | later),
            frozenset(applied),
        )

    def apply_files(self, cloud, local_files, desired, deferred, backups):
        files = {key: value for key, value in desired.items() if key.startswith("files/")}
        all_names = local_files.keys() | files.keys()
        if len({key.casefold() for key in all_names}) != len(all_names):
            raise CloudError("Zwei Cloud-Dateien haben unter Windows denselben Namen.")
        changes = {
            key: files.get(key)
            for key in local_files.keys() | files.keys()
            if key not in deferred and local_files.get(key) != files.get(key)
        }
        if not changes:
            return 0, set(), set()
        later, applied = set(), set()
        with tempfile.TemporaryDirectory(prefix="cloud-", dir=self.paths.directory("cache")) as temporary:
            staged = {}
            for index, (key, value) in enumerate(changes.items()):
                path = safe_file(self.paths.root, key[6:])
                if path.exists() and not path.is_file():
                    raise CloudError("Ein Cloud-Dateiname ist auf diesem PC bereits ein Ordner.")
                if value is not None:
                    target = Path(temporary) / str(index)
                    try:
                        cloud.get(value, target)
                    except (FileNotFoundError, CloudError):
                        later.add(key)
                    else:
                        staged[key] = target
            for key, value in changes.items():
                if key in later:
                    continue
                path = safe_file(self.paths.root, key[6:])
                try:
                    if path.exists() != (key in local_files):
                        later.add(key)
                        continue
                    if key in local_files:
                        old = self.hashes[path]
                        if file_stamp(path) != old[0]:
                            later.add(key)
                            continue
                        backup = backups / "files" / local_files[key]["sha256"] / key[6:]
                        if not backup.exists():
                            with path.open("rb") as source, atomic_output(backup) as target:
                                shutil.copyfileobj(source, target)
                            if file_stamp(path) != old[0]:
                                later.add(key)
                                continue
                    if value is None:
                        path.unlink(missing_ok=True)
                        self.hashes.pop(path, None)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(staged[key], path)
                        self.hashes[path] = file_stamp(path), value
                    applied.add(key)
                except (FileNotFoundError, PermissionError):
                    later.add(key)
        return len(staged.keys() - later), applied, later
