"""Native desktop chrome and one shared navigation state for tree, path and history."""

from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import Button

ROLE = Qt.ItemDataRole.UserRole
PAGE_NAMES = ("Alle Accounts", "Accounts verwalten", "Spielzeit", "Addons", "Einstellungen", "Hilfe")
PAGE_ICONS = ("accounts", "account", "clock", "addon", "settings", "help")
ADDON_NAMES = ("Verwalten", "Stat Monitor", "Clips and Record", "Theme Creator")


@dataclass(frozen=True)
class Location:
    page: int = 0
    group: str = "all"
    section: str = ""


@lru_cache(maxsize=128)
def desktop_icon(name, color="#3979ae"):
    """Small bundled vectors, with no font, web resource or icon-pack dependency."""
    shapes = {
        "folder": '<path d="M3 6h7l2 3h9v11H3Z" fill="{c}" fill-opacity=".24"/><path d="M3 6h7l2 3h9v11H3Z"/>',
        "account": '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3Z" fill="{c}" fill-opacity=".14"/>',
        "accounts": '<circle cx="10" cy="7" r="3.5"/><path d="M2 21v-3a8 8 0 0 1 16 0v3M17 4a4 4 0 0 1 0 8m3 3a7 7 0 0 1 2 6"/>',
        "play": '<path d="m7 3 15 9L7 21Z" fill="{c}"/>',
        "add": '<circle cx="9" cy="7" r="4"/><path d="M2 22v-4a7 7 0 0 1 12-5m5-2v10m-5-5h10"/>',
        "edit": '<path d="m4 15 12-12 5 5L9 20l-7 2Z" fill="{c}" fill-opacity=".17"/><path d="m4 15 12-12 5 5L9 20l-7 2Zm9-9 5 5"/>',
        "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l5 3"/>',
        "addon": '<path d="M3 4h6a3 3 0 1 1 6 0h6v6a3 3 0 1 0 0 6v6h-6a3 3 0 1 1-6 0H3v-6a3 3 0 1 0 0-6Z" fill="{c}" fill-opacity=".15"/>',
        "settings": '<circle cx="12" cy="12" r="4"/><path d="m10 2 4 0 1 4 4 0 3 4-3 3 1 4-4 3-3-2-4 3-4-3 1-4-3-3 2-4 4 0Z"/>',
        "help": '<circle cx="12" cy="12" r="10"/><path d="M8 8a4 4 0 0 1 8 0c0 3-4 2-4 6m0 3v1"/>',
        "window": '<rect x="2" y="4" width="20" height="16" rx="1"/><path d="M2 9h20m-16-3h1m2 0h1"/>',
        "save": '<path d="M3 3h15l3 3v15H3Zm4 0v6h10V3M7 21v-7h10v7"/>',
        "lock": '<rect x="4" y="10" width="16" height="12" rx="1"/><path d="M7 10V7a5 5 0 0 1 10 0v3m-5 5v3"/>',
        "home": '<rect x="2" y="3" width="20" height="14" rx="1"/><path d="M8 22h8m-4-5v5"/>',
        "back": '<path d="m14 4-8 8 8 8M6 12h15"/>',
        "forward": '<path d="m10 4 8 8-8 8M18 12H3"/>',
        "up": '<path d="m4 14 8-8 8 8M12 6v15"/>',
    }
    shape = shapes.get(name, shapes["folder"]).format(c=QColor(color).name())
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{QColor(color).name()}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round">{shape}</svg>'
    )
    pix = QPixmap(40, 40)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(source.encode()).render(painter)
    painter.end()
    return QIcon(pix)


class BreadcrumbBar(QFrame):
    activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("breadcrumb")
        self.setAccessibleName("Launcher-Pfadleiste")
        self.line = QHBoxLayout(self)
        self.line.setContentsMargins(5, 2, 5, 2)
        self.line.setSpacing(0)
        self.buttons = []
        self.path_text = ""
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.copy_menu)

    def set_segments(self, segments):
        while self.line.count():
            item = self.line.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.buttons = []
        self.path_text = " > ".join(text for text, _, _ in segments)
        for index, (text, destination, children) in enumerate(segments):
            if index:
                arrow = QLabel("›")
                arrow.setObjectName("pathSeparator")
                self.line.addWidget(arrow)
            button = QToolButton(self)
            button.setText(text.replace("&", "&&"))
            button.setMaximumWidth(260)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setAccessibleName("Pfad: " + text)
            button.setToolTip("Öffnen: " + text)
            button.setAutoRaise(True)
            button.clicked.connect(lambda _, target=destination: self.activated.emit(target))
            if index == 0:
                button.setIcon(desktop_icon("home"))
            if children:
                menu = QMenu(button)
                for title, target in children:
                    action = menu.addAction(title.replace("&", "&&"))
                    action.setData(target)
                    action.triggered.connect(lambda _, route=target: self.activated.emit(route))
                button.setMenu(menu)
                button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            self.line.addWidget(button)
            self.buttons.append(button)
        self.line.addStretch()

    def copy_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Pfad kopieren", lambda: QApplication.clipboard().setText(self.path_text))
        menu.exec(self.mapToGlobal(pos))


