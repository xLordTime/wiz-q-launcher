"""Profile backup and restore helpers for Wiz Q Launcher."""

from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

BACKUP_FORMAT_VERSION = 1
BACKUP_EXTENSION = ".wizqbackup.zip"
BACKUP_SCOPES = ("config", "config_data", "full")


def _iter_files(base_dir: Path):
    if not base_dir.exists() or not base_dir.is_dir():
        return
    for path in sorted(base_dir.rglob("*")):
        if path.is_file():
            yield path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_scope(scope: str) -> str:
    scope = str(scope or "full").strip().lower()
    if scope not in BACKUP_SCOPES:
        return "full"
    return scope


def _build_backup_entries(paths: Dict, scope: str) -> List[Tuple[Path, str]]:
    entries: List[Tuple[Path, str]] = []
    config_file = Path(paths["config_file"])
    data_dir = Path(paths["data_dir"])
    log_dir = Path(paths["log_dir"])

    if config_file.exists():
        entries.append((config_file, "config.json"))

    if scope in ("config_data", "full"):
        for file_path in _iter_files(data_dir) or []:
            rel = file_path.relative_to(data_dir)
            entries.append((file_path, str(Path("data") / rel)))

    if scope == "full":
        for file_path in _iter_files(log_dir) or []:
            rel = file_path.relative_to(log_dir)
            entries.append((file_path, str(Path("logs") / rel)))

    return entries


def create_profile_backup(paths: Dict, scope: str = "full") -> Path:
    """Create a profile backup zip and return its path."""
    backups_dir = Path(paths["backups_dir"])
    backups_dir.mkdir(parents=True, exist_ok=True)

    scope = _normalize_scope(scope)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"wizq_profile_{timestamp}{BACKUP_EXTENSION}"

    entries = _build_backup_entries(paths, scope)
    file_hashes = {arcname: _sha256_file(src) for src, arcname in entries}

    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": int(time.time()),
        "scope": scope,
        "file_count": len(entries),
        "file_hashes": file_hashes,
        "includes": {
            "config": any(arc == "config.json" for _, arc in entries),
            "data": any(arc.startswith("data/") for _, arc in entries),
            "logs": any(arc.startswith("logs/") for _, arc in entries),
        },
    }

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for src, arcname in entries:
            archive.write(src, arcname=arcname)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    return backup_path


def inspect_backup_file(backup_file: Path) -> Dict:
    """Inspect backup metadata and validate archive hashes/version."""
    backup_file = Path(backup_file)
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    with tempfile.TemporaryDirectory(prefix="wizq_inspect_") as tmp:
        temp_root = Path(tmp)
        with zipfile.ZipFile(backup_file, "r") as archive:
            archive.extractall(temp_root)

        manifest_file = temp_root / "manifest.json"
        if not manifest_file.exists():
            raise ValueError("Invalid backup: manifest.json missing")

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_version = int(manifest.get("format_version", -1))
        if manifest_version != BACKUP_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported backup format_version={manifest_version}; "
                f"expected {BACKUP_FORMAT_VERSION}"
            )

        expected_hashes = manifest.get("file_hashes", {})
        if not isinstance(expected_hashes, dict):
            raise ValueError("Invalid backup: file_hashes missing or malformed")

        for arcname, expected_hash in expected_hashes.items():
            extracted = temp_root / Path(arcname)
            if not extracted.exists() or not extracted.is_file():
                raise ValueError(f"Invalid backup: missing file listed in manifest: {arcname}")
            actual_hash = _sha256_file(extracted)
            if actual_hash != expected_hash:
                raise ValueError(f"Backup integrity check failed for {arcname}")

        return {
            "manifest": manifest,
            "file_count": int(manifest.get("file_count", len(expected_hashes))),
            "scope": manifest.get("scope", "unknown"),
        }


def restore_profile_backup(backup_file: Path, paths: Dict, restore_scope: str = "full") -> None:
    """Restore a profile backup into the current profile paths."""
    backup_file = Path(backup_file)
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    restore_scope = _normalize_scope(restore_scope)
    inspect_backup_file(backup_file)

    config_file = Path(paths["config_file"])
    data_dir = Path(paths["data_dir"])
    log_dir = Path(paths["log_dir"])

    with tempfile.TemporaryDirectory(prefix="wizq_restore_") as tmp:
        temp_root = Path(tmp)
        with zipfile.ZipFile(backup_file, "r") as archive:
            archive.extractall(temp_root)

        manifest_file = temp_root / "manifest.json"
        if not manifest_file.exists():
            raise ValueError("Invalid backup: manifest.json missing")

        config_src = temp_root / "config.json"
        data_src = temp_root / "data"
        logs_src = temp_root / "logs"

        if restore_scope in ("config", "config_data", "full") and config_src.exists():
            config_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_src, config_file)

        if restore_scope in ("config_data", "full") and data_src.exists():
            if data_dir.exists():
                shutil.rmtree(data_dir)
            shutil.copytree(data_src, data_dir)

        if restore_scope == "full" and logs_src.exists():
            if log_dir.exists():
                shutil.rmtree(log_dir)
            shutil.copytree(logs_src, log_dir)
