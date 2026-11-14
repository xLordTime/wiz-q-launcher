import os
import shutil
import time
from contextlib import contextmanager

import pytest

from wizq.cloud import CloudError, CloudSync, new_code
from wizq.cloud_files import safe_file
from wizq.paths import Paths
from wizq.sessions import Sessions
from wizq.storage import Store, restore_backup
from wizq.vault import Vault


@contextmanager
def device(root, password="second-test-password"):
    paths = Paths(root)
    paths.prepare()
    with_store = Store(paths.database)
    try:
        vault = Vault(with_store)
        if vault.initialized:
            vault.unlock(password)
        else:
            vault.initialize(password)
        yield CloudSync(paths, with_store, vault)
    finally:
        with_store.close()


@pytest.fixture
def linked_devices(profile, tmp_path):
    first_root, first_store, first_vault = profile
    first = CloudSync(first_root, first_store, first_vault)
    folder = tmp_path / "provider"
    folder.mkdir()
    with device(tmp_path / "second") as second:
        yield first, second, folder


def save_file(sync, name, data):
    path = sync.paths.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = time.time() - 60
    os.utime(path, (stamp, stamp))
    return path


def transfer(source, destination):
    shutil.copytree(source, destination, dirs_exist_ok=True)


def record_session(sync, account, offset, seconds):
    start = time.time() - 3600 + offset
    clocks = [start, 0]
    sessions = Sessions(sync.store, wall=lambda: clocks[0], clock=lambda: clocks[1])
    ident = sessions.start(123, start, 456, "de", account)
    clocks[0] += seconds
    clocks[1] += seconds
    sessions.stop()
    return ident


def test_portable_data_and_credentials_are_encrypted_and_imported(linked_devices):
    first, second, folder = linked_devices
    group = first.store.add_group("Private group")
    ident = first.store.save_account(
        first.vault, "Private account", "private-user", "game-secret", "de", group
    )
    session = record_session(first, ident, 0, 18)
    webhook = "https://example.invalid/secret-hook"
    first.store.set("discord_webhook", first.vault.encrypt(webhook, "discord-webhook"), meta=True)
    first.store.set("launch_profiles", {"Gruppe / DE": [ident]})
    first.store.set("window_profiles", {"Minis": {"layout": "grid"}})
    first.store.set("region_language_de", "us")
    second.store.set("region_language_de", "de")
    first.store.set("region_install_de", r"C:\Games\Wizards")
    second.store.set("region_install_de", r"D:\Games\Wizards")
    first.store.set("ffmpeg_path", r"C:\Tools\ffmpeg.exe")
    first.store.set("window_account_links", {"local-window": ident})
    files = {
        "themes/custom.json": b'{"name":"Private theme"}',
        "addons/example/data/state.json": b"Private addon data",
        "recordings/clip.mkv": b"Private video frames" * 85_000,
    }
    for filename, content in files.items():
        save_file(first, filename, content)
    code = new_code()
    assert first.connect(folder, code, create=True).uploaded == len(files)
    result = second.connect(folder, code, create=False)
    assert result.devices == 2
    assert result.downloaded == len(files)
    assert second.code() == code
    assert first.vault.key != second.vault.key
    assert first.store.credentials(first.vault, ident) == second.store.credentials(second.vault, ident)
    assert second.store.accounts()[0]["group_id"] == group
    assert second.store.accounts()[0]["total_seconds"] == 18
    assert second.store.query("SELECT id,pid,hwnd,elapsed FROM sessions") == [
        {"id": session, "pid": 0, "hwnd": 0, "elapsed": 18}
    ]
    assert Sessions(second.store).activity_24h() == 18
    assert second.vault.decrypt(second.store.get("discord_webhook", meta=True), "discord-webhook") == webhook
    assert second.store.get("launch_profiles") == {"Gruppe / DE": [ident]}
    assert second.store.get("window_profiles") == {"Minis": {"layout": "grid"}}
    assert second.store.get("region_language_de") == "us"
    assert second.store.get("region_install_de") == r"D:\Games\Wizards"
    assert second.store.get("ffmpeg_path") is None
    assert second.store.get("window_account_links") is None
    for filename, content in files.items():
        assert (second.paths.root / filename).read_bytes() == content
    private = [code.encode(), b"game-secret", b"Private account", b"Private video frames", webhook.encode()]
    for path in folder.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert all(value not in data for value in private)
    assert code.encode() not in first.paths.database.read_bytes()
    first.vault.lock()
    with pytest.raises(CloudError, match="Tresor"):
        first.sync()


