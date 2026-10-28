"""
v2_engine.py - Быстрый движок тестирования VPN + Gemini доступности.

Оптимизации по сравнению с v1:
1. Только 1 пинг-цель (gemini.google.com) вместо 4
2. Gemini тест через SOCKS5 туннель с xray
3. Параллельный запуск нескольких тестов (ThreadPoolExecutor)
4. Только критически нужные проверки (vXmutd + BardChatUi)
5. Таймауты жёсткие для быстрого выхода
"""

import socket
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional
from dataclasses import dataclass, field

from v2_proxy import socks5_https_get, tcp_ping_via_socks5, extract_country_from_gemini_page, RESTRICTED_COUNTRIES
from v2_xray import XrayInstance
from v2_parser import ProxyConfig


GEMINI_HOST = "gemini.google.com"
GEMINI_PATH = "/app"


# ──────────────────────────────────────────────────────────────
# Результат теста одного VPN
# ──────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    cfg: Optional[ProxyConfig]
    label: str = ""

    # Пинг
    ping_ms: float = -1.0
    ping_loss: float = 100.0
    ping_ok: bool = False

    # IP / Гео
    country_code: str = ""
    is_restricted: bool = False

    # Gemini доступность
    gemini_accessible: bool = False
    gemini_chat_ui: bool = False
    gemini_geo_blocked: bool = False
    gemini_error: str = ""

    # Итог
    status: str = "PENDING"   # PENDING / TESTING / OK / BLOCKED / ERROR / TIMEOUT
    total_ms: float = 0.0
    error_detail: str = ""


# ──────────────────────────────────────────────────────────────
# Быстрый пинг (TCP к Gemini:443, 2 попытки макс)
# ──────────────────────────────────────────────────────────────

def fast_tcp_ping(host: str, port: int = 443, samples: int = 2, timeout: float = 2.5) -> dict:
    """TCP ping напрямую (без прокси) к хосту."""
    latencies = []
    for _ in range(samples):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((host, port))
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass

    if latencies:
        return {
            "reachable": True,
            "avg_ms": round(sum(latencies) / len(latencies), 1),
            "min_ms": round(min(latencies), 1),
            "max_ms": round(max(latencies), 1),
            "packet_loss": round((samples - len(latencies)) / samples * 100),
        }
    return {"reachable": False, "avg_ms": 0, "min_ms": 0, "max_ms": 0, "packet_loss": 100}


# ──────────────────────────────────────────────────────────────
# Тест прямого подключения (без VPN)
# ──────────────────────────────────────────────────────────────

