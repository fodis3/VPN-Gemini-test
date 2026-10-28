"""Regression coverage for subscription loss and transport fidelity."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import struct

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'v2'), str(ROOT / 'v4')]
from v2_parser import parse_text_block
from v2_xray import build_xray_config, build_singbox_config
from engine import test_one_vpn

UUID = '00000000-0000-0000-0000-000000000001'


def b64(text):
    return base64.b64encode(text.encode()).decode().rstrip('=')


class Imports(unittest.TestCase):
    def test_frozen_core_cache_is_architecture_specific(self):
        import v2_xray
        arch = 'x86' if struct.calcsize('P') == 4 else 'x64'
        other = 'x64' if arch == 'x86' else 'x86'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, finder in [('xray.exe', v2_xray._get_xray_path), ('sing-box.exe', v2_xray._get_singbox_path)]:
                expected = root / 'bin' / arch / name
                expected.parent.mkdir(parents=True, exist_ok=True)
                expected.write_bytes(b'correct architecture')
                wrong = root / 'bin' / other / name
                wrong.parent.mkdir(parents=True, exist_ok=True)
                wrong.write_bytes(b'wrong architecture')
                with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(root / 'app.exe')):
                    self.assertEqual(Path(finder()), expected)

    def test_eighty_records_keep_five_unsupported_entries(self):
        valid = [f'vless://{UUID}@s{i}.example:443?security=tls#Server{i}' for i in range(75)]
        unsupported = [f'ssr://unrecognized{i}#Unsupported{i}' for i in range(5)]
        for text in ('\n'.join(valid + unsupported), b64('\n'.join(valid + unsupported))):
            results = parse_text_block(text)
            self.assertEqual(len(results), 80)
            errors = [c for c in results if c.extra.get('import_error')]
            self.assertEqual(len(errors), 5)
            self.assertEqual(test_one_vpn(errors[0]).status, 'ERROR')
            self.assertEqual(results[-1].raw, unsupported[-1])

    def test_base64_hy2_tuic_and_multi_link_lines(self):
        links = ['hy2://user%3Apass@h.example:443?sni=tls.example',
                 f'tuic://{UUID}:pass@t.example:443?alpn=h3',
                 f'vless://{UUID}@v.example:443?security=tls#Name with spaces']
        self.assertEqual(len(parse_text_block(b64('\n'.join(links)))), 3)
        self.assertEqual(len(parse_text_block('  '.join(links))), 3)
        cfg = parse_text_block(links[0])[0]
        self.assertEqual(cfg.password, 'user:pass')

    def test_shadowsocks_uri_variants_and_invalid_port(self):
        forms = [f'ss://{b64("aes-128-gcm:p@ss")}@server.example:443',
                 f'ss://{b64("aes-128-gcm:p@ss@server.example:443")}',
                 'ss://aes-128-gcm:p%40ss@server.example:443']
        for link in forms:
            cfg = parse_text_block(link)[0]
            self.assertEqual((cfg.method, cfg.password, cfg.host, cfg.port),
                             ('aes-128-gcm', 'p@ss', 'server.example', 443))
        invalid = parse_text_block(f'vless://{UUID}@bad.example:99999')[0]
        self.assertIn('import_error', invalid.extra)

    def test_json_arrays_and_import_export_roundtrip(self):
        xray = {'protocol': 'vless', 'tag': 'original', 'settings': {'vnext': [{
            'address': 'vpn.example', 'port': 443, 'users': [{'id': UUID, 'encryption': 'none'}]}]},
            'streamSettings': {'network': 'xhttp', 'security': 'tls',
                'xhttpSettings': {'host': 'front.example', 'path': '/secret-path',
                    'extra': {'noSSEHeader': True}}, 'tlsSettings': {'serverName': 'tls.example'}}}
        singbox = {'type': 'hysteria2', 'tag': 'hy', 'server': 'hy.example', 'server_port': 443,
                   'password': 'test', 'tls': {'enabled': True, 'server_name': 'hy.example'}}
        initial = parse_text_block(json.dumps([{'outbounds': [xray]}, {'outbounds': [singbox]}]))
        reparsed = parse_text_block('\n'.join(c.raw for c in initial))
        self.assertEqual(len(reparsed), 2)
        actual = build_xray_config(reparsed[0], 16000)['outbounds'][0]
        self.assertEqual(actual['streamSettings'], xray['streamSettings'])
        self.assertEqual(build_singbox_config(reparsed[1], 16000)['outbounds'][0]['password'], 'test')

    def test_xhttp_pq_options_and_installed_core_validation(self):
        extra = '%7B%22noSSEHeader%22%3Atrue%7D'
        link = (f'vless://{UUID}@vpn.example:443?type=xhttp&security=tls'
                f'&path=%2Ftransfer&host=front.example&mode=stream-one&extra={extra}')
        cfg = parse_text_block(link)[0]
        stream = build_xray_config(cfg, 16000)['outbounds'][0]['streamSettings']
        self.assertEqual(stream['xhttpSettings'], {'path': '/transfer', 'host': 'front.example',
                         'mode': 'stream-one', 'extra': {'noSSEHeader': True}})
        pq = parse_text_block(link + '&encryption=mlkem768x25519plus.native.1rtt.test')[0]
        self.assertEqual(build_xray_config(pq, 16000)['outbounds'][0]['settings']['vnext'][0]
                         ['users'][0]['encryption'], 'mlkem768x25519plus.native.1rtt.test')
        trojan = parse_text_block('trojan://test%40password@vpn.example:443?security=tls')[0]
        for case in (cfg, trojan):
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'cfg.json'
                path.write_text(json.dumps(build_xray_config(case, 16000)), encoding='utf-8')
                result = subprocess.run([str(ROOT / 'bin' / ('x86' if __import__('struct').calcsize('P') == 4 else 'x64') / 'xray.exe'), 'run', '-test', '-c', str(path)],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
