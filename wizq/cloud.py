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
    CLOUD_DIRECTORY,
    FILE_ROOTS,
    CloudError,
    CloudFiles,
    CloudPending,
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
    accounts: int = 0
    prepared: bool = False
    pending_packets: int = 0
    waiting: str = ""


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

    def validate_folder(self, folder, *, require_directory=True):
        try:
            folder = Path(folder).resolve(strict=require_directory)
        except OSError as exc:
            raise CloudPending("Der gewählte Cloud-Ordner ist gerade nicht erreichbar.") from exc
        local = self.paths.root.resolve()
        if folder.is_relative_to(local) or local.is_relative_to(folder):
            raise CloudError("Wähle einen Cloud-Ordner außerhalb des lokalen Launcher-Profils.")
        if require_directory and not folder.is_dir():
            raise CloudError("Wähle einen synchronisierten Ordner aus.")
        return folder

    def selected_folder(self, folder, secret):
        folder = self.validate_folder(folder)
        if folder.name.casefold() == CLOUD_DIRECTORY.casefold():
            folder = folder.parent
        elif folder.parent.name.casefold() == CLOUD_DIRECTORY.casefold() and is_hex(folder.name.lower(), 32):
            if folder.name.lower() != CloudFiles.profile_id(secret):
                raise CloudError("Der Schlüssel gehört zu einem anderen Cloud-Profil.")
            folder = folder.parent.parent
        return self.validate_folder(folder)

    def connect(self, folder, code, *, create):
        with self.lock:
            vault = self.unlocked()
            if self.config():
                raise CloudError("Trenne zuerst die vorhandene Cloud-Verknüpfung.")
            secret = decode_code(code)
            folder = self.selected_folder(folder, secret)
            cloud = CloudFiles(folder, secret)
            if create and cloud.root.exists():
                raise CloudError("Für diesen Schlüssel existiert bereits ein Cloud-Profil.")
            namespace = folder / CLOUD_DIRECTORY
            if not create:
                self.check_profile_choice(namespace, cloud)
            config = {
                "folder": str(folder),
                "secret": vault.encrypt(b64(secret), META),
                "setup": "create" if create else "join",
            }
            self.store.set(META, config, meta=True)
            return self._sync_config(vault, cloud, config, settle=0)

    def check_profile_choice(self, namespace, cloud):
        try:
            if (
                namespace.is_dir()
                and not cloud.root.is_dir()
                and any(is_hex(path.name, 32) for path in namespace.iterdir())
            ):
                raise CloudError(
                    "Kein Profil für diesen Schlüssel gefunden. Ordner und Cloud-Schlüssel prüfen."
                )
        except OSError:
            # On-demand directories can come online after the pairing is saved.
            pass

    def relocate(self, folder):
        with self.lock:
            config = self.config()
            if not config:
                raise CloudError("Zuerst ein Cloud-Profil verbinden.")
            vault = self.unlocked()
            secret = unb64(vault.decrypt(config["secret"], META))
            folder = self.selected_folder(folder, secret)
            cloud = CloudFiles(folder, secret)
            config = {**config, "folder": str(folder)}
            self.check_profile_choice(folder / CLOUD_DIRECTORY, cloud)
            if config.get("setup") != "join" and not (cloud.root / "profile.wq").is_file():
                saved = self.store.get(CHECKPOINT, {}, meta=True)
                if saved.get("scope") == cloud.root.name + "/" + self.device_id():
                    config["setup"] = "create"
            self.store.set(META, config, meta=True)
            return self._sync_config(vault, cloud, config, settle=0)

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
            try:
                folder = self.validate_folder(config["folder"], require_directory=False)
            except CloudPending as exc:
                return SyncResult(0, 0, 0, 0, frozenset(), waiting=str(exc))
            cloud = CloudFiles(folder, unb64(vault.decrypt(config["secret"], META)))
            previous = self.file_blocked
            if profile_only:
                self.file_blocked = frozenset(FILE_ROOTS)
            try:
                return self._sync_config(vault, cloud, config, settle=settle)
            finally:
                self.file_blocked = previous

    def _sync_config(self, vault, cloud, config, *, settle):
        try:
            return self._sync(vault, cloud, config, settle=settle)
        except CloudPending as exc:
            return SyncResult(0, 0, 0, 0, frozenset(), waiting=str(exc))
        except OSError as exc:
            code = getattr(exc, "winerror", None)
            if isinstance(exc, PermissionError) or code in (5, 32, 33, 391, 397):
                message = "Cloud-Datei ist gesperrt oder der Ordner ist schreibgeschützt."
            elif code in (362, 369, 386, 388, 389, 393) or isinstance(exc, FileNotFoundError):
                message = "Der Cloud-Dienst stellt den Ordner oder die Datei gerade nicht bereit."
            else:
                message = "Der Cloud-Ordner konnte gerade nicht gelesen oder beschrieben werden."
            return SyncResult(0, 0, 0, 0, frozenset(), waiting=message)

    def scan(self, settle):
        files, pending, blocked = {}, set(), set(self.file_blocked)
        now = time.time()

        def unreadable(error):
            raise error

        for name in FILE_ROOTS:
            if name in self.file_blocked:
                continue
            directory = self.paths.root / name
            if linked(directory):
                blocked.add(name)
                pending.add("files/" + name + "/")
                continue
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
                    try:
                        safe_file(self.paths.root, key[6:])
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
                    except (OSError, CloudError):
                        pending.add(key)
        return files, pending, blocked

    def collect(self, cloud, device):
        packets, own, pending = [], None, 0
        for path in sorted(cloud.devices.glob("*.wq")):
            # The filename may be changed by a sync provider creating a conflict copy.
            ident = path.stem[:32]
            if not is_hex(ident, 32) or linked(path):
                continue
            try:
                packet = cloud.read_packet(path, "device/" + ident)
            except (OSError, CloudError):
                pending += 1
                continue
            validate_packet(packet, ident)
            packets.append(packet)
            if path.stem == device:
                own = packet
        return packets, own, pending

    def _sync(self, vault, cloud, config, *, settle):
        setup = config.get("setup")
        marker = cloud.root / "profile.wq"
        if linked(marker):
            raise CloudError("Die Cloud-Profilkennung verweist auf eine andere Datei.")
        try:
            with marker.open("rb") as handle:
                marker_data = handle.read(len(MARKER) + 1)
        except FileNotFoundError as exc:
            if not Path(config["folder"]).is_dir():
                raise CloudPending("Der gewählte Cloud-Ordner ist gerade nicht erreichbar.") from exc
            if setup == "create":
                with atomic_output(marker) as output:
                    output.write(MARKER)
                marker_data = MARKER
            else:
                raise CloudPending(
                    "Warte auf das Cloud-Profil. Prüfe den gewählten Ordner und den Upload."
                ) from exc
        if marker_data != MARKER:
            if MARKER.startswith(marker_data):
                raise CloudPending("Der Cloud-Dienst lädt die Profilkennung noch.")
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
        packets, own, pending_packets = self.collect(cloud, device)
        if setup == "join" and not packets:
            raise CloudPending("Warte auf den ersten gültigen Profilstand vom Cloud-Dienst.")
        if not packets and pending_packets and not state and setup != "create":
            raise CloudPending("Der Cloud-Dienst stellt den Profilstand gerade nicht vollständig bereit.")
        clock = max([state.get("clock", 0), *(packet["clock"] for packet in packets)])
        if clock >= 2**63 - 2:
            raise CloudError("Der Versionszähler im Cloud-Profil ist ungültig.")
        effective = dict(base)
        for packet in packets:
            for key, record in packet["records"].items():
                effective[key] = combine(effective.get(key), record)
        with self.store.lock:
            local = profile_records(self.store, vault)
        try:
            local_files, pending, blocked = self.scan(settle)
        except OSError:
            local_files, pending, blocked = {}, {"files/"}, frozenset(FILE_ROOTS)
        blocked_prefixes = tuple(f"files/{name}/" for name in blocked)
        current = {**local, **local_files}
        revision = [clock + 1, device]
        uploaded, edits = 0, False
        uploads = {}
        for key in sorted(current.keys() | base.keys()):
            if key in pending or key.startswith(blocked_prefixes):
                continue
            if setup == "join" and key not in base and key in effective:
                continue
            value = current.get(key)
            old, incoming = value_of(key, base.get(key)), value_of(key, effective.get(key))
            edited = (
                value != old and value != incoming and (value is not None or not key.startswith("activity/"))
            )
            if key in local_files:
                if edited or value == incoming:
                    uploads[key] = edited, value
                continue
            if edited:
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
        file_keys = {key for key in effective.keys() | base.keys() if key.startswith("files/")}
        deferred = pending | {key for key in file_keys if key.startswith(blocked_prefixes)}
        backups = self.paths.directory("backups") / "cloud"
        with self.store.lock:
            current = profile_records(self.store, vault)
            profile = {key: value for key, value in desired.items() if not key.startswith("files/")}
            later = {key for key in current.keys() | local.keys() if current.get(key) != local.get(key)}
            for key in later:
                if key in current:
                    profile[key] = current[key]
                else:
                    profile.pop(key, None)
            # Apply account data before restoring recordings and other large files.
            interim = self.checkpoint(effective, base, file_keys | later, clock)
            applied = apply_profile(
                self.store,
                vault,
                current,
                profile,
                backups,
                self.sealed_checkpoint(cloud, scope, state, interim),
            )

        def publish(previous):
            doc = {
                "format": 1,
                "schema": SCHEMA,
                "device": device,
                "clock": clock,
                "records": dict(effective),
            }
            if doc != previous:
                try:
                    cloud.write_packet(cloud.devices / (device + ".wq"), "device/" + device, doc)
                except OSError:
                    return (
                        previous,
                        "Profil lokal gespeichert. Der Cloud-Ordner nimmt den Profilstand gerade nicht an.",
                    )
            return doc, ""

        published, waiting = publish(own)
        media_edits = False
        for key, (edited, value) in uploads.items():
            try:
                if edited or not cloud.has_object(value):
                    cloud.put(safe_file(self.paths.root, key[6:]), value)
                    uploaded += 1
            except (OSError, CloudError):
                deferred.add(key)
                continue
            if edited:
                effective[key] = combine(effective.get(key), revise(key, base.get(key), value, revision))
                replacement = value_of(key, effective[key])
                if replacement is not None:
                    desired[key] = replacement
                media_edits = True
        if media_edits or waiting and uploaded:
            if media_edits:
                clock = revision[0]
            published, waiting = publish(published)
        downloaded, applied_files, later_files = self.apply_files(
            cloud, local_files, desired, deferred, backups
        )
        applied.update(applied_files)
        with self.store.lock:
            final = self.checkpoint(effective, base, deferred | later | later_files, clock)
            saved = self.sealed_checkpoint(cloud, scope, interim, final)
            if saved is not None:
                self.store.set(CHECKPOINT, saved, meta=True)
            if setup:
                self.store.set(META, {"folder": config["folder"], "secret": config["secret"]}, meta=True)
        devices = {device, *(packet["device"] for packet in packets)}
        return SyncResult(
            len(devices),
            uploaded,
            downloaded,
            len(deferred | later_files),
            frozenset(applied),
            accounts=sum(key.startswith("accounts/") for key in desired),
            prepared=published != own and not waiting,
            pending_packets=pending_packets,
            waiting=waiting,
        )

    @staticmethod
    def checkpoint(effective, base, deferred, clock):
        records = {key: value for key, value in effective.items() if key not in deferred}
        records.update({key: base[key] for key in deferred & base.keys()})
        return {"clock": clock, "records": records}

    @staticmethod
    def sealed_checkpoint(cloud, scope, previous, checkpoint):
        if checkpoint == previous:
            return None
        sealed = cloud.encode_packet(checkpoint, "local/" + scope)
        return {"scope": scope, "packet": b64(sealed)}

    def apply_files(self, cloud, local_files, desired, deferred, backups):
        files = {key: value for key, value in desired.items() if key.startswith("files/")}
        all_names = local_files.keys() | files.keys()
        counts = {}
        for key in all_names:
            counts[key.casefold()] = counts.get(key.casefold(), 0) + 1
        deferred.update(key for key in all_names if counts[key.casefold()] > 1)
        changes = {
            key: files.get(key)
            for key in local_files.keys() | files.keys()
            if key not in deferred and local_files.get(key) != files.get(key)
        }
        if not changes:
            return 0, set(), set()
        later, applied = set(), set()
        downloaded = 0
        for key, value in changes.items():
            try:
                with tempfile.TemporaryDirectory(
                    prefix="cloud-", dir=self.paths.directory("cache")
                ) as temporary:
                    path = safe_file(self.paths.root, key[6:])
                    if path.exists() and not path.is_file():
                        later.add(key)
                        continue
                    if value is not None:
                        downloaded_file = Path(temporary) / "download"
                        cloud.get(value, downloaded_file)
                    path = safe_file(self.paths.root, key[6:])
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
                        os.replace(downloaded_file, path)
                        self.hashes[path] = file_stamp(path), value
                        downloaded += 1
                    applied.add(key)
            except (OSError, CloudError):
                later.add(key)
        return downloaded, applied, later