def run_direct_test(log: Callable[[str], None] = print) -> TestResult:
    """Тест прямого подключения без VPN (базовый режим)."""
    import urllib.request, json

    res = TestResult(cfg=None, label="ПРЯМОЕ ПОДКЛЮЧЕНИЕ (без VPN)")
    t_start = time.perf_counter()

    log("→ Пинг до gemini.google.com...")
    ping = fast_tcp_ping(GEMINI_HOST, 443, samples=2)
    res.ping_ok = ping["reachable"]
    res.ping_ms = ping["avg_ms"]
    res.ping_loss = ping["packet_loss"]
    if res.ping_ok:
        log(f"  [OK] Пинг: {ping['avg_ms']} мс (потери {ping['packet_loss']}%)")
    else:
        log("  [FAIL] Gemini Host недоступен")
        res.status = "ERROR"
        return res

    log("→ Запрос страницы gemini.google.com/app...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }
        import ssl, urllib.request
        req = urllib.request.Request(f"https://{GEMINI_HOST}{GEMINI_PATH}", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()

        parsed = extract_country_from_gemini_page(raw)
        res.country_code = parsed["country_code"] or ""
        res.is_restricted = res.country_code in RESTRICTED_COUNTRIES
        res.gemini_chat_ui = parsed["chat_ui_loaded"]
        res.gemini_geo_blocked = parsed["geo_blocked"]
        res.gemini_accessible = parsed["status_ok"]

        if res.is_restricted:
            log(f"  [BLOCKED] Google видит страну: {res.country_code} (заблокирована!)")
            res.status = "BLOCKED"
        elif res.gemini_geo_blocked:
            log(f"  [BLOCKED] Обнаружена региональная блокировка Gemini")
            res.status = "BLOCKED"
        elif res.gemini_accessible:
            log(f"  [OK] Gemini доступен! Страна (по Google): {res.country_code} | Чаты: ✔")
            res.status = "OK"
        else:
            log("  [WARN] Gemini: UI не обнаружен или блокировка")
            res.status = "BLOCKED"

    except Exception as e:
        res.gemini_error = str(e)
        log(f"  [ERROR] {e}")
        res.status = "ERROR"

    res.total_ms = round((time.perf_counter() - t_start) * 1000)
    return res


# ──────────────────────────────────────────────────────────────
# Тест одного VPN конфига через xray SOCKS5
# ──────────────────────────────────────────────────────────────

def test_one_vpn(
    cfg: ProxyConfig,
    log: Callable[[str], None] = lambda x: None,
    xray_startup_wait: float = 1.3,
    gemini_timeout: float = 9.0,
    ping_samples: int = 2,
) -> TestResult:
    """Полный тест одного VPN: запуск xray → пинг → Gemini тест → стоп xray."""
    res = TestResult(cfg=cfg, label=cfg.label())
    t_start = time.perf_counter()

    if cfg.extra.get('import_error'):
        res.status = 'ERROR'
        res.error_detail = cfg.extra['import_error']
        log(f'  [✗] {res.error_detail}')
        return res

    xray = XrayInstance(cfg)

    try:
        log(f"  [►] Запуск xray для {cfg.label()[:50]}...")
        try:
            port = xray.start(startup_wait=xray_startup_wait)
        except FileNotFoundError as e:
            res.status = "ERROR"
            res.error_detail = str(e)
            log(f"  [✗] xray.exe не найден! Создайте папку bin\\ рядом с exe и поместите туда xray.exe")
            return res
        except RuntimeError as e:
            res.status = "ERROR"
            res.error_detail = str(e)
            log(f"  [✗] Ошибка запуска движка: {e}")
            return res

        if not xray._check_socks_ready():
            res.status = "ERROR"
            res.error_detail = "SOCKS5 порт не слушает после запуска xray"
            log(f"  [✗] xray SOCKS5 не готов на порту {port}")
            return res

        log(f"  [►] SOCKS5 готов на порту {port}, пинг через прокси...")


        # Быстрый TCP пинг через SOCKS5 (2 попытки)
        ping = tcp_ping_via_socks5("127.0.0.1", port, GEMINI_HOST, 443,
                                   timeout=5.5, samples=ping_samples)
        res.ping_ok = ping["reachable"]
        res.ping_ms = ping["avg_ms"]
        res.ping_loss = ping["packet_loss"]

        if not res.ping_ok:
            res.status = "ERROR"
            res.error_detail = "VPN не пропускает трафик к Gemini"
            log(f"  [✗] Нет связи через VPN")
            return res

        log(f"  [►] Пинг {ping['avg_ms']} мс → тест Gemini...")

        # Gemini тест через SOCKS5
        raw = socks5_https_get(
            "127.0.0.1", port,
            GEMINI_HOST, GEMINI_PATH,
            timeout=gemini_timeout
        )

        parsed = extract_country_from_gemini_page(raw)
        res.country_code = parsed["country_code"] or ""
        res.is_restricted = res.country_code in RESTRICTED_COUNTRIES
        res.gemini_chat_ui = parsed["chat_ui_loaded"]
        res.gemini_geo_blocked = parsed["geo_blocked"]
        res.gemini_accessible = parsed["status_ok"]

        if res.is_restricted:
            res.status = "BLOCKED"
            log(f"  [✗] Заблокирован! Google видит: {res.country_code}")
        elif res.gemini_geo_blocked:
            res.status = "BLOCKED"
            log(f"  [✗] Обнаружен баннер блокировки Gemini")
        elif res.gemini_accessible or (res.country_code and not res.is_restricted):
            res.status = "OK"
            log(f"  [✔] OK! Страна: {res.country_code or 'OK'} | Пинг: {ping['avg_ms']} мс")
        else:
            res.status = "ERROR"
            res.error_detail = "Неопределенный ответ от Gemini"
            log(f"  [?] Неопределённый статус (UI: {res.gemini_chat_ui}, Geo: {res.country_code})")

    except TimeoutError:
        res.status = "TIMEOUT"
        res.error_detail = "Превышено время ожидания"
        log(f"  [✗] TIMEOUT")
    except Exception as e:
        res.status = "ERROR"
        res.error_detail = str(e)
        log(f"  [✗] Ошибка: {e}")
    finally:
        xray.stop()
        res.total_ms = round((time.perf_counter() - t_start) * 1000)

    res.total_ms = round((time.perf_counter() - t_start) * 1000)
    return res


# ──────────────────────────────────────────────────────────────
# Параллельное тестирование списка VPN
# ──────────────────────────────────────────────────────────────

def run_batch_test(
    configs, max_workers=4, on_result=None, on_log=None, stop_event=None,
    gemini_timeout=9.0, on_started=None,
):
    """Run all configurations; cancellation skips queued work and drains active tests."""
    total = len(configs)
    results = [None] * total
    stop_event = stop_event or threading.Event()

    def run_one(index, cfg):
        if stop_event.is_set():
            return TestResult(cfg=cfg, label=cfg.label(), status="CANCELLED")
        if on_started:
            on_started(index)
        def log(message):
            if on_log:
                on_log(message, cfg.label())
        return test_one_vpn(cfg, log=log, gemini_timeout=gemini_timeout)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_one, i, cfg): i for i, cfg in enumerate(configs)}
        for done, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = TestResult(cfg=configs[index], label=configs[index].label(),
                                    status="ERROR", error_detail=str(exc))
            results[index] = result
            if on_result:
                on_result(result, done, total)
    return results
