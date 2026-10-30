from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = 1


class ProfileError(RuntimeError):
    pass


def check_database(path: Path, full=False):
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        result = con.execute("PRAGMA integrity_check" if full else "PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise ProfileError("Die Datenbankprüfung ist fehlgeschlagen. Original bleibt erhalten.")
    finally:
        con.close()


class Store:
    """Single serialized writer; UI never rewrites an out-of-date whole profile."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        if existed:
            check_database(self.path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if self.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            self.db.close()
            raise ProfileError("Das Dateisystem unterstützt den sicheren WAL-Modus nicht.")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=10000")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA:
            self.db.close()
            raise ProfileError("Dieses Profil benötigt eine neuere Launcher-Version.")
        with self.transaction() as db:
            for sql in [
                "CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY, name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, nickname TEXT NOT NULL, region TEXT NOT NULL, credentials TEXT NOT NULL, group_id TEXT REFERENCES groups(id) ON DELETE SET NULL, position INTEGER NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, legacy_seconds REAL NOT NULL DEFAULT 0 CHECK(legacy_seconds>=0), legacy_sessions INTEGER NOT NULL DEFAULT 0 CHECK(legacy_sessions>=0), last_used REAL NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL, region TEXT NOT NULL, pid INTEGER NOT NULL, created REAL NOT NULL, hwnd INTEGER NOT NULL DEFAULT 0, started REAL NOT NULL, seen REAL NOT NULL, elapsed REAL NOT NULL DEFAULT 0, ended REAL, reason TEXT)",
                "CREATE INDEX IF NOT EXISTS sessions_account ON sessions(account_id)",
                "CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY, started REAL NOT NULL, ended REAL NOT NULL)",
            ]:
                db.execute(sql)
            db.execute(f"PRAGMA user_version={SCHEMA}")

    @contextmanager
    def transaction(self):
        with self.lock:
            nested = self.db.in_transaction
            savepoint = "s" + uuid.uuid4().hex
            self.db.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
            try:
                yield self.db
                self.db.execute(f"RELEASE {savepoint}" if nested else "COMMIT")
            except BaseException:
                self.db.execute(f"ROLLBACK TO {savepoint}" if nested else "ROLLBACK")
                if nested:
                    self.db.execute(f"RELEASE {savepoint}")
                raise

    def query(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args)]

    def get(self, key, default=None, *, meta=False):
        rows = self.query(f"SELECT value FROM {'meta' if meta else 'settings'} WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key, value, *, meta=False):
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        with self.transaction() as db:
            db.execute(
                f"INSERT INTO {'meta' if meta else 'settings'} VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, encoded),
            )

    def accounts(self):
        return self.query(
            "SELECT a.id,a.nickname,a.region,a.group_id,a.position,a.favorite,a.legacy_seconds,a.legacy_sessions,a.last_used, COALESCE(SUM(s.elapsed),0)+a.legacy_seconds AS total_seconds,COUNT(s.id)+a.legacy_sessions AS session_count FROM accounts a LEFT JOIN sessions s ON s.account_id=a.id GROUP BY a.id ORDER BY a.position,a.nickname"
        )

    def save_account(self, vault, nickname, username, password, region, group_id=None, account_id=None):
        if not nickname.strip() or not username.strip() or not password:
            raise ValueError("Nickname, Username und Passwort sind erforderlich.")
        account_id = account_id or str(uuid.uuid4())
        secret = vault.encrypt({"username": username, "password": password}, account_id)
        with self.transaction() as db:
            position = db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM accounts").fetchone()[0]
            db.execute(
                "INSERT INTO accounts(id,nickname,region,credentials,group_id,position) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nickname=excluded.nickname,region=excluded.region,credentials=excluded.credentials,group_id=excluded.group_id",
                (account_id, nickname.strip(), region, secret, group_id, position),
            )
        return account_id

    def credentials(self, vault, account_id):
        rows = self.query("SELECT credentials FROM accounts WHERE id=?", (account_id,))
        if not rows:
            raise KeyError("Account nicht gefunden")
        return vault.decrypt(rows[0]["credentials"], account_id)

    def reorder(self, ids, group_id=None):
        if len(set(ids)) != len(ids):
            raise ValueError("Doppelte Account-ID")
        with self.transaction() as db:
            for pos, account_id in enumerate(ids):
                db.execute(
                    "UPDATE accounts SET position=?,group_id=? WHERE id=?", (pos, group_id, account_id)
                )

    def add_group(self, name):
        if not name.strip():
            raise ValueError("Gruppenname fehlt")
        ident = str(uuid.uuid4())
        with self.transaction() as db:
            db.execute("INSERT INTO groups VALUES(?,?,(SELECT COUNT(*) FROM groups))", (ident, name.strip()))
        return ident

    def backup(self, directory: Path, keep=10):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (time.strftime("profile-%Y%m%d-%H%M%S-") + f"{time.time_ns():020d}" + ".sqlite3")
        temporary = target.with_suffix(".part")
        try:
            with self.lock:
                if self.db.in_transaction:
                    raise ProfileError("Sicherung erst nach Ende der Transaktion möglich.")
                out = sqlite3.connect(temporary)
                try:
                    self.db.backup(out)
                finally:
                    out.close()
            check_database(temporary, full=True)
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            others = sorted(
                (p for p in directory.glob("profile-*.sqlite3") if p != target),
                key=lambda p: p.stat().st_mtime_ns,
                reverse=True,
            )
            for old in others[max(0, keep - 1) :]:
                old.unlink(missing_ok=True)
            return target
        finally:
            temporary.unlink(missing_ok=True)

    def close(self):
        with self.lock:
            self.db.close()


def restore_backup(source: Path, destination: Path):
    """Caller must close Store and own ProfileLock. Never overwrite the last original."""
    check_database(source, full=True)
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            raise ProfileError("Die Sicherung hat ein anderes Datenformat.")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"meta", "settings", "accounts", "sessions", "groups"}.issubset(tables):
            raise ProfileError("Dies ist keine Launcher-Sicherung.")
    quarantine = destination.parent / ("recovery-" + uuid.uuid4().hex)
    quarantine.mkdir(parents=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_suffix(".restoring")
    shutil.copy2(source, staged)
    check_database(staged, full=True)
    with staged.open("r+b") as handle:
        os.fsync(handle.fileno())
    for suffix in ("", "-wal", "-shm"):
        old = Path(str(destination) + suffix)
        if old.exists():
            shutil.copy2(old, quarantine / old.name)
    # Only after every original has a preserved copy do we switch the DB family.
    for suffix in ("-wal", "-shm"):
        Path(str(destination) + suffix).unlink(missing_ok=True)
    os.replace(staged, destination)
    return quarantine
