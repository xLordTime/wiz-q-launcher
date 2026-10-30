"""Readable selection colors and a visible native-view checkbox on every theme."""

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


def luminance(color):
    def linear(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return sum(
        weight * linear(value) for weight, value in zip((0.2126, 0.7152, 0.0722), QColor(color).getRgbF()[:3])
    )


def contrast(left, right):
    low, high = sorted((luminance(left), luminance(right)))
    return (high + 0.05) / (low + 0.05)


def mix(left, right, amount):
    a, b = QColor(left), QColor(right)
    return QColor(
        *(round(x * (1 - amount) + y * amount) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3]))
    ).name()


def readable_ink(background):
    return max(("#000000", "#ffffff"), key=lambda color: contrast(background, color))


@dataclass(frozen=True)
class SelectionColors:
    background: str
    foreground: str
    checked_background: str
    checked_foreground: str


def selection_colors(theme):
    surfaces = (theme.panel, mix(theme.panel, theme.background, 0.42))
    background = theme.accent
    # Change only accents which disappear into the list surface, including custom themes.
    if min(contrast(background, surface) for surface in surfaces) < 3:
        candidates = []
        for endpoint in ("#000000", "#ffffff"):
            for step in range(1, 101):
                color = mix(theme.accent, endpoint, step / 100)
                if min(contrast(color, surface) for surface in surfaces) >= 3:
                    candidates.append((step, color))
                    break
        background = min(candidates)[1] if candidates else readable_ink(theme.panel)
    checked = mix(theme.panel, background, 0.16)
    return SelectionColors(background, readable_ink(background), checked, readable_ink(checked))


class AccountCheckDelegate(QStyledItemDelegate):
    """Keep Qt's check-state/hit testing; draw a high-contrast box and actual tick."""

    def indicator_rect(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        return opt.widget.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, opt.widget
        )

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if not opt.features & QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator:
            return
        rect = self.indicator_rect(opt, index)
        if rect.isEmpty():
            return
        palette = opt.widget.palette()
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        checked = opt.checkState == Qt.CheckState.Checked
        highlight = palette.color(QPalette.ColorRole.Highlight)
        ink = palette.color(QPalette.ColorRole.HighlightedText)
        if checked:
            fill, tick = (ink, highlight) if selected else (highlight, ink)
        else:
            fill = palette.color(QPalette.ColorRole.Base)
            tick = QColor(readable_ink(fill))
        border = QColor(readable_ink(fill))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, fill)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 1.2))
        painter.drawRoundedRect(QRectF(rect).adjusted(0.6, 0.6, -0.6, -0.6), 1, 1)
        if checked:
            pen = QPen(tick, max(1.8, rect.height() * 0.15))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(rect.x() + rect.width() * 0.20, rect.y() + rect.height() * 0.52),
                        QPointF(rect.x() + rect.width() * 0.43, rect.y() + rect.height() * 0.74),
                        QPointF(rect.x() + rect.width() * 0.81, rect.y() + rect.height() * 0.28),
                    ]
                )
            )
        painter.restore()
