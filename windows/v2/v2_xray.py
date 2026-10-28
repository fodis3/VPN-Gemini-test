"""
v2_xray.py - Генератор xray-core конфигов и менеджер процессов.

Запускает экземпляры xray.exe с SOCKS5 inbound на случайных портах
для параллельного тестирования нескольких VPN-конфигураций.
"""

import json
import os
import sys
import subprocess
import socket
import struct
import time
import random
import threading
import tempfile
from copy import deepcopy
from typing import Optional

from v2_parser import ProxyConfig

# Глобальный lock для выдачи уникальных портов
_port_lock = threading.Lock()
_used_ports: set = set()


def _get_free_port(start: int = 15900, end: int = 16500) -> int:
    """Возвращает свободный порт в заданном диапазоне."""
    with _port_lock:
        for attempt in range(200):
            port = random.randint(start, end)
            if port in _used_ports:
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            try:
                s.bind(("127.0.0.1", port))
                s.close()
                _used_ports.add(port)
                return port
            except OSError:
                continue
    raise RuntimeError("Нет свободных портов в диапазоне 15900-16500")


def _release_port(port: int):
    with _port_lock:
        _used_ports.discard(port)


def _get_xray_path() -> str:
    """
    Находит xray.exe. Стратегия:
    1. bin/xray.exe рядом с .exe (постоянное место — АВ не блокирует)
    2. Если первый запуск frozen exe — копирует xray.exe из _MEIPASS в bin/
    3. Режим разработки — bin/ рядом со скриптом
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        persistent_bin = os.path.join(exe_dir, "bin", "x86" if struct.calcsize("P") == 4 else "x64", "xray.exe")

        # Уже есть постоянная копия — используем её
        if os.path.isfile(persistent_bin):
            return persistent_bin

        # Первый запуск: копируем из _MEIPASS в постоянную папку рядом с .exe
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_xray = os.path.join(meipass, "bin", "xray.exe")
            if not os.path.isfile(meipass_xray):
                meipass_xray = os.path.join(meipass, "xray.exe")

            if os.path.isfile(meipass_xray):
                try:
                    os.makedirs(os.path.dirname(persistent_bin), exist_ok=True)
                    import shutil
                    shutil.copy2(meipass_xray, persistent_bin)
                    return persistent_bin
                except Exception:
                    # Не удалось скопировать — используем прямо из MEIPASS
                    return meipass_xray

        raise FileNotFoundError(
            "xray.exe не найден!\n"
            f"Создайте папку bin\\ рядом с {os.path.basename(sys.executable)} "
            "и поместите туда xray.exe.\n"
            "Скачать: https://github.com/XTLS/Xray-core/releases/latest"
        )
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        candidates = [
            os.path.join(root, "bin", "x86" if struct.calcsize("P") == 4 else "x64", "xray.exe"),
            os.path.join(root, "bin", "xray.exe"),
            os.path.join(here, "bin", "xray.exe"),
            os.path.join(here, "xray.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        raise FileNotFoundError(
            "xray.exe не найден!\n"
            f"Проверенные пути:\n" + "\n".join(f"  {c}" for c in candidates)
        )


def _get_singbox_path() -> Optional[str]:
    """
    Находит sing-box.exe рядом с .exe или в bin/.
    Используется для протоколов Hysteria2 и TUIC.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        persistent_bin = os.path.join(exe_dir, "bin", "x86" if struct.calcsize("P") == 4 else "x64", "sing-box.exe")

        if os.path.isfile(persistent_bin):
            return persistent_bin

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_sb = os.path.join(meipass, "bin", "sing-box.exe")
            if not os.path.isfile(meipass_sb):
                meipass_sb = os.path.join(meipass, "sing-box.exe")

            if os.path.isfile(meipass_sb):
                try:
                    os.makedirs(os.path.dirname(persistent_bin), exist_ok=True)
                    import shutil
                    shutil.copy2(meipass_sb, persistent_bin)
                    return persistent_bin
                except Exception:
                    return meipass_sb

        return None
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        candidates = [
            os.path.join(root, "bin", "x86" if struct.calcsize("P") == 4 else "x64", "sing-box.exe"),
            os.path.join(root, "bin", "sing-box.exe"),
            os.path.join(here, "bin", "sing-box.exe"),
            os.path.join(here, "sing-box.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None




# ──────────────────────────────────────────────────────────────
# Генераторы xray-конфигов для каждого протокола
# ──────────────────────────────────────────────────────────────

def _stream_settings(cfg: ProxyConfig) -> dict:
    """Формирует streamSettings для xray по параметрам конфига."""
    ss: dict = {"network": cfg.network}

    if cfg.security == "reality":
        ss["security"] = "reality"
        reality_cfg = {
            "serverName": cfg.sni or cfg.host,
            "fingerprint": cfg.fingerprint or "chrome",
            "publicKey": cfg.extra.get("pbk", ""),    # ОБЯЗАТЕЛЬНО для REALITY
            "shortId": cfg.extra.get("sid", ""),
            "spiderX": cfg.extra.get("spx", ""),      # Не подставляем '/', если сервер его не ждет
        }
        ss["realitySettings"] = reality_cfg
        if cfg.extra.get('pqv'):
            reality_cfg['mldsa65Verify'] = cfg.extra['pqv']

    elif cfg.security == "tls":
        ss["security"] = "tls"
        tls_cfg: dict = {
            "serverName": cfg.sni or cfg.host,
            "allowInsecure": False,
        }
        if cfg.fingerprint:
            tls_cfg["fingerprint"] = cfg.fingerprint
        if cfg.extra.get('alpn'):
            tls_cfg['alpn'] = cfg.extra['alpn']
        if 'insecure' in cfg.extra:
            tls_cfg['allowInsecure'] = cfg.extra['insecure']
        if cfg.extra.get('echConfigList') or cfg.extra.get('ech'):
            tls_cfg['echConfigList'] = cfg.extra.get('echConfigList') or cfg.extra['ech']
        ss["tlsSettings"] = tls_cfg

    if cfg.network == "ws":
        ss["wsSettings"] = {
            "path": cfg.path or "/",
            "headers": {"Host": cfg.host_header or cfg.host},
        }
    elif cfg.network == "grpc":
        ss["grpcSettings"] = {
            "serviceName": cfg.extra.get('serviceName', cfg.path.lstrip('/')),
            "multiMode": cfg.extra.get('mode', 'gun') == 'multi',
        }
        if cfg.extra.get('authority'):
            ss['grpcSettings']['authority'] = cfg.extra['authority']
    elif cfg.network == "h2":
        ss["httpSettings"] = {
            "host": [cfg.host_header or cfg.host],
            "path": cfg.path or "/",
        }
    elif cfg.network in ('xhttp', 'splithttp'):
        ss['network'] = 'xhttp'
        ss['xhttpSettings'] = {'path': cfg.path or '/', 'mode': cfg.extra.get('mode', 'auto')}
        if cfg.host_header:
            ss['xhttpSettings']['host'] = cfg.host_header
        if cfg.extra.get('xhttp_extra'):
            ss['xhttpSettings']['extra'] = deepcopy(cfg.extra['xhttp_extra'])
    elif cfg.network == 'httpupgrade':
        ss['httpupgradeSettings'] = {'path': cfg.path or '/', 'host': cfg.host_header or cfg.host}

    return ss



def build_xray_config(cfg: ProxyConfig, socks_port: int) -> dict:
    """Строит полный xray JSON конфиг для указанного VPN сервера."""

    # --- Inbound: SOCKS5 прокси для тестирования ---
    inbounds = [
        {
            "tag": "socks_in",
            "port": socks_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False},
        }
    ]

    # --- Outbound: VPN сервер ---
    proto = cfg.protocol

    if cfg.extra.get('raw_outbound') and cfg.extra.get('engine') == 'xray':
        outbound = deepcopy(cfg.extra['raw_outbound'])
        outbound['tag'] = 'proxy_out'
    elif proto == "vless":
        outbound = {
            "tag": "proxy_out",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": cfg.host,
                        "port": cfg.port,
                        "users": [
                            {
                                "id": cfg.uuid,
                                "encryption": cfg.extra.get('encryption', 'none'),
                                "flow": cfg.flow or "",
                            }
                        ],
                    }
                ]
            },
            "streamSettings": _stream_settings(cfg),
        }

    elif proto == "vmess":
        outbound = {
            "tag": "proxy_out",
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": cfg.host,
                        "port": cfg.port,
                        "users": [
                            {
                                "id": cfg.uuid,
                                "alterId": cfg.extra.get("alterId", 0),
                                "security": "auto",
                            }
                        ],
                    }
                ]
            },
            "streamSettings": _stream_settings(cfg),
        }

    elif proto == "trojan":
        outbound = {
            "tag": "proxy_out",
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": cfg.host,
                        "port": cfg.port,
                        "password": cfg.password,
                    }
                ]
            },
            "streamSettings": _stream_settings(cfg),
        }

    elif proto == "ss":
        outbound = {
            "tag": "proxy_out",
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": cfg.host,
                        "port": cfg.port,
                        "method": cfg.method or "aes-256-gcm",
                        "password": cfg.password,
                    }
                ]
            },
        }

    elif proto in ("hysteria2", "hy2", "tuic"):
        raise ValueError(f"Xray не поддерживает {proto}, требуется sing-box")

    else:
        raise ValueError(f"Неизвестный протокол: {proto}")

    config = {
        "log": {"loglevel": "error"},
        "inbounds": inbounds,
        "outbounds": [outbound, {"tag": "direct", "protocol": "freedom", "settings": {}}],
    }

    return config


