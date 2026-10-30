from __future__ import annotations

import base64
import ctypes
import json
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def b64(value):
    return base64.b64encode(value).decode("ascii")


def unb64(value):
    return base64.b64decode(value, validate=True)


def dpapi(data: bytes, decrypt=False):
    if sys.platform != "win32":
        raise RuntimeError("Windows-Schutz ist nur unter Windows verfügbar. Masterpasswort verwenden.")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    blob = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(blob), None, None, None, None, 1, ctypes.byref(out)):
        raise RuntimeError("Windows konnte den Profilschlüssel nicht entsperren. Daten bleiben erhalten.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


class Vault:
    def __init__(self, store):
        self.store = store
        self.key = None

    @property
    def initialized(self):
        return self.store.get("vault", meta=True) is not None

    @property
    def mode(self):
        return (self.store.get("vault", {}, meta=True)).get("mode")

    @staticmethod
    def _wrap(key, password=None):
        if password is None:
            return {"version": 1, "mode": "windows", "wrapped": b64(dpapi(key))}
        if len(password) < 8:
            raise ValueError("Das Masterpasswort muss mindestens 8 Zeichen haben.")
        salt, nonce = os.urandom(16), os.urandom(12)
        wrapping = Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password.encode("utf-8"))
        return {
            "version": 1,
            "mode": "password",
            "salt": b64(salt),
            "nonce": b64(nonce),
            "n": 32768,
            "r": 8,
            "p": 1,
            "wrapped": b64(AESGCM(wrapping).encrypt(nonce, key, b"WizQLauncher/vault/1")),
        }

    def initialize(self, password=None):
        if self.initialized:
            raise ValueError("Ein Tresor existiert bereits. Er wird nicht überschrieben.")
        key = os.urandom(32)
        envelope = self._wrap(key, password)
        self.store.set("vault", envelope, meta=True)
        self.key = key

    def unlock(self, password=None):
        info = self.store.get("vault", meta=True)
        if not info or info.get("version") != 1:
            raise ValueError("Tresorformat nicht unterstützt")
        try:
            if info["mode"] == "windows":
                key = dpapi(unb64(info["wrapped"]), decrypt=True)
            elif info["mode"] == "password":
                if password is None or (info["n"], info["r"], info["p"]) != (32768, 8, 1):
                    raise ValueError("Passwort oder KDF-Parameter ungültig")
                wrapping = Scrypt(
                    salt=unb64(info["salt"]), length=32, n=info["n"], r=info["r"], p=info["p"]
                ).derive(password.encode("utf-8"))
                key = AESGCM(wrapping).decrypt(
                    unb64(info["nonce"]), unb64(info["wrapped"]), b"WizQLauncher/vault/1"
                )
            else:
                raise ValueError("Unbekannter Tresormodus")
            if len(key) != 32:
                raise ValueError("Ungültiger Schlüssel")
            self.key = key
        except Exception:
            raise ValueError(
                "Tresor nicht entsperrt. Passwort/Windows-Konto prüfen; Daten bleiben unverändert."
            ) from None

    def change_protection(self, password=None):
        if self.key is None:
            raise ValueError("Tresor ist gesperrt")
        envelope = self._wrap(self.key, password)
        self.store.set("vault", envelope, meta=True)

    def lock(self):
        self.key = None

    def encrypt(self, value, purpose):
        if self.key is None:
            raise ValueError("Tresor ist gesperrt")
        nonce = os.urandom(12)
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        encrypted = AESGCM(self.key).encrypt(nonce, data, ("WizQLauncher/1/" + purpose).encode())
        return json.dumps({"v": 1, "nonce": b64(nonce), "data": b64(encrypted)})

    def decrypt(self, value, purpose):
        if self.key is None:
            raise ValueError("Tresor ist gesperrt")
        payload = json.loads(value)
        if payload["v"] != 1:
            raise ValueError("Unbekanntes Secret-Format")
        return json.loads(
            AESGCM(self.key).decrypt(
                unb64(payload["nonce"]), unb64(payload["data"]), ("WizQLauncher/1/" + purpose).encode()
            )
        )
