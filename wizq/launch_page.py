"""Explorer account list, property pane and native instance controls."""

from datetime import datetime

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import backend
from .desktop import Location, desktop_icon
from .pages import AccountDialog
from .selection import AccountCheckDelegate, selection_colors
from .sessions import duration
from .settings import REGIONS, get
from .widgets import Button, Combo, label, row

ROLE = Qt.ItemDataRole.UserRole


class LaunchPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.checked = set(window.store.get("last_launch_selection", []))
        self.account_data = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        accounts_area = QWidget()
        body = QVBoxLayout(accounts_area)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(5)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Accounts durchsuchen …")
        self.search.setClearButtonEnabled(True)
        self.region, self.group = Combo(), Combo(self)
        self.region.addItem("Alle Regionen", "all")
        for code, name in REGIONS.items():
            self.region.addItem(code.upper() + " · " + name, code)
        self.region.setMaximumWidth(225)
        # The group control is also the controller for the tree and path menus.
        self.group.hide()
        body.addLayout(row(self.search, self.region))
        self.accounts = QTreeWidget()
        self.accounts.setObjectName("launchAccounts")
        self.accounts.setHeaderLabels(["Nickname", "Startauswahl", "Region", "Gruppe", "Spielzeit"])
        self.accounts.setItemDelegateForColumn(0, AccountCheckDelegate(self.accounts))
        self.accounts.setRootIsDecorated(False)
        self.accounts.setUniformRowHeights(True)
        self.accounts.setAlternatingRowColors(True)
        self.accounts.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.accounts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.accounts.setAllColumnsShowFocus(True)
        self.accounts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.accounts.setMinimumHeight(145)
        self.accounts.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 110), (2, 65), (3, 135), (4, 110)):
            self.accounts.setColumnWidth(column, width)
        self.accounts.setAccessibleName("Accounts – Checkboxen für die Startauswahl")
        self.accounts.itemChanged.connect(self.check_changed)
        self.accounts.currentItemChanged.connect(self.show_details)
        self.accounts.itemDoubleClicked.connect(lambda *_: self.edit_current())
        self.accounts.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.accounts.customContextMenuRequested.connect(self.context_menu)
        body.addWidget(self.accounts, 1)
        self.details = QFrame()
        self.details.setObjectName("accountDetails")
        details_line = QHBoxLayout(self.details)
        details_line.setContentsMargins(12, 9, 12, 9)
        self.account_icon = QLabel()
        self.account_icon.setPixmap(desktop_icon("account").pixmap(38, 38))
        details_line.addWidget(self.account_icon)
        detail_body = QVBoxLayout()
        detail_body.setSpacing(3)
        self.detail_name = label("Kein Account ausgewählt", name="accountName")
        self.detail_values = label("Account hinzufügen oder in der Liste auswählen.", muted=True)
        self.detail_start = label("", name="startSelectionStatus")
        detail_body.addWidget(self.detail_name)
        detail_body.addWidget(self.detail_values)
        detail_body.addWidget(self.detail_start)
        details_line.addLayout(detail_body, 1)
        details_line.addWidget(Button("Eigenschaften …", self.edit_current))
        body.addWidget(self.details)
        self.splitter.addWidget(accounts_area)
        instances = QGroupBox("Laufende Instanzen")
        instances_body = QVBoxLayout(instances)
        instances_body.setContentsMargins(7, 12, 7, 5)
        instances_body.setSpacing(4)
        self.running = QTreeWidget()
        self.running.setHeaderLabels(["Account", "Region", "Status", "Sitzung", "PID"])
        self.running.setRootIsDecorated(False)
        self.running.setUniformRowHeights(True)
        self.running.setMinimumHeight(75)
        self.running.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 65), (2, 110), (3, 110), (4, 65)):
            self.running.setColumnWidth(col, width)
        self.running.itemDoubleClicked.connect(lambda *_: self.focus())
        instances_body.addWidget(self.running, 1)
        tools = QToolBar("Instanzwerkzeuge")
        tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for text, icon, callback in (
            ("Fokussieren", "window", self.focus),
            ("Anordnen", "window", window.arrange_windows),
            ("Layout speichern", "save", window.save_layout),
            ("Account zuordnen", "account", self.assign),
            ("Neue Instanz …", "add", self.empty_dialog),
        ):
            tools.addAction(desktop_icon(icon), text, callback)
        instances_body.addWidget(tools)
        self.splitter.addWidget(instances)
        saved = window.store.get("launch_split", [365, 175])
        if isinstance(saved, list) and len(saved) == 2 and all(type(v) is int and v > 0 for v in saved):
            self.splitter.setSizes(saved)
        layout.addWidget(self.splitter, 1)
        self.profiles = Combo()
        self.profiles.setPlaceholderText("Kein Startprofil")
        self.profiles.setMinimumWidth(130)
        self.profiles.setMaximumWidth(195)
        self.profiles.setAccessibleName("Gespeichertes Startprofil")
        profile_menu = QToolButton()
        profile_menu.setText("Startprofil")
        profile_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(profile_menu)
        menu.addAction("Aktuelle Auswahl speichern …", self.save_profile)
        menu.addAction("Gewähltes Profil laden", self.load_profile)
        profile_menu.setMenu(menu)
        selection = QToolButton()
        selection.setText("Auswahl")
        selection.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        selection_menu = QMenu(selection)
        selection_menu.addAction("Alle sichtbaren auswählen", self.select_all)
        selection_menu.addAction("Sichtbare Auswahl aufheben", self.select_none)
        selection.setMenu(selection_menu)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(3, 2, 3, 3)
        bottom.setSpacing(6)
        bottom.addWidget(self.profiles)
        bottom.addWidget(profile_menu)
        bottom.addWidget(selection)
        self.selection_count = label("0 ausgewählt", muted=True)
        bottom.addWidget(self.selection_count)
        bottom.addStretch()
        self.launch_button = Button("Auswahl starten", self.launch_selected, primary=True)
        self.launch_button.setIcon(desktop_icon("play", "#639544"))
        bottom.addWidget(self.launch_button)
        layout.addLayout(bottom)
        self.count = QSpinBox(self)
        self.count.hide()
        self.count.setRange(1, 8)
        self.region.currentIndexChanged.connect(self.refresh)
        self.group.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh_groups()

    def refresh_groups(self):
        selected = self.group.currentData() if self.group.count() else "all"
        with QSignalBlocker(self.group):
            self.group.clear()
            self.group.addItem("Alle Accounts", "all")
            self.group.addItem("Ohne Gruppe", None)
            for group in self.window.store.query("SELECT * FROM groups ORDER BY position"):
                self.group.addItem(group["name"], group["id"])
            self.group.setCurrentIndex(max(0, self.group.findData(selected)))
        selected_profile = self.profiles.currentText()
        self.profiles.clear()
        for name in self.window.store.get("launch_profiles", {}):
            self.profiles.addItem(name)
        index = self.profiles.findText(selected_profile)
        if index >= 0:
            self.profiles.setCurrentIndex(index)
        self.refresh()

    def set_folder(self, group):
        with QSignalBlocker(self.group):
            self.group.setCurrentIndex(max(0, self.group.findData(None if group == "ungrouped" else group)))
        self.refresh()

    def refresh(self, *_):
        current = self.current_account()
        ident = current["id"] if current else None
        groups = {g["id"]: g["name"] for g in self.window.store.query("SELECT * FROM groups")}
        self.account_data = {a["id"]: a for a in self.window.store.accounts()}
        self.checked.intersection_update(self.account_data)
        with QSignalBlocker(self.accounts):
            self.accounts.clear()
            for a in self.account_data.values():
                if self.region.currentData() not in ("all", a["region"]):
                    continue
                if self.group.currentData() != "all" and self.group.currentData() != a["group_id"]:
                    continue
                text = a["nickname"] + " " + a["region"] + " " + groups.get(a["group_id"], "Ohne Gruppe")
                if self.search.text().casefold() not in text.casefold():
                    continue
                item = QTreeWidgetItem(
                    [
                        ("★  " if a["favorite"] else "") + a["nickname"],
                        "Ausgewählt" if a["id"] in self.checked else "—",
                        a["region"].upper(),
                        groups.get(a["group_id"], "Ohne Gruppe"),
                        duration(a["total_seconds"]),
                    ]
                )
                item.setData(0, ROLE, a["id"])
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    0, Qt.CheckState.Checked if a["id"] in self.checked else Qt.CheckState.Unchecked
                )
                item.setIcon(0, desktop_icon("account"))
                self.style_checked_item(item)
                self.accounts.addTopLevelItem(item)
                if a["id"] == ident:
                    self.accounts.setCurrentItem(item)
            if not self.accounts.currentItem() and self.accounts.topLevelItemCount():
                self.accounts.setCurrentItem(self.accounts.topLevelItem(0))
        self.accounts.setToolTip(
            "Accounts über Datei → Account hinzufügen anlegen."
            if not self.account_data
            else "Die Zeilenmarkierung zeigt Accountdetails. Häkchen und Startauswahl bestimmen, welche Accounts starten."
        )
        self.show_details()
        self.update_selection_count()

    def items(self):
        return [self.accounts.topLevelItem(i) for i in range(self.accounts.topLevelItemCount())]

    def selected_ids(self):
        # Hidden selections are remembered, but never silently launched.
        return [item.data(0, ROLE) for item in self.items() if item.checkState(0) == Qt.CheckState.Checked]

    def check_changed(self, item, column):
        if column != 0:
            return
        ident = item.data(0, ROLE)
        if item.checkState(0) == Qt.CheckState.Checked:
            self.checked.add(ident)
        else:
            self.checked.discard(ident)
        with QSignalBlocker(self.accounts):
            self.style_checked_item(item)
        self.show_details()
        self.update_selection_count()

    def style_checked_item(self, item):
        checked = item.checkState(0) == Qt.CheckState.Checked
        item.setText(1, "Ausgewählt" if checked else "—")
        item.setToolTip(1, "Startet mit der Auswahl." if checked else "Nicht für den Start ausgewählt.")
        font = self.accounts.font()
        font.setBold(checked)
        item.setFont(0, font)
        item.setFont(1, font)
        colors = selection_colors(self.window.theme) if hasattr(self.window, "theme") else None
        for column in range(self.accounts.columnCount()):
            item.setBackground(
                column, QBrush(QColor(colors.checked_background)) if checked and colors else QBrush()
            )
            item.setForeground(
                column, QBrush(QColor(colors.checked_foreground)) if checked and colors else QBrush()
            )

    def refresh_selection_style(self):
        with QSignalBlocker(self.accounts):
            for item in self.items():
                self.style_checked_item(item)
        self.accounts.viewport().update()

    def update_selection_count(self):
        count = len(self.selected_ids())
        self.selection_count.setText(f"{count} zum Starten")
        self.launch_button.setText("1 Account starten" if count == 1 else f"{count} Accounts starten")
        self.launch_button.setEnabled(count > 0)

    def select_all(self):
        for item in self.items():
            item.setCheckState(0, Qt.CheckState.Checked)

    def select_none(self):
        for item in self.items():
            item.setCheckState(0, Qt.CheckState.Unchecked)

    def current_account(self):
        item = self.accounts.currentItem()
        return self.account_data.get(item.data(0, ROLE)) if item else None

    def show_details(self, *_):
        account = self.current_account()
        if not account:
            self.detail_name.setText("Kein Account ausgewählt")
            self.detail_values.setText("Account hinzufügen oder einen anderen Ordner wählen.")
            self.detail_start.clear()
            return
        group = next(
            (
                g["name"]
                for g in self.window.store.query("SELECT * FROM groups")
                if g["id"] == account["group_id"]
            ),
            "Ohne Gruppe",
        )
        used = (
            datetime.fromtimestamp(account["last_used"]).strftime("%d.%m.%Y %H:%M")
            if account["last_used"]
            else "Noch nicht gestartet"
        )
        self.detail_name.setText(account["nickname"])
        self.detail_values.setText(
            f"{REGIONS.get(account['region'], account['region'])} · {group}\n"
            f"Spielzeit: {duration(account['total_seconds'])} · Zuletzt: {used}"
        )
        self.detail_start.setText(
            "✓ Für den Start ausgewählt"
            if account["id"] in self.selected_ids()
            else "Nicht für den Start ausgewählt · Checkbox anklicken"
        )

    def edit_current(self):
        account = self.current_account()
        if not account:
            self.window.notice("Einen Account in der Liste auswählen.")
        elif self.window.ensure_unlocked() and AccountDialog(self.window, account).exec():
            self.window.refresh_accounts()

    def context_menu(self, pos):
        item = self.accounts.itemAt(pos)
        if not item:
            return
        self.accounts.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(desktop_icon("edit"), "Eigenschaften …", self.edit_current)
        menu.addAction("Zur Startauswahl hinzufügen", lambda: item.setCheckState(0, Qt.CheckState.Checked))
        menu.addAction("Aus Startauswahl entfernen", lambda: item.setCheckState(0, Qt.CheckState.Unchecked))
        menu.exec(self.accounts.viewport().mapToGlobal(pos))

    def launch_selected(self):
        ids = self.selected_ids()
        if not ids:
            self.window.notice("Mindestens einen Account ankreuzen oder eine leere Instanz öffnen.")
            return
        if self.window.ensure_unlocked():
            self.window.store.set("last_launch_selection", ids)
            self.window.launch_accounts([a for a in self.window.store.accounts() if a["id"] in ids])

    def empty_dialog(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Quicklaunch – leere Instanz")
        dialog.setMinimumWidth(340)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        region = Combo()
        for code, name in REGIONS.items():
            region.addItem(code.upper() + " · " + name, code)
        selected = self.region.currentData()
        if selected == "all":
            selected = get(self.window.store, "current_region")
        region.setCurrentIndex(max(0, region.findData(selected)))
        count = QSpinBox()
        count.setRange(1, 8)
        count.setValue(self.count.value())
        form.addRow("Region / Serverprofil", region)
        form.addRow("Anzahl Instanzen", count)
        layout.addLayout(form)
        layout.addWidget(label("Öffnet den Spielclient ohne gespeicherte Zugangsdaten.", muted=True))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Öffnen")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            self.count.setValue(count.value())
            self.window.launch_accounts([None] * count.value(), region.currentData())

    def launch_empty(self):
        self.empty_dialog()

    def save_profile(self):
        ids = self.selected_ids()
        if not ids:
            self.window.notice("Zuerst Accounts ankreuzen.")
            return
        name, ok = QInputDialog.getText(self, "Startprofil", "Name für diese Auswahl")
        if ok and name.strip():
            profiles = self.window.store.get("launch_profiles", {})
            profiles[name.strip()] = ids
            self.window.store.set("launch_profiles", profiles)
            self.refresh_groups()
            self.profiles.setCurrentText(name.strip())

    def load_profile(self):
        ids = self.window.store.get("launch_profiles", {}).get(self.profiles.currentText())
        if ids is None:
            self.window.notice("Zuerst ein gespeichertes Startprofil wählen.")
            return
        self.search.clear()
        self.region.setCurrentIndex(0)
        self.window.go(Location())
        self.checked = set(ids)
        self.refresh()

    def current_instance(self):
        item = self.running.currentItem()
        if not item:
            raise ValueError("Eine laufende Instanz auswählen.")
        return item.data(0, ROLE)

    def focus(self):
        self.window.guard(lambda: backend.focus(self.current_instance()["hwnd"]))

    def assign(self):
        def act():
            instance = self.current_instance()
            accounts = self.window.store.accounts()
            if not accounts:
                raise ValueError("Zuerst einen Account anlegen.")
            choices = [f"{a['nickname']} · {a['region'].upper()} · {a['id'][:6]}" for a in accounts]
            chosen, ok = QInputDialog.getItem(self, "Instanz zuordnen", "Account", choices, 0, False)
            if ok:
                a = accounts[choices.index(chosen)]
                identity = (instance["pid"], instance["created"])
                if identity not in self.window.sessions.live:
                    self.window.sessions.start(*identity, instance["hwnd"], a["region"], a["id"])
                else:
                    self.window.sessions.assign(*identity, a["id"])
                self.window.poll()

        self.window.guard(act)

    def refresh_running(self, found):
        selected = self.running.currentItem()
        previous = selected.data(0, ROLE) if selected else None
        identity = (previous["pid"], previous["created"]) if previous else None
        self.running.clear()
        names = {a["id"]: a["nickname"] for a in self.window.store.accounts()}
        for instance in found:
            key = (instance["pid"], instance["created"])
            state = self.window.sessions.live.get(key, {})
            item = QTreeWidgetItem(
                [
                    names.get(state.get("account_id"), "Nicht zugeordnet"),
                    state.get("region", "—").upper(),
                    "Aktiv",
                    duration(state.get("seconds", 0)),
                    str(instance["pid"]),
                ]
            )
            item.setIcon(0, desktop_icon("window"))
            item.setData(0, ROLE, instance)
            self.running.addTopLevelItem(item)
            if key == identity:
                self.running.setCurrentItem(item)
        self.running.setToolTip(
            "Keine Instanz geöffnet." if not found else "Doppelklick fokussiert das Spielfenster."
        )
