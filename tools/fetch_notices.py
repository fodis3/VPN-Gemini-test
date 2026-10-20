from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
dest = root / 'app/src/main/assets/licenses'
dest.mkdir(parents=True, exist_ok=True)
sources = {
    'Xray-MPL-2.0.txt': 'https://raw.githubusercontent.com/XTLS/Xray-core/v26.3.27/LICENSE',
    'sing-box-notice.txt': 'https://raw.githubusercontent.com/SagerNet/sing-box/v1.14.3/LICENSE',
    'GPL-3.0.txt': 'https://www.gnu.org/licenses/gpl-3.0.txt',
    'Apache-2.0.txt': 'https://www.apache.org/licenses/LICENSE-2.0.txt',
}
for name, url in sources.items():
    (dest / name).write_bytes(urllib.request.urlopen(url, timeout=40).read())
(dest / 'SOURCES.txt').write_text('''Unmodified upstream Android executables, launched as separate processes.
Xray-core v26.3.27, MPL-2.0
Source: https://github.com/XTLS/Xray-core/archive/refs/tags/v26.3.27.tar.gz
Build instructions: https://github.com/XTLS/Xray-core/tree/v26.3.27
sing-box v1.14.3, GPL-3.0-or-later
Source: https://github.com/SagerNet/sing-box/archive/refs/tags/v1.14.3.tar.gz
Build instructions: https://github.com/SagerNet/sing-box/tree/v1.14.3
AndroidX / Jetpack Compose, OkHttp and Kotlin: Apache-2.0.
Exact Gradle dependencies are pinned in app/build.gradle.kts.
''', encoding='utf-8')
print('License notices ready')