def build_singbox_config(cfg: ProxyConfig, socks_port: int) -> dict:
    """Генерирует конфиг sing-box для протоколов Hysteria2 и TUIC."""
    proto = (cfg.protocol or "").lower()
    inbounds = [
        {
            "type": "socks",
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "listen_port": socks_port,
        }
    ]

    if cfg.extra.get('raw_outbound') and cfg.extra.get('engine') == 'sing-box':
        outbound = deepcopy(cfg.extra['raw_outbound'])
        outbound['tag'] = 'proxy-out'
    elif proto in ("hysteria2", "hy2"):
        outbound = {
            "type": "hysteria2",
            "tag": "proxy-out",
            "server": cfg.host,
            "server_port": cfg.port,
            "password": cfg.password or "",
            "tls": {
                "enabled": True,
                "server_name": cfg.sni or cfg.host,
                "insecure": True,
            },
        }
        if cfg.extra.get("obfs"):
            outbound["obfs"] = {
                "type": cfg.extra["obfs"],
                "password": cfg.extra.get("obfs_password", ""),
            }
        if cfg.extra.get('alpn'):
            outbound['tls']['alpn'] = cfg.extra['alpn']
    elif proto == "tuic":
        outbound = {
            "type": "tuic",
            "tag": "proxy-out",
            "server": cfg.host,
            "server_port": cfg.port,
            "uuid": cfg.uuid or "",
            "password": cfg.password or "",
            "congestion_control": cfg.extra.get("congestion_control", "bbr"),
            "tls": {
                "enabled": True,
                "server_name": cfg.sni or cfg.host,
                "insecure": True,
            },
        }
        if cfg.extra.get('alpn'):
            outbound['tls']['alpn'] = cfg.extra['alpn']
    else:
        raise ValueError(f"Протокол {proto} не поддерживается sing-box генератором")

    return {
        "log": {"level": "error"},
        "inbounds": inbounds,
        "outbounds": [outbound],
    }


