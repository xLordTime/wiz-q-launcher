from __future__ import annotations

import json
import shutil
import uuid
from collections import deque
from dataclasses import asdict, replace
from pathlib import Path

import psutil
from PySide6.QtCore import QIODevice, QPointF, QSaveFile, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .addons import BUILTINS, AddonWorker, discover
from .capture import Capture
from .themes import Backdrop, catalog, save_theme, stylesheet, validate_theme
from .widgets import Button, Combo, label, panel, row


class Sparkline(QWidget):
    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=90)
        self.setMinimumHeight(110)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self.palette().highlight().color(), 2))
        points = [
            QPointF(i * self.width() / 89, self.height() * (1 - v / 100)) for i, v in enumerate(self.values)
        ]
        for a, b in zip(points, points[1:]):
            p.drawLine(a, b)


class StatsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window, self.pending = window, False
        layout = QVBoxLayout(self)
        layout.addWidget(label("Stat Monitor", name="title"))
        self.metrics = label("Wird beim Öffnen gemessen …", name="metric")
        layout.addWidget(self.metrics)
        self.graph = Sparkline()
        layout.addWidget(self.graph)
        self.details = label("", muted=True)
        layout.addWidget(self.details)
        layout.addWidget(
            label(
                "CPU-Verlauf · 90 begrenzte Messpunkte. Nicht verfügbare GPU-/Temperaturwerte werden nicht erfunden.",
                muted=True,
            )
        )
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.sample)

    def showEvent(self, event):
        super().showEvent(event)
        if self.window.addon_enabled("stat-monitor"):
            self.timer.start()
            self.sample()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def sample(self):
        if self.pending or not self.window.addon_enabled("stat-monitor"):
            return
        self.pending = True

        def collect():
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(self.window.paths.root)
            gpu = "GPU-Metrik: nicht verfügbar"
            executable = shutil.which("nvidia-smi")
            if executable:
                import subprocess

                try:
                    result = subprocess.run(
                        [
                            executable,
                            "--query-gpu=utilization.gpu,temperature.gpu,memory.used",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=1,
                        creationflags=0x08000000 if __import__("sys").platform == "win32" else 0,
                    )
                    if result.returncode == 0:
                        gpu = (
                            "NVIDIA GPU · Auslastung %, Temperatur °C, VRAM MiB: "
                            + result.stdout.strip()[:200]
                        )
                except (OSError, subprocess.TimeoutExpired):
                    pass
            return (
                psutil.cpu_percent(),
                memory.percent,
                memory.used / 1024**3,
                memory.total / 1024**3,
                disk.free / 1024**3,
                gpu,
            )

        def done(values):
            cpu, mem, used, total, disk, gpu = values
            self.metrics.setText(f"CPU {cpu:.0f}%    ·    RAM {mem:.0f}%")
            self.details.setText(
                f"Arbeitsspeicher {used:.1f} / {total:.1f} GiB\nFreier Profilspeicher {disk:.1f} GiB\n{gpu}"
            )
            self.graph.values.append(cpu)
            self.graph.update()

        task = self.window.task(collect, done)
        task.signals.done.connect(lambda: setattr(self, "pending", False))


class CapturePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.capture = Capture(window.paths, window.store, self)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Clips and Record", name="title"))
        layout.addWidget(
            label(
                "Fensteraufnahme und Replay-Clips. Aufnahme startet nur auf deine Aktion; Audio ist standardmäßig aus.",
                muted=True,
            )
        )
        self.windows = Combo()
        layout.addLayout(row(self.windows, Button("Fenster aktualisieren", self.refresh)))
        self.status = label("Keine Aufnahme aktiv.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        layout.addLayout(
            row(
                Button("Screenshot", self.screenshot),
                Button("Aufnahme starten", lambda: self.start(False), primary=True),
                Button("Replay starten", lambda: self.start(True)),
                Button("Stoppen", self.capture.stop),
            )
        )
        layout.addLayout(
            row(
                Button("Clip speichern", self.save_clip),
                Button(
                    "Aufnahmen öffnen",
                    lambda: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(window.paths.directory("recordings")))
                    ),
                ),
                Button("Hilfe zur Aufnahme", lambda: window.open_help("Clips & Aufnahme")),
            )
        )
        layout.addWidget(
            label(
                "FFmpeg-Pfad, FPS, Replay-Dauer, Audio-Gerät und Speicherlimit stehen in den Einstellungen. Der Replay-Puffer besteht aus komprimierten Segmenten auf der Festplatte.",
                muted=True,
            )
        )
        layout.addStretch()
        self.capture.changed.connect(self.status.setText)

    def refresh(self):
        from .backend import instances

        def done(values):
            self.windows.clear()
            for instance in values:
                self.windows.addItem(f"Wizard101 · PID {instance['pid']}", instance["hwnd"])

        self.window.task(instances, done)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hwnd(self):
        value = self.windows.currentData()
        if value is None:
            raise ValueError("Zuerst ein laufendes Spielfenster auswählen.")
        return value

    def start(self, replay):
        self.window.guard(lambda: self.capture.start(self.hwnd(), replay))

    def screenshot(self):
        def save():
            import time

            from PySide6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            image = screen.grabWindow(self.hwnd())
            target = self.window.paths.directory("recordings") / (
                time.strftime("screenshot-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".png"
            )
            if image.isNull() or not image.save(str(target)):
                raise ValueError("Das Fenster konnte nicht aufgenommen werden. Fenster sichtbar lassen.")
            self.status.setText("Screenshot gespeichert: " + str(target))

        self.window.guard(save)

    def save_clip(self):
        try:
            fn = self.capture.prepare_clip()
            self.window.task(fn, lambda path: self.status.setText("Clip gespeichert: " + path))
        except Exception as exc:
            self.window.notice(str(exc))


def contrast(a, b):
    def light(value):
        components = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in components]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    x, y = sorted((light(a), light(b)))
    return (y + 0.05) / (x + 0.05)


