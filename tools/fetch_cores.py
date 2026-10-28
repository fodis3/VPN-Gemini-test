# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch pinned, upstream Android executables. No Windows binaries are used."""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.downloads'
CACHE.mkdir(exist_ok=True)

def fetch(spec):
    abi, engine, url, member = spec
    archive = CACHE / url.rsplit('/', 1)[1]
    if not archive.exists():
        req = urllib.request.Request(url, headers={'User-Agent': 'VPN-Gemini-build/4.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        archive.write_bytes(data)
    data = archive.read_bytes()
    lock = ROOT / 'cores.lock.json'
    if lock.exists():
        expected = next((item for item in json.loads(lock.read_text(encoding='utf-8')) if item['url'] == url), None)
        if expected and hashlib.sha256(data).hexdigest() != expected['archive_sha256']:
            raise RuntimeError(f'Archive SHA-256 mismatch: {archive.name}')
    if engine == 'xray':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            binary = z.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
            entry = next(m for m in t.getmembers() if m.isfile() and m.name.endswith('/sing-box'))
            binary = t.extractfile(entry).read()
    if expected and hashlib.sha256(binary).hexdigest() != expected['binary_sha256']:
        raise RuntimeError('Binary SHA-256 mismatch')
    assert binary[:4] == b'\x7fELF', 'Not an Android ELF executable'
    dest = ROOT / 'app/src/main/jniLibs' / abi / ('lib' + engine + '.so')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(binary)
    return {'abi': abi, 'engine': engine, 'url': url, 'archive_sha256': hashlib.sha256(data).hexdigest(), 'binary_sha256': hashlib.sha256(binary).hexdigest()}

if __name__ == '__main__':
    manifest = json.loads((ROOT / 'cores.lock.json').read_text(encoding='utf-8'))
    specs = [(item['abi'], item['engine'], item['url'], item.get('member', 'xray')) for item in manifest]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, specs))
    print('Android cores ready: armeabi-v7a, arm64-v8a, x86_64')
