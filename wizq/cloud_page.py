"""Opt-in cloud linking and unattended synchronization in the existing Addons UI."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .cloud import CloudSync, new_code
from .widgets import Button, Task, label, row


class CloudPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.service = CloudSync(window.paths, window.store, window.vault)
        self.busy = False
        self.exit_flushed = False
        self.last_success = None
        self.failure = ""
        self.timer = QTimer(self)
        self.timer.setInterval(30_000)
        self.timer.timeout.connect(self.automatic)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Cloud-Synchronisierung", name="title"))
        layout.addWidget(
            label(
                "Wähle auf jedem Gerät denselben synchronisierten Ordner in OneDrive, Dropbox, Google Drive oder einem anderen Cloud-Dienst. "
                "Der Launcher verschlüsselt dein Profil und deine Dateien. Dein Cloud-Dienst überträgt sie.",
                muted=True,
            )
        )
        self.folder = label("")
        self.status = label("")
        layout.addWidget(self.folder)
        layout.addWidget(self.status)
        self.create_button = Button("Cloud-Profil erstellen …", self.create, primary=True)
        self.join_button = Button("Gerät verbinden …", self.join)
        layout.addLayout(row(self.create_button, self.join_button))
        self.sync_button = Button("Jetzt abgleichen", self.sync, primary=True)
        self.code_button = Button("Cloud-Schlüssel anzeigen …", self.show_key)
        self.disconnect_button = Button("Dieses Gerät trennen", self.disconnect)
        layout.addLayout(row(self.sync_button, self.code_button, self.disconnect_button))
        self.automatic_box = QCheckBox("Automatisch abgleichen, solange der Tresor entsperrt ist")
        self.automatic_box.setChecked(window.store.get("cloud_automatic", True))
        self.automatic_box.toggled.connect(self.toggle_automatic)
        layout.addWidget(self.automatic_box)
        layout.addWidget(
            label(
                "Accounts, Gruppen, Spielzeit, Einstellungen, Start- und Fensterprofile sowie Themes, Add-on-Dateien und Aufnahmen wandern mit. "
                "Spiel- und FFmpeg-Pfade sowie Aufnahmegeräte richtest du auf jedem PC ein.",
                muted=True,
            )
        )
        layout.addWidget(Button("Hilfe zur Cloud", lambda: window.open_help("Cloud-Synchronisierung")))
        layout.addStretch()
        self.refresh()

    def refresh(self):
        config = self.service.config()
        connected = bool(config)
        self.folder.setText(str(config["folder"]) if connected else "Dieses Gerät ist lokal eingerichtet.")
        for button in (self.create_button, self.join_button):
            button.setEnabled(not self.busy and not connected)
        for button in (self.sync_button, self.code_button, self.disconnect_button):
            button.setEnabled(not self.busy and connected)
        self.automatic_box.setEnabled(not self.busy and connected)
        if self.busy:
            self.status.setText("Cloud-Profil wird abgeglichen …")
        elif not connected:
            self.status.setText("Cloud-Verknüpfung ist aus.")
        elif self.failure:
            self.status.setText(self.failure)
        elif self.window.vault.key is None:
            self.status.setText("Abgleich pausiert, bis du den Tresor entsperrst.")
        elif self.last_success is not None:
            stamp, result = self.last_success
            message = (
                f"Letzter Abgleich {stamp} · {result.devices} Gerät(e) · "
                f"{result.uploaded} Dateien bereitgestellt · {result.downloaded} Dateien geladen"
            )
            if result.pending:
                message += f" · {result.pending} Dateien ausstehend"
            self.status.setText(message)
        else:
            self.status.setText("Verbunden. Der Cloud-Dienst überträgt den verschlüsselten Ordner.")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def start(self):
        if self.enabled() and self.service.config() and self.automatic_box.isChecked():
            self.timer.start()
            QTimer.singleShot(1000, self.automatic)

    def stop(self):
        self.timer.stop()

    def enabled(self):
        return self.window.addon_enabled("cloud-sync") and not self.window.shutting_down

    def toggle_automatic(self, enabled):
        self.window.store.set("cloud_automatic", enabled)
        if enabled:
            self.start()
        else:
            self.stop()

    def automatic(self):
        if self.timer.isActive() and self.enabled() and self.window.vault.key is not None:
            self.run(self.service.sync)
        else:
            self.refresh()

    def pick_folder(self):
        return QFileDialog.getExistingDirectory(
            self, "Synchronisierten Cloud-Ordner wählen", str(Path.home())
        )

    def create(self):
        if not self.enabled() or not self.window.ensure_unlocked():
            return
        folder = self.pick_folder()
        if folder:
            code = new_code()
            self.run(
                lambda: self.service.connect(folder, code, create=True),
                lambda: self.key_dialog(code),
                manual=True,
            )

    def join(self):
        if not self.enabled() or not self.window.ensure_unlocked():
            return
        folder = self.pick_folder()
        if not folder:
            return
        code, ok = QInputDialog.getText(
            self, "Cloud-Profil verbinden", "Cloud-Schlüssel", QLineEdit.EchoMode.Password
        )
        if ok:
            self.run(lambda: self.service.connect(folder, code, create=False), manual=True)

    def show_key(self):
        if self.window.ensure_unlocked():
            self.window.guard(lambda: self.key_dialog(self.service.code()))

    def key_dialog(self, code):
        dialog = QDialog(self)
        dialog.setWindowTitle("Cloud-Schlüssel")
        dialog.setMinimumWidth(510)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            label(
                "Diesen Schlüssel für das zweite Gerät sicher aufbewahren. Er öffnet das gesamte Cloud-Profil."
            )
        )
        text = QLineEdit(code)
        text.setReadOnly(True)
        text.setAccessibleName("Cloud-Schlüssel")
        layout.addWidget(text)
        layout.addWidget(Button("Schließen", dialog.accept))
        text.selectAll()
        dialog.exec()
        text.clear()

    def disconnect(self):
        if self.busy:
            return
        self.window.guard(self.service.disconnect)
        self.stop()
        self.failure = ""
        self.last_success = None
        self.refresh()

    def sync(self):
        if self.enabled() and self.window.ensure_unlocked():
            self.run(lambda: self.service.sync(settle=0), manual=True)

    def files_in_use(self):
        active = set()
        if self.window.addons_page.workers:
            active.add("addons")
        page = self.window.addons_page.capture
        if page.clip_tasks or (page.capture.process is not None and not page.capture.replay):
            active.add("recordings")
        return frozenset(active)

    def run(self, work, after=None, *, manual=False):
        if self.busy or self.window.updating or self.window.launch_tasks or QApplication.activeModalWidget():
            if manual:
                self.window.notice(
                    "Nach Abschluss der laufenden Aktion kannst du das Cloud-Profil abgleichen."
                )
            return False
        self.service.file_blocked = self.files_in_use()
        self.busy = True
        self.failure = ""
        self.refresh()
        task = Task(work)
        task.signals.error.connect(self.error)
        task.signals.done.connect(self.finished)
        self.window.run_task(task, lambda result: self.completed(result, after))
        return True

    def error(self, message):
        self.failure = message

    def finished(self):
        self.busy = False
        self.refresh()
        if self.window.close_after_cloud:
            QTimer.singleShot(0, self.window.quit_app)

    def completed(self, result, after):
        self.last_success = time.strftime("%H:%M:%S"), result
        if not self.timer.isActive() and not self.exit_flushed:
            self.start()
        window = self.window
        changed = result.changed
        if "settings/last_launch_selection" in changed:
            window.launch_page.checked = set(window.store.get("last_launch_selection", []))
        if any(key.startswith(("accounts/", "groups/")) for key in changed):
            with window.store.lock:
                ids = {account["id"] for account in window.store.accounts()}
                for state in window.sessions.live.values():
                    if state["account_id"] not in ids:
                        state["account_id"] = None
            window.refresh_accounts()
        else:
            if any(key.startswith("launch_profiles/") for key in changed):
                window.launch_page.refresh_groups()
            elif "settings/last_launch_selection" in changed:
                window.launch_page.refresh()
            if window.stack.currentIndex() == 2 and any(
                key.startswith(("sessions/", "activity/", "recent/")) for key in changed
            ):
                window.playtime_page.refresh()
        if any(key.startswith("files/addons/") for key in changed):
            window.addons_page.refresh_custom_controls()
        if any(key.startswith("settings/addon:") for key in changed):
            window.addons_page.refresh_builtin_controls()
        themes = any(key.startswith("files/themes/") for key in changed)
        if themes or "settings/theme" in changed:
            window.addons_page.themes.refresh()
        window.settings_page.refresh_cloud_settings(changed, themes)
        if themes or changed.intersection(
            {"settings/theme", "settings/font_size", "settings/animations", "settings/performance"}
        ):
            window.apply_theme()
        if after and not window.close_after_cloud:
            QTimer.singleShot(0, after)

    def flush_on_exit(self):
        if (
            self.exit_flushed
            or not self.enabled()
            or self.window.vault.key is None
            or self.window.updating
            or self.window.restore_path is not None
            or not self.service.config()
            or not self.automatic_box.isChecked()
        ):
            return False

        def flush():
            with self.window.store.lock:
                self.window.sessions.stop()
            return self.service.sync(profile_only=True)

        if not self.run(flush):
            return False
        self.exit_flushed = True
        self.stop()
        return True
