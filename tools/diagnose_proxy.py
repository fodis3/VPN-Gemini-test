# SPDX-License-Identifier: GPL-3.0-or-later
"""Local Windows-core diagnostic. Read a share URI from stdin; never print/save it."""
from pathlib import Path
import http.client
import json
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

workspace = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(workspace / 'v2'))
from v2_parser import parse_text_block
from v2_xray import build_xray_config
from v2_proxy import extract_country_from_gemini_page

def exact(sock, count):
    data = b''
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise EOFError('Tunnel closed')
        data += part
    return data

def main():
    uri = sys.stdin.readline().strip()
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    config = build_xray_config(parse_text_block(uri)[0], port)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', prefix='vpn-diagnostic-', delete=False, encoding='utf-8') as handle:
        json.dump(config, handle)
        config_path = Path(handle.name)
    process = None
    try:
        process = subprocess.Popen([str(workspace / 'bin/xray.exe'), 'run', '-c', str(config_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                socket.create_connection(('127.0.0.1', port), .1).close()
                break
            except OSError:
                time.sleep(.05)
        url = 'https://gemini.google.com/app'
        for _ in range(5):
            u = urlsplit(url)
            start = time.perf_counter()
            with socket.create_connection(('127.0.0.1', port), 15) as sock:
                sock.settimeout(15)
                sock.sendall(b'\x05\x01\x00')
                assert exact(sock, 2) == b'\x05\x00'
                host = u.hostname.encode()
                sock.sendall(bytes([5, 1, 0, 3, len(host)]) + host + (443).to_bytes(2, 'big'))
                header = exact(sock, 4)
                assert header[1] == 0
                size = {1: 4, 4: 16}.get(header[3])
                exact(sock, (size if size else exact(sock, 1)[0]) + 2)
                ack_ms = round((time.perf_counter() - start) * 1000, 3)
                tls = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
                tls_ms = round((time.perf_counter() - start) * 1000, 1)
                conn = http.client.HTTPSConnection(u.hostname, 443, timeout=15)
                conn.sock = tls
                conn.request('GET', u.path or '/', headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache'})
                response = conn.getresponse()
                body = response.read(8 * 1024 * 1024).decode('utf-8', 'replace')
                location = response.getheader('Location')
                conn.close()
            country = re.search(r'"vXmutd"\s*:\s*"([A-Z]{2})"', body.replace('\\"', '"'))
            title = re.search(r'<title[^>]*>(.*?)</title>', body, re.S)
            desktop = extract_country_from_gemini_page(body.encode())
            idx = body.find('vXmutd')
            fragment = body[max(idx-5, 0):idx+380] if idx >= 0 else ''
            # Keep only shape and two-letter country codes; never dump bootstrap tokens.
            shape = re.sub(r'"(?:\\.|[^"\\])*"', lambda m: m.group() if re.fullmatch(r'"[A-Z]{2}"', m.group()) else '"<text>"', fragment)
            print(json.dumps({'http': response.status, 'host': u.hostname, 'path': u.path, 'socks_ack_ms': ack_ms,
                'verified_tls_ms': tls_ms, 'bytes': len(body), 'title': title.group(1)[:120] if title else '',
                'country': desktop['country_code'],
                'script_markers': 'BardChatUi' in body and 'geminiweb-pa' in body,
                'desktop': {k:v for k,v in desktop.items() if k!='raw_vxmutd'},
                'vx_shape': re.sub(r'[A-Za-z0-9_-]+', lambda m: m.group() if m.group() in ['vXmutd','US','RU','null','true','false'] or re.fullmatch(r'u[0-9a-fA-F]{4}', m.group()) else '<'+str(len(m.group()))+'>', body[idx:idx+160]) if idx>=0 else '',
                'raw_block_markers': [p for p in ['location_unavailable','/unavailable',"not currently supported","not supported in your country","not available in your country"] if p in body.lower()]}))
            if response.status in (301, 302, 303, 307, 308) and location and location.startswith('https://'):
                url = location
            else:
                break
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc).replace(uri, '[configuration]'))
    finally:
        if process:
            process.terminate()
            process.wait(timeout=5)
        config_path.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
