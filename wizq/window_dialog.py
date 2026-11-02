"""Native multi-monitor layout editor; previews never move game windows."""

from __future__ import annotations

import copy
import sys

from PySide6.QtCore import QRectF, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import Button, Combo, Task, label, row
from .windowing import (
    LAYOUTS,
    MODES,
    SIZES,
    Monitor,
    arrange,
    fit_rect,
    identity,
    nearest_monitor,
    preferences,
    rectangle,
    window_config,
)

ROLE = Qt.ItemDataRole.UserRole


class MonitorCanvas(QWidget):
    edited = Signal(int, object)
    selected = Signal(int)

    def __init__(self, monitors, parent=None):
        super().__init__(parent)
        self.monitors, self.plans, self.active, self.drag = monitors, [], -1, None
        self.setMinimumSize(400, 180)
        self.setMouseTracking(True)
        self.setAccessibleName("Monitorvorschau: Fenster ziehen oder unten rechts skalieren")
        self.setToolTip(
            "Fenster auswählen und ziehen. Unten rechts die Größe ändern. Erst Anwenden bewegt die echten Spielfenster."
        )

    def transform(self):
        left = min(m.rect[0] for m in self.monitors)
        top = min(m.rect[1] for m in self.monitors)
        width = max(m.rect[0] + m.rect[2] for m in self.monitors) - left
        height = max(m.rect[1] + m.rect[3] for m in self.monitors) - top
        scale = min(max(1, self.width() - 32) / width, max(1, self.height() - 32) / height)
        return (
            scale,
            (self.width() - width * scale) / 2 - left * scale,
            (self.height() - height * scale) / 2 - top * scale,
        )

    def canvas_rect(self, rect):
        scale, ox, oy = self.transform()
        return QRectF(rect[0] * scale + ox, rect[1] * scale + oy, rect[2] * scale, rect[3] * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, monitor in enumerate(self.monitors):
            bounds = self.canvas_rect(monitor.rect)
            painter.setPen(QPen(self.palette().mid().color(), 1))
            painter.setBrush(self.palette().alternateBase())
            painter.drawRect(bounds)
            work = self.canvas_rect(monitor.work)
            painter.fillRect(work, self.palette().base())
            painter.setPen(self.palette().text().color())
            painter.drawText(
                bounds.adjusted(4, 3, -4, -3),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                f"Monitor {i + 1}" + (" · Hauptmonitor" if monitor.primary else ""),
            )
        for i, plan in enumerate(self.plans):
            bounds = self.canvas_rect(plan["rect"])
            color = QColor(self.palette().highlight().color())
            color.setAlpha(140 if i == self.active else 65)
            painter.setBrush(color)
            painter.setPen(QPen(self.palette().highlight().color(), 2 if i == self.active else 1))
            painter.drawRect(bounds)
            painter.save()
            painter.setClipRect(bounds.adjusted(3, 3, -3, -3))
            painter.setPen(self.palette().text().color())
            painter.drawText(
                bounds.adjusted(5, 4, -5, -4),
                Qt.AlignmentFlag.AlignCenter,
                f"{i + 1}. {plan['entry']['name']}\n{plan['rect'][2]} × {plan['rect'][3]}",
            )
            painter.restore()
            if i == self.active:
                painter.fillRect(
                    QRectF(bounds.right() - 7, bounds.bottom() - 7, 7, 7), self.palette().highlight()
                )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        order = [self.active] if 0 <= self.active < len(self.plans) else []
        order += [i for i in reversed(range(len(self.plans))) if i != self.active]
        for i in order:
            bounds = self.canvas_rect(self.plans[i]["rect"])
            if bounds.contains(event.position()):
                self.active = i
                self.selected.emit(i)
                resize = (event.position() - bounds.bottomRight()).manhattanLength() < 16
                self.drag = (event.position(), list(self.plans[i]["rect"]), resize)
                self.update()
                break

    def mouseMoveEvent(self, event):
        if not self.drag:
            return
        origin, rect, resize = self.drag
        scale, _, _ = self.transform()
        delta = event.position() - origin
        dx, dy = round(delta.x() / scale), round(delta.y() / scale)
        value = [*rect]
        if resize:
            value[2], value[3] = max(64, min(32768, rect[2] + dx)), max(64, min(32768, rect[3] + dy))
        else:
            value[0], value[1] = rect[0] + dx, rect[1] + dy
            # Snap to display/work-area and other preview-window edges.
            targets = [r for m in self.monitors for r in (m.rect, m.work)]
            targets += [p["rect"] for i, p in enumerate(self.plans) if i != self.active]
            for axis in (0, 1):
                edges = [r[axis] + offset for r in targets for offset in (0, r[axis + 2])]
                candidates = [
                    edge - value[axis] - offset for edge in edges for offset in (0, value[axis + 2])
                ]
                nearest = min(candidates, key=abs, default=0)
                if abs(nearest) <= 8 / scale:
                    value[axis] += nearest
        value[0], value[1] = max(-131072, min(131072, value[0])), max(-131072, min(131072, value[1]))
        self.edited.emit(self.active, rectangle(value))

    def mouseReleaseEvent(self, event):
        self.drag = None


class WindowDialog(QDialog):
    def __init__(self, window, account=None, instance=None, monitors=None):
        super().__init__(window)
        self.window, self.manager, self.busy = window, window.window_manager, False
        self.account, self.selected_instance = account, instance
        self.setWindowTitle("Spielfenster anordnen und bearbeiten")
        self.setMinimumSize(780, 620)
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1080, screen.width() - 30), min(790, screen.height() - 30))
        if monitors is None:
            if sys.platform == "win32":
                monitors = self.manager.api.monitors()
            else:
                monitors = [
                    Monitor(
                        s.name(),
                        (s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height()),
                        (
                            s.availableGeometry().x(),
                            s.availableGeometry().y(),
                            s.availableGeometry().width(),
                            s.availableGeometry().height(),
                        ),
                        s is QApplication.primaryScreen(),
                    )
                    for s in QApplication.screens()
                ]
        self.monitors, self.plans = monitors, []
        self.options = preferences(window.store)
        layout = QVBoxLayout(self)
        profile_row = QHBoxLayout()
        self.profiles = Combo()
        self.profiles.setAccessibleName("Gespeichertes Fensterprofil")
        self.refresh_profiles()
        profile_row.addWidget(label("Fensterprofil"))
        profile_row.addWidget(self.profiles, 1)
        profile_row.addWidget(Button("Laden", self.load_profile))
        profile_row.addWidget(Button("Speichern …", self.save_profile))
        profile_row.addWidget(Button("Löschen", self.delete_profile))
        profile_row.addWidget(Button("Aktualisieren", self.refresh_live))
        layout.addLayout(profile_row)
        split = QSplitter()
        self.windows = QTreeWidget()
        self.windows.setHeaderLabels(["Fenster / Account", "Maße"])
        self.windows.setRootIsDecorated(False)
        self.windows.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.windows.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.windows.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.windows.setColumnWidth(0, 165)
        self.windows.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.windows.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.windows.setToolTip(
            "Ankreuzen bestimmt die betroffenen Fenster. Reihenfolge per Drag & Drop; erstes Fenster = Hauptfenster."
        )
        self.windows.setAccessibleName("Fenster für die Anordnung auswählen und sortieren")
        split.addWidget(self.windows)
        self.canvas = MonitorCanvas(monitors)
        split.addWidget(self.canvas)
        split.setSizes([270, 740])
        layout.addWidget(split, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.arrangement_controls(), "Anordnen")
        self.tabs.addTab(self.custom_controls(), "Eigene Position und Größe")
        layout.addWidget(self.tabs)
        layout.addWidget(
            label(
                "Maße in physischen Pixeln. Eigene Spielbereichsmaße ändern die Windows-Fenstergröße; die interne Grafikauflösung wählst du im Spiel. Rahmenlose Fenster lassen sich hier in der Vorschau verschieben und skalieren.",
                muted=True,
            )
        )
        self.remember = QCheckBox("Nach dem Anwenden als Startvorgabe für zugeordnete Accounts speichern")
        layout.addWidget(self.remember)
        layout.addLayout(
            row(
                Button("Account-Startvorgaben speichern", self.save_defaults),
                Button("Startvorgaben entfernen", self.remove_defaults),
                Button("Alle auswählen", lambda: self.check_all(True)),
                Button("Keine auswählen", lambda: self.check_all(False)),
            )
        )
        self.status = label("Vorschau – erst Anwenden ändert die Spielfenster.")
        layout.addWidget(self.status)
        self.apply_button = Button("Anwenden", self.apply, primary=True)
        layout.addLayout(
            row(
                Button("Letzte Änderung rückgängig", lambda: self.restore(True)),
                Button("Originalzustand wiederherstellen", lambda: self.restore(False)),
                self.apply_button,
                Button("Schließen", self.reject),
            )
        )
        self.populate(account, instance)
        self.windows.currentItemChanged.connect(self.select_window)
        self.windows.itemChanged.connect(self.update_preview)
        self.windows.model().rowsMoved.connect(self.update_preview)
        self.canvas.selected.connect(self.select_plan)
        self.canvas.edited.connect(self.canvas_edited)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.update_preview()
        if self.windows.topLevelItemCount():
            self.windows.setCurrentItem(self.windows.topLevelItem(0))

    def spin(self, low, high, value):
        control = QSpinBox()
        control.setRange(low, high)
        control.setValue(value)
        return control

    def arrangement_controls(self):
        body, form = QWidget(), QGridLayout()
        body.setLayout(form)
        self.layout_choice, self.monitor, self.mode, self.aspect, self.topmost = (
            Combo(),
            Combo(),
            Combo(),
            Combo(),
            Combo(),
        )
        for code, title in LAYOUTS.items():
            self.layout_choice.addItem(title, code)
        self.monitor.addItem("Hauptmonitor", "primary")
        self.monitor.addItem("Alle Monitore · gleichmäßig verteilen", "all")
        for i, monitor in enumerate(self.monitors):
            self.monitor.addItem(
                f"Monitor {i + 1} · {monitor.rect[2]} × {monitor.rect[3]} · {monitor.id}", monitor.id
            )
        for code, title in MODES.items():
            self.mode.addItem(title, code)
        for title, value in (
            ("Beibehalten", None),
            ("Immer im Vordergrund", True),
            ("Normaler Vordergrund", False),
        ):
            self.topmost.addItem(title, value)
        for value in ("free", "16:9", "16:10", "4:3"):
            self.aspect.addItem("Freie Proportionen" if value == "free" else value, value)
        for control, key in (
            (self.layout_choice, "layout"),
            (self.monitor, "monitor"),
            (self.mode, "mode"),
            (self.aspect, "aspect"),
            (self.topmost, "topmost"),
        ):
            control.setCurrentIndex(max(0, control.findData(self.options[key])))
        self.work_area = QCheckBox("Taskleiste freilassen")
        self.work_area.setChecked(self.options["work_area"])
        self.gap, self.margin = (
            self.spin(0, 200, self.options["gap"]),
            self.spin(0, 200, self.options["margin"]),
        )
        self.columns, self.rows = (
            self.spin(1, 16, self.options["columns"]),
            self.spin(1, 16, self.options["rows"]),
        )
        self.main = self.spin(30, 85, self.options["main"])
        fields = [
            ("Layout", self.layout_choice),
            ("Zielmonitor", self.monitor),
            ("Fenstermodus", self.mode),
            ("Seitenverhältnis", self.aspect),
            ("Abstand", self.gap),
            ("Bildschirmrand", self.margin),
            ("Spalten", self.columns),
            ("Zeilen", self.rows),
            ("Hauptfenster (%)", self.main),
            ("Fensterreihenfolge", self.topmost),
        ]
        for i, (title, control) in enumerate(fields):
            control.setAccessibleName(title)
            form.addWidget(label(title), i // 2, i % 2 * 2)
            form.addWidget(control, i // 2, i % 2 * 2 + 1)
        form.addWidget(self.work_area, 5, 0, 1, 4)
        for control in (self.layout_choice, self.monitor, self.mode, self.aspect, self.topmost):
            control.currentIndexChanged.connect(self.update_preview)
        for control in (self.gap, self.margin, self.columns, self.rows, self.main):
            control.valueChanged.connect(self.update_preview)
        self.work_area.toggled.connect(self.update_preview)
        return body

    def custom_controls(self):
        body, form = QWidget(), QGridLayout()
        body.setLayout(form)
        self.x, self.y, self.width_value, self.height_value = (
            self.spin(-131072, 131072, 0),
            self.spin(-131072, 131072, 0),
            self.spin(64, 32768, 1280),
            self.spin(64, 32768, 720),
        )
        self.preset, self.size_kind, self.custom_mode, self.custom_topmost = (
            Combo(),
            Combo(),
            Combo(),
            Combo(),
        )
        self.preset.addItem("Eigene Maße", None)
        for w, h in SIZES:
            self.preset.addItem(f"{w} × {h}", (w, h))
        self.size_kind.addItem("Außenmaß · einschließlich Rahmen", "outer")
        self.size_kind.addItem("Spielbereich · ohne Rahmen", "client")
        for code, title in MODES.items():
            self.custom_mode.addItem(title, code)
        for title, value in (
            ("Beibehalten", None),
            ("Immer im Vordergrund", True),
            ("Normaler Vordergrund", False),
        ):
            self.custom_topmost.addItem(title, value)
        controls = [
            ("X", self.x),
            ("Y", self.y),
            ("Breite", self.width_value),
            ("Höhe", self.height_value),
            ("Größenvorgabe", self.preset),
            ("Maßart", self.size_kind),
            ("Fenstermodus", self.custom_mode),
            ("Vordergrund", self.custom_topmost),
        ]
        for i, (title, control) in enumerate(controls):
            control.setAccessibleName("Eigenes Fenster: " + title)
            form.addWidget(label(title), i // 2, i % 2 * 2)
            form.addWidget(control, i // 2, i % 2 * 2 + 1)
        form.addWidget(Button("Auf Zielmonitor zentrieren", self.center), 4, 0, 1, 2)
        form.addWidget(Button("Zielmonitor rahmenlos füllen", self.fill_monitor), 4, 2, 1, 2)
        for control in (self.x, self.y, self.width_value, self.height_value):
            control.valueChanged.connect(self.edit_changed)
        for control in (self.size_kind, self.custom_mode, self.custom_topmost):
            control.currentIndexChanged.connect(self.edit_changed)
        self.preset.currentIndexChanged.connect(self.use_preset)
        return body

    def entries(self, checked=False):
        return [
            self.windows.topLevelItem(i).entry
            for i in range(self.windows.topLevelItemCount())
            if not checked or self.windows.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        ]

    def populate(self, account, selected_instance):
        names = {a["id"]: a["nickname"] for a in self.window.store.accounts()}
        saved = self.window.store.get("window_placements", {})
        found_account = False
        for instance in self.window.found:
            state = self.window.sessions.live.get((instance["pid"], instance["created"]), {})
            account_id = state.get("account_id") or self.manager.account_for(instance)
            found_account |= bool(account and account_id == account["id"])
            actual = self.manager.api.snapshot(instance["hwnd"])
            entry = {
                "instance": instance,
                "account_id": account_id,
                "name": names.get(account_id, f"Instanz {instance['pid']}"),
                "rect": actual.get("layout_rect", actual["rect"]),
                "mode": "borderless" if not actual["style"] & 0x00C00000 else "unchanged",
                "topmost": actual["topmost"],
                "size_kind": "outer",
            }
            checked = (
                account_id == account["id"]
                if account
                else identity(instance) == identity(selected_instance)
                if selected_instance
                else True
            )
            self.add_entry(entry, checked)
        if account and not found_account:
            primary = next((m for m in self.monitors if m.primary), self.monitors[0])
            config = saved.get(
                account["id"], {"rect": fit_rect([primary.work[0], primary.work[1], 1280, 720], primary.work)}
            )
            config = window_config(config, self.options["mode"])
            self.add_entry(
                {
                    "instance": None,
                    "account_id": account["id"],
                    "name": account["nickname"] + " · Startvorgabe",
                    "mode": self.options["mode"],
                    "topmost": None,
                    "size_kind": "outer",
                    **config,
                },
                True,
            )
            self.layout_choice.setCurrentIndex(self.layout_choice.findData("custom"))
            self.tabs.setCurrentIndex(1)

    def add_entry(self, entry, checked=True):
        item = QTreeWidgetItem([entry["name"], ""])
        item.setFlags(
            (item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            & ~Qt.ItemFlag.ItemIsDropEnabled
        )
        item.entry = entry
        item.setData(0, ROLE, entry["name"])
        item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.windows.addTopLevelItem(item)

    def current_entry(self):
        item = self.windows.currentItem()
        return item.entry if item else None

    def read_options(self):
        return {
            "layout": self.layout_choice.currentData(),
            "monitor": self.monitor.currentData(),
            "mode": self.mode.currentData(),
            "aspect": self.aspect.currentData(),
            "topmost": self.topmost.currentData(),
            "work_area": self.work_area.isChecked(),
            "gap": self.gap.value(),
            "margin": self.margin.value(),
            "columns": self.columns.value(),
            "rows": self.rows.value(),
            "main": self.main.value(),
        }

    def update_preview(self, *_):
        if not hasattr(self, "status"):
            return
        try:
            options = self.read_options()
            entries = self.entries(True)
            self.plans = (
                [{"entry": e, **{k: e[k] for k in ("rect", "mode", "topmost", "size_kind")}} for e in entries]
                if options["layout"] == "custom"
                else arrange(self.monitors, entries, options)
            )
            self.canvas.plans = self.plans
            self.canvas.active = next(
                (i for i, p in enumerate(self.plans) if p["entry"] is self.current_entry()), -1
            )
            self.canvas.update()
            with QSignalBlocker(self.windows):
                for i in range(self.windows.topLevelItemCount()):
                    item = self.windows.topLevelItem(i)
                    plan = next((p for p in self.plans if p["entry"] is item.entry), None)
                    item.setText(1, f"{plan['rect'][2]} × {plan['rect'][3]}" if plan else "—")
            self.columns.setEnabled(options["layout"] == "grid")
            self.rows.setEnabled(options["layout"] == "grid")
            self.main.setEnabled(options["layout"].startswith("main-"))
            self.apply_button.setEnabled(any(p["entry"]["instance"] for p in self.plans))
            self.status.setText(
                f"Vorschau: {len(self.plans)} Fenster. Erst Anwenden ändert die Spielfenster."
            )
            self.select_window()
        except (ValueError, KeyError) as exc:
            self.plans, self.canvas.plans = [], []
            self.canvas.update()
            self.apply_button.setEnabled(False)
            self.status.setText(str(exc))

    def select_window(self, *_):
        entry = self.current_entry()
        if entry is None:
            return
        plan = next((p for p in self.plans if p["entry"] is entry), entry)
        self.canvas.active = next((i for i, p in enumerate(self.plans) if p["entry"] is entry), -1)
        self.canvas.update()
        for control, value in zip((self.x, self.y, self.width_value, self.height_value), plan["rect"]):
            with QSignalBlocker(control):
                control.setValue(value)
        for control, key in (
            (self.size_kind, "size_kind"),
            (self.custom_mode, "mode"),
            (self.custom_topmost, "topmost"),
        ):
            with QSignalBlocker(control):
                control.setCurrentIndex(max(0, control.findData(plan[key])))

    def select_plan(self, index):
        entry = self.plans[index]["entry"]
        for i in range(self.windows.topLevelItemCount()):
            item = self.windows.topLevelItem(i)
            if item.entry is entry:
                self.windows.setCurrentItem(item)

    def freeze_preview(self):
        for plan in self.plans:
            plan["entry"].update(
                {k: copy.deepcopy(plan[k]) for k in ("rect", "mode", "topmost", "size_kind")}
            )

    def canvas_edited(self, index, rect):
        entry = self.plans[index]["entry"]
        self.freeze_preview()
        entry["rect"] = rect
        self.to_custom()

    def to_custom(self):
        with QSignalBlocker(self.layout_choice):
            self.layout_choice.setCurrentIndex(self.layout_choice.findData("custom"))
        with QSignalBlocker(self.tabs):
            self.tabs.setCurrentIndex(1)
        self.update_preview()

    def tab_changed(self, index):
        if index == 1:
            self.freeze_preview()
            self.to_custom()

    def edit_changed(self, *_):
        entry = self.current_entry()
        if entry is None:
            return
        value = {
            "rect": [c.value() for c in (self.x, self.y, self.width_value, self.height_value)],
            "mode": self.custom_mode.currentData(),
            "topmost": self.custom_topmost.currentData(),
            "size_kind": self.size_kind.currentData(),
        }
        self.freeze_preview()
        entry.update(value)
        self.to_custom()

    def use_preset(self):
        value = self.preset.currentData()
        if value:
            with QSignalBlocker(self.width_value), QSignalBlocker(self.height_value):
                self.width_value.setValue(value[0])
                self.height_value.setValue(value[1])
            self.edit_changed()

    def target_monitor(self):
        entry = self.current_entry()
        return next(
            (m for m in self.monitors if m.id == self.monitor.currentData()),
            nearest_monitor(entry["rect"], self.monitors),
        )

    def center(self):
        entry = self.current_entry()
        if entry:
            self.freeze_preview()
            bounds = self.target_monitor().work if self.work_area.isChecked() else self.target_monitor().rect
            rect = fit_rect(entry["rect"], bounds)
            rect[0], rect[1] = bounds[0] + (bounds[2] - rect[2]) // 2, bounds[1] + (bounds[3] - rect[3]) // 2
            entry["rect"] = rect
            self.to_custom()

    def fill_monitor(self):
        entry = self.current_entry()
        if entry:
            self.freeze_preview()
            bounds = self.target_monitor().work if self.work_area.isChecked() else self.target_monitor().rect
            entry.update(rect=list(bounds), mode="borderless", size_kind="outer")
            self.to_custom()

    def check_all(self, checked):
        with QSignalBlocker(self.windows):
            for i in range(self.windows.topLevelItemCount()):
                self.windows.topLevelItem(i).setCheckState(
                    0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
        self.update_preview()

    def operation(self, fn, done):
        self.busy = True
        self.setEnabled(False)
        task = Task(fn)
        task.signals.error.connect(lambda error: self.status.setText(error))
        task.signals.done.connect(self.operation_done)
        self.window.run_task(task, done)

    def operation_done(self):
        self.busy = False
        self.setEnabled(True)

    def refresh_live(self):
        from . import backend

        staged = {identity(e["instance"]): e for e in self.entries() if e["instance"]}

        def done(found):
            self.window.found = found
            with QSignalBlocker(self.windows):
                self.windows.clear()
                self.populate(self.account, self.selected_instance)
                for entry in self.entries():
                    previous = staged.get(identity(entry["instance"])) if entry["instance"] else None
                    if previous:
                        entry.update({k: previous[k] for k in ("rect", "mode", "topmost", "size_kind")})
            self.update_preview()
            if self.windows.topLevelItemCount():
                self.windows.setCurrentItem(self.windows.topLevelItem(0))

        self.operation(backend.instances, done)

    def apply(self):
        plans, options = copy.deepcopy(self.plans), self.read_options()
        live = [p for p in plans if p["entry"]["instance"]]
        if not live:
            return
        remember = self.remember.isChecked()

        def act():
            count = self.manager.apply(live)
            self.window.store.set("window_arrangement", options)
            self.window.store.set("window_layout", options["layout"])
            self.window.store.set("window_mode", options["mode"])
            self.window.store.set("window_gap", options["gap"])
            self.window.store.set("window_margin", options["margin"])
            if remember:
                self.manager.save_accounts([p["entry"] for p in live])
            return count

        def done(count):
            self.window.settings_page.refresh_window_settings()
            self.status.setText(f"{count} Spielfenster angeordnet.")

        self.operation(act, done)

    def restore(self, undo):
        instances = [e["instance"] for e in self.entries(True) if e["instance"]]

        def done(count):
            for entry in self.entries():
                if entry["instance"] and self.manager.api.valid(entry["instance"]):
                    actual = self.manager.api.snapshot(entry["instance"]["hwnd"])
                    entry.update(
                        rect=actual.get("layout_rect", actual["rect"]),
                        topmost=actual["topmost"],
                        mode="unchanged",
                        size_kind="outer",
                    )
            self.to_custom()
            self.status.setText(
                f"{count} Fenster wiederhergestellt. Geschlossene oder fremde Fenster werden ausgelassen."
            )

        self.operation(lambda: self.manager.restore(instances, undo=undo), done)

    def save_defaults(self):
        entries = [
            {**p["entry"], **{k: p[k] for k in ("rect", "mode", "topmost", "size_kind")}, "instance": None}
            for p in self.plans
        ]
        count = self.manager.save_accounts(entries)
        self.status.setText(
            f"Startvorgaben für {count} Accounts gespeichert. Sie gelten beim nächsten Start."
        )

    def remove_defaults(self):
        saved = self.window.store.get("window_placements", {})
        for entry in self.entries(True):
            saved.pop(entry.get("account_id"), None)
        self.window.store.set("window_placements", saved)
        self.status.setText("Startvorgaben für die gewählten Accounts entfernt.")

    def refresh_profiles(self):
        self.profiles.clear()
        for name in self.window.store.get("window_profiles", {}):
            self.profiles.addItem(name)

    def save_profile(self):
        name, ok = QInputDialog.getText(self, "Fensterprofil speichern", "Name")
        if ok and name.strip() and self.plans:
            profiles = self.window.store.get("window_profiles", {})
            windows = [
                {
                    "account_id": p["entry"]["account_id"],
                    "slot": i,
                    **{k: p[k] for k in ("rect", "mode", "topmost", "size_kind")},
                }
                for i, p in enumerate(self.plans)
            ]
            profiles[name.strip()] = {"options": self.read_options(), "windows": windows}
            self.window.store.set("window_profiles", profiles)
            self.refresh_profiles()
            self.profiles.setCurrentText(name.strip())
            self.status.setText("Fensterprofil gespeichert; enthält keine Zugangsdaten.")

    def load_profile(self):
        profile = self.window.store.get("window_profiles", {}).get(self.profiles.currentText())
        if not profile:
            return
        try:
            configs = [{**c, **window_config(c)} for c in profile["windows"]]
            if len(configs) > 256 or any(
                type(c["slot"]) is not int
                or not 0 <= c["slot"] < 256
                or c["account_id"] is not None
                and not isinstance(c["account_id"], str)
                for c in configs
            ):
                raise ValueError("Ungültige Fensterzuordnung im Profil.")
        except (KeyError, TypeError, ValueError):
            self.status.setText("Dieses Fensterprofil enthält ungültige Werte und wurde nicht geladen.")
            return
        self.check_all(False)
        used = set()
        for config in configs:
            for i, entry in enumerate(self.entries()):
                matches = (
                    entry["account_id"] == config["account_id"]
                    if config["account_id"]
                    else not entry["account_id"] and i == config["slot"]
                )
                if i not in used and matches:
                    entry.update({k: config[k] for k in ("rect", "mode", "topmost", "size_kind")})
                    self.windows.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)
                    used.add(i)
                    break
        self.to_custom()
        self.status.setText(
            f"Profil geladen: {len(used)} Fenster zugeordnet; {len(profile['windows']) - len(used)} aktuell nicht verfügbar. Erst Anwenden ändert Fenster."
        )

    def delete_profile(self):
        profiles = self.window.store.get("window_profiles", {})
        profiles.pop(self.profiles.currentText(), None)
        self.window.store.set("window_profiles", profiles)
        self.refresh_profiles()

    def reject(self):
        if not self.busy:
            super().reject()
