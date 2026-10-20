# SPDX-License-Identifier: GPL-3.0-or-later
"""Check APK payload and package source separately from local SDK/build caches."""
import os
import subprocess
import argparse
import re
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

root = Path(__file__).resolve().parents[1]
workspace = root.parent
parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['debug', 'release'], default='debug')
args = parser.parse_args()
version = re.search(r'versionName = "([0-9.]+)"', (root / 'app/build.gradle.kts').read_text(encoding='utf-8')).group(1)
artifact_name = 'vpn_gemini_android_v' + version.replace('.', '_')
apk = root / f'app/build/outputs/apk/{args.variant}/app-{args.variant}.apk'
results = root / 'app/build/test-results/testDebugUnitTest'
count = 0
for report in results.glob('TEST-*.xml'):
    suite = ET.parse(report).getroot()
    assert suite.get('failures') == '0' and suite.get('errors') == '0'
    count += int(suite.get('tests'))
with zipfile.ZipFile(apk) as z:
    assert z.testzip() is None
    for core in json.loads((root / 'cores.lock.json').read_text(encoding='utf-8')):
        binary = z.read(f"lib/{core['abi']}/lib{core['engine']}.so")
        assert hashlib.sha256(binary).hexdigest() == core['binary_sha256']
    for name in ['VPN-Gemini.txt', 'Xray-MPL-2.0.txt', 'sing-box-notice.txt', 'GPL-3.0.txt', 'SOURCES.txt']:
        assert len(z.read('assets/licenses/' + name)) > 100
    assert 'classes.dex' in z.namelist()

if args.variant == 'release':
    sdk_path = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk_path:
        raise RuntimeError('Set ANDROID_HOME to verify the release signature with apksigner')
    executable = 'apksigner.bat' if os.name == 'nt' else 'apksigner'
    signers = sorted((Path(sdk_path) / 'build-tools').glob('*/' + executable))
    if not signers:
        raise RuntimeError('Android SDK apksigner not found')
    subprocess.run([str(signers[-1]), 'verify', str(apk)], check=True)

preview = root / 'preview'
preview.mkdir(exist_ok=True)
for image in (root / 'app/build/screenshots').glob('*.png'):
    shutil.copy2(image, preview / image.name)

dest = workspace / (artifact_name + '.apk')
shutil.copy2(apk, dest)
with zipfile.ZipFile(workspace / (artifact_name + '_source.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {'.git', '.gradle', '.kotlin', 'build', '.downloads', 'jniLibs', '__pycache__'} for part in relative.parts):
            continue
        if relative.name in {'local.properties', 'keystore.properties', 'signing.json'} or path.suffix in {'.log', '.p12', '.jks', '.keystore'}:
            continue
        z.write(path, Path('android') / relative)
sha = hashlib.sha256(dest.read_bytes()).hexdigest()
(workspace / (artifact_name + '.apk.sha256')).write_text(sha + '  ' + dest.name + '\n', encoding='ascii')
print(f'Packaged {dest.name}: {dest.stat().st_size / 1024 / 1024:.1f} MiB; {count} tests; all four native core hashes match.')
