"""Offline regression checks and actual Qt widget renders. No VPN keys required."""
import os
os.environ['QT_QPA_PLATFORM'] = 'windows'
import sys
import csv
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'v2'), str(ROOT / 'v4')]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
import engine
import app as ui
from v2_parser import parse_text_block

KEYS = '\n'.join(f'vless://00000000-0000-0000-0000-000000000001@server{i}.example:443?security=tls#{name}'
                 for i, name in enumerate(['Amsterdam', 'Frankfurt', 'Paris', 'Helsinki']))


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyle('Fusion')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        self.window = ui.MainWindow(self.settings)
        self.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.window.show()
        QTest.qWait(40)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.qt.processEvents()
        self.temp.cleanup()

    def wait_done(self):
        limit = time.monotonic() + 5
        while (self.window.running or self.window.importing or self.window.jobs) and time.monotonic() < limit:
            QTest.qWait(20)
        self.assertFalse(self.window.running)
        self.assertFalse(self.window.jobs)

    def test_engine_timeout_cancellation_and_order(self):
        configs = parse_text_block(KEYS)
        stop = threading.Event()
        seen = []
        callbacks = []
        def fake(cfg, **kwargs):
            seen.append(kwargs['gemini_timeout'])
            stop.set()
            return engine.TestResult(cfg=cfg, status='OK')
        with patch.object(engine, 'test_one_vpn', fake):
            results = engine.run_batch_test(configs, max_workers=1, stop_event=stop,
                gemini_timeout=17, on_result=lambda r, d, t: callbacks.append((d, t)))
        self.assertEqual(seen, [17])
        self.assertEqual([r.status for r in results], ['OK', 'CANCELLED', 'CANCELLED', 'CANCELLED'])
        self.assertEqual([r.cfg for r in results], configs)
        self.assertEqual(callbacks, [(i, 4) for i in range(1, 5)])

    def test_grpc_share_link_transport_roundtrip(self):
        from v2_xray import build_xray_config
        from v2_parser import ProxyConfig
        for scheme, credentials in [('vless', '00000000-0000-0000-0000-000000000001'),
                                    ('trojan', 'sample-password')]:
            link = (f'{scheme}://{credentials}@vpn.example:443?type=grpc&security=tls'
                    '&serviceName=my%2Ftunnel&authority=grpc.example&mode=multi'
                    '&alpn=h2%2Chttp%2F1.1&sni=tls.example')
            cfg = parse_text_block(link)[0]
            stream = build_xray_config(cfg, 16000)['outbounds'][0]['streamSettings']
            self.assertEqual(stream['grpcSettings'], {'serviceName': 'my/tunnel',
                             'authority': 'grpc.example', 'multiMode': True})
            self.assertEqual(stream['tlsSettings']['alpn'], ['h2', 'http/1.1'])
            self.assertEqual(stream['tlsSettings']['serverName'], 'tls.example')
            gun = parse_text_block(link.replace('mode=multi', 'mode=gun'))[0]
            self.assertFalse(build_xray_config(gun, 16000)['outbounds'][0]
                             ['streamSettings']['grpcSettings']['multiMode'])
        legacy = ProxyConfig()
        legacy.protocol, legacy.network, legacy.path = 'vmess', 'grpc', '/legacy'
        self.assertEqual(build_xray_config(legacy, 16000)['outbounds'][0]
                         ['streamSettings']['grpcSettings']['serviceName'], 'legacy')

    def test_fluent_icons_navigation_and_keyboard_switch(self):
        from fluent import ASSETS
        from PySide6.QtSvg import QSvgRenderer
        icons = list((ASSETS / 'icons').glob('*.svg'))
        self.assertGreaterEqual(len(icons), 30)
        for path in icons:
            self.assertTrue(QSvgRenderer(str(path)).isValid(), str(path))
        w = self.window
        self.assertTrue(all(not b.icon().isNull() for b in w.nav_buttons))
        self.assertNotIn('▶', w.run_button.text())
        w.navigate(2)
        self.assertEqual([b.isChecked() for b in w.nav_buttons], [False, False, True])
        w.motion.setFocus()
        before = w.motion.isChecked()
        QTest.keyClick(w.motion, Qt.Key.Key_Space)
        self.assertNotEqual(w.motion.isChecked(), before)
        self.assertEqual(self.qt.property('motion'), not before)

    def test_context_menu_editing_and_render(self):
        from menus import edit_menu
        w = self.window
        previous = self.qt.clipboard().text()
        try:
            w.keys.setPlainText('Example text')
            w.keys.selectAll()
            for theme, name in [(1, 'dark'), (2, 'light')]:
                w.theme.setCurrentIndex(theme)
                menu = edit_menu(w.keys)
                menu.ensurePolished()
                menu.resize(menu.sizeHint())
                menu.setActiveAction(menu.actions()[4])
                menu.grab().save(str(ROOT / 'artifacts' / f'v4_context_menu_{name}.png'))
                menu.deleteLater()
            menu = edit_menu(w.keys)
            actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
            actions['Вырезать'].trigger()
            self.assertEqual(w.keys.toPlainText(), '')
            self.assertEqual(self.qt.clipboard().text(), 'Example text')
            menu2 = edit_menu(w.keys)
            {a.text(): a for a in menu2.actions()}['Отменить'].trigger()
            self.assertEqual(w.keys.toPlainText(), 'Example text')
            w.keys.setReadOnly(True)
            menu3 = edit_menu(w.keys)
            readonly = {a.text(): a for a in menu3.actions()}
            self.assertFalse(readonly['Вырезать'].isEnabled())
            self.assertFalse(readonly['Вставить'].isEnabled())
            for m in (menu, menu2, menu3):
                m.deleteLater()
        finally:
            self.qt.clipboard().setText(previous)

    def test_system_accent_palette_and_live_refresh(self):
        import system_theme
        data = bytes.fromhex('cfe6ed00 aec5d500 738cac00 5d769c00 495c8200 2f3c6100 11173b00')
        with patch.object(system_theme, '_read_palette_bytes', return_value=data):
            palette = system_theme.read_accent_palette()
        self.assertEqual(palette.base, '#5d769c')
        self.assertEqual(palette.fill(True), '#aec5d5')
        self.assertEqual(palette.fill(False), '#495c82')
        with patch.object(system_theme, '_read_palette_bytes', return_value=b'bad'):
            self.assertEqual(system_theme.read_accent_palette(), system_theme.AccentPalette())
        w = self.window
        custom = system_theme.AccentPalette(base='#8a008a', dark_fill='#efa7ef', light_fill='#6d006d')
        with patch.object(ui, 'read_accent_palette', return_value=custom):
            w.refresh_system_accent()
        for mode, color in [(1, '#efa7ef'), (2, '#6d006d')]:
            w.theme.setCurrentIndex(mode)
            self.assertEqual(w.motion.property('accent'), color)
            self.assertEqual(w.nav_buttons[0].property('accent'), color)
            self.assertIn(f'background: {color}', w.styleSheet())

    def test_settings_number_spacing(self):
        w = self.window
        w.navigate(2)
        for mode, name in [(1, 'dark'), (2, 'light')]:
            w.theme.setCurrentIndex(mode)
            w.workers.setFocus()
            QTest.qWait(280)
            for control, field in [(w.workers, 'workers'), (w.timeout, 'timeout')]:
                margin = control.lineEdit().textMargins().left()
                self.assertGreaterEqual(margin, 12)
                self.assertGreaterEqual(control.lineEdit().x() + margin, 12)
                self.assertGreater(control.lineEdit().width(), 60)
                control.grab().save(str(ROOT / 'artifacts' / f'v4_{field}_{name}.png'))
            w.grab().save(str(ROOT / 'artifacts' / f'v4_settings_{name}.png'))

    def test_ui_lifecycle_filters_sort_copy_export_themes(self):
        w = self.window
        w.timeout.setValue(17)
        w.keys.setPlainText(KEYS)
        states = ['OK', 'BLOCKED', 'ERROR', 'TIMEOUT']
        pings = [120, 9, 80, 30]
        def fake(cfg, **kwargs):
            self.assertEqual(kwargs['gemini_timeout'], 17)
            i = int(cfg.host[6])
            return engine.TestResult(cfg=cfg, label=cfg.label(), status=states[i],
                country_code=['NL', 'DE', 'FR', 'FI'][i], ping_ok=True,
                ping_ms=pings[i], total_ms=1500, gemini_chat_ui=i == 0)
        with patch.object(engine, 'test_one_vpn', fake):
            w.start_test()
            self.assertFalse(w.run_button.isEnabled())
            self.wait_done()
        self.assertEqual([c.text() for c in w.counters], ['4', '1', '1', '2'])
        for col in range(1, 6):
            self.assertEqual(w.model.item(0, col).textAlignment(), Qt.AlignmentFlag.AlignCenter)
            self.assertEqual(w.model.headerData(col, Qt.Orientation.Horizontal,
                             Qt.ItemDataRole.TextAlignmentRole), Qt.AlignmentFlag.AlignCenter)
        w.filter.setCurrentIndex(1)
        self.assertEqual(w.proxy.rowCount(), 1)
        w.filter.setCurrentIndex(3)
        self.assertEqual(w.proxy.rowCount(), 2)
        w.filter.setCurrentIndex(0)
        w.search.setText('Frankfurt')
        self.assertEqual(w.proxy.rowCount(), 1)
        w.search.clear()
        w.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.assertEqual(w.proxy.index(0, 3).data(), '9')
        clipboard_before = self.qt.clipboard().text()
        try:
            w.copy_ok()
            self.assertEqual(self.qt.clipboard().text(), w.results[0].cfg.raw)
        finally:
            self.qt.clipboard().setText(clipboard_before)
        report = str(Path(self.temp.name) / 'results.csv')
        with patch.object(ui.QFileDialog, 'getSaveFileName', return_value=(report, 'CSV')):
            w.export_csv()
        with open(report, encoding='utf-8-sig', newline='') as stream:
            self.assertEqual(len(list(csv.reader(stream))), 5)
        w.toast.hide()
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        for theme, name in [(1, 'dark'), (2, 'light')]:
            w.theme.setCurrentIndex(theme)
            QTest.qWait(300)
            self.assertTrue(w.grab().save(str(artifacts / f'v4_{name}.png')))
        w.navigate(2)
        QTest.qWait(300)
        w.grab().save(str(artifacts / 'v4_settings.png'))
        w.navigate(1)
        QTest.qWait(300)
        w.grab().save(str(artifacts / 'v4_log.png'))
        w.navigate(0)
        w.resize(1100, 740)
        QTest.qWait(300)
        w.grab().save(str(artifacts / 'v4_compact.png'))
        # Rerun with an active selection and sorted/filtered proxy model.
        w.table.selectRow(0)
        with patch.object(engine, 'test_one_vpn', fake):
            w.start_test()
            self.wait_done()
        self.assertEqual(w.model.rowCount(), 4)

    def test_import_failure_recovers_controls(self):
        w = self.window
        w.url.setText('https://subscription.example/test')
        with patch.object(ui, 'fetch_subscription', side_effect=OSError('unavailable')):
            w.import_subscription()
            self.wait_done()
        self.assertTrue(w.import_button.isEnabled())
        self.assertTrue(w.run_button.isEnabled())
        self.assertIn('OSError', w.log_view.toPlainText())

    def test_import_and_cancellation(self):
        w = self.window
        w.url.setText('https://subscription.example/test')
        with patch.object(ui, 'fetch_subscription', return_value=parse_text_block(KEYS)):
            w.import_subscription()
            self.wait_done()
        self.assertEqual(len(parse_text_block(w.keys.toPlainText())), 4)
        w.workers.setValue(1)
        started = threading.Event()
        def fake(cfg, **kwargs):
            started.set()
            time.sleep(.1)
            return engine.TestResult(cfg=cfg, label=cfg.label(), status='ERROR')
        with patch.object(engine, 'test_one_vpn', fake):
            w.start_test()
            limit = time.monotonic() + 3
            while not started.is_set() and time.monotonic() < limit:
                QTest.qWait(10)
            self.assertTrue(started.is_set())
            w.stop_test()
            self.wait_done()
        self.assertGreater(sum(r.status == 'CANCELLED' for r in w.results), 0)
        self.assertEqual(w.counters[3].text(), '1')
        self.assertTrue(w.run_button.isEnabled())


if __name__ == '__main__':
    unittest.main(verbosity=2)