def test_offline_edits_merge_and_deletions_survive_old_device_packets(linked_devices, tmp_path):
    first, second, folder = linked_devices
    old = first.store.save_account(first.vault, "Old", "old-user", "old-password", "de")
    shared = first.store.save_account(first.vault, "Shared", "shared-user", "shared-password", "de")
    first.store.set("launch_profiles", {"Solo": [old]})
    code = new_code()
    first.connect(folder, code, create=True)
    other_folder = tmp_path / "provider-offline"
    transfer(folder, other_folder)
    second.connect(other_folder, code, create=False)
    first.store.save_account(
        first.vault, "Renamed", "shared-user", "shared-password", "de", account_id=shared
    )
    second.store.save_account(second.vault, "Shared", "new-user", "new-password", "de", account_id=shared)
    with first.store.transaction() as db:
        db.execute("DELETE FROM accounts WHERE id=?", (old,))
    with second.store.transaction() as db:
        db.execute("UPDATE accounts SET nickname='Edited while offline' WHERE id=?", (old,))
    first.store.set("launch_profiles", {"Morgens": [shared]})
    second.store.set("launch_profiles", {"Solo": [old], "Abends": [shared]})
    first.store.set("region_language_de", "us")
    second.store.set("font_size", 14)
    record_session(first, shared, 0, 9)
    record_session(second, shared, 60, 13)
    first.sync()
    second.sync()
    transfer(other_folder, folder)
    first.sync()
    transfer(folder, other_folder)
    second.sync()
    transfer(other_folder, folder)
    assert first.sync().changed == frozenset()
    assert second.sync().changed == frozenset()
    for sync in (first, second):
        (account,) = sync.store.accounts()
        assert account["id"] == shared
        assert account["nickname"] == "Renamed"
        assert account["total_seconds"] == 22
        assert account["session_count"] == 2
        assert sync.store.credentials(sync.vault, shared) == {
            "username": "new-user",
            "password": "new-password",
        }
        assert sync.store.get("launch_profiles") == {"Morgens": [shared], "Abends": [shared]}
        assert sync.store.get("region_language_de") == "us"
        assert sync.store.get("font_size") == 14
    # A restarted device uses its persisted checkpoint and identity.
    restarted = CloudSync(second.paths, second.store, second.vault)
    assert restarted.device_id() == second.device_id()
    assert restarted.sync().changed == frozenset()
    assert list((second.paths.root / "backups" / "cloud").glob("*.sqlite3"))


def test_profile_arrives_before_files_and_authentication_preserves_existing_file(linked_devices):
    first, second, folder = linked_devices
    account = first.store.save_account(first.vault, "Account", "user", "password", "de")
    relative = "recordings/clip.mkv"
    clip = save_file(first, relative, b"original clip")
    code = new_code()
    first.connect(folder, code, create=True)
    (original_object,) = folder.rglob("*.wqo")
    original_payload = original_object.read_bytes()
    original_object.unlink()
    assert second.connect(folder, code, create=False).pending == 1
    assert second.store.accounts()[0]["id"] == account
    local_clip = second.paths.root / relative
    assert not local_clip.exists()
    original_object.write_bytes(original_payload)
    assert second.sync().downloaded == 1
    assert local_clip.read_bytes() == b"original clip"

    clip.write_bytes(b"updated clip")
    assert first.sync(settle=0).uploaded == 1
    (updated_object,) = [path for path in folder.rglob("*.wqo") if path != original_object]
    content = updated_object.read_bytes()
    updated_object.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    assert second.sync().pending == 1
    assert local_clip.read_bytes() == b"original clip"
    updated_object.write_bytes(content)
    assert second.sync().downloaded == 1
    assert local_clip.read_bytes() == b"updated clip"
    assert (
        next((second.paths.root / "backups" / "cloud" / "files").rglob("clip.mkv")).read_bytes()
        == b"original clip"
    )


def test_unavailable_folder_and_wrong_code_preserve_local_changes(linked_devices):
    first, second, folder = linked_devices
    code = new_code()
    first.connect(folder, code, create=True)
    with pytest.raises(CloudError, match="Profil fehlt"):
        second.connect(folder, new_code(), create=False)
    assert second.config() is None
    second.connect(folder, code, create=False)
    offline = folder.with_name("offline")
    folder.rename(offline)
    account = second.store.save_account(second.vault, "Offline", "user", "password", "us")
    with pytest.raises(CloudError, match="nicht erreichbar"):
        second.sync()
    offline.rename(folder)
    second.sync()
    first.sync()
    assert first.store.accounts()[0]["id"] == account


def test_recovery_uses_the_baseline_from_the_restored_database(tmp_path):
    folder = tmp_path / "provider"
    folder.mkdir()
    root = tmp_path / "launcher"
    with device(root) as first:
        first.store.set("font_size", 10)
        first.connect(folder, new_code(), create=True)
        backup = first.store.backup(first.paths.directory("backups"))
        first.store.set("font_size", 14)
        account = first.store.save_account(first.vault, "Recovered", "user", "password", "de")
        first.sync()
    restore_backup(backup, Paths(root).database)
    with device(root) as restored:
        assert restored.store.get("font_size") == 10
        assert restored.store.accounts() == []
        restored.sync()
        assert restored.store.get("font_size") == 14
        assert restored.store.accounts()[0]["id"] == account


@pytest.mark.parametrize("name", ("addons/../settings.ini", "themes/aux.json", "recordings/a.mkv:stream"))
def test_cloud_paths_stay_inside_portable_profile(profile, name):
    paths, _, _ = profile
    with pytest.raises(CloudError, match="Dateipfad"):
        safe_file(paths.root, name)
