"""VPN Gemini 4.0 — Fluent desktop application."""
import csv
import ctypes
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (Qt, Signal, QObject, QThread, QTimer, QSettings, QSize,
                            QPropertyAnimation, QEasingCurve, QSortFilterProxyModel, QUrl)
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPixmap, QStandardItem,
                           QStandardItemModel, QDesktopServices, QLinearGradient, QFontDatabase, QAction)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPlainTextEdit,
    QComboBox, QSpinBox, QCheckBox, QStackedWidget, QProgressBar, QTableView,
    QHeaderView, QFileDialog, QGraphicsOpacityEffect, QScrollArea,
    QAbstractItemView, QMenu, QTabWidget)

from fluent import icon as fluent_icon, NavigationButton, ToggleSwitch, StatusDelegate, ASSETS
from system_theme import read_accent_palette
from menus import FluentMenu, install_edit_menu

from engine import TestResult, run_batch_test
from v2_parser import parse_text_block
from v2_subscription import fetch_subscription, generate_hwid

VERSION = '4.0'
STATUS = {'PENDING': 'В очереди', 'TESTING': 'Проверка', 'OK': 'Доступен',
          'BLOCKED': 'Блокировка', 'ERROR': 'Ошибка', 'TIMEOUT': 'Таймаут',
          'CANCELLED': 'Отменён'}


def app_icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor('#54c9ff'))
    gradient.setColorAt(1, QColor('#0057b8'))
    p.setBrush(gradient)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    fluent_icon('shield_checkmark', '#ffffff').paint(p, 12, 12, 40, 40)
    p.end()
    return QIcon(pix)


def label(text, role=None):
    w = QLabel(text)
    if role:
        w.setObjectName(role)
    return w


def button(text, callback, role=None):
    w = QPushButton(text)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    if role:
        w.setObjectName(role)
    w.clicked.connect(callback)
    names = {'Вставить': 'clipboard_paste', 'Из файла': 'folder_open',
             'Очистить': 'delete', 'Обновить HWID': 'arrow_sync',
             'Загрузить подписку': 'arrow_download', 'Начать проверку': 'play',
             'Остановить': 'stop', 'Копировать доступные': 'copy',
             'Копировать': 'copy', 'Экспорт CSV': 'arrow_download',
             'Открыть Gemini': 'open'}
    if text in names:
        w.setProperty('iconName', names[text])
        w.setIconSize(QSize(20, 20))
        w.setIcon(fluent_icon(names[text]))
        w.setText(' ' + text)
    if role == 'iconOnly':
        w.setAccessibleName(text)
        w.setToolTip(text)
        w.setText('')
        w.setFixedSize(34, 34)
    return w


def card():
    w = QFrame()
    w.setObjectName('card')
    layout = QVBoxLayout(w)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    return w, layout


class Events(QObject):
    log = Signal(str)
    result = Signal(object, int, int)
    started = Signal(int)
    imported = Signal(str, int)
    failed = Signal(str)
    finished = Signal(object)


class Job(QThread):
    """Only signals cross the worker/UI boundary."""
    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        self.fn()


