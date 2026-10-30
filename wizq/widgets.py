from PySide6.QtCore import Property, QEasingCurve, QObject, QPropertyAnimation, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class Button(QPushButton):
    motion = True

    def __init__(self, text, callback=None, primary=False, parent=None):
        super().__init__(text, parent)
        self.setCursor(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CursorShape.PointingHandCursor)
        self.setProperty("primary", primary)
        self.setMinimumHeight(38)
        self._hover = 0.0
        self.animation = QPropertyAnimation(self, b"hover", self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if callback:
            self.clicked.connect(callback)

    def _get_hover(self):
        return self._hover

    def _set_hover(self, value):
        self._hover = value
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def transition(self, value):
        self.animation.stop()
        if self.motion:
            self.animation.setStartValue(self._hover)
            self.animation.setEndValue(value)
            self.animation.start()
        else:
            self._set_hover(value)

    def enterEvent(self, event):
        self.transition(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.transition(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hover > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QColor(QApplication.palette().highlight().color())
            c.setAlphaF(self._hover * 0.7)
            p.setPen(QPen(c, 1.5))
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)


class Combo(QComboBox):
    def showPopup(self):
        super().showPopup()
        if Button.motion:
            popup = self.view().window()
            self.fade = QPropertyAnimation(popup, b"windowOpacity", self)
            self.fade.setStartValue(0.65)
            self.fade.setEndValue(1.0)
            self.fade.setDuration(130)
            self.fade.start()


def label(text, muted=False, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setProperty("muted", muted)
    if name:
        widget.setObjectName(name)
    return widget


def panel():
    frame = QFrame()
    frame.setProperty("panel", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    return frame, layout


def row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(10)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    done = Signal()
    progress = Signal(int)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.result.emit(self.fn())
        except Exception as exc:
            # Never serialize arbitrary exception reprs: request URLs may be secrets.
            safe = (
                str(exc)
                if isinstance(exc, (ValueError, RuntimeError, PermissionError))
                else f"{type(exc).__name__}: Aktion fehlgeschlagen; Rechte, Netzwerk oder Speicher prüfen."
            )
            self.signals.error.emit(safe)
        finally:
            self.signals.done.emit()
