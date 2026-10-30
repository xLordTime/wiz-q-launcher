from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QIODevice, QPointF, QSaveFile, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    background: str
    panel: str
    elevated: str
    text: str
    muted: str
    accent: str
    secondary: str
    radius: int = 12
    pattern: str = "none"
    animated: bool = False
    font: str = "Segoe UI"
    spacing: int = 10


BUILTINS = [
    Theme(
        "obsidian",
        "Obsidian",
        "#0c0d12",
        "#161820",
        "#20232f",
        "#f0efff",
        "#a0a0b5",
        "#a899ff",
        "#6b56c9",
        10,
    ),
    Theme(
        "porcelain",
        "Porcelain",
        "#eef2f8",
        "#ffffff",
        "#e1e8f4",
        "#17233c",
        "#52617e",
        "#255bd8",
        "#bacff8",
        14,
    ),
    Theme(
        "graphite-pro",
        "Graphite Pro",
        "#151719",
        "#202326",
        "#303539",
        "#f5f6f7",
        "#afb7bc",
        "#ffb369",
        "#8b552b",
        4,
        "grid",
        False,
        "Segoe UI",
        7,
    ),
    Theme(
        "midnight-blue",
        "Midnight Blue",
        "#0b1528",
        "#12213a",
        "#1c3151",
        "#e8f1ff",
        "#a1b4d0",
        "#81b8ff",
        "#325e91",
        12,
        "lines",
    ),
    Theme(
        "sandstone",
        "Sandstone",
        "#eee5d6",
        "#faf4e8",
        "#e6d4bc",
        "#422b23",
        "#73574a",
        "#a3462b",
        "#d1a76c",
        18,
        "arches",
    ),
    Theme(
        "forest-desk",
        "Forest Desk",
        "#0d211a",
        "#183028",
        "#254238",
        "#f0f3dd",
        "#b0c2a5",
        "#9ed1a6",
        "#c29b6f",
        8,
        "leaves",
    ),
    Theme(
        "nordic-frost",
        "Nordic Frost",
        "#eaf4f7",
        "#f9fdff",
        "#d9eaf0",
        "#143242",
        "#506a78",
        "#146c8d",
        "#a4ccd8",
        10,
        "lines",
        False,
        "Segoe UI",
        14,
    ),
    Theme(
        "rose-quartz",
        "Rose Quartz",
        "#f5e7ee",
        "#fff6fa",
        "#edd3e2",
        "#47273e",
        "#79546e",
        "#963b79",
        "#dcb3cd",
        22,
        "petals",
    ),
    Theme(
        "solar-contrast",
        "Solar Contrast",
        "#050505",
        "#0f0f0f",
        "#252525",
        "#ffffff",
        "#d2d2d2",
        "#ffe44d",
        "#6b611d",
        2,
    ),
    Theme(
        "e-ink",
        "E-Ink",
        "#e7e7e7",
        "#fafafa",
        "#d8d8d8",
        "#161616",
        "#515151",
        "#252525",
        "#aaaaaa",
        0,
        "none",
        False,
        "Segoe UI",
        8,
    ),
    Theme(
        "mythic-explorers",
        "Mythic Explorers",
        "#100d22",
        "#1a1632",
        "#2b2448",
        "#f2edf9",
        "#b5abc8",
        "#e2c17b",
        "#7961b9",
        14,
        "compass",
        True,
    ),
    Theme(
        "arcane-observatory",
        "Arcane Observatory",
        "#171823",
        "#252531",
        "#363444",
        "#f3e5c8",
        "#c2b39a",
        "#e3ba71",
        "#8087bd",
        8,
        "rings",
        True,
        "Georgia",
    ),
    Theme(
        "aurora-drift",
        "Aurora Drift",
        "#091e26",
        "#122c36",
        "#214350",
        "#e2fff6",
        "#a0c3c6",
        "#76eacb",
        "#ab8eed",
        18,
        "aurora",
        True,
    ),
    Theme(
        "emberforge",
        "Emberforge",
        "#20120e",
        "#321f19",
        "#493025",
        "#fff0db",
        "#d0ae94",
        "#ffb25e",
        "#ad5c40",
        6,
        "sparks",
        True,
    ),
    Theme(
        "ocean-depths",
        "Ocean Depths",
        "#061b2b",
        "#0d2b3c",
        "#154251",
        "#e4fbff",
        "#9fbec9",
        "#68dfde",
        "#2e83b4",
        20,
        "waves",
        True,
    ),
    Theme(
        "neon-circuit",
        "Neon Circuit",
        "#0d1020",
        "#181c30",
        "#282c44",
        "#ecf4ff",
        "#adb8d1",
        "#70e8ff",
        "#e181de",
        5,
        "circuit",
        True,
        "Consolas",
        8,
    ),
    Theme(
        "clockwork-brass",
        "Clockwork Brass",
        "#211b15",
        "#31291f",
        "#493c2b",
        "#f5ead5",
        "#c0b297",
        "#dfba70",
        "#9c7753",
        7,
        "gears",
        True,
        "Georgia",
    ),
    Theme(
        "sakura-breeze",
        "Sakura Breeze",
        "#f4eaf0",
        "#fff9f7",
        "#ebd6e1",
        "#493446",
        "#795c72",
        "#9f426d",
        "#d6a2b7",
        20,
        "petals",
        True,
    ),
    Theme(
        "desert-mirage",
        "Desert Mirage",
        "#1d1a31",
        "#2d2745",
        "#453958",
        "#fcebd1",
        "#c4b0ad",
        "#f0bd75",
        "#b0778a",
        16,
        "arches",
        True,
    ),
    Theme(
        "celestial-atlas",
        "Celestial Atlas",
        "#10182b",
        "#1a2740",
        "#2c3b58",
        "#eef4ff",
        "#a9bbd6",
        "#b7cdf5",
        "#776ac4",
        9,
        "stars",
        True,
    ),
]
PATTERNS = {t.pattern for t in BUILTINS}


