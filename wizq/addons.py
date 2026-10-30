"""Trusted extensions use isolated workers. This is deliberately not called a sandbox."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

BUILTINS = [
    ("stat-monitor", "Stat Monitor", "CPU, RAM und verfügbare PC-Metriken"),
    ("clips-record", "Clips and Record", "Screenshots, Aufnahme und komprimierter Replay-Puffer"),
    ("theme-creator", "Theme Creator", "Eigene Designs mit Live-Vorschau"),
]


def discover(directory):
    result = []
    for path in sorted(Path(directory).glob("*/addon.json")):
        try:
            if path.stat().st_size > 65536:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("api_version") != 1 or data.get("id") != path.parent.name:
                continue
            if (
                not all(c.islower() or c.isdigit() or c == "-" for c in data["id"])
                or not 1 <= len(data["id"]) <= 64
            ):
                continue
            entry = (path.parent / data["entrypoint"]).resolve()
            if (
                entry.parent != path.parent.resolve()
                or entry.suffix != ".py"
                or entry.stat().st_size > 1024 * 1024
            ):
                continue
            if not set(data.get("capabilities", [])).issubset({"sessions.read", "ui.cards", "storage"}):
                continue
            data.update(
                path=entry, fingerprint=hashlib.sha256(path.read_bytes() + entry.read_bytes()).hexdigest()
            )
            result.append(data)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return result


class AddonWorker(QObject):
    message = Signal(str)
    failed = Signal(str)

    def __init__(self, manifest, data_dir, parent=None):
        super().__init__(parent)
        self.manifest = manifest
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(manifest["path"].parent))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.buffer = b""
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(
            lambda _: self.failed.emit("Addon-Worker konnte nicht ausgeführt werden.")
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        args = ["--addon-worker", str(manifest["path"]), "--addon-data", str(data_dir)]
        if not getattr(sys, "frozen", False):
            args.insert(0, str(Path(__file__).resolve().parent.parent / "main.py"))
        self.process.start(sys.executable, args)
        self.process.started.connect(lambda: self.send_event("host.ready", {}))

    def read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 65536:
            self.stop()
            self.failed.emit("Addon sendet zu große Nachrichten und wurde gestoppt.")
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                packet = json.loads(line)
                if packet.get("type") == "status" and isinstance(packet.get("text"), str):
                    self.message.emit(packet["text"][:2000])
            except (ValueError, TypeError):
                self.stop()
                self.failed.emit("Ungültiges Addon-Protokoll")
                return

    def send_event(self, name, data):
        if name.startswith("session.") and "sessions.read" not in self.manifest.get("capabilities", []):
            return
        self.process.write((json.dumps({"type": "event", "event": name, "data": data}) + "\n").encode())

    def stop(self):
        self.send_event("host.stop", {})
        self.process.terminate()
        # Bound shutdown; do not leave executable addon code after Disable/Exit.
        if not self.process.waitForFinished(500):
            self.process.kill()
            self.process.waitForFinished(500)


def worker_main(path, data):
    import os

    os.environ["WIZQ_ADDON_DATA"] = str(Path(data).resolve())
    try:
        runpy.run_path(path, run_name="__main__")
        return 0
    except Exception:
        return 1
