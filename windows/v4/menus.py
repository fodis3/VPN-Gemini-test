"""Consistent menu columns, using standard QMenu keyboard and action behavior."""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QKeySequence
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QApplication
from fluent import icon


class FluentMenu(QMenu):
    def sizeHint(self):
        hint = super().sizeHint()
        fm = self.fontMetrics()
        width = max((fm.horizontalAdvance(a.text()) for a in self.actions()), default=100)
        width += max((fm.horizontalAdvance(a.shortcut().toString(QKeySequence.SequenceFormat.NativeText))
                      for a in self.actions()), default=0) + 88
        return QSize(max(280, width, hint.width()), hint.height())

    def paintEvent(self, event):
        dark = bool(getattr(self.window_parent(), 'dark', False))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#2d2d2d' if dark else '#ffffff'))
        p.setPen(QPen(QColor('#494949' if dark else '#dedede'), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 8, 8)
        shortcut_width = max((self.fontMetrics().horizontalAdvance(
            a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)) for a in self.actions()), default=0)
        for action in self.actions():
            r = self.actionGeometry(action)
            if action.isSeparator():
                p.setPen(QColor('#454545' if dark else '#e5e5e5'))
                p.drawLine(12, r.center().y(), self.width() - 12, r.center().y())
                continue
            if action == self.activeAction() and action.isEnabled():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor('#3b3b3b' if dark else '#eeeeee'))
                p.drawRoundedRect(QRectF(r).adjusted(4, 1, -4, -1), 4, 4)
            p.save()
            if not action.isEnabled():
                p.setOpacity(.4)
            action.icon().paint(p, 12, r.center().y() - 10, 20, 20)
            p.setPen(QColor('#ffffff' if dark else '#1a1a1a'))
            p.drawText(r.adjusted(44, 0, -(shortcut_width + 32) if shortcut_width else -16, 0),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       action.text())
            p.setPen(QColor('#c5c5c5' if dark else '#616161'))
            p.drawText(r.adjusted(0, 0, -16, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       action.shortcut().toString(QKeySequence.SequenceFormat.NativeText))
            p.restore()

    def window_parent(self):
        parent = self.parentWidget()
        return parent.window() if parent else None


def edit_menu(widget):
    menu = FluentMenu(widget)
    dark = bool(getattr(widget.window(), 'dark', False))
    fg = '#ffffff' if dark else '#242424'
    plain = isinstance(widget, QPlainTextEdit)
    selection = widget.textCursor().hasSelection() if plain else widget.hasSelectedText()
    editable = not widget.isReadOnly()
    document = widget.document() if plain else widget

    def add(name, symbol, callback, shortcut, enabled=True):
        action = menu.addAction(icon(symbol, fg), name, callback)
        action.setShortcut(QKeySequence(shortcut))
        action.setEnabled(enabled)

    def remove_selection():
        if plain:
            cursor = widget.textCursor()
            cursor.removeSelectedText()
        else:
            widget.backspace()

    add('Отменить', 'arrow_undo', widget.undo, QKeySequence.StandardKey.Undo,
        editable and document.isUndoAvailable())
    add('Повторить', 'arrow_redo', widget.redo, QKeySequence.StandardKey.Redo,
        editable and document.isRedoAvailable())
    menu.addSeparator()
    add('Вырезать', 'cut', widget.cut, QKeySequence.StandardKey.Cut, editable and selection)
    add('Копировать', 'copy', widget.copy, QKeySequence.StandardKey.Copy, selection)
    add('Вставить', 'clipboard_paste', widget.paste, QKeySequence.StandardKey.Paste,
        editable and bool(QApplication.clipboard().text()))
    add('Удалить', 'delete', remove_selection, Qt.Key.Key_Delete, editable and selection)
    menu.addSeparator()
    text = widget.toPlainText() if plain else widget.text()
    add('Выделить всё', 'select_all_on', widget.selectAll, QKeySequence.StandardKey.SelectAll, bool(text))
    return menu


def install_edit_menu(widget):
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def popup(pos):
        menu = edit_menu(widget)
        origin = widget.viewport() if isinstance(widget, QPlainTextEdit) else widget
        menu.exec(origin.mapToGlobal(pos))
        menu.deleteLater()
    widget.customContextMenuRequested.connect(popup)
