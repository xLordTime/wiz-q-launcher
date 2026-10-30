import base64
import json

import pytest
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from wizq.migration import migrate
from wizq.sessions import Sessions


def legacy(source, accounts, password="0"):
    (source / "data").mkdir(parents=True)
    salt = bytes(range(16))
    key = base64.urlsafe_b64encode(
        PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000).derive(
            password.encode()
        )
    )
    (source / "config.json").write_text(
        json.dumps(
            {
                "master_password_mode": "placeholder" if password == "0" else "password",
                "current_region": "de",
                "region_install_de": "D:/Wizard101(DE)",
            }
        ),
        encoding="utf-8",
    )
    (source / "data/accounts.enc.json").write_text(
        json.dumps(
            {
                "salt": base64.b64encode(salt).decode(),
                "iterations": 390000,
                "data": Fernet(key).encrypt(json.dumps(accounts).encode()).decode(),
            }
        )
    )


def test_legacy_import_preserves_exact_stats_and_is_idempotent(profile, tmp_path):
    paths, store, vault = profile
    source = tmp_path / "old"
    legacy(
        source,
        [
            {
                "name": "Old DE",
                "username": "legacy-user",
                "password": "legacy-password",
                "region": "de",
                "total_playtime": 12345.75,
                "sessions_count": 17,
                "last_used": 123456,
            }
        ],
    )
    original = (source / "data/accounts.enc.json").read_bytes()
    report = migrate(store, vault, source)
    migrate(store, vault, source)
    assert len(store.accounts()) == 1
    account = store.accounts()[0]
    assert account["total_seconds"] == 12345.75
    assert account["session_count"] == 17
    assert store.credentials(vault, account["id"])["password"] == "legacy-password"
    assert store.get("region_install_de") == "D:/Wizard101(DE)"
    assert (source / "data/accounts.enc.json").read_bytes() == original
    backup = paths.directory("backups") / report["backup"]
    assert "legacy-user" not in backup.read_text()
    assert "data/accounts.enc.json" in vault.decrypt(backup.read_text(), "legacy-backup")["files"]


def test_wrong_old_password_does_not_create_empty_migration(profile, tmp_path):
    _, store, vault = profile
    source = tmp_path / "old"
    legacy(source, [{"name": "A", "username": "U", "password": "P"}], password="correct old password")
    with pytest.raises(InvalidToken):
        migrate(store, vault, source, "wrong")
    assert store.accounts() == []
    assert store.get("legacy_migrated", meta=True) is None


def test_unavailable_cached_windows_password_still_allows_master_password(profile, tmp_path, monkeypatch):
    from wizq import migration

    _, store, vault = profile
    source = tmp_path / "old-other-pc"
    legacy(source, [{"name": "A", "username": "U", "password": "P"}], password="correct old password")
    config = json.loads((source / "config.json").read_text())
    config["master_password_secret_b64"] = base64.b64encode(b"not-this-windows-account").decode()
    (source / "config.json").write_text(json.dumps(config))

    def fail(*args, **kwargs):
        raise RuntimeError("DPAPI unavailable")

    monkeypatch.setattr(migration, "dpapi", fail)
    with pytest.raises(PermissionError):
        migrate(store, vault, source)
    assert migrate(store, vault, source, "correct old password")["accounts"] == 1


def test_invalid_second_account_rolls_back_entire_import(profile, tmp_path):
    _, store, vault = profile
    source = tmp_path / "old"
    legacy(
        source,
        [
            {"name": "Good", "username": "u", "password": "p"},
            {"name": "Bad", "username": "v", "password": "p", "total_playtime": -20},
        ],
    )
    with pytest.raises(ValueError):
        migrate(store, vault, source)
    assert store.accounts() == []
    assert store.get("legacy_migrated", meta=True) is None


def test_crash_recovery_no_offline_credit_and_pid_reuse(profile):
    _, store, vault = profile
    ident = store.save_account(vault, "A", "U", "P", "de")
    now = [1000.0]
    sessions = Sessions(store, clock=lambda: now[0], wall=lambda: now[0])
    sessions.start(7, 100, 101, "de", ident)
    now[0] += 10
    sessions.heartbeat()
    now[0] += 3600
    recovered = Sessions(store, clock=lambda: now[0], wall=lambda: now[0])
    assert store.accounts()[0]["total_seconds"] == 10
    assert store.query("SELECT ended FROM sessions")[0]["ended"] == 1010
    recovered.start(7, 200, 102, "us", ident)
    now[0] += 10
    recovered.heartbeat(lambda pid, created: created == 200)
    assert store.accounts()[0]["total_seconds"] == 20
    assert store.accounts()[0]["session_count"] == 2


def test_overlapping_activity_and_suspend_gap(profile):
    _, store, _ = profile
    now = [1000.0]
    s = Sessions(store, clock=lambda: now[0], wall=lambda: now[0])
    s.start(1, 1, 1, "de")
    s.start(2, 2, 2, "us")
    now[0] += 10
    s.heartbeat()
    assert s.activity_24h() == 10
    now[0] += 3600
    s.heartbeat()
    assert s.activity_24h() == 10
