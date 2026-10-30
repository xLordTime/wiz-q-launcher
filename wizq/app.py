from __future__ import annotations

import argparse
import ctypes
import math
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from cryptography.fernet import InvalidToken
from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__, backend, updates
from .addon_pages import AddonsPage
from .hotkeys import Hotkeys
from .migration import legacy_sources, migrate
from .pages import AccountsPage, HelpPage, LaunchPage, PlaytimePage
from .paths import Paths, ProfileLock
from .sessions import Sessions
from .settings import get
from .settings_page import SettingsPage
from .storage import ProfileError, Store, check_database, restore_backup
from .themes import BUILTINS, Backdrop, catalog, stylesheet
from .vault import Vault
from .widgets import Button, Task, label, row


def password_dialog(parent, title, confirm=False, windows_option=False):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(470)
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        label(
            "Accounts werden lokal verschlüsselt gespeichert. Ein vergessenes echtes Masterpasswort kann nicht umgangen werden.",
            muted=True,
        )
    )
    windows = QCheckBox("Windows-Schutz für dieses Benutzerkonto verwenden")
    windows.setChecked(windows_option and sys.platform == "win32")
    if windows_option and sys.platform == "win32":
        layout.addWidget(windows)
    form = QFormLayout()
    password, repeat = QLineEdit(), QLineEdit()
    for field in (password, repeat):
        field.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("Masterpasswort", password)
    if confirm:
        form.addRow("Wiederholen", repeat)
    layout.addLayout(form)
    error = label("")
    layout.addWidget(error)

    def accept():
        if windows.isChecked():
            dialog.accept()
        elif confirm and (len(password.text()) < 8 or password.text() != repeat.text()):
            error.setText("Mindestens 8 Zeichen; beide Eingaben müssen übereinstimmen.")
        else:
            dialog.accept()

    layout.addLayout(row(Button("Abbrechen", dialog.reject), Button("Weiter", accept, primary=True)))
    windows.toggled.connect(lambda on: (password.setEnabled(not on), repeat.setEnabled(not on)))
    password.setEnabled(not windows.isChecked())
    repeat.setEnabled(not windows.isChecked())
    if not dialog.exec():
        return False, None
    value = None if windows.isChecked() else password.text()
    password.clear()
    repeat.clear()
    return True, value


def unlock(vault, parent=None):
    if vault.mode == "windows":
        try:
            vault.unlock()
            return True
        except ValueError as exc:
            QMessageBox.warning(parent, "Windows-Schutz", str(exc))
            return False
    while True:
        ok, password = password_dialog(parent, "Tresor entsperren")
        if not ok:
            return False
        try:
            vault.unlock(password)
            return True
        except ValueError as exc:
            QMessageBox.warning(parent, "Nicht entsperrt", str(exc))


def app_icon():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="16" fill="#19152c"/><circle cx="32" cy="32" r="22" fill="none" stroke="#dfc17c" stroke-width="2"/><path d="M42 19 35 35 20 44 27 27Z" fill="#dfc17c"/><circle cx="32" cy="32" r="3" fill="#19152c"/></svg>'
    pix = QPixmap()
    pix.loadFromData(svg)
    return QIcon(pix)


