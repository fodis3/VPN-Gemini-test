"""Collect pinned dependency licenses from Go's module cache, without local paths."""
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parents[1]
data = subprocess.check_output(['go', 'list', '-m', '-json', 'all'], cwd=root / 'engine').decode()
decoder = json.JSONDecoder()
modules = []
while data.strip():
    module, at = decoder.raw_decode(data.lstrip())
    modules.append(module)
    data = data.lstrip()[at:]
parts = ['VPN Gemini iOS 4.0.0 — GPL-3.0-or-later\n', (root / 'LICENSE').read_text()]
for module in modules:
    if not module.get('Dir') or module.get('Main'):
        continue
    directory = Path(module['Dir'])
    licenses = [p for p in directory.iterdir() if p.is_file() and
                p.name.upper().split('.')[0] in {'LICENSE', 'LICENCE', 'COPYING', 'NOTICE'}]
    parts.append('\n\n' + '=' * 70 + '\n' + module['Path'] + ' ' + module.get('Version', '') + '\n')
    for path in sorted(licenses):
        parts.append(path.name + '\n' + path.read_text(errors='replace'))
(root / 'App/NOTICES.txt').write_text('\n'.join(parts), encoding='utf-8')
print(f'Collected notices for {len(modules)-1} pinned modules')
