from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .settings import get


class Capture(QObject):
    changed = Signal(str)

    def __init__(self, paths, store, parent=None):
        super().__init__(parent)
        self.paths, self.store = paths, store
        self.process = None
        self.replay = False
        self.buffer_dir = None
        self.last_error = ""
        self.janitor = QTimer(self)
        self.janitor.setInterval(2000)
        self.janitor.timeout.connect(self.prune)

    def executable(self):
        path = get(self.store, "ffmpeg_path") or shutil.which("ffmpeg")
        if not path or not Path(path).is_file():
            raise ValueError(
                "FFmpeg fehlt. In Einstellungen → Clips and Record eine FFmpeg-EXE mit gdigrab und libx264 auswählen."
            )
        return str(Path(path).resolve())

    def start(self, hwnd, replay=False):
        if sys.platform != "win32":
            raise RuntimeError("Fensteraufnahme benötigt Windows.")
        from .backend import instances

        if int(hwnd) not in {entry["hwnd"] for entry in instances()}:
            raise ValueError("Das ausgewählte Spielfenster existiert nicht mehr. Fensterliste aktualisieren.")
        if self.process is not None:
            raise ValueError("Eine Aufnahme läuft bereits. Zuerst stoppen.")
        if shutil.disk_usage(self.paths.root).free < 256 * 1024 * 1024:
            raise ValueError("Zu wenig Speicher für die Aufnahme")
        executable = self.executable()
        self.replay, self.last_error = replay, ""
        stamp = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.buffer_dir = self.paths.directory("cache") / ("replay-" + stamp)
        if replay:
            self.buffer_dir.mkdir()
        output = (
            str(self.buffer_dir / "part-%06d.mkv")
            if replay
            else str(self.paths.directory("recordings") / (stamp + ".mkv"))
        )
        fps = get(self.store, "capture_fps")
        args = [
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "gdigrab",
            "-framerate",
            str(fps),
            "-i",
            f"hwnd={int(hwnd)}",
        ]
        device = get(self.store, "capture_audio_device")
        if device:
            args += ["-f", "dshow", "-i", "audio=" + device]
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-g",
            str(fps * 5),
        ]
        args += ["-c:a", "aac"] if device else ["-an"]
        if replay:
            args += ["-f", "segment", "-segment_time", "5", "-reset_timestamps", "1"]
        args.append(output)
        process = QProcess(self)
        self.process = process
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardError.connect(lambda: self._stderr(process))
        process.readyReadStandardOutput.connect(lambda: process.readAllStandardOutput())
        process.finished.connect(lambda code, _: self._finished(process, code))
        process.errorOccurred.connect(lambda _: self._error(process))
        process.start(executable, args)
        self.janitor.start()
        self.changed.emit(
            "Replay-Puffer läuft · Audio " + ("aktiv" if device else "aus")
            if replay
            else "Aufnahme läuft · " + output
        )

    def _stderr(self, process):
        self.last_error = (
            self.last_error + bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
        )[-2000:]

    def _error(self, process):
        self.changed.emit("Encoderfehler. FFmpeg-Pfad und unterstützte Geräte prüfen.")
        if process.state() == QProcess.ProcessState.NotRunning:
            self._finished(process, 1)

    def _finished(self, process, code):
        if self.process is not process:
            return
        self.process = None
        self.janitor.stop()
        self.changed.emit(
            "Aufnahme beendet." if code == 0 else "Aufnahme beendet/fehlgeschlagen. " + self.last_error[-500:]
        )
        process.deleteLater()
        if self.replay and self.buffer_dir:
            shutil.rmtree(self.buffer_dir, ignore_errors=True)

    def prune(self):
        if self.process is None:
            return
        if shutil.disk_usage(self.paths.root).free < 128 * 1024 * 1024:
            self.stop()
            self.changed.emit("Aufnahme wegen niedrigem freien Speicher gestoppt.")
            return
        if not self.replay:
            return
        files = sorted(self.buffer_dir.glob("part-*.mkv"))
        closed = files[:-1]
        keep = max(2, get(self.store, "clip_buffer_seconds") // 5 + 1)
        quota = get(self.store, "capture_quota_mb") * 1024 * 1024
        size = sum(p.stat().st_size for p in files if p.exists())
        for index, path in enumerate(closed):
            if len(closed) - index > keep or size > quota:
                size -= path.stat().st_size
                path.unlink(missing_ok=True)
        if size > quota:
            self.stop()
            self.changed.emit("Replay-Speicherlimit erreicht; Puffer gestoppt.")

    def prepare_clip(self):
        if not self.replay or self.process is None:
            raise ValueError("Zuerst Replay starten und mindestens 5 Sekunden warten.")
        files = sorted(self.buffer_dir.glob("part-*.mkv"))[:-1]
        count = max(1, get(self.store, "clip_buffer_seconds") // 5)
        files = files[-count:]
        if not files:
            raise ValueError("Noch kein vollständiges Segment im Puffer")
        snapshot = self.paths.directory("cache") / ("clip-" + uuid.uuid4().hex)
        snapshot.mkdir()
        try:
            for i, path in enumerate(files):
                # AppData normally resides on NTFS: a hardlink snapshots a
                # closed segment instantly without copying a large clip in UI.
                try:
                    os.link(path, snapshot / f"segment-{i}.mkv")
                except OSError:
                    shutil.copy2(path, snapshot / f"segment-{i}.mkv")
            (snapshot / "list.txt").write_text(
                "\n".join(f"file 'segment-{i}.mkv'" for i in range(len(files))), encoding="utf-8"
            )
        except Exception:
            shutil.rmtree(snapshot, ignore_errors=True)
            raise
        output = self.paths.directory("recordings") / (
            time.strftime("clip-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".mp4"
        )
        executable = self.executable()

        def encode():
            try:
                result = subprocess.run(
                    [
                        executable,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "1",
                        "-i",
                        "list.txt",
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(output),
                    ],
                    cwd=snapshot,
                    capture_output=True,
                    timeout=120,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                if result.returncode:
                    output.unlink(missing_ok=True)
                    raise RuntimeError("Clip konnte nicht zusammengesetzt werden. Encoderformat prüfen.")
                return str(output)
            finally:
                shutil.rmtree(snapshot, ignore_errors=True)

        return encode

    def stop(self):
        if self.process is not None:
            process = self.process
            process.write(b"q\n")
            QTimer.singleShot(4000, lambda: process.kill() if self.process is process else None)

    def shutdown(self):
        if self.process is not None:
            self.process.write(b"q\n")
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(500)