def validate_theme(data):
    allowed = set(Theme.__dataclass_fields__)
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("Unbekannte Theme-Felder")
    for key in ("background", "panel", "elevated", "text", "muted", "accent", "secondary"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(data.get(key, ""))):
            raise ValueError("Theme-Farben müssen #RRGGBB entsprechen")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", str(data.get("id", ""))):
        raise ValueError("Ungültige Theme-ID")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 80:
        raise ValueError("Ungültiger Theme-Name")
    for field, low, high in (("radius", 0, 24), ("spacing", 4, 20)):
        if type(data.get(field, low)) is not int or not low <= data.get(field, low) <= high:
            raise ValueError("Theme-Abstände außerhalb des Bereichs")
    if data.get("pattern", "none") not in PATTERNS or type(data.get("animated", False)) is not bool:
        raise ValueError("Ungültiges Animationspreset")
    if data.get("font", "Segoe UI") not in ("Segoe UI", "Georgia", "Consolas", "Arial"):
        raise ValueError("Nicht unterstützte Schriftfamilie")
    return Theme(**data)


def catalog(folder):
    themes = list(BUILTINS)
    seen = {t.id for t in themes}
    for path in sorted(Path(folder).glob("*.json")):
        try:
            if path.stat().st_size > 65536:
                continue
            theme = validate_theme(json.loads(path.read_text(encoding="utf-8")))
            if theme.id not in seen:
                themes.append(theme)
                seen.add(theme.id)
        except (ValueError, TypeError, OSError):
            continue
    return themes


def save_theme(theme, folder):
    validate_theme(asdict(theme))
    path = Path(folder) / (theme.id + ".json")
    file = QSaveFile(str(path))
    payload = json.dumps(asdict(theme), ensure_ascii=False, indent=2).encode("utf-8")
    if (
        not file.open(QIODevice.OpenModeFlag.WriteOnly)
        or file.write(payload) != len(payload)
        or not file.commit()
    ):
        raise OSError("Theme konnte nicht sicher gespeichert werden")
    return path


