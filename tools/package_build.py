"""Check APK payload and package source separately from local SDK/build caches."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

root = Path(__file__).resolve().parents[1]
workspace = root.parent
apk = root / 'app/build/outputs/apk/debug/app-debug.apk'
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
    for name in ['Xray-MPL-2.0.txt', 'sing-box-notice.txt', 'GPL-3.0.txt', 'SOURCES.txt']:
        assert len(z.read('assets/licenses/' + name)) > 100
    assert 'classes.dex' in z.namelist()

preview = root / 'preview'
preview.mkdir(exist_ok=True)
for image in (root / 'app/build/screenshots').glob('*.png'):
    shutil.copy2(image, preview / image.name)

dest = workspace / 'vpn_gemini_android_v4_0_5.apk'
shutil.copy2(apk, dest)
with zipfile.ZipFile(workspace / 'vpn_gemini_android_v4_0_5_source.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {'.git', '.gradle', '.kotlin', 'build', '.downloads', 'jniLibs', '__pycache__'} for part in relative.parts):
            continue
        if relative.name == 'local.properties' or path.suffix == '.log':
            continue
        z.write(path, Path('android') / relative)
sha = hashlib.sha256(dest.read_bytes()).hexdigest()
(workspace / 'vpn_gemini_android_v4_0_5.apk.sha256').write_text(sha + '  vpn_gemini_android_v4_0_5.apk\n', encoding='ascii')
print(f'Packaged {dest.name}: {dest.stat().st_size / 1024 / 1024:.1f} MiB; {count} tests; all four native core hashes match.')
