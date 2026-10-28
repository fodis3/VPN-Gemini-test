"""Windows Fluent geometry: 4px controls, 8px surfaces, 14px body type."""
from fluent import ASSETS
from PySide6.QtGui import QColor


def flatten(foreground, background, opacity):
    front, back = QColor(foreground), QColor(background)
    return QColor(*(round(a * opacity + b * (1 - opacity))
                    for a, b in zip(front.getRgb()[:3], back.getRgb()[:3]))).name()


def stylesheet(dark, accent, colors):
    bg = '#202020' if dark else '#f3f3f3'
    pane = '#272727' if dark else '#fafafa'
    card = '#2d2d2d' if dark else '#ffffff'
    field = '#333333' if dark else '#ffffff'
    fg = '#ffffff' if dark else '#1a1a1a'
    muted = '#c5c5c5' if dark else '#616161'
    border = '#404040' if dark else '#e5e5e5'
    hover = '#383838' if dark else '#f5f5f5'
    selected = '#393939' if dark else '#eaeaea'
    icon_dir = (ASSETS / ('dark' if dark else 'light')).as_posix()
    accent_hover = flatten(accent, card, .9)
    accent_pressed = flatten(accent, card, .8)
    return f'''
        QWidget {{ font-family: 'Segoe UI'; font-size: 14px; color: {fg}; background: transparent; }}
        QWidget#root {{ background: {bg}; }}
        QFrame#contentPane {{ background: {pane}; border: 1px solid {border}; border-top-left-radius: 8px; }}
        QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 4px; }}
        QLabel {{ border: none; background: transparent; }}
        QLabel#brand {{ font-size: 16px; font-weight: 600; }}
        QLabel#navHeading {{ font-size: 12px; color: {muted}; padding-left: 12px; }}
        QLabel#breadcrumb {{ font-size: 12px; color: {muted}; }}
        QLabel#title {{ font-family: 'Segoe UI Variable Display', 'Segoe UI'; font-size: 28px; font-weight: 600; }}
        QLabel#section {{ font-size: 16px; font-weight: 600; }}
        QLabel#muted {{ color: {muted}; font-size: 12px; }}
        QLabel#number, QLabel#successNumber, QLabel#errorNumber, QLabel#warningNumber {{ font-size: 28px; font-weight: 600; }}
        QLabel#successNumber {{ color: {colors['OK']}; }}
        QLabel#errorNumber {{ color: {colors['BLOCKED']}; }}
        QLabel#warningNumber {{ color: {colors['ERROR']}; }}
        QLabel#emptyTitle {{ font-size: 20px; font-weight: 600; }}
        QPushButton {{ background: {card}; border: 1px solid {border}; border-bottom-color: {'#565656' if dark else '#cdcdcd'};
                       border-radius: 4px; padding: 6px 12px; min-height: 20px; }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:pressed {{ background: {selected}; color: {muted}; border-color: {border}; }}
        QPushButton:focus {{ border: 1px solid {accent}; }}
        QPushButton:disabled {{ color: {'#858585' if dark else '#a0a0a0'}; background: {card}; border-color: {border}; }}
        QPushButton#primary {{ background: {accent}; color: {'#000000' if dark else '#ffffff'};
                             border: 1px solid {accent}; font-weight: 600; min-height: 24px; }}
        QPushButton#primary:hover {{ background: {accent_hover}; }}
        QPushButton#primary:pressed {{ background: {accent_pressed}; }}
        QPushButton#primary:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
        QPushButton#nav {{ text-align: left; background: transparent; border: 1px solid transparent;
                         padding: 8px 14px; min-height: 22px; }}
        QPushButton#nav:hover {{ background: {selected}; }}
        QPushButton#nav:checked {{ background: {selected}; font-weight: 400; }}
        QPushButton#nav:focus {{ border-color: {accent}; }}
        QPushButton#subtle, QPushButton#iconOnly {{ background: transparent; border: 1px solid transparent; }}
        QPushButton#subtle:hover, QPushButton#iconOnly:hover {{ background: {selected}; }}
        QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{ background: {field}; border: 1px solid {border};
                            border-bottom-color: {'#969696' if dark else '#8a8a8a'};
                            border-radius: 4px; padding: 6px 10px; min-height: 20px;
                            selection-background-color: {accent}; selection-color: {'#00324b' if dark else '#ffffff'}; }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ background: {hover}; }}
        QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-bottom: 2px solid {accent}; }}
        QComboBox {{ padding-right: 32px; }}
        QComboBox::drop-down {{ border: none; width: 30px; }}
        QComboBox::down-arrow {{ image: url({icon_dir}/chevron_down.svg); width: 14px; height: 14px; }}
        QComboBox QAbstractItemView {{ background: {card}; color: {fg}; border: 1px solid {border};
                    selection-background-color: {selected}; selection-color: {fg}; padding: 4px; outline: none; }}
        QSpinBox {{ padding: 6px 30px 6px 0px; }}
        QSpinBox QLineEdit {{ background: transparent; border: none; padding: 0px; min-height: 0px; }}
        QSpinBox QLineEdit:focus {{ border: none; }}
        QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: none; }}
        QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; border: none; }}
        QSpinBox::up-arrow {{ image: url({icon_dir}/chevron_up.svg); width: 12px; height: 12px; }}
        QSpinBox::down-arrow {{ image: url({icon_dir}/chevron_down.svg); width: 12px; height: 12px; }}
        QTableView {{ background: transparent; border: none; selection-background-color: {selected};
                    selection-color: {fg}; outline: none; }}
        QTableView::item {{ padding: 8px 6px; border: none; }}
        QTableView::item:hover {{ background: {hover}; }}
        QHeaderView::section {{ background: {card}; color: {muted}; padding: 10px 6px; border: none;
                               border-bottom: 1px solid {border}; font-size: 12px; }}
        QHeaderView::up-arrow {{ image: url({icon_dir}/chevron_up.svg); width: 10px; height: 10px; }}
        QHeaderView::down-arrow {{ image: url({icon_dir}/chevron_down.svg); width: 10px; height: 10px; }}
        QTabWidget::pane {{ border: none; }}
        QTabBar::tab {{ padding: 10px 12px; margin-right: 8px; border-bottom: 2px solid transparent; color: {muted}; }}
        QTabBar::tab:selected {{ color: {fg}; border-bottom-color: {accent}; }}
        QTabBar::tab:hover {{ background: {hover}; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
        QProgressBar {{ background: {border}; border: none; border-radius: 2px; }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 2px; }}
        QPlainTextEdit#log {{ font-family: 'Cascadia Code', 'Consolas'; font-size: 12px; }}
        QScrollArea {{ border: none; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {'#727272' if dark else '#b0b0b0'}; border-radius: 3px; min-height: 30px; margin: 1px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {'#727272' if dark else '#b0b0b0'}; border-radius: 3px; min-width: 30px; margin: 1px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
        QMenu {{ background: {card}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 8px 16px; border-radius: 4px; min-width: 240px; }}
        QMenu::separator {{ height: 9px; margin: 0px; }}
        QMenu::item:selected {{ background: {selected}; }}
        QLabel#toast {{ background: {card}; border: 1px solid {border}; border-radius: 4px; padding: 12px 16px; }}
        QToolTip {{ background: {card}; color: {fg}; border: 1px solid {border}; padding: 6px; }}
    '''
