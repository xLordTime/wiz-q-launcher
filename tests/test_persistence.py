import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from wizq.paths import ProfileLock
from wizq.storage import Store, check_database, restore_backup
from wizq.vault import Vault


def test_vault_authentication_and_password_change(profile):
    paths, store, vault = profile
    account = store.save_account(vault, "Test", "user-secret", "  password stays exact  ", "de")
    cipher = store.query("SELECT credentials FROM accounts")[0]["credentials"]
    with pytest.raises(InvalidTag):
        vault.decrypt(cipher, "a-different-account")
    vault.change_protection("a-different-master")
    vault.lock()
    with pytest.raises(ValueError):
        vault.unlock("test-master-password")
    vault.unlock("a-different-master")
    assert store.credentials(vault, account)["password"] == "  password stays exact  "
    assert "user-secret" not in paths.database.read_bytes().decode(errors="ignore")
    assert "password stays exact" not in (Path(str(paths.database) + "-wal")).read_bytes().decode(
        errors="ignore"
    )


def test_transaction_rolls_back_all_account_changes(profile):
    _, store, vault = profile
    ident = store.save_account(vault, "Before", "user", "password", "de")
    with pytest.raises(RuntimeError):
        with store.transaction() as db:
            db.execute("UPDATE accounts SET nickname='After'")
            store.set("theme", "porcelain")
            raise RuntimeError("simulated failure")
    assert store.accounts()[0]["nickname"] == "Before"
    assert store.get("theme") is None
    assert store.credentials(vault, ident)["username"] == "user"


def test_online_backup_includes_wal_and_rotation_keeps_valid(profile, tmp_path):
    paths, store, vault = profile
    store.set("preserved", {"value": 42})
    for _ in range(5):
        snapshot = store.backup(paths.directory("backups"), keep=3)
    assert len(list(paths.directory("backups").glob("profile-*.sqlite3"))) == 3
    copy = Store(snapshot)
    try:
        assert copy.get("preserved") == {"value": 42}
    finally:
        copy.close()
    dest = tmp_path / "restored.sqlite3"
    quarantine = restore_backup(snapshot, dest)
    check_database(dest, full=True)
    assert quarantine.exists()


def test_corrupt_database_is_never_replaced_with_defaults(tmp_path):
    path = tmp_path / "broken.sqlite3"
    path.write_bytes(b"interrupted or broken input")
    original = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        Store(path)
    assert path.read_bytes() == original


def test_profile_lock_prevents_a_second_writer(tmp_path):
    first = ProfileLock(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            ProfileLock(tmp_path)
    finally:
        first.close()
    ProfileLock(tmp_path).close()


def test_killed_writer_keeps_last_committed_state(tmp_path):
    path = tmp_path / "crash.sqlite3"
    code = """
import sys,time
from pathlib import Path
from wizq.storage import Store
s=Store(Path(sys.argv[1]))
s.set('safe','committed')
with s.transaction():
    s.set('safe','uncommitted')
    s.set('partial','must not survive')
    print('ready',flush=True)
    time.sleep(60)
"""
    proc = subprocess.Popen([sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
    finally:
        proc.kill()
        proc.wait(timeout=10)
    store = Store(path)
    try:
        assert store.get("safe") == "committed"
        assert store.get("partial") is None
        check_database(path, full=True)
    finally:
        store.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_windows_protection_round_trip(tmp_path):
    store = Store(tmp_path / "windows.sqlite3")
    try:
        vault = Vault(store)
        vault.initialize()
        ident = store.save_account(vault, "A", "user", "password", "us")
        vault.lock()
        vault.unlock()
        assert store.credentials(vault, ident)["password"] == "password"
    finally:
        store.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native module")
def test_native_module_no_game_required():
    import wizq_native

    assert isinstance(wizq_native.windows(), list)
    with pytest.raises(RuntimeError):
        wizq_native.login(0, "synthetic-user", "synthetic-password")
