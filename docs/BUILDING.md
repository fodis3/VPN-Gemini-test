# Сборка Android-приложения

Нужны JDK 17+, Android SDK Platform 37 / Build Tools 36 и Python 3.
Укажите SDK через `ANDROID_HOME` или `local.properties` (`sdk.dir=...`).

## Ядра и отладочная сборка

Из корня проекта:

```sh
python tools/fetch_cores.py
# Linux/macOS:
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
# Windows:
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`.
Официальные URL, версии и SHA-256 ядер закреплены в `cores.lock.json`.
Бинарные ядра скачиваются отдельно и не хранятся в Git.
Xray 26.3.27 и sing-box 1.14.3 запускаются как отдельные процессы.
Ссылки на соответствующие исходники находятся в
`app/src/main/assets/licenses/SOURCES.txt`.

## Подписанная сборка выпуска

Создайте собственный keystore или используйте сохранённый постоянный ключ.
Задайте локальные переменные окружения:

| Переменная | Значение |
| --- | --- |
| `VPN_GEMINI_KEYSTORE` | Абсолютный путь к файлу keystore |
| `VPN_GEMINI_STORE_PASSWORD` | Пароль хранилища |
| `VPN_GEMINI_KEY_ALIAS` | Псевдоним ключа |
| `VPN_GEMINI_KEY_PASSWORD` | Пароль ключа |

```sh
./gradlew :app:assembleRelease :app:lintRelease
```

На Windows используйте `gradlew.bat`. Результат:
`app/build/outputs/apk/release/app-universal-release.apk`.
Без `VPN_GEMINI_KEYSTORE` release APK остаётся неподписанным.
Ключи и пароли не добавляйте в Git или публичные артефакты.
Сохраните защищённую резервную копию ключа: все следующие обновления
распространяемой сборки должны использовать тот же ключ.

APK 4.0.5 использовал debug-подпись. В 4.0.6 введена постоянная release-подпись:
для перехода с прежней установки требуется удалить её и установить APK заново.

## Проверки и упаковка

Unit-тесты проверяют разбор конфигураций и региона Google, классификацию
ответов Gemini, отсутствие прямого обхода неработающего туннеля,
TLS через SOCKS, политику QUIC и интерфейс в Robolectric.
Некоторые интеграционные тесты используют Windows-бинарники из `.downloads`.
`LiveParityTest` принимает профили только через переменную
`VPN_GEMINI_LIVE_CASES`; без неё эта проверка пропускается.
Не включайте реальные профили и токены в исходники или журнал сборки.

После сборки и тестов `python tools/package_build.py --variant release`
проверяет хеши ядер и лицензии в APK и создаёт APK, исходный ZIP и SHA-256
в родительском каталоге проекта. Для release также вызывается `apksigner verify` (нужен `ANDROID_HOME`).
Отпечаток сертификата можно посмотреть через `apksigner verify --print-certs`.

Официальный sing-box executable имеет ELF alignment 4 КБ, Xray — 16 КБ.
Работа sing-box на устройствах со страницами памяти 16 КБ отдельно не
подтверждена. Сборка и тесты в рабочем окружении не заменяют проверку
на физическом Android-устройстве и требования выбранного каталога приложений.

## Публичный отпечаток подписи выпуска

SHA-256 сертификата первой release-сборки 4.0.6:

```text
8c5d682d5cfb2d7be4ba92b682a972cda3865707d3b4d16fc2b23013f205d83e
```

Это публичный идентификатор сертификата; закрытый ключ не публикуется.

## Android ARMv7 (32 бит)

Сборка создаёт отдельные APK для armeabi-v7a, arm64-v8a и x86_64, а также
универсальный APK. Минимальная версия Android остаётся 8.0.
Xray ARMv7 собирается из тега 26.3.27 с Android NDK и Go 1.26.8;
workflow `.github/workflows/android-arm32-core.yml` содержит параметры сборки.
Точный commit, хеши и адрес артефакта указаны в `cores.lock.json`.
sing-box ARMv7 взят из официального архива Android ARM версии 1.14.3.
ARMv7-ядра проверены по формату ELF32 ARM; физический телефон ARMv7
в рабочем окружении не подключён.
