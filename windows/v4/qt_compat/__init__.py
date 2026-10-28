"""Qt 6 on x64; supported Qt 5.15 bindings for 32-bit Windows."""
import sys
try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg, QtTest
    QT6 = True
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets, QtSvg, QtTest
    QT6 = False
    QtGui.QAction = QtWidgets.QAction
    for cls in (QtWidgets.QApplication, QtWidgets.QMenu):
        if not hasattr(cls, 'exec'):
            cls.exec = cls.exec_
for name, module in [('QtCore', QtCore), ('QtGui', QtGui), ('QtWidgets', QtWidgets), ('QtSvg', QtSvg), ('QtTest', QtTest)]:
    sys.modules[__name__ + '.' + name] = module

def system_dark():
    if QT6:
        return QtWidgets.QApplication.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
    except OSError:
        return False

if not hasattr(QtTest.QTest, 'qWait'):
    def _qwait(milliseconds):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
    QtTest.QTest.qWait = staticmethod(_qwait)