class ThemeEditor(QDialog):
    def __init__(self, window, theme):
        super().__init__(window)
        self.window = window
        self.theme = replace(theme, id="custom-" + uuid.uuid4().hex[:12], name=theme.name + " Custom")
        self.setWindowTitle("Theme Creator · neues Design")
        self.resize(870, 650)
        layout = QHBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.theme.name)
        form.addRow("Name", self.name)
        for key in ("background", "panel", "elevated", "text", "muted", "accent", "secondary"):
            button = Button(getattr(self.theme, key))
            button.clicked.connect(lambda _, k=key, b=button: self.pick_color(k, b))
            form.addRow(key, button)
        self.radius, self.spacing = QSpinBox(), QSpinBox()
        self.radius.setRange(0, 24)
        self.radius.setValue(self.theme.radius)
        self.spacing.setRange(4, 20)
        self.spacing.setValue(self.theme.spacing)
        form.addRow("Rundung", self.radius)
        form.addRow("Abstände", self.spacing)
        self.font = Combo()
        self.font.addItems(["Segoe UI", "Georgia", "Consolas", "Arial"])
        self.font.setCurrentText(self.theme.font)
        form.addRow("Schrift", self.font)
        self.motion = QCheckBox("Animiert")
        self.motion.setChecked(self.theme.animated)
        form.addRow("Bewegung", self.motion)
        self.pattern = Combo()
        from .themes import PATTERNS

        self.pattern.addItems(sorted(PATTERNS))
        self.pattern.setCurrentText(self.theme.pattern)
        form.addRow("Motiv", self.pattern)
        self.warning = label("")
        form.addRow(self.warning)
        form.addRow(Button("Speichern & anwenden", self.save, primary=True))
        form.addRow(Button("Abbrechen", self.reject))
        layout.addLayout(form, 1)
        self.preview = Backdrop(self.theme)
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(22, 22, 22, 22)
        preview_layout.addWidget(label("Dein nächstes Design", name="title"))
        preview_layout.addWidget(label("Live-Vorschau mit echten Qt-Controls.", muted=True))
        card, content = panel()
        content.addWidget(label("Wizard101 · Launch", name="metric"))
        content.addWidget(QLineEdit("Beispiel-Account"))
        combo = Combo()
        combo.addItems(["Deutschland", "United States"])
        content.addWidget(combo)
        content.addWidget(Button("Auswahl starten", primary=True))
        content.addWidget(QCheckBox("Favorit"))
        preview_layout.addWidget(card)
        preview_layout.addStretch()
        layout.addWidget(self.preview, 2)
        for signal in (
            self.radius.valueChanged,
            self.spacing.valueChanged,
            self.font.currentTextChanged,
            self.motion.toggled,
            self.pattern.currentTextChanged,
        ):
            signal.connect(self.update_preview)
        self.update_preview()

    def pick_color(self, key, button):
        color = QColorDialog.getColor(QColor(getattr(self.theme, key)), self, key)
        if color.isValid():
            self.theme = replace(self.theme, **{key: color.name()})
            button.setText(color.name())
            self.update_preview()

    def update_preview(self, *_):
        self.theme = replace(
            self.theme,
            radius=self.radius.value(),
            spacing=self.spacing.value(),
            font=self.font.currentText(),
            animated=self.motion.isChecked(),
            pattern=self.pattern.currentText(),
        )
        self.preview.theme = self.theme
        self.preview.setStyleSheet(stylesheet(self.theme))
        self.preview.update()
        ratio = contrast(self.theme.text, self.theme.panel)
        self.warning.setText(
            f"Textkontrast {ratio:.1f}:1"
            + (" · für kleine Schrift zu niedrig" if ratio < 4.5 else " · gut lesbar")
        )

    def save(self):
        try:
            self.theme = replace(self.theme, name=self.name.text().strip())
            save_theme(self.theme, self.window.paths.directory("themes"))
            self.window.store.set("theme", self.theme.id)
            self.window.apply_theme()
            self.accept()
        except Exception as exc:
            self.warning.setText(str(exc))


class ThemesPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.addWidget(label("Theme Creator", name="title"))
        layout.addWidget(
            label(
                "20 eigenständige Designs. Als Vorlage verwenden und ohne ausführbaren Code weitergestalten.",
                muted=True,
            )
        )
        self.list = QListWidget()
        layout.addWidget(self.list)
        layout.addLayout(
            row(
                Button("Anwenden", self.apply, primary=True),
                Button("Bearbeiten / duplizieren", self.edit),
                Button("Import", self.import_theme),
                Button("Export", self.export),
            )
        )
        self.list.itemDoubleClicked.connect(lambda *_: self.apply())
        self.refresh()

    def refresh(self):
        self.themes = catalog(self.window.paths.directory("themes"))
        self.list.clear()
        self.list.addItems(
            [
                t.name + ("   ·   animiert + statisch" if t.animated else "   ·   statisch")
                for t in self.themes
            ]
        )
        self.list.setCurrentRow(
            next(
                (
                    i
                    for i, t in enumerate(self.themes)
                    if t.id == self.window.store.get("theme", "aero-explorer")
                ),
                0,
            )
        )

    def chosen(self):
        return self.themes[max(0, self.list.currentRow())]

    def apply(self):
        self.window.store.set("theme", self.chosen().id)
        self.window.apply_theme()

    def edit(self):
        if ThemeEditor(self.window, self.chosen()).exec():
            self.refresh()

    def import_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, "Theme importieren", "", "Theme (*.json)")
        if path:

            def load():
                if Path(path).stat().st_size > 65536:
                    raise ValueError("Theme zu groß")
                theme = validate_theme(json.loads(Path(path).read_text(encoding="utf-8")))
                theme = replace(theme, id="custom-" + uuid.uuid4().hex[:12])
                save_theme(theme, self.window.paths.directory("themes"))
                self.refresh()

            self.window.guard(load)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Theme exportieren", self.chosen().id + ".json", "Theme (*.json)"
        )
        if path:

            def save():
                file = QSaveFile(path)
                data = json.dumps(asdict(self.chosen()), ensure_ascii=False, indent=2).encode()
                if (
                    not file.open(QIODevice.OpenModeFlag.WriteOnly)
                    or file.write(data) != len(data)
                    or not file.commit()
                ):
                    raise OSError("Export fehlgeschlagen")

            self.window.guard(save)


class AddonsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window, self.workers = window, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(label("Addons", name="title"))
        layout.addWidget(label("Ein schlanker Core. Erweiterungen nach deinem Bedarf.", muted=True))
        split = QSplitter()
        self.navigation = QListWidget()
        self.navigation.setMaximumWidth(230)
        self.stack = QStackedWidget()
        overview = QWidget()
        body = QVBoxLayout(overview)
        self.stats, self.capture, self.themes = StatsPage(window), CapturePage(window), ThemesPage(window)
        self.stack.addWidget(overview)
        self.navigation.addItem("Verwalten")
        for ident, name, desc in BUILTINS:
            control = QCheckBox(name)
            control.setChecked(window.addon_enabled(ident))
            control.setToolTip(desc)
            control.toggled.connect(lambda value, i=ident: self.toggle_builtin(i, value))
            body.addWidget(control)
            self.navigation.addItem(name)
        body.addWidget(
            label(
                "Eigene Erweiterungen laufen mit deinen Benutzerrechten. Nur vertrauenswürdigen Code aktivieren.",
                muted=True,
            )
        )
        self.custom_manifests = discover(window.paths.directory("addons")) if not window.safe_mode else []
        for manifest in self.custom_manifests:
            control = QCheckBox(str(manifest.get("name", manifest["id"])))
            control.toggled.connect(lambda on, m=manifest, c=control: self.toggle_custom(m, on, c))
            body.addWidget(control)
        self.custom_status = label("Eigene Addons werden nicht automatisch gestartet.", muted=True)
        body.addWidget(self.custom_status)
        body.addWidget(
            Button(
                "Addon-Ordner öffnen",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.paths.directory("addons")))),
            )
        )
        body.addWidget(
            Button(
                "Entwickleranleitung",
                lambda: QDesktopServices.openUrl(
                    QUrl(
                        "https://github.com/xLordTime/wiz-q-launcher/blob/Version-6.0/documentation/ADDON_SDK.md"
                    )
                ),
            )
        )
        body.addStretch()
        for widget in (self.stats, self.capture, self.themes):
            self.stack.addWidget(widget)
        self.navigation.currentRowChanged.connect(self.choose)
        split.addWidget(self.navigation)
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.navigation.setCurrentRow(0)

    def choose(self, index):
        if index > 0 and not self.window.addon_enabled(BUILTINS[index - 1][0]):
            self.window.notice("Dieses Addon zuerst unter Verwalten aktivieren.")
            self.navigation.setCurrentRow(0)
            return
        self.stack.setCurrentIndex(max(0, index))

    def toggle_builtin(self, ident, on):
        self.window.store.set("addon:" + ident, on)
        if not on:
            if ident == "stat-monitor":
                self.stats.timer.stop()
            if ident == "clips-record":
                self.capture.capture.shutdown()
            if self.stack.currentIndex() == [b[0] for b in BUILTINS].index(ident) + 1:
                self.navigation.setCurrentRow(0)

    def toggle_custom(self, manifest, on, control):
        ident = manifest["id"]
        if not on:
            worker = self.workers.pop(ident, None)
            if worker:
                worker.stop()
            return
        if (
            QMessageBox.question(
                self,
                "Vertrauenswürdiges Addon?",
                "Diese Erweiterung kann mit deinen Windows-Rechten auf Dateien und Netzwerk zugreifen. Ein Workerprozess ist keine Sandbox. Diesen Code jetzt ausführen?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            control.setChecked(False)
            return
        worker = AddonWorker(manifest, self.window.paths.directory("addons") / ident / "data", self)
        self.workers[ident] = worker
        worker.message.connect(self.custom_status.setText)
        worker.failed.connect(lambda text: (self.custom_status.setText(text), control.setChecked(False)))

    def emit_event(self, name, data):
        for worker in self.workers.values():
            worker.send_event(name, data)

    def shutdown(self):
        self.stats.timer.stop()
        self.capture.capture.shutdown()
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()
