from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def default(cls):
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            if sys.platform == "win32":
                raise RuntimeError(
                    "LOCALAPPDATA fehlt. Das Profil wird nicht an einen anderen Ort verschoben."
                )
            # Developer runs on other platforms still require an explicit profile.
            raise RuntimeError("Entwicklungsstart: --profile <Ordner> verwenden.")
        return cls(Path(base) / "WizQLauncher")

    @property
    def database(self):
        return self.root / "data" / "launcher-v6.sqlite3"

    def directory(self, name):
        if name not in {"data", "logs", "backups", "themes", "addons", "recordings", "cache", "updates"}:
            raise ValueError("Unbekannter Profilbereich")
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def prepare(self):
        for name in ("data", "logs", "backups", "themes", "addons", "recordings", "cache", "updates"):
            self.directory(name)


class ProfileLock:
    """OS-owned advisory lock: automatically released even after a killed process."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.file = (root / "profile.lock").open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("Dieses Profil ist bereits in einem anderen Launcher geöffnet.") from None

    def close(self):
        if not self.file.closed:
            self.file.close()
