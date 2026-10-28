"""Small Qt controls using Microsoft Fluent System Icons (MIT, bundled)."""
from functools import lru_cache
from pathlib import Path

from qt_compat.QtCore import Qt, QSize, QRectF, Property, QPropertyAnimation, QEasingCurve
from qt_compat.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from qt_compat.QtSvg import QSvgRenderer
from qt_compat.QtWidgets import (QApplication, QPushButton, QCheckBox,
                               QStyledItemDelegate, QStyle, QStyleOptionViewItem)

ASSETS = Path(__file__).resolve().parent / 'assets'


@lru_cache(maxsize=256)
def icon(name, color='#242424', filled=False):
    style = 'filled' if filled else 'regular'
    source = ASSETS / 'icons' / f'{name}_{style}.svg'
    if not source.exists():
        source = ASSETS / 'icons' / f'{name}_regular.svg'
    data = source.read_bytes().replace(b'fill="#212121"', f'fill="{color}"'.encode())
    renderer = QSvgRenderer(data)
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        for dpr in (1, 2):
            pixmap = QPixmap(size * dpr, size * dpr)
            pixmap.fill(Qt.GlobalColor.transparent)
            pixmap.setDevicePixelRatio(dpr)
            painter = QPainter(pixmap)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
            result.addPixmap(pixmap)
    return result


class NavigationButton(QPushButton):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.property('accent') or '#0067c0'))
            p.drawRoundedRect(QRectF(0, (self.height() - 16) / 2, 3, 16), 1.5, 1.5)


class ToggleSwitch(QCheckBox):
    """Fluent switch, preserving QCheckBox's keyboard/accessibility behavior."""
    def __init__(self, text):
        super().__init__(text)
        self._position = 1.0 if self.isChecked() else 0.0
        self.animation = QPropertyAnimation(self, b'position', self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self.slide)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def get_position(self):
        return self._position

    def set_position(self, value):
        self._position = value
        self.update()

    position = Property(float, get_position, set_position)

    def slide(self, checked):
        self.animation.stop()
        self.animation.setEndValue(float(checked))
        if QApplication.instance().property('motion') is False:
            self.set_position(float(checked))
        else:
            self.animation.start()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 64, 40)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        dark = bool(self.property('dark'))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - 20) / 2
        track = QRectF(1, y, 40, 20)
        accent = QColor(self.property('accent') or ('#60cdff' if dark else '#0067c0'))
        p.setPen(QPen(accent if self.isChecked() else QColor('#989898' if dark else '#616161'), 1))
        p.setBrush(accent if self.isChecked() else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(track, 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#000000' if dark else '#ffffff') if self.isChecked()
                   else QColor('#d6d6d6' if dark else '#616161'))
        p.drawEllipse(QRectF(5 + self._position * 20, y + 4, 12, 12))
        p.setPen(QColor('#ffffff' if dark else '#1a1a1a'))
        p.drawText(self.rect().adjusted(53, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            p.setPen(QPen(accent, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ''
        QApplication.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter)
        color = index.data(Qt.ItemDataRole.ForegroundRole).color()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = min(option.rect.width() - 12, option.fontMetrics.horizontalAdvance(text) + 20)
        rect = QRectF(option.rect.x() + (option.rect.width() - width) / 2,
                      option.rect.center().y() - 12, width, 25)
        background = QColor(color)
        background.setAlpha(25)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
