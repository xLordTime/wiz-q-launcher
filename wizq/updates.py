"""GitHub release updates: explicit asset selection, digest verification, restart relay."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests
from packaging.version import Version

from . import __version__
from .paths import ProfileLock

REPOSITORY = "xLordTime/wiz-q-launcher"
API = f"https://api.github.com/repos/{REPOSITORY}"
MAX_DOWNLOAD = 600 * 1024 * 1024


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_asset(info):
    url = urlparse(info["url"])
    if (
        url.scheme != "https"
        or url.netloc != "github.com"
        or not url.path.startswith(f"/{REPOSITORY}/releases/download/")
    ):
        raise ValueError("Update-Quelle ist nicht das konfigurierte GitHub-Repository")
    if len(info.get("sha256", "")) != 64 or any(c not in "0123456789abcdef" for c in info["sha256"]):
        raise ValueError(
            "GitHub stellt für dieses Asset keinen gültigen SHA256-Digest bereit. Automatischer Austausch gesperrt."
        )
    if not 1 <= info.get("size", 0) <= MAX_DOWNLOAD:
        raise ValueError("Unzulässige Updategröße")


def check(channel="stable"):
    endpoint = API + ("/releases/latest" if channel == "stable" else "/releases?per_page=20")
    response = requests.get(endpoint, timeout=(5, 15), headers={"Accept": "application/vnd.github+json"})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    releases = data if isinstance(data, list) else [data]
    candidates = []
    for release in releases:
        if release.get("draft") or (channel == "stable" and release.get("prerelease")):
            continue
        try:
            version = Version(release["tag_name"].lstrip("v"))
        except (KeyError, ValueError):
            continue
        if version <= Version(__version__):
            continue
        expected = f"WizQLauncher-{release['tag_name']}.exe"
        assets = [a for a in release.get("assets", []) if a["name"] == expected]
        if len(assets) != 1:
            continue
        asset = assets[0]
        info = {
            "version": str(version),
            "url": asset["browser_download_url"],
            "sha256": asset.get("digest", "").removeprefix("sha256:"),
            "size": asset["size"],
            "notes": (release.get("body") or "Keine Versionshinweise.")[:16000],
        }
        validate_asset(info)
        candidates.append((version, info))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def download(info, directory, progress=lambda value: None):
    validate_asset(info)
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < info["size"] * 3 + 64 * 1024 * 1024:
        raise OSError("Nicht genug freier Speicher für Download und Rückfallkopie")
    dest = directory / ("update-" + uuid.uuid4().hex + ".exe")
    part = dest.with_suffix(".part")
    try:
        with requests.get(info["url"], timeout=(5, 30), stream=True) as response:
            response.raise_for_status()
            count = 0
            with part.open("xb") as handle:
                for chunk in response.iter_content(128 * 1024):
                    count += len(chunk)
                    if count > info["size"]:
                        raise ValueError("Der Download ist größer als das veröffentlichte Asset")
                    handle.write(chunk)
                    progress(int(count * 100 / info["size"]))
                handle.flush()
                os.fsync(handle.fileno())
        if count != info["size"] or digest(part) != info["sha256"]:
            raise ValueError("Updateprüfung fehlgeschlagen. Die vorhandene EXE bleibt unverändert.")
        os.replace(part, dest)
        return dest
    finally:
        part.unlink(missing_ok=True)


def prepare_apply(paths, store, source, info):
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        raise RuntimeError("EXE-Austausch ist nur in der kompilierten Windows-App verfügbar.")
    validate_asset(info)
    source = Path(source).resolve()
    updates = paths.directory("updates").resolve()
    if source.parent != updates or digest(source) != info["sha256"]:
        raise ValueError("Das bereitgestellte Update wurde verändert")
    snapshot = store.backup(updates / "rollback", keep=3)
    ident = uuid.uuid4().hex
    helper = updates / ("helper-" + ident + ".exe")
    shutil.copy2(sys.executable, helper)
    target = Path(sys.executable).resolve()
    if shutil.disk_usage(target.parent).free < target.stat().st_size + info["size"] + 32 * 1024 * 1024:
        raise OSError("Zu wenig Speicher im Ordner der Launcher-EXE")
    job = updates / ("job-" + ident + ".json")
    atomic_json(
        job,
        {
            "state": "ready",
            "target": str(target),
            "source": str(source),
            "sha256": info["sha256"],
            "pid": os.getpid(),
            "created": psutil.Process().create_time(),
            "profile": str(paths.root.resolve()),
            "snapshot": str(snapshot.resolve()),
        },
    )
    subprocess.Popen(
        [str(helper), "--apply-update", str(job)], creationflags=0x00000008 | 0x00000200, close_fds=True
    )
    return job


def same_process(pid, created):
    try:
        return abs(psutil.Process(pid).create_time() - created) < 0.01
    except psutil.Error:
        return False


def load_job(job):
    job = Path(job).resolve()
    if job.stat().st_size > 65536:
        raise ValueError("Unzulässiger Updateauftrag")
    info = json.loads(job.read_text(encoding="utf-8"))
    profile = Path(info["profile"]).resolve()
    if job.parent != profile / "updates" or Path(info["source"]).resolve().parent != job.parent:
        raise ValueError("Updateauftrag außerhalb des Updateordners")
    if Path(info["target"]).suffix.lower() != ".exe":
        raise ValueError("Ungültiges Updateziel")
    return job, info


def confirm_start(job, profile):
    job, info = load_job(job)
    if Path(profile).resolve() != Path(info["profile"]).resolve() or info["state"] not in (
        "started",
        "awaiting-confirmation",
    ):
        raise ValueError("Updateauftrag passt nicht zum gestarteten Profil")
    info["state"] = "healthy"
    atomic_json(job, info)


def apply_worker(job):
    job, info = load_job(job)
    replaced = False
    proc = None
    try:
        deadline = time.monotonic() + 120
        while same_process(info["pid"], info["created"]):
            if time.monotonic() > deadline:
                raise TimeoutError("Alter Launcher läuft weiter")
            time.sleep(0.25)
        source, target = Path(info["source"]), Path(info["target"])
        if digest(source) != info["sha256"]:
            raise ValueError("Update wurde nach dem Download verändert")
        previous = target.with_suffix(".previous.exe")
        staged = target.with_name(target.name + ".new")
        backup_stage = target.with_name(target.name + ".previous.part")
        shutil.copy2(target, backup_stage)
        os.replace(backup_stage, previous)
        shutil.copy2(source, staged)
        if digest(staged) != info["sha256"]:
            raise ValueError("Stagingprüfung fehlgeschlagen")
        info["state"] = "replacing"
        atomic_json(job, info)
        os.replace(staged, target)
        replaced = True
        info["state"] = "started"
        atomic_json(job, info)
        command = [str(target), "--profile", info["profile"], "--update-job", str(job)]
        if info.get("smoke_test"):
            command.append("--smoke-test")
        proc = subprocess.Popen(command)
        info["new_pid"] = proc.pid
        info["new_created"] = psutil.Process(proc.pid).create_time()
        atomic_json(job, info)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if json.loads(job.read_text(encoding="utf-8")).get("state") == "healthy":
                return 0
            if proc.poll() is not None:
                from .storage import restore_backup

                snapshot = Path(info["snapshot"]).resolve()
                if snapshot.parent != job.parent / "rollback":
                    raise ValueError("Ungültiger Rückfall-Snapshot")
                lock = ProfileLock(Path(info["profile"]))
                try:
                    restore_backup(snapshot, Path(info["profile"]) / "data/launcher-v6.sqlite3")
                    os.replace(previous, target)
                finally:
                    lock.close()
                info["state"] = "rolled-back"
                atomic_json(job, info)
                subprocess.Popen([str(target), "--profile", info["profile"]])
                return 1
            time.sleep(0.5)
        # User may still be unlocking the vault. Never kill a live app or restore
        # the DB underneath it just because the readiness timeout elapsed.
        info["state"] = "awaiting-confirmation"
        atomic_json(job, info)
        return 0
    except Exception as exc:
        info["state"], info["error"] = "failed", type(exc).__name__
        # A replacement that cannot even be executed must also roll back. Do
        # not touch a live new process or a profile opened by another launcher.
        if replaced and (proc is None or proc.poll() is not None):
            try:
                from .storage import restore_backup

                snapshot = Path(info["snapshot"]).resolve()
                if snapshot.parent != job.parent / "rollback":
                    raise ValueError("Ungültiger Rückfall-Snapshot")
                lock = ProfileLock(Path(info["profile"]))
                try:
                    restore_backup(snapshot, Path(info["profile"]) / "data/launcher-v6.sqlite3")
                    os.replace(Path(info["target"]).with_suffix(".previous.exe"), Path(info["target"]))
                    info["state"] = "rolled-back"
                finally:
                    lock.close()
                subprocess.Popen([info["target"], "--profile", info["profile"]])
            except Exception:
                info["state"] = "recovery-required"
        atomic_json(job, info)
        return 2