class ResultsFilter(QSortFilterProxyModel):
    query = ''
    status = 'ALL'

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        state = model.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if self.status == 'ERRORS':
            if state not in ('ERROR', 'TIMEOUT'):
                return False
        elif self.status != 'ALL' and state != self.status:
            return False
        return self.query in ' '.join(model.item(row, c).text().lower()
                                       for c in range(model.columnCount()))


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings('VPNGemini', 'Fluent4')
        self.setWindowTitle('VPN Gemini · 4.0')
        self.setWindowIcon(app_icon())
        self.resize(1440, 940)
        self.setMinimumSize(1200, 760)
        self.jobs = []
        self.results = []
        self.configs = []
        self.lookup = {}
        self.running = False
        self.importing = False
        self.stop_event = threading.Event()
        self.events = Events(self)
        self.events.log.connect(self.log)
        self.events.result.connect(self.on_result)
        self.events.started.connect(self.on_started)
        self.events.imported.connect(self.on_imported)
        self.events.failed.connect(self.on_failed)
        self.events.finished.connect(self.on_finished)
        self.animations = []
        self.accent_palette = read_accent_palette()
        self.build_ui()
        for editor in self.findChildren(QLineEdit) + self.findChildren(QPlainTextEdit):
            install_edit_menu(editor)
        self.apply_theme()
        self.accent_timer = QTimer(self)
        self.accent_timer.setInterval(2000)
        self.accent_timer.timeout.connect(self.refresh_system_accent)
        self.accent_timer.start()
        self.log('VPN Gemini 4.0 готов к работе. Добавьте конфигурации для проверки.')

    def build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(224)
        nav = QVBoxLayout(side)
        nav.setContentsMargins(12, 24, 12, 20)
        nav.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(32, 32))
        brand.addWidget(logo)
        brand.addWidget(label('VPN Gemini', 'brand'))
        brand.addStretch()
        nav.addLayout(brand)
        nav.addSpacing(28)
        nav.addWidget(label('Рабочая область', 'navHeading'))
        nav.addSpacing(8)
        self.nav_buttons = []
        for i, (text, name) in enumerate([('Проверка', 'home'), ('Журнал', 'text_bullet_list_ltr'), ('Настройки', 'settings')]):
            if i == 2:
                nav.addStretch()
            b = NavigationButton('  ' + text)
            b.setObjectName('nav')
            b.setProperty('iconName', name)
            b.setIconSize(QSize(20, 20))
            b.clicked.connect(lambda checked=False, idx=i: self.navigate(idx))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            nav.addWidget(b)
            self.nav_buttons.append(b)
        self.nav_buttons[0].setChecked(True)
        nav.addSpacing(16)
        nav.addWidget(label('    Версия 4.0', 'muted'))
        shell.addWidget(side)
        content = QFrame()
        content.setObjectName('contentPane')
        body = QVBoxLayout(content)
        body.setContentsMargins(32, 24, 32, 24)
        body.setSpacing(20)
        top = QHBoxLayout()
        top.addWidget(label('VPN Gemini', 'breadcrumb'))
        top.addStretch()
        self.state_label = label('Готово к проверке', 'muted')
        top.addWidget(self.state_label)
        body.addLayout(top)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_test_page())
        self.stack.addWidget(self.build_log_page())
        self.stack.addWidget(self.build_settings_page())
        body.addWidget(self.stack, 1)
        self.toast = label('', 'toast')
        self.toast.setVisible(False)
        body.addWidget(self.toast)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)
        shell.addWidget(content, 1)

    def build_test_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label('Проверка подключения', 'title'))
        titles.addWidget(label('Найдите VPN-серверы с доступом к Google Gemini.', 'muted'))
        title_row.addLayout(titles)
        title_row.addStretch()
        title_row.addWidget(button('Открыть Gemini', self.open_gemini))
        layout.addLayout(title_row)
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.counters = []
        for title, role, name in [('Всего серверов', 'number', 'server'), ('Доступны', 'successNumber', 'checkmark_circle'),
                            ('Блокировка', 'errorNumber', 'dismiss_circle'), ('Ошибки', 'warningNumber', 'warning')]:
            box, col = card()
            stat_row = QHBoxLayout()
            words = QVBoxLayout()
            words.setSpacing(4)
            words.addWidget(label(title, 'muted'))
            value = label('0', role)
            words.addWidget(value)
            stat_row.addLayout(words)
            stat_row.addStretch()
            badge = QLabel()
            badge.setObjectName('statIcon')
            badge.setProperty('iconName', name)
            badge.setProperty('tone', role)
            badge.setFixedSize(40, 40)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stat_row.addWidget(badge)
            col.addLayout(stat_row)
            self.counters.append(value)
            stats.addWidget(box, 1)
        layout.addLayout(stats)
        work = QHBoxLayout()
        work.setSpacing(18)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(320)
        input_card, inputs = card()
        inputs.addWidget(label('Конфигурации', 'section'))
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)
        inputs.addWidget(tabs, 1)
        key_tab, sub_tab = QWidget(), QWidget()
        tabs.addTab(key_tab, 'Ключи')
        tabs.addTab(sub_tab, 'Подписка')
        key_layout, sub_layout = QVBoxLayout(key_tab), QVBoxLayout(sub_tab)
        for tab_layout in (key_layout, sub_layout):
            tab_layout.setContentsMargins(0, 16, 0, 0)
            tab_layout.setSpacing(12)
        key_layout.addWidget(label('VPN-ссылки, по одной на строку', 'muted'))
        self.keys = QPlainTextEdit()
        self.keys.setPlaceholderText('Вставьте VPN-ключи, по одному на строку\n\nvless:// · vmess:// · trojan://\nss:// · hy2:// · tuic://\nJSON или Base64')
        self.keys.setMinimumHeight(150)
        key_layout.addWidget(self.keys, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button('Вставить', self.paste_keys))
        row.addWidget(button('Из файла', self.load_file))
        self.clear_button = button('Очистить', self.keys.clear, 'iconOnly')
        row.addWidget(self.clear_button)
        key_layout.addLayout(row)
        formats = label('VLESS, VMess, Trojan, Shadowsocks,\nHysteria2, TUIC, JSON и Base64', 'muted')
        key_layout.addWidget(formats)
        sub_layout.addWidget(label('Адрес подписки', 'muted'))
        self.url = QLineEdit()
        self.url.setPlaceholderText('https://…')
        self.url.setClearButtonEnabled(True)
        sub_layout.addWidget(self.url)
        sub_layout.addWidget(label('Идентификатор устройства', 'muted'))
        hw = QHBoxLayout()
        self.hwid = QLineEdit()
        self.hwid.setPlaceholderText('HWID (необязательно)')
        hw.addWidget(self.hwid)
        hw.addWidget(button('Обновить HWID', lambda: self.hwid.setText(generate_hwid()), 'iconOnly'))
        sub_layout.addLayout(hw)
        self.import_button = button('Загрузить подписку', self.import_subscription)
        sub_layout.addWidget(self.import_button)
        sub_note = label('Загрузите конфигурации по ссылке провайдера. HWID нужен только для подписок с привязкой к устройству.', 'muted')
        sub_note.setWordWrap(True)
        sub_layout.addWidget(sub_note)
        sub_layout.addStretch()
        scroll.setWidget(input_card)
        left = QWidget()
        left.setFixedWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(scroll, 1)
        controls_card, controls = card()
        left_layout.addWidget(controls_card)
        self.run_button = button('Начать проверку', self.start_test, 'primary')
        controls.addWidget(self.run_button)
        self.stop_button = button('Остановить', self.stop_test)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.stop_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        controls.addWidget(self.progress)
        self.progress_label = label('Готово к запуску', 'muted')
        self.progress_label.setWordWrap(True)
        controls.addWidget(self.progress_label)
        work.addWidget(left)
        result_card, results = card()
        row = QHBoxLayout()
        row.addWidget(label('Результаты', 'section'))
        row.addStretch()
        self.copy_button = button('Копировать доступные', self.copy_ok, 'subtle')
        self.export_button = button('Экспорт CSV', self.export_csv, 'subtle')
        self.copy_button.setEnabled(False)
        self.export_button.setEnabled(False)
        row.addWidget(self.copy_button)
        row.addWidget(self.export_button)
        results.addLayout(row)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск сервера, страны, протокола…')
        self.search.setClearButtonEnabled(True)
        self.search_action = QAction(self.search)
        self.search.addAction(self.search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.filter_results)
        filters.addWidget(self.search, 1)
        self.filter = QComboBox()
        for text, data in [('Все статусы', 'ALL'), ('Доступны', 'OK'),
                           ('Блокировка', 'BLOCKED'), ('Ошибки', 'ERRORS'),
                           ('В очереди', 'PENDING'), ('Проверяются', 'TESTING'),
                           ('Отменены', 'CANCELLED')]:
            self.filter.addItem(text, data)
        self.filter.currentIndexChanged.connect(self.filter_results)
        filters.addWidget(self.filter)
        results.addLayout(filters)
        self.model = QStandardItemModel(0, 6, self)
        self.model.setHorizontalHeaderLabels(['Сервер', 'Статус', 'Страна', 'Пинг, мс', 'Время, с', 'Протокол'])
        for column in range(1, 6):
            self.model.setHeaderData(column, Qt.Orientation.Horizontal,
                Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)
        self.proxy = ResultsFilter(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole + 1)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setItemDelegateForColumn(1, StatusDelegate(self.table))
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.selectionModel().selectionChanged.connect(self.show_details)
        results.addWidget(self.table, 1)
        self.table.setVisible(False)
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setSpacing(12)
        empty_layout.addStretch()
        empty_icon = QLabel()
        empty_icon.setProperty('iconName', 'shield_checkmark')
        empty_icon.setObjectName('emptyIcon')
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = label('Проверьте доступ к Gemini', 'emptyTitle')
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_text = label('Добавьте VPN-конфигурации слева и начните проверку.\nЗдесь появятся доступность, страна и задержка.', 'muted')
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text.setWordWrap(True)
        empty_layout.addWidget(empty_text)
        empty_layout.addStretch()
        results.addWidget(self.empty, 1)
        self.details = label('Выберите сервер, чтобы посмотреть подробности.', 'muted')
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(48)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        results.addWidget(self.details)
        work.addWidget(result_card, 1)
        layout.addLayout(work, 1)
        return page

    def build_log_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(18)
        col.addWidget(label('Журнал событий', 'title'))
        col.addWidget(label('Диагностика и события текущего сеанса.', 'muted'))
        box, inside = card()
        row = QHBoxLayout()
        row.addWidget(label('События в реальном времени', 'section'))
        row.addStretch()
        row.addWidget(button('Копировать', self.copy_log))
        row.addWidget(button('Очистить', lambda: self.log_view.clear()))
        inside.addLayout(row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setObjectName('log')
        inside.addWidget(self.log_view)
        col.addWidget(box, 1)
        return page

    def build_settings_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(18)
        col.addWidget(label('Настройки', 'title'))
        col.addWidget(label('Внешний вид и параметры проверки.', 'muted'))
        box, inside = card()
        inside.addWidget(label('Внешний вид', 'section'))
        self.theme = QComboBox()
        self.theme.addItems(['Как в системе', 'Тёмная', 'Светлая'])
        self.theme.setCurrentIndex(int(self.settings.value('theme', 0)))
        inside.addWidget(label('Тема приложения', 'muted'))
        inside.addWidget(self.theme)
        self.motion = ToggleSwitch('Плавные анимации')
        self.motion.setChecked(str(self.settings.value('motion', 'true')).lower() == 'true')
        self.motion.toggled.connect(self.motion_changed)
        inside.addWidget(self.motion)
        self.theme.currentIndexChanged.connect(self.theme_changed)
        col.addWidget(box)
        box, inside = card()
        inside.addWidget(label('Проверка серверов', 'section'))
        grid = QGridLayout()
        grid.addWidget(label('Одновременных проверок', 'muted'), 0, 0)
        self.workers = QSpinBox()
        self.workers.setFixedWidth(160)
        self.workers.lineEdit().setTextMargins(12, 0, 8, 0)
        self.workers.setRange(1, 12)
        self.workers.setValue(int(self.settings.value('workers', 4)))
        self.workers.valueChanged.connect(lambda v: self.settings.setValue('workers', v))
        grid.addWidget(self.workers, 0, 1)
        grid.addWidget(label('Таймаут запроса Gemini', 'muted'), 1, 0)
        self.timeout = QSpinBox()
        self.timeout.setFixedWidth(160)
        self.timeout.lineEdit().setTextMargins(12, 0, 8, 0)
        self.timeout.setRange(4, 60)
        self.timeout.setSuffix(' с')
        self.timeout.setValue(int(self.settings.value('timeout', 9)))
        self.timeout.valueChanged.connect(lambda v: self.settings.setValue('timeout', v))
        grid.addWidget(self.timeout, 1, 1)
        inside.addLayout(grid)
        note = label('Таймаут относится к сетевым операциям запроса Gemini. Запуск туннеля и замер пинга занимают дополнительное время. При остановке текущие проверки завершаются, ожидающие — отменяются.', 'muted')
        note.setWordWrap(True)
        inside.addWidget(note)
        col.addWidget(box)
        box, inside = card()
        inside.addWidget(label('VPN Gemini 4.0', 'section'))
        about = label('Пакетная проверка VPN-конфигураций и доступности Google Gemini.\nКлючи и адрес подписки не сохраняются между запусками.\nРезультат отражает сетевую проверку; доступ в аккаунте Google может отличаться.', 'muted')
        about.setWordWrap(True)
        inside.addWidget(about)
        col.addWidget(box)
        col.addStretch()
        return page

    def theme_changed(self):
        self.settings.setValue('theme', self.theme.currentIndex())
        self.apply_theme()

    def refresh_system_accent(self):
        palette = read_accent_palette()
        if palette != self.accent_palette:
            self.accent_palette = palette
            self.apply_theme()

    def motion_changed(self, value):
        self.settings.setValue('motion', value)
        QApplication.instance().setProperty('motion', value)
        if not value:
            for anim in list(self.animations):
                anim.setCurrentTime(anim.duration())

    def refresh_icons(self):
        fg = '#ffffff' if self.dark else '#242424'
        accent = self.accent_palette.fill(self.dark)
        self.motion.setProperty('dark', self.dark)
        self.motion.setProperty('accent', accent)
        self.motion.update()
        QApplication.instance().setProperty('motion', self.motion.isChecked())
        for w in self.findChildren(QPushButton):
            name = w.property('iconName')
            if not name:
                continue
            primary = w.objectName() == 'primary'
            color = ('#000000' if self.dark else '#ffffff') if primary else fg
            w.setIcon(fluent_icon(name, color, isinstance(w, NavigationButton) and w.isChecked()))
            if isinstance(w, NavigationButton):
                w.setProperty('accent', accent)
                w.update()
        self.search_action.setIcon(fluent_icon('search', '#c5c5c5' if self.dark else '#616161'))
        for w in self.findChildren(QLabel):
            name = w.property('iconName')
            if not name:
                continue
            tones = {'successNumber': self.colors['OK'], 'errorNumber': self.colors['BLOCKED'],
                     'warningNumber': self.colors['ERROR'], 'number': accent}
            color = tones.get(w.property('tone'), accent)
            size = 64 if w.objectName() == 'emptyIcon' else 24
            w.setPixmap(fluent_icon(name, color).pixmap(size, size))
            if w.objectName() == 'statIcon':
                w.setStyleSheet(f'background: {"#383838" if self.dark else "#f5f5f5"}; border-radius: 4px;')

    def apply_theme(self):
        mode = self.theme.currentIndex()
        self.dark = mode == 1 or (mode == 0 and QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        accent = self.accent_palette.fill(self.dark)
        muted = '#b5b5b5' if self.dark else '#626262'
        self.colors = {'OK': '#69d69a' if self.dark else '#107c41',
                       'BLOCKED': '#ff9299' if self.dark else '#c42b3b',
                       'ERROR': '#f6ca77' if self.dark else '#926000',
                       'TIMEOUT': '#f6ca77' if self.dark else '#926000',
                       'TESTING': self.accent_palette.text(self.dark), 'PENDING': muted, 'CANCELLED': muted}
        from theme import stylesheet
        self.setStyleSheet(stylesheet(self.dark, accent, self.colors))
        self.refresh_icons()
        for row, result in enumerate(self.results):
            self.paint_row(row, result)
        self.native_backdrop()

    def native_backdrop(self):
        if sys.platform != 'win32':
            return
        try:
            hwnd = ctypes.c_void_p(int(self.winId()))
            dark = ctypes.c_int(int(self.dark))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            if sys.getwindowsversion().build >= 22621:
                material = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(material), 4)
        except (OSError, AttributeError):
            pass

    def animate(self, target, prop, end, duration=220):
        for old in list(self.animations):
            if old.targetObject() == target and old.propertyName() == prop:
                old.stop()
                self.animations.remove(old)
                old.deleteLater()
        if not self.motion.isChecked():
            target.setProperty(bytes(prop).decode(), end)
            return
        anim = QPropertyAnimation(target, prop, self)
        anim.setDuration(duration)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animations.append(anim)
        def release():
            if anim in self.animations:
                self.animations.remove(anim)
            anim.deleteLater()
        anim.finished.connect(release)
        anim.start()

    def navigate(self, index):
        if index == self.stack.currentIndex():
            self.nav_buttons[index].setChecked(True)
            return
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == index)
        self.refresh_icons()
        page = self.stack.currentWidget()
        effect = page.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
        effect.setOpacity(0.35 if self.motion.isChecked() else 1.0)
        self.animate(effect, b'opacity', 1.0, 240)

    def notify(self, text):
        self.toast.setText(text)
        self.toast.show()
        effect = self.toast.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.toast)
            self.toast.setGraphicsEffect(effect)
        effect.setOpacity(0.2 if self.motion.isChecked() else 1.0)
        self.animate(effect, b'opacity', 1.0)
        self.toast_timer.start(4200)

    def log(self, text):
        self.log_view.appendPlainText(f'{datetime.now():%H:%M:%S}  {text}')

    def launch(self, fn):
        job = Job(fn, self)
        self.jobs.append(job)
        def cleanup():
            self.jobs.remove(job)
            job.deleteLater()
        job.finished.connect(cleanup)
        job.start()

    def paste_keys(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.keys.appendPlainText(text)
        else:
            self.notify('В буфере обмена нет текста.')

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Импорт конфигураций', '', 'Конфигурации (*.txt *.json *.conf);;Все файлы (*)')
        if path:
            try:
                self.keys.appendPlainText(Path(path).read_text(encoding='utf-8-sig'))
                self.notify('Файл добавлен.')
            except Exception as exc:
                self.notify(f'Не удалось прочитать файл: {exc}')

    def import_subscription(self):
        if self.importing or self.running:
            return
        url = self.url.text().strip()
        if not url.startswith(('https://', 'http://')):
            self.notify('Введите адрес подписки, начинающийся с https:// или http://.')
            return
        hwid = self.hwid.text().strip() or None
        self.importing = True
        self.import_button.setEnabled(False)
        self.import_button.setText('Загрузка…')
        self.run_button.setEnabled(False)
        self.log('Загрузка подписки…')
        def work():
            try:
                configs = fetch_subscription(url, hwid=hwid)
                self.events.imported.emit('\n'.join(c.raw for c in configs), len(configs))
            except Exception as exc:
                self.events.failed.emit(f'Не удалось загрузить подписку ({type(exc).__name__}). Проверьте адрес и подключение.')
        self.launch(work)

    def reset_import(self):
        self.importing = False
        self.import_button.setEnabled(not self.running)
        self.import_button.setText('Загрузить подписку')
        self.run_button.setEnabled(not self.running)

    def on_imported(self, text, count):
        self.reset_import()
        if text:
            self.keys.appendPlainText(text)
        invalid = [cfg for cfg in parse_text_block(text) if cfg.extra.get('import_error')]
        message = (f'Импортировано записей: {count}; распознано: {count - len(invalid)}; '
                   f'требуют проверки: {len(invalid)}.') if invalid else f'Подписка загружена: {count} конфигураций.'
        if not count:
            message = 'В ответе подписки не найдены VPN-конфигурации. Проверьте адрес и формат подписки.'
        self.notify(message)
        self.log(message)
        for cfg in invalid:
            self.log(f'[{cfg.label()}] {cfg.extra["import_error"]}')

    def on_failed(self, message):
        self.reset_import()
        self.log(message)
        self.notify(message)

    def start_test(self):
        if self.running or self.importing:
            return
        try:
            configs = parse_text_block(self.keys.toPlainText().strip())
        except Exception as exc:
            self.notify(f'Не удалось разобрать конфигурации: {exc}')
            return
        if not configs:
            self.notify('Добавьте хотя бы одну корректную VPN-конфигурацию.')
            return
        self.configs = configs
        self.lookup = {id(cfg): i for i, cfg in enumerate(configs)}
        self.results = [TestResult(cfg=c, label=c.label()) for c in configs]
        self.model.setRowCount(0)
        self.running = True
        self.stop_event.clear()
        self.set_running_controls(True)
        self.empty.hide()
        self.table.show()
        self.details.setText('Выберите сервер, чтобы посмотреть подробности.')
        self.progress.setValue(0)
        self.progress_label.setText(f'Проверено 0 из {len(configs)}')
        self.state_label.setText('Выполняется проверка')
        for i, result in enumerate(self.results):
            self.paint_row(i, result)
        self.update_counters()
        workers, timeout = self.workers.value(), self.timeout.value()
        self.log(f'Запуск: {len(configs)} серверов · потоков: {workers} · таймаут Gemini: {timeout} с.')
        def work():
            try:
                results = run_batch_test(configs, max_workers=workers,
                    gemini_timeout=timeout, stop_event=self.stop_event,
                    on_log=lambda text, name: self.events.log.emit(f'[{name}] {text}'),
                    on_started=self.events.started.emit, on_result=self.events.result.emit)
                self.events.finished.emit(results)
            except Exception as exc:
                self.events.log.emit(f'Ошибка пакетной проверки: {exc}')
                self.events.finished.emit(None)
        self.launch(work)

    def set_running_controls(self, running):
        self.run_button.setEnabled(not running and not self.importing)
        self.import_button.setEnabled(not running and not self.importing)
        self.stop_button.setEnabled(running)
        self.keys.setReadOnly(running)
        self.clear_button.setEnabled(not running)
        self.workers.setEnabled(not running)
        self.timeout.setEnabled(not running)

    def stop_test(self):
        if self.running:
            self.stop_event.set()
            self.stop_button.setEnabled(False)
            self.state_label.setText('Ожидание текущих проверок')
            self.progress_label.setText('Остановка: завершаются активные подключения…')
            self.log('Запрошена остановка. Ожидающие конфигурации будут отменены.')

    def on_started(self, row):
        if self.results[row].status == 'PENDING':
            self.results[row].status = 'TESTING'
            self.paint_row(row, self.results[row])

    def on_result(self, result, done, total):
        row = self.lookup[id(result.cfg)]
        self.results[row] = result
        self.paint_row(row, result)
        self.update_counters()
        self.animate(self.progress, b'value', int(done / total * 1000))
        if not self.stop_event.is_set():
            self.progress_label.setText(f'Проверено {done} из {total}')
        self.show_details()

    def on_finished(self, results):
        self.running = False
        if results is not None:
            self.results = results
        else:
            for r in self.results:
                if r.status in ('PENDING', 'TESTING'):
                    r.status = 'ERROR'
                    r.error_detail = 'Пакетная проверка прервана ошибкой.'
        for i, result in enumerate(self.results):
            self.paint_row(i, result)
        self.set_running_controls(False)
        self.update_counters()
        cancelled = sum(r.status == 'CANCELLED' for r in self.results)
        ok = sum(r.status == 'OK' for r in self.results)
        text = f'Доступны: {ok} из {len(self.results)}' + (f' · отменено: {cancelled}' if cancelled else '')
        self.progress_label.setText(text)
        self.state_label.setText('Проверка остановлена' if self.stop_event.is_set() else 'Проверка завершена')
        self.animate(self.progress, b'value', 1000)
        self.log(text)
        self.notify(text)
        self.show_details()

    def paint_row(self, row, result):
        cfg = result.cfg
        values = [result.label, STATUS.get(result.status, result.status), result.country_code or '—',
                  f'{result.ping_ms:.0f}' if result.ping_ok else '—',
                  f'{result.total_ms / 1000:.1f}' if result.total_ms else '—', cfg.protocol.upper()]
        sort_values = [result.label.lower(), values[1], values[2], result.ping_ms if result.ping_ok else -1,
                       result.total_ms, values[5]]
        if row >= self.model.rowCount():
            self.model.appendRow([QStandardItem() for _ in values])
        for col, (text, sort_value) in enumerate(zip(values, sort_values)):
            item = self.model.item(row, col)
            item.setText(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col else
                                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setData(sort_value, Qt.ItemDataRole.UserRole + 1)
            item.setData(result.status if col == 1 else row, Qt.ItemDataRole.UserRole)
            item.setToolTip(f'{cfg.host}:{cfg.port}' if col == 0 else text)
            if col == 1:
                item.setForeground(QColor(self.colors[result.status]))

    def update_counters(self):
        values = [len(self.results), sum(r.status == 'OK' for r in self.results),
                  sum(r.status == 'BLOCKED' for r in self.results),
                  sum(r.status in ('ERROR', 'TIMEOUT') for r in self.results)]
        for w, value in zip(self.counters, values):
            w.setText(str(value))
        self.copy_button.setEnabled(values[1] > 0)
        self.export_button.setEnabled(any(r.status not in ('PENDING', 'TESTING') for r in self.results))

    def filter_results(self):
        self.proxy.query = self.search.text().strip().lower()
        self.proxy.status = self.filter.currentData()
        self.proxy.invalidate()

    def selected_result(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = self.proxy.mapToSource(rows[0]).row()
        return self.results[row]

    def show_details(self, *_):
        result = self.selected_result()
        if result:
            cfg = result.cfg
            self.details.setText(f'{cfg.host}:{cfg.port} · {cfg.protocol.upper()} · {STATUS[result.status]}\n'
                                 + (result.error_detail or f'Страна Google: {result.country_code or "не определена"} · Интерфейс чата: {"обнаружен" if result.gemini_chat_ui else "не подтверждён"}'))
        else:
            self.details.setText('Выберите сервер, чтобы посмотреть подробности.')

    def context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        menu = FluentMenu(self)
        menu.addAction('Копировать ключ', self.copy_selected)
        menu.addAction('Копировать доступные', self.copy_ok)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def copy_selected(self):
        result = self.selected_result()
        if result:
            QApplication.clipboard().setText(result.cfg.raw)
            self.notify('Ключ скопирован.')

    def copy_ok(self):
        keys = [r.cfg.raw for r in self.results if r.status == 'OK']
        if keys:
            QApplication.clipboard().setText('\n'.join(keys))
            self.notify(f'Скопировано ключей: {len(keys)}.')

    def copy_log(self):
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.notify('Журнал скопирован.')

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить результаты', 'vpn_gemini_4_results.csv', 'CSV (*.csv)')
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['SERVER', 'STATUS', 'COUNTRY', 'PING_MS', 'TIME_MS', 'PROTOCOL', 'HOST', 'PORT', 'RAW_KEY'])
                    for r in self.results:
                        writer.writerow([r.label, r.status, r.country_code, r.ping_ms if r.ping_ok else '',
                                         r.total_ms, r.cfg.protocol, r.cfg.host, r.cfg.port, r.cfg.raw])
                self.notify('Отчёт CSV сохранён.')
            except Exception as exc:
                self.notify(f'Не удалось сохранить отчёт: {exc}')

    def open_gemini(self):
        QDesktopServices.openUrl(QUrl('https://gemini.google.com/app'))

    def closeEvent(self, event):
        if any(job.isRunning() for job in self.jobs):
            if self.running:
                self.stop_test()
            self.notify('Дождитесь завершения текущих сетевых операций, затем закройте окно.')
            event.ignore()
        else:
            event.accept()


def run_gui(smoke_report=None):
    app = QApplication(sys.argv)
    app.setApplicationName('VPN Gemini')
    app.setApplicationVersion(VERSION)
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow()
    if smoke_report:
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    app.styleHints().colorSchemeChanged.connect(lambda _: window.apply_theme())
    window.show()
    if smoke_report:
        def report():
            import json
            from v2_xray import _get_xray_path, _get_singbox_path
            try:
                data = {'version': VERSION, 'pages': window.stack.count(),
                        'fluent_icons': len(list((ASSETS / 'icons').glob('*.svg'))),
                        'xray': str(_get_xray_path()), 'singbox': str(_get_singbox_path()),
                        'title': window.windowTitle()}
                target = Path(smoke_report)
                window.grab().save(str(target.with_suffix('.png')))
                target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                app.exit(0)
            except Exception as exc:
                Path(smoke_report).write_text(str(exc), encoding='utf-8')
                app.exit(1)
        QTimer.singleShot(500, report)
    return app.exec()