class Window(QMainWindow):
    def __init__(self, paths, store, vault, safe_mode=False):
        super().__init__()
        self.paths, self.store, self.vault, self.safe_mode = paths, store, vault, safe_mode
        self.sessions = Sessions(store)
        self.tasks, self.launch_tasks = set(), set()
        self.pool, self.launch_pool = QThreadPool(self), QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.force_quit, self.restore_path = False, None
        self.last_interaction = self.last_backup = time.monotonic()
        self.poll_pending = self.rpc_pending = False
        self.shutting_down = False
        self.found = []
        self.setWindowTitle("Wiz Q Launcher · " + __version__)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(950, 670)
        size = store.get("window_size", [1240, 840])
        self.resize(max(950, min(1800, int(size[0]))), max(670, min(1100, int(size[1]))))
        self.background = Backdrop(BUILTINS[10])
        root = QVBoxLayout(self.background)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(self.background)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(208)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 20, 12, 14)
        side.setSpacing(7)
        self.brand = label("WIZ Q\nLAUNCHER", name="metric")
        side.addWidget(self.brand)
        self.version_label = label("VERSION 6 · BETA", muted=True)
        side.addWidget(self.version_label)
        side.addSpacing(20)
        self.stack, self.nav = QStackedWidget(), []
        for i, text in enumerate(
            ("◈   Launch", "☷   Accounts", "◷   Playtime", "◇   Addons", "⚙   Einstellungen", "?   Help")
        ):
            button = Button(text, lambda _, index=i: self.navigate(index))
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setToolTip(text)
            side.addWidget(button)
            self.nav.append(button)
        side.addStretch()
        side.addWidget(Button("☰  Navigation", self.collapse_sidebar))
        side.addWidget(Button("Tresor sperren", self.lock_vault))
        side.addWidget(Button("Tutorial", self.tutorial))
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.status = label("Bereit · Daten lokal geschützt", muted=True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setContentsMargins(20, 7, 20, 7)
        root.addWidget(self.status)
        self.launch_page, self.accounts_page = LaunchPage(self), AccountsPage(self)
        self.playtime_page, self.addons_page = PlaytimePage(self), AddonsPage(self)
        self.settings_page, self.help_page = SettingsPage(self), HelpPage(self)
        for page in (
            self.launch_page,
            self.accounts_page,
            self.playtime_page,
            self.addons_page,
            self.settings_page,
            self.help_page,
        ):
            self.stack.addWidget(page)
        self.fade_effect = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(self.fade_effect)
        self.fade_effect.setOpacity(1)
        self.fade = QPropertyAnimation(self.fade_effect, b"opacity", self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.apply_theme()
        self.navigate(0)
        for i in range(6):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda index=i: self.navigate(index))
        QShortcut(QKeySequence("F1"), self, activated=lambda: self.open_help(""))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.lock_vault)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("Wiz Q Launcher 6")
            menu = QMenu(self)
            menu.addAction("Öffnen", self.reveal)
            menu.addAction("Auswahl starten", self.launch_page.launch_selected)
            menu.addAction("Tresor sperren", self.lock_vault)
            menu.addSeparator()
            menu.addAction("Beenden", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda reason: self.reveal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
            )
            self.tray.show()
        self.hotkeys = Hotkeys(QApplication.instance(), self.launch_page.launch_selected, self.hotkey_clip)
        from integrations.discord_presence import DEFAULT_CLIENT_ID, DiscordRichPresence

        self.rpc = DiscordRichPresence(DEFAULT_CLIENT_ID)
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(10000)
        self.heartbeat.timeout.connect(self.poll)
        self.heartbeat.start()
        self.maintenance = QTimer(self)
        self.maintenance.setInterval(30000)
        self.maintenance.timeout.connect(self.maintain)
        self.maintenance.start()
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(200, self.poll)

    def apply_theme(self):
        themes = BUILTINS if self.safe_mode else catalog(self.paths.directory("themes"))
        ident = "obsidian" if self.safe_mode else get(self.store, "theme")
        self.theme = next((t for t in themes if t.id == ident), BUILTINS[0])
        QApplication.instance().setStyleSheet(stylesheet(self.theme, get(self.store, "font_size")))
        palette = QApplication.palette()
        for role, color in (
            (QPalette.ColorRole.Window, self.theme.background),
            (QPalette.ColorRole.WindowText, self.theme.text),
            (QPalette.ColorRole.Base, self.theme.panel),
            (QPalette.ColorRole.Text, self.theme.text),
            (QPalette.ColorRole.Highlight, self.theme.accent),
            (QPalette.ColorRole.ButtonText, self.theme.text),
        ):
            palette.setColor(role, QColor(color))
        QApplication.setPalette(palette)
        motion = (
            get(self.store, "animations") and get(self.store, "performance") != "eco" and not self.safe_mode
        )
        if sys.platform == "win32":
            enabled = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            motion = motion and bool(enabled.value)
        Button.motion = motion
        self.background.theme, self.background.motion = self.theme, motion
        self.background.update()

    def addon_enabled(self, ident):
        return not self.safe_mode and self.store.get("addon:" + ident, True)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            self.last_interaction = time.monotonic()
        return super().eventFilter(obj, event)

    def collapse_sidebar(self):
        narrow = self.sidebar.width() > 100
        self.sidebar.setFixedWidth(78 if narrow else 208)
        self.brand.setText("WQ" if narrow else "WIZ Q\nLAUNCHER")
        self.version_label.setVisible(not narrow)
        for button in self.nav:
            button.setText(button.toolTip()[0] if narrow else button.toolTip())

    def navigate(self, index):
        self.fade.stop()
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)
        if index == 2:
            self.playtime_page.refresh()
        if Button.motion and self.isVisible():
            self.fade.setStartValue(0.25)
            self.fade.setEndValue(1.0)
            self.fade.start()
        else:
            self.fade_effect.setOpacity(1)

    def notice(self, text, transient=False):
        self.status.setText(str(text)[:600])
        if transient:
            QTimer.singleShot(
                3500,
                lambda: (
                    self.status.setText("Bereit · Daten lokal geschützt")
                    if self.status.text() == text
                    else None
                ),
            )

    def guard(self, fn):
        try:
            return fn()
        except Exception as exc:
            self.notice(
                str(exc)
                if isinstance(exc, (ValueError, RuntimeError))
                else f"{type(exc).__name__}: Aktion fehlgeschlagen. Daten bleiben erhalten."
            )

    def task(self, fn, done=None):
        task = Task(fn)
        self.run_task(task, done)
        return task

    def run_task(self, task, done=None, launch=False):
        self.tasks.add(task)
        if launch:
            self.launch_tasks.add(task)
        if done:
            task.signals.result.connect(done)
        task.signals.error.connect(self.notice)
        task.signals.done.connect(lambda: self.tasks.discard(task))
        task.signals.done.connect(lambda: self.launch_tasks.discard(task))
        (self.launch_pool if launch else self.pool).start(task)

    def refresh_accounts(self):
        self.accounts_page.refresh()
        self.launch_page.refresh_groups()
        self.playtime_page.refresh()

    def ensure_unlocked(self):
        if self.vault.key is None:
            return unlock(self.vault, self)
        self.last_interaction = time.monotonic()
        return True

    def lock_vault(self):
        self.vault.lock()
        self.notice("Tresor gesperrt · Spiele und Spielzeiterfassung bleiben aktiv.")

    def ask_new_password(self, title="Masterpasswort ändern"):
        ok, password = password_dialog(self, title, confirm=True)
        return password if ok else None

    def open_help(self, text):
        self.navigate(5)
        self.help_page.open_topic(text)

    def tutorial(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Willkommen · deine erste Reise")
        dialog.resize(580, 400)
        layout = QVBoxLayout(dialog)
        title, body = label("", name="title"), label("")
        layout.addWidget(title)
        layout.addWidget(body, 1)
        steps = [
            (
                "1 · Dein Launcher",
                "Accounts und Einstellungen bleiben auf deinem PC. Help erklärt jederzeit jede Funktion.",
            ),
            (
                "2 · Die passende Region",
                "Unter Einstellungen → Launcher & Regionen pro Region den Spielordner wählen. Er enthält Bin/WizardGraphicalClient.exe.",
            ),
            (
                "3 · Accounts organisieren",
                "Nickname, Username und Passwort im Account Management speichern. Gruppen und Drag & Drop helfen beim Sortieren.",
            ),
            (
                "4 · Gemeinsam starten",
                "Accounts unter Launch ankreuzen. Startprofile merken sich die Auswahl. Leere Instanzen starten ohne gespeicherte Zugangsdaten.",
            ),
            (
                "5 · Dein Stil",
                "Addons enthält Stat Monitor, Clips and Record und den Theme Creator mit 20 Themes. Das Sparprofil reduziert Effekte auf älteren PCs.",
            ),
        ]
        current = [0]
        button = Button("Weiter", primary=True)

        def next_step():
            current[0] += 1
            if current[0] == len(steps):
                dialog.accept()
                return
            title.setText(steps[current[0]][0])
            body.setText(steps[current[0]][1])
            button.setText("Los geht’s" if current[0] == len(steps) - 1 else "Weiter")

        button.clicked.connect(next_step)
        title.setText(steps[0][0])
        body.setText(steps[0][1])
        layout.addLayout(row(Button("Später", dialog.reject), button))
        dialog.exec()
        self.store.set("tutorial_seen", True)

    def launch_accounts(self, accounts, region=None):
        self.launch_pool.setMaxThreadCount(get(self.store, "parallel_launches"))
        if len(self.launch_tasks) + len(accounts) > 32:
            self.notice("Maximal 32 Startaufträge gleichzeitig vormerken.")
            return
        self.notice(f"{len(accounts)} Startauftrag/Startaufträge in der Warteschlange …")
        for index, account in enumerate(accounts):
            code = account["region"] if account else region

            def start(a=account, c=code, delay=get(self.store, "launch_delay") if index else 0):
                if delay:
                    time.sleep(delay)
                return backend.launch(self.store, self.vault, c, a)

            self.run_task(Task(start), self.instance_started, launch=True)

    def instance_started(self, result):
        if get(self.store, "auto_playtime_tracking"):
            self.sessions.start(
                result["pid"], result["created"], result["hwnd"], result["region"], result["account_id"]
            )
        self.notice(
            result["warning"]
            or (
                "Client gestartet · Anmeldebefehl gesendet, Serveranmeldung bitte prüfen."
                if result["account_id"]
                else "Leere Instanz gestartet."
            )
        )
        positions = self.store.get("window_placements", {})
        if result["account_id"] in positions:
            self.guard(
                lambda: backend.placement(
                    result["hwnd"], positions[result["account_id"]], get(self.store, "borderless")
                )
            )
        self.addons_page.emit_event("session.started", {"region": result["region"], "pid": result["pid"]})
        self.webhook("start", result["account_id"])
        self.poll()

    def poll(self):
        if self.poll_pending or self.shutting_down:
            return
        self.poll_pending = True

        def collect():
            ended = self.sessions.heartbeat(backend.alive)
            return backend.instances(), ended

        def done(result):
            self.found, ended = result
            for state in ended:
                self.webhook("end", state["account_id"], state["seconds"])
                self.addons_page.emit_event(
                    "session.ended", {"region": state["region"], "seconds": state["seconds"]}
                )
            visible = (
                self.found
                if get(self.store, "track_without_autologin")
                else [i for i in self.found if (i["pid"], i["created"]) in self.sessions.live]
            )
            self.launch_page.refresh_running(visible)
            if self.stack.currentIndex() == 2:
                self.playtime_page.refresh()
            self.update_discord()

        task = self.task(collect, done)
        task.signals.done.connect(lambda: setattr(self, "poll_pending", False))

    def update_discord(self):
        if self.rpc_pending:
            return
        self.rpc_pending = True
        account = next(
            (
                a
                for a in self.store.accounts()
                if any(s["account_id"] == a["id"] for s in self.sessions.live.values())
            ),
            None,
        )
        values = dict(
            total_24h_seconds=self.sessions.activity_24h(),
            selected_account_name=account["nickname"]
            if account and get(self.store, "discord_show_nickname")
            else None,
            selected_session_seconds=max((s["seconds"] for s in self.sessions.live.values()), default=0),
            active_sessions_count=len(self.found),
            region=account["region"] if account else get(self.store, "current_region"),
            total_account_playtime_seconds=account["total_seconds"] if account else 0,
        )

        def update():
            self.rpc.enabled = get(self.store, "discord_rich_presence")
            self.rpc.rpc_yield_to_game = get(self.store, "discord_rpc_yield_to_game")
            self.rpc.update_interval_seconds = get(self.store, "discord_rpc_update_interval")
            if self.rpc.enabled:
                self.rpc.update_presence(**values)
            elif self.rpc._connected:
                self.rpc.close()

        task = self.task(update)
        task.signals.done.connect(lambda: setattr(self, "rpc_pending", False))

    def webhook(self, event, account_id, seconds=0):
        if (
            not get(self.store, "discord_notifications")
            or not get(self.store, "discord_session_" + event)
            or self.vault.key is None
        ):
            return
        secret = self.store.get("discord_webhook", meta=True)
        account = next((a for a in self.store.accounts() if a["id"] == account_id), None)
        if not secret or not account:
            return
        try:
            url = self.vault.decrypt(secret, "discord-webhook")
        except Exception:
            return
        from integrations.discord_integration import DiscordIntegration

        discord = DiscordIntegration(url)
        if event == "start":
            discord.send_custom_message(
                "Wizard101 · Sitzung gestartet", account["nickname"] + " · " + account["region"].upper()
            )
        else:
            discord.send_session_ended(account["nickname"], seconds / 60)

    def maintain(self):
        if time.monotonic() - self.last_backup >= get(self.store, "backup_interval") * 60:
            self.last_backup = time.monotonic()
            self.backup()
        minutes = get(self.store, "lock_minutes")
        if (
            minutes
            and self.vault.key is not None
            and time.monotonic() - self.last_interaction >= minutes * 60
        ):
            self.lock_vault()

    def backup(self):
        return self.task(
            lambda: self.store.backup(self.paths.directory("backups"), get(self.store, "backup_keep")),
            lambda _: self.notice("Sicherung erstellt und geprüft.", transient=True),
        )

    def arrange_windows(self):
        def act():
            if not self.found:
                raise ValueError("Keine laufenden Instanzen gefunden.")
            rect = QApplication.primaryScreen().availableGeometry()
            n, mode = len(self.found), get(self.store, "window_layout")
            columns = n if mode == "horizontal" else 1 if mode == "vertical" else math.ceil(math.sqrt(n))
            rows = math.ceil(n / columns)
            for i, instance in enumerate(self.found):
                backend.placement(
                    instance["hwnd"],
                    [
                        rect.x() + (i % columns) * rect.width() // columns,
                        rect.y() + (i // columns) * rect.height() // rows,
                        rect.width() // columns,
                        rect.height() // rows,
                    ],
                    get(self.store, "borderless"),
                )

        self.guard(act)

    def save_layout(self):
        def save():
            positions = self.store.get("window_placements", {})
            for state in self.sessions.live.values():
                if state["account_id"]:
                    positions[state["account_id"]] = backend.window_rect(state["hwnd"])
            self.store.set("window_placements", positions)
            self.notice("Fensterlayout für zugeordnete Accounts gespeichert.")

        self.guard(save)

    def hotkey_clip(self):
        if self.addon_enabled("clips-record"):
            self.addons_page.capture.save_clip()

    def request_restore(self, path):
        def request():
            check_database(path, full=True)
            if (
                QMessageBox.question(
                    self,
                    "Sicherung wiederherstellen",
                    "Launcher schließen und Sicherung verwenden? Aktuelle Daten bleiben als Recovery-Kopie erhalten. Änderungen seit der Sicherung fehlen danach.",
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.restore_path = path
                self.quit_app()

        self.guard(request)

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.force_quit = True
        self.close()

    def closeEvent(self, event):
        if not self.force_quit and self.tray and get(self.store, "close_to_tray"):
            self.hide()
            event.ignore()
        elif self.launch_tasks:
            self.notice("Startvorgänge laufen noch. Nach Abschluss erneut beenden.")
            self.force_quit = False
            event.ignore()
        else:
            event.accept()
            QApplication.instance().quit()

    def shutdown(self):
        self.shutting_down = True
        QApplication.instance().removeEventFilter(self)
        self.heartbeat.stop()
        self.maintenance.stop()
        self.hotkeys.close()
        self.addons_page.shutdown()
        self.pool.waitForDone()
        self.launch_pool.waitForDone()
        self.rpc.close()
        self.sessions.stop()
        self.store.set("window_size", [self.width(), self.height()])
        if self.tray:
            self.tray.hide()


def startup_profile(paths, exe_dir):
    store = Store(paths.database)
    try:
        vault = Vault(store)
        if not vault.initialized:
            ok, password = password_dialog(
                None, "Lokalen Tresor einrichten", confirm=True, windows_option=True
            )
            if not ok:
                store.close()
                return None, None
            vault.initialize(password)
        elif not unlock(vault):
            store.close()
            return None, None
        if not store.get("migration_checked", False, meta=True):
            sources = legacy_sources(paths.root, exe_dir)
            if sources:
                source = sources[0]
                if len(sources) > 1:
                    choice, ok = QInputDialog.getItem(
                        None,
                        "Altprofil wählen",
                        "Welches alte Profil übernehmen?",
                        list(map(str, sources)),
                        0,
                        False,
                    )
                    if not ok:
                        store.close()
                        return None, None
                    source = Path(choice)
                password = None
                while True:
                    try:
                        report = migrate(store, vault, source, password)
                        QMessageBox.information(
                            None,
                            "Übernahme abgeschlossen",
                            f"{report['accounts']} Accounts und alle {report['seconds']:.0f} gespeicherten Spielzeitsekunden übernommen. Quelldateien bleiben unverändert.",
                        )
                        break
                    except (PermissionError, InvalidToken):
                        ok, password = password_dialog(None, "Bisheriges Masterpasswort für die Übernahme")
                        if not ok:
                            store.close()
                            return None, None
            store.set("migration_checked", True, meta=True)
        return store, vault
    except BaseException:
        store.close()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Wiz Q Launcher 6")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--safe-mode", action="store_true")
    parser.add_argument("--update-job", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.smoke_test and args.profile is None:
        parser.error("Smoke tests require an explicit disposable profile.")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("WizQLauncher")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(stylesheet(BUILTINS[0]))
    lock, store, window = None, None, None
    try:
        paths = Paths(args.profile.resolve()) if args.profile else Paths.default()
        paths.prepare()
        lock = ProfileLock(paths.root)
        exe_dir = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent
        )
        try:
            store, vault = startup_profile(paths, exe_dir)
        except (sqlite3.DatabaseError, ProfileError):
            backups = []
            for candidate in sorted(paths.directory("backups").glob("profile-*.sqlite3"), reverse=True):
                try:
                    check_database(candidate, full=True)
                    backups.append(candidate)
                except Exception:
                    pass
            if not backups:
                raise ProfileError(
                    "Profil beschädigt, keine geprüfte Sicherung vorhanden. Original bleibt erhalten. Eine .sqlite3-Sicherung im backups-Ordner ablegen und erneut starten."
                )
            choice, ok = QInputDialog.getItem(
                None,
                "Profil wiederherstellen",
                "Original bleibt erhalten. Geprüfte Sicherung wählen:",
                [p.name for p in backups],
                0,
                False,
            )
            if not ok:
                return 1
            restore_backup(next(p for p in backups if p.name == choice), paths.database)
            store, vault = startup_profile(paths, exe_dir)
        if store is None:
            return 0
        window = Window(paths, store, vault, args.safe_mode)
        window.show()
        store.set("last_successful_version", __version__, meta=True)
        if not store.get("tutorial_seen", False):
            QTimer.singleShot(300, window.tutorial)
        if args.update_job:
            QTimer.singleShot(
                500, lambda: window.guard(lambda: updates.confirm_start(args.update_job, paths.root))
            )
        if get(store, "check_for_updates"):
            QTimer.singleShot(3000, window.settings_page.check_update)
        if args.smoke_test:
            QTimer.singleShot(1500, window.quit_app)
        result = app.exec()
        window.shutdown()
        store.backup(paths.directory("backups"), get(store, "backup_keep"))
        store.close()
        store = None
        if window.restore_path:
            restore_backup(window.restore_path, paths.database)
            command = (
                [sys.executable]
                if getattr(sys, "frozen", False)
                else [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py")]
            )
            subprocess.Popen(command + ["--profile", str(paths.root)])
        return result
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Launcher konnte nicht starten",
            str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else f"{type(exc).__name__}: Start angehalten. Vorhandene Daten wurden nicht zurückgesetzt.",
        )
        return 1
    finally:
        if store:
            store.close()
        if lock:
            lock.close()
