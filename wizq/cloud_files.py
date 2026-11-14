"""Authenticated profile packets and streaming objects in a synced folder."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CHUNK = 1024 * 1024
PACKET_LIMIT = 64 * CHUNK
FILE_ROOTS = ("themes", "addons", "recordings")
HEX = re.compile(r"[a-f0-9]+\Z")
INVALID_NAME = re.compile(r'[<>:"\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    family + index for family in ("COM", "LPT") for index in "123456789¹²³"
}


class CloudError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def is_hex(value, size):
    return isinstance(value, str) and len(value) == size and HEX.fullmatch(value) is not None


@contextmanager
def atomic_output(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".wizq-part-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            yield file
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def safe_file(root, name):
    if not isinstance(name, str) or len(name) > 1000:
        raise CloudError("Ungültiger Dateiname im Cloud-Profil.")
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or parts[0] not in FILE_ROOTS or "/".join(parts) != name:
        raise CloudError("Ungültiger Dateipfad im Cloud-Profil.")
    path = root
    for part in parts:
        if (
            part in (".", "..")
            or len(part) > 240
            or INVALID_NAME.search(part)
            or part.endswith((".", " "))
            or part.split(".", 1)[0].upper() in RESERVED
        ):
            raise CloudError("Ungültiger Dateipfad im Cloud-Profil.")
        path /= part
        if linked(path):
            raise CloudError("Ein Profilpfad verweist über einen Link auf einen anderen Ordner.")
    return path


def file_stamp(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class CloudFiles:
    """The cloud service receives ciphertext, random device names and keyed object IDs."""

    def __init__(self, folder, secret):
        self.root = folder / "WizQ Cloud" / hmac.digest(secret, b"profile/v1", "sha256").hex()[:32]
        self.packet_key = AESGCM(hmac.digest(secret, b"packets/v1", "sha256"))
        self.object_key = hmac.digest(secret, b"objects/v1", "sha256")
        self.name_key = hmac.digest(secret, b"names/v1", "sha256")
        self.devices = self.root / "devices"
        self.objects = self.root / "objects"
        if any(linked(path) for path in (self.root.parent, self.root, self.devices, self.objects)):
            raise CloudError("Der Cloud-Profilordner verweist über einen Link auf einen anderen Ordner.")

    def read_packet(self, path, purpose):
        with path.open("rb") as handle:
            return self.decode_packet(handle.read(PACKET_LIMIT + 29), purpose)

    def decode_packet(self, data, purpose):
        try:
            if len(data) > PACKET_LIMIT + 28:
                raise CloudError("Der Cloud-Profilstand ist zu groß.")
            clear = self.packet_key.decrypt(data[:12], data[12:], purpose.encode())
            return json.loads(clear)
        except (InvalidTag, ValueError, RecursionError) as exc:
            raise CloudError("Ein Cloud-Profilstand konnte nicht entschlüsselt oder geprüft werden.") from exc

    def write_packet(self, path, purpose, data):
        packet = self.encode_packet(data, purpose)
        with atomic_output(path) as handle:
            handle.write(packet)

    def encode_packet(self, data, purpose):
        payload = encoded(data)
        if len(payload) > PACKET_LIMIT:
            raise CloudError("Der Cloud-Profilstand ist zu groß.")
        nonce = os.urandom(12)
        return nonce + self.packet_key.encrypt(nonce, payload, purpose.encode())

    def object_path(self, sha256):
        if not is_hex(sha256, 64):
            raise CloudError("Ungültige Dateiprüfsumme im Cloud-Profil.")
        ident = hmac.digest(self.name_key, bytes.fromhex(sha256), "sha256").hex()
        return self.objects / (ident + ".wqo")

    def put(self, path, descriptor):
        target = self.object_path(descriptor["sha256"])
        nonce = os.urandom(12)
        encrypt = Cipher(algorithms.AES(self.object_key), modes.GCM(nonce)).encryptor()
        encrypt.authenticate_additional_data(target.name.encode())
        with path.open("rb") as source, atomic_output(target) as output:
            output.write(nonce)
            hashed = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: source.read(CHUNK), b""):
                hashed.update(chunk)
                size += len(chunk)
                output.write(encrypt.update(chunk))
            if hashed.hexdigest() != descriptor["sha256"] or size != descriptor["size"]:
                raise CloudError("Eine Datei wird gerade geändert. Der Abgleich versucht es erneut.")
            output.write(encrypt.finalize())
            output.write(encrypt.tag)

    def get(self, descriptor, destination):
        source = self.object_path(descriptor["sha256"])
        if linked(source):
            raise CloudError("Eine Cloud-Datei verweist über einen Link auf eine andere Datei.")
        size = descriptor["size"]
        with source.open("rb") as handle:
            if os.fstat(handle.fileno()).st_size != size + 28:
                raise CloudError("Eine Cloud-Datei ist unvollständig. Warte auf den Cloud-Dienst.")
            nonce = handle.read(12)
            handle.seek(size + 12)
            tag = handle.read(16)
            if len(nonce) != 12 or len(tag) != 16:
                raise CloudError("Eine Cloud-Datei ist unvollständig.")
            decrypt = Cipher(algorithms.AES(self.object_key), modes.GCM(nonce, tag)).decryptor()
            decrypt.authenticate_additional_data(source.name.encode())
            handle.seek(12)
            hashed = hashlib.sha256()
            try:
                with atomic_output(destination) as output:
                    remaining = size
                    while remaining:
                        chunk = handle.read(min(CHUNK, remaining))
                        if not chunk:
                            raise CloudError("Eine Cloud-Datei ist unvollständig.")
                        remaining -= len(chunk)
                        clear = decrypt.update(chunk)
                        hashed.update(clear)
                        output.write(clear)
                    output.write(decrypt.finalize())
                    if hashed.hexdigest() != descriptor["sha256"]:
                        raise CloudError("Eine Cloud-Datei hat eine ungültige Prüfsumme.")
            except InvalidTag as exc:
                raise CloudError("Eine Cloud-Datei konnte nicht authentifiziert werden.") from exc
