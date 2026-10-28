"""Build version 4 without deleting previous release artifacts."""
from pathlib import Path
import shutil
import subprocess
import sys
import os

ROOT = Path(__file__).resolve().parent


def build():
    output = ROOT / 'dist' / 'v4'
    sys.path[:0] = [str(ROOT / 'v4'), str(ROOT / 'v2')]
    from PySide6.QtWidgets import QApplication
    from app import app_icon
    application = QApplication.instance() or QApplication([])
    icon = ROOT / 'v4' / 'app.ico'
    app_icon().pixmap(64, 64).save(str(icon))
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--name', 'vpn_gemini_v4',
        '--distpath', str(output), '--workpath', str(ROOT / 'build' / 'v4'),
        '--paths', str(ROOT / 'v2'), '--paths', str(ROOT / 'v4'),
        '--exclude-module', 'tkinter', '--exclude-module', 'PySide6.QtWebEngineCore',
        '--exclude-module', 'PySide6.QtQml', '--exclude-module', 'PySide6.QtQuick',
        '--version-file', str(ROOT / 'v4' / 'version_info.txt')]
    command += ['--icon', str(icon)]
    command += ['--add-data', f'{ROOT / "v4" / "assets"};assets']
    for name in ('xray.exe', 'sing-box.exe'):
        source = ROOT / 'bin' / name
        if not source.is_file():
            raise FileNotFoundError(source)
        command += ['--add-binary', f'{source};bin']
    command += [str(ROOT / 'v4' / 'main.py')]
    # Native toolchains in the shell PATH may contain incompatible namesakes of
    # Windows DLLs (notably ICU). Keep discovery limited to Python and Windows.
    build_env = os.environ.copy()
    windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    python_root = Path(sys.base_prefix)
    build_env['PATH'] = os.pathsep.join(str(p) for p in (
        python_root, python_root / 'DLLs', python_root / 'Scripts',
        windows / 'System32', windows))
    subprocess.run(command, cwd=ROOT, env=build_env, check=True)
    # A failed executable must never replace the user-facing release.
    subprocess.run([sys.executable, str(ROOT / 'v4' / 'verify_release.py'),
                    str(output / 'vpn_gemini_v4.exe')], cwd=ROOT, env=build_env, check=True)
    target = ROOT / 'vpn_gemini_v4.exe'
    try:
        shutil.copy2(output / target.name, target)
    except PermissionError:
        # Leave an open instance and its unsaved configuration/results intact.
        target = ROOT / 'vpn_gemini_v4_updated.exe'
        shutil.copy2(output / 'vpn_gemini_v4.exe', target)
        print('Existing release is in use; wrote the update to a separate executable.')
    print(f'Ready: {target} ({target.stat().st_size / 1024**2:.1f} MB)')


if __name__ == '__main__':
    build()
