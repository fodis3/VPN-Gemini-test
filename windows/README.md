# VPN Gemini для Windows

Настольное приложение на PySide6 в стиле Fluent Design.
Импорт подписок и конфигураций, параллельная проверка Gemini, фильтры,
журнал, копирование результатов и экспорт CSV.

## Запуск

Скачайте `vpn_gemini_windows_v4_0_0.exe` из релиза `windows-v4.0.0`.
Python и Qt устанавливать не требуется, Xray и sing-box включены.
Сборка предназначена для Windows x64, проверена в Windows 11.
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