# ──────────────────────────────────────────────────────────────
# Менеджер процессов xray / sing-box
# ──────────────────────────────────────────────────────────────

class XrayInstance:
    """Запускает и управляет экземпляром xray.exe или sing-box.exe."""

    def __init__(self, cfg: ProxyConfig):
        self.cfg = cfg
        self.socks_port: int = 0
        self._proc: Optional[subprocess.Popen] = None
        self._config_file: Optional[str] = None

    def start(self, startup_wait: float = 1.5) -> int:
        """Запускает xray или sing-box и возвращает порт SOCKS5 прокси."""
        self.socks_port = _get_free_port()
        proto = (self.cfg.protocol or "").lower()

        if proto in ("hysteria2", "hy2", "tuic") or self.cfg.extra.get('engine') == 'sing-box':
            engine_name = "sing-box"
            sb_path = _get_singbox_path()
            if not sb_path:
                raise RuntimeError(
                    f"Протокол {self.cfg.protocol} требует sing-box.exe!\n"
                    "Поместите sing-box.exe в папку bin/ рядом с приложением."
                )
            config_dict = build_singbox_config(self.cfg, self.socks_port)
            fd, self._config_file = tempfile.mkstemp(suffix=".json", prefix="sb_cfg_")
            with os.fdopen(fd, "w") as f:
                json.dump(config_dict, f)

            self._proc = subprocess.Popen(
                [sb_path, "run", "-c", self._config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        else:
            engine_name = "xray"
            xray_path = _get_xray_path()
            config_dict = build_xray_config(self.cfg, self.socks_port)

            fd, self._config_file = tempfile.mkstemp(suffix=".json", prefix="xray_cfg_")
            with os.fdopen(fd, "w") as f:
                json.dump(config_dict, f)

            self._proc = subprocess.Popen(
                [xray_path, "run", "-c", self._config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

        # Ожидание старта и проверка
        deadline = time.perf_counter() + startup_wait + 0.8
        while time.perf_counter() < deadline:
            ret = self._proc.poll()
            if ret is not None:
                out, err = self._proc.communicate()
                detail = (out + b'\n' + err).decode("utf-8", errors="replace").strip()[-1600:]
                raise RuntimeError(
                    f"{engine_name} завершился с кодом {ret}.\n"
                    f"Вывод: {detail or '(пусто)'}\n"
                    f"Возможные причины:\n"
                    f"  - Антивирус заблокировал {engine_name}.exe\n"
                    f"  - Неверный формат конфига (протокол {self.cfg.protocol})\n"
                    f"  - Порт {self.socks_port} занят другим процессом"
                )
            if self._check_socks_ready():
                break
            time.sleep(0.1)

        return self.socks_port

    def _check_socks_ready(self) -> bool:
        """Проверяет, слушает ли xray SOCKS5 порт."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", self.socks_port))
            s.close()
            return True
        except Exception:
            return False

    def stop(self):
        """Останавливает xray и освобождает ресурсы."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        if self._config_file and os.path.exists(self._config_file):
            try:
                os.unlink(self._config_file)
            except Exception:
                pass
            self._config_file = None

        if self.socks_port:
            _release_port(self.socks_port)
            self.socks_port = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
