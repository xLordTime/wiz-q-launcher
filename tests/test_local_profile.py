from contextlib import closing
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from wizq import app
from wizq.paths import Paths, ProfileLock
from wizq.profile_setup import create_new_local_profile
from wizq.storage import Store
from wizq.vault import Vault

OLD_PASSWORD = "existing-test-password"
NEW_PASSWORD = "different-test-password"


@pytest.fixture
def local_appdata(tmp_path, monkeypatch):
    folder = tmp_path / "Local AppData"
    folder.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(folder))
    return folder


def test_only_completed_new_profile_becomes_default(local_appdata):
    original = Paths.default()
    new = Paths.new_local()
    with pytest.raises(ValueError, match="mindestens 8"):
        create_new_local_profile("short")
    assert not list(local_appdata.iterdir())
    assert Paths.default() == original
    new.root.mkdir()
    existing_file = new.root / "existing.txt"
    existing_file.write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError, match="bereits"):
        create_new_local_profile(NEW_PASSWORD)
    assert existing_file.read_text(encoding="utf-8") == "keep me"
    assert Paths.default() == original


@pytest.mark.parametrize("startup", ("first", "existing", "migration"))
def test_three_f6_create_new_default_from_startup_password(local_appdata, startup, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    original = Paths.default()
    account = None
    if startup == "existing":
        with closing(Store(original.database)) as store:
            vault = Vault(store)
            vault.initialize(OLD_PASSWORD)
            account = store.save_account(vault, "Original", "example", "old-game-secret", "de")
            store.set("migration_checked", True, meta=True)
    elif startup == "migration":
        original.database.parent.mkdir(parents=True)
        (original.root / "config.json").write_text('{"master_password_mode":"password"}', encoding="utf-8")
        (original.database.parent / "accounts.enc.json").write_text("{}", encoding="utf-8")
    titles = {
        "first": "Lokalen Tresor einrichten",
        "existing": "Tresor entsperren",
        "migration": "Bisheriges Masterpasswort für die Übernahme",
    }
    confirm_calls, critical, started = [], [], []
    real_dialog = app.password_dialog

    def drive_password(parent, title, **options):
        if title == "Tresor für New-WizQ-Launcher einrichten":
            assert Paths.default() == original
            assert not Paths.new_local().root.exists()
            assert options["confirm"] and options["windows_option"]
            return True, NEW_PASSWORD
        if startup == "migration" and title == "Lokalen Tresor einrichten":
            return True, OLD_PASSWORD
        assert title == titles[startup]

        def press_f6():
            dialog = qt.activeModalWidget()
            dialog.activateWindow()
            qt.processEvents()
            for _ in range(2):
                QTest.keyClick(dialog, Qt.Key.Key_F6)
            confirm_calls.append("two keys")
            QTest.keyClick(dialog, Qt.Key.Key_F6)
            if dialog.isVisible():
                dialog.reject()

        QTimer.singleShot(0, press_f6)
        return real_dialog(parent, title, **options)

    def confirm(_parent, title, message, buttons, default):
        confirm_calls.append(title)
        assert "New-WizQ-Launcher" in message
        assert default == QMessageBox.StandardButton.No
        return QMessageBox.StandardButton.Yes

    def window(paths, store, vault, _safe_mode):
        assert paths == Paths.new_local() == Paths.default()
        assert store.accounts() == []
        assert store.get("migration_checked", meta=True) is True
        assert store.get("legacy_migrated", meta=True) is None
        assert vault.key is not None
        started.append(paths)
        store.set("tutorial_seen", True)
        store.set("check_for_updates", False)
        return SimpleNamespace(
            show_at_startup=lambda: QTimer.singleShot(0, qt.quit),
            shutdown=lambda: None,
            restore_path=None,
            restart_with_new_profile=False,
        )

    monkeypatch.setattr(app, "password_dialog", drive_password)
    monkeypatch.setattr(QMessageBox, "warning", confirm)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: critical.append(args))
    monkeypatch.setattr(app, "Window", window)
    assert app.main([]) == 0, critical
    assert confirm_calls == ["two keys", "Achtung · Neues Standardprofil"]
    assert started == [Paths.new_local()]
    if startup == "first":
        assert not original.database.exists()
    elif startup == "existing":
        with closing(ProfileLock(original.root)), closing(Store(original.database)) as store:
            vault = Vault(store)
            with pytest.raises(ValueError, match="Tresor nicht entsperrt"):
                vault.unlock(NEW_PASSWORD)
            vault.unlock(OLD_PASSWORD)
            assert store.credentials(vault, account)["password"] == "old-game-secret"
    else:
        assert (original.database.parent / "accounts.enc.json").read_text(encoding="utf-8") == "{}"
    with closing(Store(Paths.default().database)) as store:
        vault = Vault(store)
        with pytest.raises(ValueError, match="Tresor nicht entsperrt"):
            vault.unlock(OLD_PASSWORD)
        vault.unlock(NEW_PASSWORD)


def test_cancel_new_profile_setup_keeps_default(local_appdata, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    original = Paths.default()
    monkeypatch.setattr(app, "password_dialog", lambda *args, **kwargs: (False, None))
    assert app.main(["--new-local-profile"]) == 0
    assert Paths.default() == original
    assert not list(local_appdata.iterdir())
    assert QApplication.instance() is qt