class DesktopShell:
    def build_desktop(self):
        self.location, self.history, self.history_index = Location(), [], -1
        self._routing = False
        self.group_names = {}
        self.route_items = {}
        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setObjectName("navigationTree")
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.setUniformRowHeights(True)
        self.navigation_tree.setMinimumWidth(160)
        self.navigation_tree.setIndentation(16)
        self.navigation_tree.setAnimated(False)
        self.navigation_tree.setAccessibleName("Mein Launcher – Baumansicht")
        self.navigation_tree.itemSelectionChanged.connect(self.tree_selected)
        self.sidebar = self.navigation_tree
        self.breadcrumb = BreadcrumbBar()
        self.breadcrumb.activated.connect(
            lambda target: self.go_home() if target == Location() else self.go(target)
        )
        self.desktop_split = QSplitter()
        self.desktop_split.setObjectName("desktopSplitter")
        self.desktop_split.setChildrenCollapsible(False)
        self.desktop_split.addWidget(self.navigation_tree)
        self.desktop_split.addWidget(self.stack)
        self.desktop_split.setStretchFactor(1, 1)
        widths = self.store.get("desktop_split", [205, 895])
        if isinstance(widths, list) and len(widths) == 2 and all(type(v) is int and v > 0 for v in widths):
            self.desktop_split.setSizes(widths)
        root = QVBoxLayout(self.background)
        root.setContentsMargins(5, 5, 5, 0)
        root.setSpacing(5)
        root.addWidget(self.breadcrumb)
        root.addWidget(self.desktop_split, 1)
        self.setCentralWidget(self.background)
        self.status = QLabel("Bereit · Daten lokal geschützt")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.statusBar().addWidget(self.status, 1)
        version = QLabel("Lokales Profil · Beta")
        version.setObjectName("versionStatus")
        self.statusBar().addPermanentWidget(version)
        self.actions = {}
        self.action_icons = {}

        def action(key, title, callback, icon=None, shortcut=None):
            item = QAction(title, self)
            item.triggered.connect(callback)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            self.actions[key] = item
            if icon:
                self.action_icons[key] = icon
            return item

        style = self.style()
        action("back", "Zurück", self.back, shortcut="Alt+Left")
        action("forward", "Vorwärts", self.forward, shortcut="Alt+Right")
        action("up", "Eine Ebene höher", self.up, shortcut="Alt+Up")
        for key, standard in (
            ("back", QStyle.StandardPixmap.SP_ArrowBack),
            ("forward", QStyle.StandardPixmap.SP_ArrowForward),
            ("up", QStyle.StandardPixmap.SP_ArrowUp),
        ):
            self.actions[key].setIcon(style.standardIcon(standard))
        action("home", "Mein Launcher", self.go_home, "home", "Alt+Home")
        action("launch", "Auswahl starten", self.launch_page.launch_selected, "play", "F5")
        action("empty", "Leere Instanz …", self.launch_empty_dialog, "window", "Ctrl+Shift+N")
        action("add", "Account hinzufügen …", self.accounts_page.add, "add", "Ctrl+N")
        action("group", "Gruppe hinzufügen …", self.accounts_page.add_group, "folder")
        action("edit", "Eigenschaften …", self.edit_current, "edit", "Alt+Return")
        action("backup", "Profil sichern", self.backup, "save", "Ctrl+S")
        action("layout", "Spielfenster anordnen", self.arrange_windows, "window")
        action("settings", "Einstellungen", lambda: self.navigate(4), "settings", "Ctrl+,")
        action("lock", "Tresor sperren", self.lock_vault, "lock")
        action("help", "Hilfe öffnen", lambda: self.open_help(""), "help")
        action("quit", "Beenden", self.quit_app)
        bar = self.menuBar()
        file_menu = bar.addMenu("&Datei")
        for key in ("add", "group", "empty"):
            file_menu.addAction(self.actions[key])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["backup"])
        file_menu.addAction(self.actions["lock"])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["quit"])
        edit_menu = bar.addMenu("&Bearbeiten")
        edit_menu.addAction(self.actions["edit"])
        edit_menu.addAction("Alle Accounts auswählen", self.launch_page.select_all)
        edit_menu.addAction("Startauswahl aufheben", self.launch_page.select_none)
        view_menu = bar.addMenu("&Ansicht")
        view_menu.addAction(self.actions["back"])
        view_menu.addAction(self.actions["forward"])
        view_menu.addAction(self.actions["up"])
        view_menu.addSeparator()
        for index, title in enumerate(PAGE_NAMES):
            view_menu.addAction(title, lambda i=index: self.navigate(i))
        tools_menu = bar.addMenu("E&xtras")
        tools_menu.addAction(self.actions["layout"])
        tools_menu.addAction("Fensterlayout speichern", self.save_layout)
        tools_menu.addSeparator()
        tools_menu.addAction(self.actions["settings"])
        tools_menu.addAction("Updates …", lambda: self.go(Location(4, section="Updates")))
        help_menu = bar.addMenu("&Hilfe")
        help_menu.addAction(self.actions["help"])
        help_menu.addAction("Tutorial", self.tutorial)
        toolbar = QToolBar("Werkzeugleiste", self)
        toolbar.setObjectName("desktopToolbar")
        toolbar.setIconSize(QSize(19, 19))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setFloatable(False)
        for key in ("back", "forward", "up"):
            toolbar.addAction(self.actions[key])
            toolbar.widgetForAction(self.actions[key]).setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
            )
        toolbar.addSeparator()
        for key in ("launch", "add", "edit"):
            toolbar.addAction(self.actions[key])
        toolbar.addSeparator()
        toolbar.addAction(self.actions["backup"])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(self.actions["settings"])
        self.addToolBar(toolbar)
        self.toolbar = toolbar
        view_menu.addSeparator()
        view_menu.addAction(toolbar.toggleViewAction())
        self.settings_page.categories.currentTextChanged.connect(self.section_changed)
        self.addons_page.navigation.currentRowChanged.connect(lambda _: self.section_changed())
        self.launch_page.group.currentIndexChanged.connect(self.launch_group_changed)
        self.refresh_navigation()

    def groups(self):
        return [
            ("Alle Accounts", "all"),
            ("Ohne Gruppe", "ungrouped"),
            *[(g["name"], g["id"]) for g in self.store.query("SELECT * FROM groups ORDER BY position")],
        ]

    def refresh_navigation(self):
        self.group_names = {ident: name for name, ident in self.groups()}
        with QSignalBlocker(self.navigation_tree):
            self.navigation_tree.clear()
            self.route_items = {}
            root = QTreeWidgetItem(["Mein Launcher"])
            root.setIcon(0, desktop_icon("home"))
            root.setData(0, ROLE, Location())
            self.navigation_tree.addTopLevelItem(root)
            for index, title in enumerate(PAGE_NAMES):
                item = QTreeWidgetItem(root, [title])
                item.setIcon(0, desktop_icon(PAGE_ICONS[index]))
                destination = Location(index)
                item.setData(0, ROLE, destination)
                self.route_items[destination] = item
                if index in (0, 1):
                    for name, ident in self.groups()[1:]:
                        child = QTreeWidgetItem(item, [name])
                        child.setIcon(0, desktop_icon("folder", "#b28b34"))
                        route = Location(index, ident)
                        child.setData(0, ROLE, route)
                        self.route_items[route] = child
                elif index in (3, 4):
                    for title in ADDON_NAMES if index == 3 else self.settings_page.sections:
                        child = QTreeWidgetItem(item, [title])
                        route = Location(index, section=title)
                        child.setData(0, ROLE, route)
                        child.setIcon(0, desktop_icon("addon" if index == 3 else "settings"))
                        self.route_items[route] = child
                item.setExpanded(index == 0)
            root.setExpanded(True)
        if self.history_index >= 0:
            self.go(self.location, record=False)

    def normalize_location(self, destination):
        if not isinstance(destination, Location) or destination.page not in range(6):
            return Location()
        group = destination.group if destination.group in self.group_names else "all"
        section = destination.section
        if destination.page == 4 and section and section not in self.settings_page.sections:
            section = ""
        if destination.page == 3 and section and section not in ADDON_NAMES:
            section = ""
        if destination.page not in (3, 4):
            section = ""
        return Location(destination.page, group if destination.page in (0, 1) else "all", section)

    def go(self, destination, record=True):
        if self._routing:
            return
        destination = self.normalize_location(destination)
        if record and (self.history_index < 0 or destination != self.location):
            del self.history[self.history_index + 1 :]
            self.history.append(destination)
            self.history_index = len(self.history) - 1
        self.location = destination
        self._routing = True
        previous_page = self.stack.currentIndex()
        try:
            if hasattr(self, "fade"):
                self.fade.stop()
                self.fade_effect.setOpacity(1)
            self.stack.setCurrentIndex(destination.page)
            if destination.page in (0, 1):
                self.launch_page.set_folder(destination.group)
                self.accounts_page.set_group_filter(destination.group)
            elif destination.page == 2:
                self.playtime_page.refresh()
            elif destination.page == 4:
                self.settings_page.categories.setCurrentRow(
                    self.settings_page.sections.index(destination.section) if destination.section else 0
                )
            elif destination.page == 3:
                self.addons_page.navigation.setCurrentRow(
                    ADDON_NAMES.index(destination.section) if destination.section else 0
                )
                # A disabled addon can redirect itself to its management page.
                if (
                    destination.section
                    and ADDON_NAMES[self.addons_page.navigation.currentRow()] != destination.section
                ):
                    self.location = Location(3)
            item = self.route_items.get(self.location) or self.route_items.get(Location(destination.page))
            if item:
                with QSignalBlocker(self.navigation_tree):
                    self.navigation_tree.setCurrentItem(item)
                    ancestor = item.parent()
                    while ancestor:
                        ancestor.setExpanded(True)
                        ancestor = ancestor.parent()
            if self.history_index >= 0:
                self.history[self.history_index] = self.location
            self.update_breadcrumb()
            self.actions["back"].setEnabled(self.history_index > 0)
            self.actions["forward"].setEnabled(self.history_index + 1 < len(self.history))
            self.actions["up"].setEnabled(self.location != Location())
            self.actions["edit"].setEnabled(destination.page in (0, 1))
            self.actions["launch"].setEnabled(destination.page == 0)
            if (
                hasattr(self, "fade")
                and previous_page != destination.page
                and Button.motion
                and self.isVisible()
            ):
                self.fade.setStartValue(0.88)
                self.fade.setEndValue(1.0)
                self.fade.start()
        finally:
            self._routing = False

    def update_breadcrumb(self):
        location = self.location
        roots = [(name, Location(i)) for i, name in enumerate(PAGE_NAMES)]
        segments = [("Mein Launcher", Location(), roots)]
        if location.page in (0, 1):
            siblings = [(name, Location(location.page, ident)) for name, ident in self.groups()]
            segments.append((PAGE_NAMES[location.page], Location(location.page), siblings))
            if location.group != "all":
                segments.append((self.group_names[location.group], location, siblings))
        else:
            children = []
            if location.page in (3, 4):
                names = ADDON_NAMES if location.page == 3 else self.settings_page.sections
                children = [(name, Location(location.page, section=name)) for name in names]
            segments.append((PAGE_NAMES[location.page], Location(location.page), children))
            if location.section:
                segments.append((location.section, location, children))
        self.breadcrumb.set_segments(segments)

    def navigate(self, index):
        self.go(Location(index))

    def tree_selected(self):
        item = self.navigation_tree.currentItem()
        if item:
            self.go(item.data(0, ROLE))

    def section_changed(self, *_):
        if self._routing:
            return
        if self.stack.currentIndex() == 4:
            self.go(Location(4, section=self.settings_page.categories.currentItem().text()))
        elif self.stack.currentIndex() == 3:
            self.go(Location(3, section=ADDON_NAMES[self.addons_page.navigation.currentRow()]))

    def launch_group_changed(self):
        if not self._routing and self.stack.currentIndex() == 0:
            group = self.launch_page.group.currentData()
            self.go(Location(0, "ungrouped" if group is None else group))

    def go_home(self):
        self.launch_page.search.clear()
        self.launch_page.region.setCurrentIndex(0)
        self.go(Location())

    def back(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.go(self.history[self.history_index], record=False)

    def forward(self):
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self.go(self.history[self.history_index], record=False)

    def up(self):
        location = self.location
        if location.group != "all":
            self.go(Location(location.page))
        elif location.section:
            self.go(Location(location.page))
        else:
            self.go_home()

    def edit_current(self):
        if self.stack.currentIndex() == 1:
            self.accounts_page.edit()
        else:
            self.launch_page.edit_current()

    def launch_empty_dialog(self):
        self.launch_page.empty_dialog()

    def collapse_sidebar(self):
        self.navigation_tree.setVisible(not self.navigation_tree.isVisible())

    def desktop_theme_changed(self):
        for key in ("back", "forward", "up"):
            self.actions[key].setIcon(desktop_icon(key, self.theme.text))
        for key, name in self.action_icons.items():
            color = "#79a65b" if name == "play" else self.theme.accent
            self.actions[key].setIcon(desktop_icon(name, color))
        control = self.settings_page.controls["theme"]
        with QSignalBlocker(control):
            if control.findData(self.theme.id) < 0:
                control.addItem(self.theme.name, self.theme.id)
            control.setCurrentIndex(max(0, control.findData(self.theme.id)))
        self.navigation_tree.setAnimated(Button.motion)
