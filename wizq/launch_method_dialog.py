"""Manage named launch methods and choose their local Wizard101 client."""

import sqlite3

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from .game_install import CLIENT
from .launch_methods import (
    LAUNCH_METHOD_PATH_PREFIX,
    MODE_NAMES,
    delete_launch_method,
    launch_methods,
    save_launch_method,
)
from .settings import REGIONS, get, login_endpoint
from .widgets import Button, Combo, label, row

ROLE = Qt.ItemDataRole.UserRole


def region_label(region):
    if region == "us":
        return "US · Nordamerika (NA)"
    return f"{region.upper()} · Europa · {REGIONS[region]}"


class LaunchMethodDialog(QDialog):
    def __init__(self, parent, store, method=None):
        super().__init__(parent)
        self.store = store
        self.method_id = method.id if method else None
        self.setWindowTitle("Startmethode bearbeiten" if method else "Neue Startmethode")
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(method.name if method else "")
        self.region, self.mode = Combo(), Combo()
        for region in REGIONS:
            self.region.addItem(region_label(region), region)
        for steam, title in MODE_NAMES.items():
            self.mode.addItem(title, steam)
        self.region.setCurrentIndex(
            self.region.findData(method.region if method else get(store, "current_region"))
        )
        self.mode.setCurrentIndex(self.mode.findData(method.steam if method else False))
        self.path = QLineEdit(store.get(LAUNCH_METHOD_PATH_PREFIX + method.id, "") if method else "")
        self.path.setPlaceholderText(r"A:\Spiele\Wizard101\Bin\WizardGraphicalClient.exe")
        browse = Button("Auswählen …", self.choose_client)
        browse.setAutoDefault(False)
        fields = (
            ("Name", self.name),
            ("Serverprofil", self.region),
            ("Startmodus", self.mode),
            ("Clientdatei auf diesem PC", self.path),
        )
        for title, field in fields:
            field.setAccessibleName(title)
            form.addRow(title, row(field, browse) if field is self.path else field)
        layout.addLayout(form)
        self.endpoint = label("", muted=True)
        layout.addWidget(self.endpoint)
        self.region.currentIndexChanged.connect(self.show_endpoint)
        self.mode.currentIndexChanged.connect(self.show_endpoint)
        self.show_endpoint()
        self.error = label("", muted=True)
        layout.addWidget(self.error)
        save = Button("Startmethode speichern", self.save, primary=True)
        save.setDefault(True)
        layout.addLayout(row(Button("Abbrechen", self.reject), save))

    def show_endpoint(self):
        host, port = login_endpoint(self.store, self.region.currentData(), steam=self.mode.currentData())
        self.endpoint.setText(f"Loginserver · {host}:{port}")

    def choose_client(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Wizard101-Spielclient auswählen",
            self.path.text(),
            f"Wizard101-Spielclient ({CLIENT.name})",
        )
        if filename:
            self.path.setText(filename)

    def save(self):
        try:
            self.method_id = save_launch_method(
                self.store,
                self.name.text(),
                self.region.currentData(),
                self.mode.currentData(),
                self.path.text(),
                method_id=self.method_id,
            )
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(
                str(exc) if isinstance(exc, ValueError) else "Startmethode konnte nicht gespeichert werden."
            )
            return
        self.accept()


class LaunchMethodsDialog(QDialog):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.store, self.changed = store, False
        self.setWindowTitle("Startmethoden verwalten")
        self.resize(570, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Eigene Startmethoden", name="title"))
        layout.addWidget(
            label("Wähle eine gespeicherte Methode in den Account-Eigenschaften aus.", muted=True)
        )
        self.methods_list = QListWidget()
        self.methods_list.setAccessibleName("Eigene Startmethoden")
        layout.addWidget(self.methods_list, 1)
        self.details = label("", muted=True)
        layout.addWidget(self.details)
        self.edit_button = Button("Bearbeiten …", self.edit_selected)
        self.delete_button = Button("Löschen …", self.delete_selected)
        layout.addLayout(
            row(
                Button("Neu …", lambda: self.open_editor(), primary=True),
                self.edit_button,
                self.delete_button,
                Button("Schließen", self.accept),
            )
        )
        self.methods_list.currentItemChanged.connect(self.show_selected)
        self.methods_list.itemDoubleClicked.connect(self.edit_selected)
        self.refresh()

    def selected_method(self):
        item = self.methods_list.currentItem()
        return self.methods.get(item.data(ROLE)) if item else None

    def refresh(self, selected_id=None):
        self.methods = launch_methods(self.store)
        index = 0
        with QSignalBlocker(self.methods_list):
            self.methods_list.clear()
            for method in sorted(self.methods.values(), key=lambda value: value.name.casefold()):
                item = QListWidgetItem(f"{method.name} · {region_label(method.region)}")
                item.setData(ROLE, method.id)
                self.methods_list.addItem(item)
                if method.id == selected_id:
                    index = self.methods_list.count() - 1
            self.methods_list.setCurrentRow(index)
        self.show_selected()

    def show_selected(self):
        method = self.selected_method()
        self.edit_button.setEnabled(method is not None)
        self.delete_button.setEnabled(method is not None)
        if method:
            path = self.store.get(LAUNCH_METHOD_PATH_PREFIX + method.id, "")
            self.details.setText(
                f"{MODE_NAMES[method.steam]}\n{path or 'Clientdatei auf diesem PC auswählen.'}"
            )
        else:
            self.details.setText("Noch keine eigenen Startmethoden erstellt.")

    def open_editor(self, method=None):
        editor = LaunchMethodDialog(self, self.store, method)
        if editor.exec():
            self.changed = True
            self.refresh(editor.method_id)

    def edit_selected(self):
        method = self.selected_method()
        if method:
            self.open_editor(method)

    def delete_selected(self):
        method = self.selected_method()
        if (
            not method
            or QMessageBox.question(
                self,
                "Startmethode löschen",
                "Ausgewählte Startmethode löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            delete_launch_method(self.store, method.id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.details.setText(
                str(exc) if isinstance(exc, ValueError) else "Startmethode konnte nicht gelöscht werden."
            )
            return
        self.changed = True
        self.refresh()
