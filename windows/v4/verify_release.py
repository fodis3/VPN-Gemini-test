"""Launch the built EXE in an empty directory to verify bundled dependencies."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'vpn_gemini_v4.exe'
with tempfile.TemporaryDirectory(prefix='vpn_gemini_4_release_') as temp:
    folder = Path(temp)
    executable = folder / 'vpn_gemini_v4.exe'
    shutil.copy2(SOURCE, executable)
    report = folder / 'smoke.json'
    result = subprocess.run([str(executable), '--smoke-test', str(report)], cwd=folder,
                            timeout=60, capture_output=True)
    assert result.returncode == 0, (result.returncode, result.stderr)
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['version'] == '4.0.1'
    assert data['pages'] == 3
    assert data['fluent_icons'] >= 30, data
    for key in ('xray', 'singbox'):
        assert Path(data[key]).is_file(), data
        assert Path(data[key]).is_relative_to(folder), data
    shutil.copy2(report.with_suffix('.png'), ROOT / 'artifacts' / 'v4_release.png')
    (ROOT / 'artifacts' / 'v4_release_check.json').write_text(json.dumps({
        'version': data['version'], 'pages': data['pages'],
        'standalone_launch': 'PASS', 'bundled_fluent_icons': data['fluent_icons'], 'bundled_xray': 'PASS',
        'bundled_singbox': 'PASS', 'exit_code': result.returncode,
    }, indent=2), encoding='utf-8')
    print('Standalone EXE: PASS; 4.0.1 UI, Qt platform, Xray and sing-box bundled.')
