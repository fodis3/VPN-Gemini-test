# VPN Gemini для Windows

Настольное приложение на PySide6 в стиле Fluent Design.
Импорт подписок и конфигураций, параллельная проверка Gemini, фильтры,
журнал, копирование результатов и экспорт CSV.

## Запуск

Скачайте `vpn_gemini_windows_v4_0_1_x64.exe` или `vpn_gemini_windows_v4_0_1_x86.exe`
из релиза `windows-v4.0.1`.
Python и Qt устанавливать не требуется, Xray и sing-box включены.
Доступны Windows x64 и x86 (32 бит). Сборки проверены в Windows 11 x64;
x86 запускается через WOW64. Физическая 32-битная ОС отдельно не проверена.
Минимум — Windows 10; Windows 7 не поддерживается этими версиями ядер.
EXE не подписан сертификатом издателя.

## Сборка из исходников

Из этого каталога:

```powershell
python -m pip install -r requirements-v4.txt
python tools/fetch_cores.py
python v4/test_imports.py
python v4/verify.py
python v4_build.py
```

Сборка создаёт `dist/v4/vpn_gemini_v4.exe` и проверяет автономный запуск.
Артефакты проверок сохраняются в `artifacts` (создайте каталог перед проверками).
Ядра: Xray 26.3.27 и sing-box 1.14.3, официальные исходники:
https://github.com/XTLS/Xray-core/tree/v26.3.27
https://github.com/SagerNet/sing-box/tree/v1.14.3
Лицензии: MPL-2.0 и GPL-3.0-or-later. Иконки Microsoft Fluent — MIT.
PySide6 / Qt — LGPL-3.0; исходники и инструкции Qt: https://code.qt.io/cgit/pyside/pyside-setup.git/ и https://code.qt.io/cgit/qt/qtbase.git/.

CSV содержит исходные конфигурации; храните его как приватные данные.
Проверка не выполняет вход в Google или генерацию ответа модели.

## Архитектуры

Для x64: Python x64 и `requirements-v4.txt` (PySide6 / Qt 6).
Для x86: Python 3.10 x86 и `requirements-win32.txt` (PySide2 / Qt 5.15).
Запускайте `v4_build.py` соответствующим Python. Общий интерфейс и движок
используют слой `v4/qt_compat`; настройки, темы и анимации сохраняются.
Ядра загружаются в `bin/x86` и `bin/x64`, их SHA-256 закреплены в `cores.lock.json`.
PySide2 / Qt 5.15 сохраняют LGPL-лицензию; исходники: https://code.qt.io/cgit/pyside/pyside-setup.git/?h=5.15.2 и https://code.qt.io/cgit/qt/qtbase.git/?h=5.15.2 .