def stylesheet(t, size=11):
    return f"""
    QWidget {{ color: {t.text}; font-family: '{t.font}'; font-size: {size}pt; }}
    QMainWindow, QDialog {{ background: {t.background}; }}
    QWidget#sidebar, QFrame[panel='true'], QGroupBox {{ background: {t.panel}; border: 1px solid {t.elevated}; border-radius: {t.radius}px; }}
    QFrame#hero {{ background: {t.panel}; border: 1px solid {t.secondary}; border-radius: {t.radius + 4}px; }}
    QLabel {{ background: transparent; border: none; }}
    QLabel[muted='true'] {{ color: {t.muted}; }}
    QLabel#title {{ font-size: {size + 13}pt; font-weight: 700; }}
    QLabel#heroTitle {{ font-size: {size + 18}pt; font-weight: 700; }}
    QLabel#metric {{ font-size: {size + 9}pt; font-weight: 600; color: {t.accent}; }}
    QPushButton, QToolButton {{ background: {t.elevated}; border: 1px solid transparent; border-radius: {max(3, t.radius - 3)}px; padding: 9px 14px; }}
    QPushButton:hover, QToolButton:hover {{ border: 1px solid {t.accent}; }}
    QPushButton:pressed {{ background: {t.secondary}; }}
    QPushButton:disabled {{ color: {t.muted}; background: {t.panel}; }}
    QPushButton[primary='true'] {{ background: {t.accent}; color: {t.background}; font-weight: 700; }}
    QPushButton#nav {{ text-align: left; padding: 12px 18px; background: transparent; }}
    QPushButton#nav:checked {{ background: {t.elevated}; border-left: 3px solid {t.accent}; }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser {{ background: {t.panel}; border: 1px solid {t.elevated}; border-radius: {max(3, t.radius - 5)}px; padding: 9px; selection-background-color: {t.secondary}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPushButton:focus {{ border: 1px solid {t.accent}; }}
    QComboBox QAbstractItemView, QMenu {{ background: {t.panel}; color: {t.text}; selection-background-color: {t.elevated}; border: 1px solid {t.secondary}; padding: 4px; }}
    QMenu::item {{ padding: 8px 18px; }}
    QListWidget, QTreeWidget, QTableWidget {{ background: {t.panel}; border: 1px solid {t.elevated}; border-radius: {t.radius}px; outline: none; }}
    QListWidget::item, QTreeWidget::item {{ padding: {t.spacing}px; border-bottom: 1px solid {t.elevated}; }}
    QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {t.elevated}; }}
    QHeaderView::section {{ background: {t.elevated}; color: {t.muted}; border: none; padding: 10px; }}
    QCheckBox {{ spacing: 9px; background: transparent; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {t.muted}; border-radius: 4px; background: {t.panel}; }}
    QCheckBox::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent}; image: url(:/none); }}
    QScrollArea, QStackedWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: {t.background}; width: 9px; }}
    QScrollBar::handle:vertical {{ background: {t.secondary}; min-height: 24px; border-radius: 4px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QToolTip {{ background: {t.elevated}; color: {t.text}; border: 1px solid {t.secondary}; padding: 6px; }}
    QProgressBar {{ background: {t.elevated}; border: none; border-radius: 4px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
    """


class Backdrop(QWidget):
    """Bounded vector decoration, no WebEngine, video textures or unbounded particles."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.motion = True
        self.origin = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.animate)
        self.timer.start()

    def animate(self):
        if (
            self.theme.animated
            and self.motion
            and self.isVisible()
            and not self.window().isMinimized()
            and self.window().isActiveWindow()
        ):
            self.update()

    def paintEvent(self, event):
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(t.background))
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        top = QColor(t.secondary)
        top.setAlpha(45)
        bottom = QColor(t.background)
        bottom.setAlpha(0)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        p.fillRect(self.rect(), gradient)
        if t.pattern == "none":
            return
        phase = (time.monotonic() - self.origin) * 0.08 if self.motion and t.animated else 0.0
        color = QColor(t.accent)
        color.setAlpha(32)
        p.setPen(QPen(color, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() * 0.85, self.height() * 0.3
        if t.pattern in ("rings", "gears", "compass"):
            p.translate(cx, cy)
            p.rotate(phase * 12)
            for r in (75, 112, 150, 190):
                p.drawEllipse(QPointF(0, 0), r, r)
            rays = 12 if t.pattern == "gears" else 8
            for i in range(rays):
                p.rotate(360 / rays)
                p.drawLine(QPointF(0, -65), QPointF(0, -210))
        elif t.pattern in ("waves", "aurora", "arches"):
            for j in range(9):
                points = [
                    QPointF(
                        x,
                        self.height() * 0.3 + j * 35 + math.sin(x / (110 + j * 7) + phase + j) * (35 + j * 4),
                    )
                    for x in range(0, self.width() + 12, 12)
                ]
                for a, b in zip(points, points[1:]):
                    p.drawLine(a, b)
        elif t.pattern in ("grid", "circuit", "lines"):
            for x in range(0, self.width() + 80, 70):
                p.drawLine(QPointF(x, 0), QPointF(x - 100, self.height()))
            for y in range(0, self.height(), 70):
                p.drawLine(0, y, self.width(), y)
            if t.pattern == "circuit":
                p.setBrush(color)
                for i in range(8):
                    p.drawEllipse(
                        QPointF(
                            (i * 137 + phase * 80) % max(1, self.width()), i * 79 % max(1, self.height())
                        ),
                        4,
                        4,
                    )
        else:
            p.setBrush(color)
            for i in range(28):
                x = (i * 173.3 + math.sin(phase + i) * 12) % max(1, self.width())
                y = (i * 97.7 + phase * (35 if t.pattern == "petals" else -15)) % max(1, self.height())
                if t.pattern in ("petals", "leaves"):
                    p.drawEllipse(QPointF(x, y), 6, 2.5)
                elif t.pattern == "sparks":
                    p.drawLine(QPointF(x, y), QPointF(x + 2, y - 7))
                else:
                    p.drawEllipse(QPointF(x, y), 1.5, 1.5)
