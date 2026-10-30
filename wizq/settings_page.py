from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import backend, updates
from .settings import SETTINGS, get, set_value
from .storage import Store
from .themes import catalog
from .vault import Vault
from .widgets import Button, Combo, Task, label, panel, row


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(label("Einstellungen", name="title"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Einstellung finden …")
        layout.addWidget(self.search)
        split = QSplitter()
        self.categories = QListWidget()
        self.sections = list(dict.fromkeys(s.section for s in SETTINGS))
        self.categories.addItems(self.sections)
        self.categories.setMaximumWidth(230)
        split.addWidget(self.categories)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(10, 0, 10, 10)
        self.body.setSpacing(12)
        self.rows, self.controls = [], {}
        for spec in SETTINGS:
            card, content = panel()
            heading = label(spec.title)
            content.addWidget(heading)
            content.addWidget(label(spec.help, muted=True))
            value = get(window.store, spec.key)
            if spec.key == "theme":
                control = Combo()
                for theme in catalog(window.paths.directory("themes")):
                    control.addItem(theme.name, theme.id)
                control.setCurrentIndex(max(0, control.findData(value)))
                control.currentIndexChanged.connect(
                    lambda _, k=spec.key, c=control: self.save(k, c.currentData())
                )
            elif spec.choices:
                control = Combo()
                for choice in spec.choices:
                    control.addItem(str(choice), choice)
                control.setCurrentIndex(max(0, control.findData(value)))
                control.currentIndexChanged.connect(
                    lambda _, k=spec.key, c=control: self.save(k, c.currentData())
                )
            elif isinstance(spec.default, bool):
                control = QCheckBox("Aktiviert")
                control.setChecked(value)
                control.toggled.connect(lambda val, k=spec.key: self.save(k, val))
            elif isinstance(spec.default, int):
                control = QSpinBox()
                control.setRange(spec.low, spec.high)
                control.setValue(value)
                control.valueChanged.connect(lambda val, k=spec.key: self.save(k, val))
            else:
                control = QLineEdit(str(value))
                control.editingFinished.connect(lambda k=spec.key, c=control: self.save(k, c.text()))
            control.setAccessibleName(spec.title)
            control.setToolTip(spec.help)
            self.controls[spec.key] = control
            actions = row(control, Button("?", lambda _, k=spec.title: window.open_help(k)))
            if spec.key.startswith("region_install_") or spec.key == "ffmpeg_path":
                actions.addWidget(
                    Button("Auswählen …", lambda _, k=spec.key, c=control: self.pick_path(k, c))
                )
            content.addLayout(actions)
            self.body.addWidget(card)
            self.rows.append((spec.section, spec.title + " " + spec.help + " " + spec.key, card))
        self.extra("Launcher & Regionen", self.install_actions())
        self.extra("Sicherheit", self.security_actions())
        self.extra("Speicher & Sicherungen", self.backup_actions())
        self.extra("Discord", self.discord_actions())
        self.extra("Updates", self.update_actions())
        self.body.addStretch()
        scroll.setWidget(body)
        split.addWidget(scroll)
        split.setStretchFactor(1, 1)
        layout.addWidget(split)
        self.categories.currentTextChanged.connect(self.filter)
        self.search.textChanged.connect(self.filter)
        self.categories.setCurrentRow(0)
        self.update_info = None
        self.update_path = None

    def extra(self, section, card):
        self.rows.append((section, section, card))
        self.body.addWidget(card)

    def filter(self, *_):
        query = self.search.text().casefold()
        section = self.categories.currentItem().text() if self.categories.currentItem() else "Allgemein"
        for category, text, card in self.rows:
            card.setVisible(query in text.casefold() if query else category == section)

    def save(self, key, value):
        try:
            set_value(self.window.store, key, value)
            if key in ("theme", "animations", "performance", "font_size"):
                self.window.apply_theme()
            self.window.notice("Gespeichert", transient=True)
        except Exception as exc:
            self.window.notice("Nicht gespeichert: " + str(exc))

    def pick_path(self, key, control):
        path = (
            QFileDialog.getOpenFileName(self, "FFmpeg auswählen", "", "Programm (*.exe)")[0]
            if key == "ffmpeg_path"
            else QFileDialog.getExistingDirectory(self, "Spielordner auswählen")
        )
        if path:
            control.setText(str(Path(path)))
            self.save(key, str(Path(path)))

    def install_actions(self):
        card, layout = panel()
        layout.addWidget(label("Installationen erkennen", name="metric"))
        layout.addWidget(
            label(
                "Sucht in den üblichen KingsIsle-Ordnern. Vorhandene Pfade werden nicht überschrieben.",
                muted=True,
            )
        )
        layout.addWidget(Button("Automatisch erkennen", self.detect))
        return card

    def detect(self):
        def done(found):
            for code, path in found.items():
                key = "region_install_" + code
                if not get(self.window.store, key):
                    self.controls[key].setText(path)
                    self.save(key, path)
            self.window.notice(f"{len(found)} Installation(en) erkannt.")

        self.window.task(backend.detect_installs, done)

    def security_actions(self):
        card, layout = panel()
        layout.addWidget(label("Tresorschutz", name="metric"))
        layout.addWidget(
            label(
                "Windows-Schutz für diesen Benutzer oder echtes Masterpasswort. Ein Wechsel erhält die Zugangsdaten.",
                muted=True,
            )
        )
        layout.addLayout(
            row(
                Button("Masterpasswort setzen/ändern", self.change_password),
                Button("Windows-Schutz verwenden", self.use_windows),
                Button("Jetzt sperren", self.window.lock_vault),
            )
        )
        return card

    def change_password(self):
        if not self.window.ensure_unlocked():
            return
        password = self.window.ask_new_password()
        if password is not None:
            self.window.guard(lambda: self.window.vault.change_protection(password))

    def use_windows(self):
        if self.window.ensure_unlocked():
            self.window.guard(lambda: self.window.vault.change_protection())

    def backup_actions(self):
        card, layout = panel()
        layout.addWidget(label("Sicherung & Umzug", name="metric"))
        layout.addWidget(
            label(
                "Normale Sicherungen bewahren deinen Schutzmodus. Ein Export mit Transportpasswort kann auf einem anderen PC entsperrt werden.",
                muted=True,
            )
        )
        layout.addLayout(
            row(
                Button("Jetzt sichern", self.window.backup),
                Button("Sicherung wiederherstellen", self.restore),
                Button("Geschützt exportieren", self.export_profile),
            )
        )
        layout.addWidget(
            Button(
                "Profilordner öffnen",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.window.paths.root))),
            )
        )
        return card

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Sicherung wählen",
            str(self.window.paths.directory("backups")),
            "Launcher-Sicherung (*.sqlite3)",
        )
        if path:
            self.window.request_restore(Path(path))

    def export_profile(self):
        if not self.window.ensure_unlocked():
            return
        password = self.window.ask_new_password("Transportpasswort für Export")
        if password is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Geschützter Export", "WizQ-Profil.sqlite3", "Launcher-Sicherung (*.sqlite3)"
        )
        if not path:
            return
        key = self.window.vault.key

        def export():
            temp = Path(tempfile.mkdtemp(dir=self.window.paths.directory("cache"), prefix="export-"))
            try:
                copy = self.window.store.backup(temp)
                snapshot = Store(copy)
                try:
                    vault = Vault(snapshot)
                    vault.key = key
                    vault.change_protection(password)
                finally:
                    snapshot.close()
                staged = Path(path).with_suffix(".part")
                shutil.copy2(copy, staged)
                import os

                os.replace(staged, path)
                return path
            finally:
                shutil.rmtree(temp, ignore_errors=True)

        self.window.task(export, lambda _: self.window.notice("Geschütztes Profil exportiert."))

    def discord_actions(self):
        card, layout = panel()
        layout.addWidget(label("Webhook-URL", name="metric"))
        self.webhook = QLineEdit()
        self.webhook.setEchoMode(QLineEdit.EchoMode.Password)
        self.webhook.setPlaceholderText("Neue URL eingeben · vorhandene URL wird nicht angezeigt")
        layout.addWidget(self.webhook)
        layout.addLayout(
            row(
                Button("Verschlüsselt speichern", self.save_webhook),
                Button("Webhook entfernen", self.remove_webhook),
            )
        )
        return card

    def save_webhook(self):
        from urllib.parse import urlparse

        value = self.webhook.text()
        url = urlparse(value)
        if (
            url.scheme != "https"
            or url.netloc not in ("discord.com", "discordapp.com")
            or not url.path.startswith("/api/webhooks/")
        ):
            self.window.notice("Eine gültige HTTPS-Discord-Webhook-URL eingeben.")
            return
        if self.window.ensure_unlocked():
            self.window.store.set(
                "discord_webhook", self.window.vault.encrypt(value, "discord-webhook"), meta=True
            )
            self.webhook.clear()
            self.window.notice("Webhook verschlüsselt gespeichert.")

    def remove_webhook(self):
        self.window.store.set("discord_webhook", None, meta=True)
        self.window.notice("Webhook entfernt.")

    def update_actions(self):
        card, layout = panel()
        layout.addWidget(label("Launcher aktualisieren", name="metric"))
        layout.addWidget(
            label(
                "Prüft Größe und SHA256 anhand der GitHub-Release-API über HTTPS. Zusätzliche Herausgebersignatur ist in dieser Beta noch nicht eingerichtet.",
                muted=True,
            )
        )
        self.update_status = label("Noch keine Prüfung.")
        self.update_status.setTextFormat(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.TextFormat.PlainText
        )
        layout.addWidget(self.update_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.check_button = Button("Nach Updates suchen", self.check_update)
        self.download_button = Button("Herunterladen", self.download_update)
        self.download_button.setEnabled(False)
        self.apply_button = Button("Neustarten & anwenden", self.apply_update, primary=True)
        self.apply_button.setEnabled(False)
        layout.addLayout(row(self.check_button, self.download_button, self.apply_button))
        return card

    def check_update(self):
        self.check_button.setEnabled(False)
        self.update_status.setText("GitHub wird geprüft …")

        def done(info):
            self.update_info = info
            self.download_button.setEnabled(info is not None)
            self.update_status.setText(
                f"Version {info['version']} verfügbar.\n\n{info['notes'][:3000]}"
                if info
                else "Keine neuere Version im gewählten Kanal verfügbar."
            )

        task = self.window.task(lambda: updates.check(get(self.window.store, "update_channel")), done)
        task.signals.done.connect(lambda: self.check_button.setEnabled(True))

    def download_update(self):
        if not self.update_info:
            return
        info = dict(self.update_info)
        self.download_button.setEnabled(False)
        self.progress.show()
        self.progress.setValue(0)
        task = Task(
            lambda: updates.download(info, self.window.paths.directory("updates"), task.signals.progress.emit)
        )
        task.signals.progress.connect(self.progress.setValue)

        def done(path):
            self.update_path = path
            self.update_status.setText("Download vollständig und SHA256 geprüft. Bereit für den Neustart.")
            import sys

            self.apply_button.setEnabled(getattr(sys, "frozen", False) and sys.platform == "win32")

        self.window.run_task(task, done)

    def apply_update(self):
        if self.update_info and self.update_path:
            if self.window.launch_tasks:
                self.window.notice(
                    "Zuerst die laufenden Spielstarts abschließen lassen, dann das Update anwenden."
                )
                return
            self.window.updating = True
            self.window.setEnabled(False)
            task = self.window.task(
                lambda: updates.prepare_apply(
                    self.window.paths, self.window.store, self.update_path, self.update_info
                ),
                lambda _: self.window.quit_app(),
            )

            def failed(_):
                self.window.updating = False
                self.window.setEnabled(True)

            task.signals.error.connect(failed)
