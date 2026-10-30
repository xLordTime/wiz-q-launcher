from __future__ import annotations

import csv
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import backend
from .sessions import duration
from .settings import REGIONS, SETTINGS, get
from .widgets import Button, Combo, label, panel, row

ROLE = Qt.ItemDataRole.UserRole


def page(title, subtitle):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(16)
    layout.addWidget(label(title, name="title"))
    layout.addWidget(label(subtitle, muted=True))
    return widget, layout


class AccountDialog(QDialog):
    def __init__(self, window, account=None):
        super().__init__(window)
        self.window, self.account = window, account
        self.setWindowTitle("Account bearbeiten" if account else "Account hinzufügen")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Deine Zugangsdaten bleiben verschlüsselt auf diesem PC.", muted=True))
        form = QFormLayout()
        self.nick, self.user, self.password = QLineEdit(), QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.region, self.group = Combo(), Combo()
        for code, name in REGIONS.items():
            self.region.addItem(f"{code.upper()} · {name}", code)
        self.group.addItem("Ohne Gruppe", None)
        for g in window.store.query("SELECT * FROM groups ORDER BY position"):
            self.group.addItem(g["name"], g["id"])
        self.region.setCurrentIndex(self.region.findData(get(window.store, "current_region")))
        for title, control in (
            ("Nickname", self.nick),
            ("Username", self.user),
            ("Passwort", self.password),
            ("Region", self.region),
            ("Gruppe", self.group),
        ):
            form.addRow(title, control)
        layout.addLayout(form)
        visible = QCheckBox("Passwort kurz anzeigen")
        visible.toggled.connect(
            lambda on: self.password.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(visible)
        from PySide6.QtCore import QTimer

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(lambda: visible.setChecked(False))
        visible.toggled.connect(lambda on: self.hide_timer.start(10000) if on else self.hide_timer.stop())
        self.error = label("", muted=True)
        layout.addWidget(self.error)
        layout.addLayout(
            row(Button("Abbrechen", self.reject), Button("Account speichern", self.save, primary=True))
        )
        if account:
            credentials = window.store.credentials(window.vault, account["id"])
            self.nick.setText(account["nickname"])
            self.user.setText(credentials["username"])
            self.password.setText(credentials["password"])
            self.region.setCurrentIndex(self.region.findData(account["region"]))
            self.group.setCurrentIndex(max(0, self.group.findData(account["group_id"])))

    def save(self):
        try:
            self.window.store.save_account(
                self.window.vault,
                self.nick.text(),
                self.user.text(),
                self.password.text(),
                self.region.currentData(),
                self.group.currentData(),
                self.account["id"] if self.account else None,
            )
            self.password.clear()
            self.accept()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(
                str(exc)
                if isinstance(exc, ValueError)
                else "Nicht gespeichert. Freien Speicher und Schreibrechte prüfen."
            )


class AccountTree(QTreeWidget):
    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Nickname / Gruppe", "Region", "Spielzeit", "Sitzungen"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class AccountsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(label("Account Management", name="title"))
        layout.addWidget(
            label("Ordnen, gruppieren, gemeinsam starten. Zugangsdaten bleiben lokal.", muted=True)
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Accounts nach Nickname oder Region finden …")
        layout.addWidget(self.search)
        self.tree = AccountTree()
        layout.addWidget(self.tree, 1)
        layout.addLayout(
            row(
                Button("＋ Account", self.add, primary=True),
                Button("＋ Gruppe", self.add_group),
                Button("Bearbeiten", self.edit),
                Button("★ Favorit", self.favorite),
                Button("Entfernen", self.remove),
            )
        )
        self.search.textChanged.connect(self.filter)
        self.tree.itemDoubleClicked.connect(lambda *_: self.edit())
        self.tree.reordered.connect(self.reorder)
        self.refresh()

    def selected(self):
        ids = {i.data(0, ROLE) for i in self.tree.selectedItems() if i.data(0, ROLE + 1) == "account"}
        return [a for a in self.window.store.accounts() if a["id"] in ids]

    def refresh(self):
        self.tree.clear()
        groups = {None: QTreeWidgetItem(["Ohne Gruppe"])}
        for g in self.window.store.query("SELECT * FROM groups ORDER BY position"):
            groups[g["id"]] = QTreeWidgetItem([g["name"]])
        for ident, item in groups.items():
            item.setData(0, ROLE, ident)
            item.setData(0, ROLE + 1, "group")
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDropEnabled
            )
            self.tree.addTopLevelItem(item)
            item.setExpanded(True)
        for a in self.window.store.accounts():
            item = QTreeWidgetItem(
                [
                    ("★  " if a["favorite"] else "") + a["nickname"],
                    a["region"].upper(),
                    duration(a["total_seconds"]),
                    str(a["session_count"]),
                ]
            )
            item.setData(0, ROLE, a["id"])
            item.setData(0, ROLE + 1, "account")
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
            )
            groups.get(a["group_id"], groups[None]).addChild(item)
        self.filter(self.search.text())

    def filter(self, text):
        text = text.casefold()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                item = group.child(j)
                item.setHidden(
                    text not in (item.text(0) + " " + item.text(1) + " " + group.text(0)).casefold()
                )

    def add(self):
        if self.window.ensure_unlocked() and AccountDialog(self.window).exec():
            self.window.refresh_accounts()

    def edit(self):
        accounts = self.selected()
        if len(accounts) != 1:
            self.window.notice("Einen Account zum Bearbeiten auswählen.")
            return
        if self.window.ensure_unlocked() and AccountDialog(self.window, accounts[0]).exec():
            self.window.refresh_accounts()

    def add_group(self):
        name, ok = QInputDialog.getText(self, "Gruppe", "Gruppenname")
        if ok and name.strip():
            self.window.store.add_group(name)
            self.window.refresh_accounts()

    def favorite(self):
        with self.window.store.transaction() as db:
            for a in self.selected():
                db.execute("UPDATE accounts SET favorite=1-favorite WHERE id=?", (a["id"],))
        self.window.refresh_accounts()

    def remove(self):
        selected = self.selected()
        if selected:
            if (
                QMessageBox.question(
                    self,
                    "Accounts entfernen",
                    "Ausgewählte Accounts entfernen? Ihre bisherigen Sitzungen bleiben ohne Accountzuordnung erhalten.",
                )
                == QMessageBox.StandardButton.Yes
            ):
                with self.window.store.transaction() as db:
                    for a in selected:
                        db.execute("DELETE FROM accounts WHERE id=?", (a["id"],))
        else:
            item = self.tree.currentItem()
            ident = item.data(0, ROLE) if item else None
            if (
                ident
                and QMessageBox.question(
                    self, "Gruppe entfernen", "Gruppe entfernen? Accounts bleiben ohne Gruppe erhalten."
                )
                == QMessageBox.StandardButton.Yes
            ):
                with self.window.store.transaction() as db:
                    db.execute("DELETE FROM groups WHERE id=?", (ident,))
        self.window.refresh_accounts()

    def reorder(self):
        try:
            with self.window.store.transaction():
                for i in range(self.tree.topLevelItemCount()):
                    group = self.tree.topLevelItem(i)
                    if group.data(0, ROLE + 1) != "group":
                        raise ValueError("Accounts bitte in eine Gruppe ziehen.")
                    ids = [group.child(j).data(0, ROLE) for j in range(group.childCount())]
                    self.window.store.reorder(ids, group.data(0, ROLE))
        except Exception:
            self.window.notice("Accounts bitte auf eine Gruppe oder innerhalb einer Gruppe ziehen.")
        self.window.refresh_accounts()


class LaunchPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        hero, hero_layout = panel()
        hero.setObjectName("hero")
        hero_layout.addWidget(label("Die nächste Reise beginnt hier.", name="heroTitle"))
        hero_layout.addWidget(label("Deine Accounts. Deine Welten. Ein gemeinsamer Start.", muted=True))
        layout.addWidget(hero)
        self.region, self.group = Combo(), Combo()
        self.region.addItem("Alle Regionen", "all")
        for code, name in REGIONS.items():
            self.region.addItem(f"{code.upper()} · {name}", code)
        self.region.setCurrentIndex(max(0, self.region.findData(get(window.store, "current_region"))))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Account suchen …")
        layout.addLayout(row(self.search, self.region, self.group))
        self.accounts = QListWidget()
        self.accounts.setMinimumHeight(130)
        layout.addWidget(self.accounts, 2)
        self.launch_button = Button("▶ Auswahl starten · Autologin", self.launch_selected, primary=True)
        self.count = QSpinBox()
        self.count.setRange(1, 8)
        self.count.setPrefix("Instanzen: ")
        layout.addLayout(
            row(self.launch_button, self.count, Button("Leere Instanz öffnen", self.launch_empty))
        )
        self.profiles = Combo()
        layout.addLayout(
            row(
                self.profiles,
                Button("Startprofil speichern", self.save_profile),
                Button("Profil laden", self.load_profile),
                Button("Alle auswählen", self.select_all),
            )
        )
        layout.addWidget(label("Laufende Instanzen", name="title"))
        self.running = QListWidget()
        self.running.setMinimumHeight(110)
        layout.addWidget(self.running, 1)
        layout.addLayout(
            row(
                Button("Fenster fokussieren", self.focus),
                Button("Anordnen", window.arrange_windows),
                Button("Layout speichern", window.save_layout),
                Button("Account zuordnen", self.assign),
            )
        )
        self.region.currentIndexChanged.connect(self.refresh)
        self.group.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.running.itemDoubleClicked.connect(lambda *_: self.focus())
        self.refresh_groups()

    def refresh_groups(self):
        selected = self.group.currentData() if self.group.count() else "all"
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem("Alle Gruppen", "all")
        self.group.addItem("Ohne Gruppe", None)
        for g in self.window.store.query("SELECT * FROM groups ORDER BY position"):
            self.group.addItem(g["name"], g["id"])
        self.group.setCurrentIndex(max(0, self.group.findData(selected)))
        self.group.blockSignals(False)
        self.profiles.clear()
        for name in self.window.store.get("launch_profiles", {}):
            self.profiles.addItem(name)
        self.refresh()

    def refresh(self, *_):
        checked = (
            self.window.store.get("last_launch_selection", [])
            if self.accounts.count() == 0
            else self.selected_ids()
        )
        self.accounts.clear()
        for a in self.window.store.accounts():
            if self.region.currentData() not in ("all", a["region"]):
                continue
            if self.group.currentData() != "all" and self.group.currentData() != a["group_id"]:
                continue
            if self.search.text().casefold() not in a["nickname"].casefold():
                continue
            item = QListWidgetItem(
                ("★  " if a["favorite"] else "")
                + a["nickname"]
                + "    ·    "
                + a["region"].upper()
                + "    ·    "
                + duration(a["total_seconds"])
            )
            item.setData(ROLE, a["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if a["id"] in checked else Qt.CheckState.Unchecked)
            self.accounts.addItem(item)
        if not self.accounts.count():
            self.accounts.setToolTip(
                "Noch keine Accounts für diesen Filter. Account Management öffnen oder eine leere Instanz starten."
            )

    def selected_ids(self):
        return [
            self.accounts.item(i).data(ROLE)
            for i in range(self.accounts.count())
            if self.accounts.item(i).checkState() == Qt.CheckState.Checked
        ]

    def select_all(self):
        for i in range(self.accounts.count()):
            self.accounts.item(i).setCheckState(Qt.CheckState.Checked)

    def launch_selected(self):
        ids = self.selected_ids()
        if not ids:
            self.window.notice("Mindestens einen Account auswählen oder eine leere Instanz öffnen.")
            return
        if self.window.ensure_unlocked():
            self.window.store.set("last_launch_selection", ids)
            self.window.launch_accounts([a for a in self.window.store.accounts() if a["id"] in ids])

    def launch_empty(self):
        region = self.region.currentData()
        if region == "all":
            self.window.notice("Für eine leere Instanz zuerst eine bestimmte Region auswählen.")
            return
        self.window.launch_accounts([None] * self.count.value(), region)

    def save_profile(self):
        ids = self.selected_ids()
        if not ids:
            self.window.notice("Zuerst Accounts auswählen.")
            return
        name, ok = QInputDialog.getText(self, "Startprofil", "Name für diese Auswahl")
        if ok and name.strip():
            profiles = self.window.store.get("launch_profiles", {})
            profiles[name.strip()] = ids
            self.window.store.set("launch_profiles", profiles)
            self.refresh_groups()

    def load_profile(self):
        ids = self.window.store.get("launch_profiles", {}).get(self.profiles.currentText(), [])
        self.region.setCurrentIndex(0)
        self.group.setCurrentIndex(0)
        self.search.clear()
        for i in range(self.accounts.count()):
            self.accounts.item(i).setCheckState(
                Qt.CheckState.Checked if self.accounts.item(i).data(ROLE) in ids else Qt.CheckState.Unchecked
            )

    def current_instance(self):
        item = self.running.currentItem()
        if not item:
            raise ValueError("Eine laufende Instanz auswählen.")
        return item.data(ROLE)

    def focus(self):
        self.window.guard(lambda: backend.focus(self.current_instance()["hwnd"]))

    def assign(self):
        def act():
            instance = self.current_instance()
            accounts = self.window.store.accounts()
            choices = [f"{a['nickname']} · {a['region'].upper()} · {a['id'][:6]}" for a in accounts]
            chosen, ok = QInputDialog.getItem(self, "Instanz zuordnen", "Account", choices, 0, False)
            if ok:
                a = accounts[choices.index(chosen)]
                identity = (instance["pid"], instance["created"])
                if identity not in self.window.sessions.live:
                    self.window.sessions.start(*identity, instance["hwnd"], a["region"], a["id"])
                else:
                    self.window.sessions.assign(*identity, a["id"])

        self.window.guard(act)

    def refresh_running(self, found):
        selection = self.running.currentItem().data(ROLE)["pid"] if self.running.currentItem() else None
        self.running.clear()
        names = {a["id"]: a["nickname"] for a in self.window.store.accounts()}
        for instance in found:
            state = self.window.sessions.live.get((instance["pid"], instance["created"]), {})
            text = (
                names.get(state.get("account_id"), "Nicht zugeordnet")
                + f"    ·    PID {instance['pid']}    ·    "
                + duration(state.get("seconds", 0))
            )
            item = QListWidgetItem(text)
            item.setData(ROLE, instance)
            self.running.addItem(item)
            if selection == instance["pid"]:
                self.running.setCurrentItem(item)


class PlaytimePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(label("Playtime", name="title"))
        self.summary = label("", name="metric")
        layout.addWidget(self.summary)
        layout.addWidget(
            label(
                "Client-Laufzeit einschließlich historischer Summen. Gleichzeitige Accounts zählen getrennt; 24h-Aktivität zählt Überschneidungen nur einmal.",
                muted=True,
            )
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Nickname oder Region filtern …")
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Account", "Region", "Gesamtzeit", "Sitzungen"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 2)
        layout.addWidget(label("Neue Sitzungen nach Tag", muted=True))
        self.days = QListWidget()
        layout.addWidget(self.days, 1)
        layout.addLayout(
            row(Button("Statistik als CSV exportieren", self.export), Button("Aktualisieren", self.refresh))
        )
        self.search.textChanged.connect(self.refresh)

    def refresh(self, *_):
        accounts = self.window.store.accounts()
        self.summary.setText(
            duration(sum(a["total_seconds"] for a in accounts))
            + " insgesamt   ·   "
            + duration(self.window.sessions.activity_24h())
            + " aktiv / 24h"
        )
        visible = [
            a
            for a in accounts
            if self.search.text().casefold() in (a["nickname"] + " " + a["region"]).casefold()
        ]
        self.table.setRowCount(len(visible))
        for index, a in enumerate(visible):
            for col, text in enumerate(
                (a["nickname"], a["region"].upper(), duration(a["total_seconds"]), str(a["session_count"]))
            ):
                self.table.setItem(index, col, QTableWidgetItem(text))
        self.days.clear()
        for r in self.window.store.query(
            "SELECT date(started,'unixepoch','localtime') day,SUM(elapsed) seconds,COUNT(*) count FROM sessions GROUP BY day ORDER BY day DESC LIMIT 60"
        ):
            self.days.addItem(f"{r['day']}    ·    {duration(r['seconds'])}    ·    {r['count']} Sitzungen")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Statistik exportieren", "WizQ-Spielzeit.csv", "CSV (*.csv)"
        )
        if path:

            def write():
                with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.writer(handle, delimiter=";")
                    writer.writerow(["Nickname", "Region", "Sekunden", "Sitzungen"])
                    for a in self.window.store.accounts():
                        # Avoid spreadsheet formula execution from account nicknames.
                        name = a["nickname"]
                        if name.startswith(("=", "+", "-", "@")):
                            name = "'" + name
                        writer.writerow([name, a["region"], a["total_seconds"], a["session_count"]])
                self.window.notice("Statistik exportiert.")

            self.window.guard(write)


ARTICLES = {
    "Schnellstart": "# Willkommen bei Wiz Q Launcher 6\n\n1. Unter **Einstellungen → Launcher & Regionen** den Spielordner je Region auswählen.\n2. Im **Account Management** einen Nickname, Username, Passwort und die passende Region speichern.\n3. Unter **Launch** die Accounts ankreuzen und **Auswahl starten** wählen.\n\nEine **leere Instanz** startet ohne gespeicherte Zugangsdaten. Nach Spielupdates kann Autologin vorübergehend nicht verfügbar sein. In diesem Fall bleibt die manuelle Anmeldung möglich.",
    "Accounts & Gruppen": "# Accounts und Gruppen\n\nDer Nickname ist dein frei änderbarer Anzeigename; der Username wird für die Anmeldung benötigt. Passwörter werden nicht gekürzt oder getrimmt. Gruppen organisieren Accounts, ohne Zugangsdaten zu duplizieren.\n\n**Beispiel:** Eine Gruppe ‚DE-Team‘ und eine Gruppe ‚US‘. Ziehe einen Account auf einen Gruppennamen oder innerhalb einer Gruppe an seine gewünschte Position. Sterne markieren Favoriten. Ein Startprofil speichert die Auswahl anhand stabiler Account-IDs.",
    "Regionen & Autologin": "# Regionen und Autologin\n\nDE und US können unterschiedliche Installationsordner und Spielmuster verwenden. Der Launcher wechselt bei einem fehlenden Regionspfad niemals still zur anderen Installation.\n\n**Spielordner** bedeutet der Ordner, der **Bin/WizardGraphicalClient.exe** enthält. Die Serverprofile wurden aus 5.x übernommen; ihre aktuelle Verfügbarkeit und Autologin müssen pro Region geprüft werden.\n\nDas native Backend basiert auf Deimos wizlaunch und verwendet einen temporären Spielspeicher-Hook. Fehlende oder mehrdeutige Muster brechen die Anmeldung ab. ‚Anmeldebefehl gesendet‘ ist keine Bestätigung einer erfolgreichen Serveranmeldung. Steam-Start ist in dieser ersten Beta noch kein freigegebener Ablauf.",
    "Spielzeit": "# Spielzeit verstehen\n\nGemessen wird die **Client-Laufzeit**, keine AFK- oder Charakterspielzeit. Zwei gleichzeitig laufende Accounts ergeben zwei Accountstunden pro realer Stunde. Die 24h-Aktivität vereint Überschneidungen.\n\nHistorische Summen werden genau einmal importiert. Eine nachträgliche Tageshistorie lässt sich daraus nicht rekonstruieren. Neue Tageswerte beziehen sich auf den Sitzungstag.\n\nAlle zehn Sekunden wird ein Zwischenstand gespeichert. Nach einem Absturz wird bis zum letzten gespeicherten Stand gezählt; die Zeit bis zum nächsten PC-Start zählt nicht. Lange Suspend-/Zeitlücken werden nicht pauschal gutgeschrieben. Nicht zugeordnete externe Clients kannst du im Launch-Tab einem Account zuweisen.",
    "Sicherheit & Sicherungen": "# Sicherheit und Wiederherstellung\n\nPasswörter und Webhook-URLs sind authentifiziert verschlüsselt. Ohne Masterpasswort schützt Windows den Profilschlüssel für dein Benutzerkonto. Ein PC-Wechsel benötigt einen passwortgeschützten Export. Ein vergessenes echtes Masterpasswort kann der Launcher nicht umgehen.\n\nEinstellungen werden in SQLite mit WAL und FULL-Synchronisation geschrieben. Regelmäßige Sicherungen werden vor Aktivierung geprüft. Eine lokale Kopie schützt nicht vor dem Verlust der ganzen Festplatte.\n\nBei beschädigter Datenbank bietet der Startdialog eine geprüfte Sicherung an. Die Originaldateien bleiben im Recovery-Ordner erhalten. Normale Sicherungen bewahren auch den bisherigen Schutzmodus; der Export mit Transportpasswort ist für Umzüge gedacht.",
    "Updates": "# Updates\n\nDer Wechsel von 5.x darf eine neue EXE herunterladen. Die alten Daten im AppData-Profil bleiben erhalten und werden beim ersten Start übernommen. Der alte 5.5.1-Austauschfehler kann einen einmaligen manuellen Start nötig machen.\n\n6.0 wählt das richtige Produkt-Asset explizit und prüft Größe und SHA256 gegen die über HTTPS gelieferte GitHub-Release-Metadatei. Das ist **keine zusätzliche Herausgebersignatur**. Fehlt der Digest oder stimmt er nicht, erfolgt kein Austausch.\n\nVor dem Austausch gibt es einen Datensnapshot und eine vorige EXE. Ein Helper wartet auf das Ende des alten Prozesses. Startet die neue App nicht erfolgreich, wird nach ihrem Ende zurückgerollt. Eine noch laufende App wird wegen eines verzögerten Entsperrdialogs nicht abgewürgt.",
    "Addons": "# Addons\n\nStat Monitor, Clips and Record und Theme Creator sind enthalten und einzeln abschaltbar. Aufnahme startet niemals automatisch. Deaktivierte Erweiterungen geben ihre Timer/Prozesse frei.\n\nEigene Erweiterungen liegen in **addons/<id>/addon.json** und werden erst nach bewusster Aktivierung ausgeführt. Ein eigener Prozess schützt gegen manche Abstürze, ist aber **keine Sicherheitssandbox**: fremder Python-Code läuft mit deinen Benutzerrechten. Installiere nur Code, dem du vertraust.\n\nDie Entwickleranleitung und ein lauffähiges Beispiel befinden sich im Repository unter **documentation/ADDON_SDK.md** und **examples/addons**.",
    "Clips & Aufnahme": "# Clips and Record\n\nWähle ein laufendes Wizard101-Fenster. **Aufnahme** schreibt eine MKV-Datei; **Replay** speichert komprimierte Fünf-Sekunden-Segmente und verwirft ältere Segmente nach Dauer/Speicherlimit. **Clip speichern** setzt die letzten vollständigen Segmente als MP4 zusammen. Am Anfang kann der Clip kürzer sein; das gerade geschriebene Segment ist nicht enthalten.\n\nFFmpeg muss vorhanden sein; Pfad unter Einstellungen setzen. Es wird kein Encoder ungefragt heruntergeladen. Benötigt: gdigrab, libx264, AAC bei Audio. Audio bleibt aus, bis ein genauer DirectShow-Gerätename eingetragen ist. Minimierte Fenster können je nach Spiel/Grafiktreiber schwarze Bilder ergeben.\n\nBei wenig Speicher wird gestoppt. Fertige Aufnahmen werden nicht automatisch gelöscht.",
    "Themes & Leistung": "# Themes und Leistung\n\n20 mitgelieferte Themes haben eigene Paletten, Formen und Hintergrundmotive. Animierte Themes funktionieren auch statisch. **Sparsam** schaltet dekorative Bewegung aus; verdeckte/minimierte Fenster pausieren Effekte.\n\nDer Theme Creator erzeugt JSON-Daten, keinen ausführbaren Code. Live-Vorschau, Kontrastanzeige und Import/Export helfen beim Gestalten. Ungültige Designs werden nicht geladen.\n\n**Shortcuts:** Strg+1 bis Strg+6 für die Hauptseiten, Strg+L zum Sperren, F1 für Hilfe, Strg+Q zum vollständigen Beenden. Globale Hotkeys: Strg+Alt+L startet die gespeicherte Auswahl; Strg+Alt+C speichert einen Replay-Clip.",
    "Discord": "# Discord\n\nDie bisherigen Funktionen bleiben über Einstellungen steuerbar. **Normale Wizard101-Spielerkennung bevorzugen** gibt den Launcher-Status frei, solange Spielinstanzen laufen. Deaktiviere diese Option für den eigenen Launcher-Rich-Presence-Status.\n\nNicknames erscheinen nur nach Aktivierung der entsprechenden Sichtbarkeitsoption. Webhook-URL und Zugangsdaten werden nicht öffentlich gezeigt. Webhook-Benachrichtigungen sind optional. Discord muss für lokale RPC laufen, ein eigener Botserver ist nicht nötig.",
    "Fehlerhilfe": "# Häufige Probleme\n\n**Spielordner fehlt:** Den richtigen Regionsordner mit der Bin-Unterstruktur wählen.\n\n**Autologin nicht verfügbar:** Kompilierten Windows-Build mit nativem Adapter verwenden; nach Spielupdates kann eine neue Backend-Version nötig sein. Leere Instanz starten und manuell anmelden.\n\n**Tresor gesperrt:** Mit dem bisherigen Schutzmodus entsperren. Keinen neuen Tresor über die vorhandenen Daten legen.\n\n**Speichern fehlgeschlagen:** Freien Speicher, Schreibrechte und Virenscanner prüfen. Bei Fehlern werden die letzten gültigen Daten nicht durch leere Defaults ersetzt.\n\n**Problem mit Theme/Addon:** Mit **--safe-mode** starten. Benutzerdefinierte Themes und Erweiterungen bleiben dabei deaktiviert.\n\n**Versionsstatus:** Dies ist eine Entwicklungs-Beta. Windows-/Client-Tests vor Stable sind erforderlich.",
}


class HelpPage(QWidget):
    def __init__(self, window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(label("Help", name="title"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Funktion, Einstellung oder Problem suchen …")
        layout.addWidget(self.search)
        split = QSplitter()
        self.topics, self.body = QListWidget(), QTextBrowser()
        self.body.setOpenExternalLinks(False)
        self.body.anchorClicked.connect(
            lambda url: QDesktopServices.openUrl(url) if url.scheme() == "https" else None
        )
        split.addWidget(self.topics)
        split.addWidget(self.body)
        split.setStretchFactor(1, 3)
        layout.addWidget(split)
        self.articles = dict(ARTICLES)
        for spec in SETTINGS:
            self.articles["Einstellung · " + spec.title] = (
                f"# {spec.title}\n\nBereich: **{spec.section}**\n\n{spec.help}\n\nStandardwert: **{spec.default}**\n\nTechnischer Schlüssel: **{spec.key}**"
            )
        self.topics.currentTextChanged.connect(
            lambda title: self.body.setMarkdown(self.articles.get(title, ""))
        )
        self.search.textChanged.connect(self.filter)
        self.filter("")

    def filter(self, text):
        self.topics.clear()
        for title, body in self.articles.items():
            if text.casefold() in (title + " " + body).casefold():
                self.topics.addItem(title)
        if self.topics.count():
            self.topics.setCurrentRow(0)

    def open_topic(self, text):
        self.search.setText(text)
