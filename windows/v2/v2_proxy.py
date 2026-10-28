"""
v2_proxy.py - Минимальный SOCKS5 туннель для HTTPS без внешних зависимостей.

Реализует SOCKS5 CONNECT метод для туннелирования SSL/TLS трафика
через локальный SOCKS5 прокси (xray-core).
"""
import socket
import ssl
import re
 
# Страны и территории, где Google Gemini официально недоступен / заблокирован
RESTRICTED_COUNTRIES = {
    "RU", "BY", "CN", "IR", "KP", "CU", "SY",  # Санкционные регионы
    "UZ", "TM", "TJ",                          # Центральная Азия без Gemini
    "HK", "MO", "MM",                          # Азия (Гонконг, Макао, Мьянма)
    "AF", "VE", "YE", "SD", "SS", "SO", "ER",  # Ближний Восток / Африка / Латам
    "CD", "CF",                                # Прочие регионы без доступа
}


def socks5_https_get(
    proxy_host: str,
    proxy_port: int,
    target_host: str,
    target_path: str = "/",
    timeout: float = 12.0,
    extra_headers: dict = None,
    max_redirects: int = 3,
) -> bytes:
    """
    Выполняет HTTP GET запрос через SOCKS5 прокси с поддержкой редиректов.
    Возвращает сырые байты ответа (headers + body).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)

    try:
        s.connect((proxy_host, proxy_port))

        # --- SOCKS5 хэндшейк (RFC 1928) ---
        s.sendall(b"\x05\x01\x00")
        auth_resp = s.recv(2)
        if len(auth_resp) < 2 or auth_resp[1] != 0x00:
            raise ConnectionError(f"SOCKS5: auth negotiation failed: {auth_resp!r}")

        # --- SOCKS5 CONNECT к целевому хосту на порт 443 ---
        host_enc = target_host.encode("idna")
        connect_req = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_enc)])
            + host_enc
            + b"\x01\xbb"  # port 443 big-endian
        )
        s.sendall(connect_req)
        connect_resp = s.recv(10)
        if len(connect_resp) < 2 or connect_resp[1] != 0x00:
            err_code = connect_resp[1] if len(connect_resp) >= 2 else "?"
            raise ConnectionError(f"SOCKS5: CONNECT refused, code={err_code}")

        # --- TLS поверх SOCKS5 туннеля ---
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_sock = ctx.wrap_socket(s, server_hostname=target_host)

        # --- HTTP/1.1 GET запрос ---
        headers = {
            "Host": target_host,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "close",
        }
        if extra_headers:
            headers.update(extra_headers)

        header_lines = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
        request = f"GET {target_path} HTTP/1.1\r\n{header_lines}\r\n\r\n"
        ssl_sock.sendall(request.encode())

        # --- Чтение ответа ---
        chunks = []
        while True:
            try:
                chunk = ssl_sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            except (ssl.SSLError, OSError):
                break

        ssl_sock.close()
        raw_content = b"".join(chunks)

        # Обработка редиректов (301, 302, 303, 307, 308)
        if max_redirects > 0 and (raw_content.startswith(b"HTTP/1.1 30") or raw_content.startswith(b"HTTP/1.0 30")):
            hdr_text = raw_content[:4096].decode("latin1", errors="ignore")
            loc_m = re.search(r"(?:^|\r\n)Location:\s*([^\r\n]+)", hdr_text, re.IGNORECASE)
            if loc_m:
                new_loc = loc_m.group(1).strip()
                import urllib.parse as up
                p = up.urlparse(new_loc)
                new_host = p.hostname or target_host
                new_path = p.path or "/"
                if p.query:
                    new_path += "?" + p.query
                return socks5_https_get(
                    proxy_host, proxy_port, new_host, new_path,
                    timeout=timeout, extra_headers=extra_headers, max_redirects=max_redirects - 1
                )

        return raw_content

    except Exception:
        try:
            s.close()
        except Exception:
            pass
        raise


def tcp_ping_via_socks5(
    proxy_host: str,
    proxy_port: int,
    target_host: str,
    target_port: int = 443,
    timeout: float = 6.0,
    samples: int = 2,
) -> dict:
    """
    Замеряет TCP-задержку к target_host:target_port через SOCKS5 туннель.
    Возвращает avg_ms, min_ms, max_ms, packet_loss %.
    """
    latencies = []
    for _ in range(samples):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            import time
            t0 = time.perf_counter()
            s.connect((proxy_host, proxy_port))

            s.sendall(b"\x05\x01\x00")
            auth = s.recv(2)
            if len(auth) < 2 or auth[1] != 0x00:
                s.close()
                continue

            host_enc = target_host.encode("idna")
            connect_req = (
                b"\x05\x01\x00\x03"
                + bytes([len(host_enc)])
                + host_enc
                + bytes([target_port >> 8, target_port & 0xFF])
            )
            s.sendall(connect_req)
            resp = s.recv(10)
            t1 = time.perf_counter()

            if len(resp) >= 2 and resp[1] == 0x00:
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
    return {
        "reachable": False,
        "avg_ms": 0,
        "min_ms": 0,
        "max_ms": 0,
        "packet_loss": 100,
    }


def extract_country_from_gemini_page(raw_bytes: bytes) -> dict:
    """
    Парсит ответ Gemini и извлекает:
    - Страну (ISO-код) из WIZ_global_data.vXmutd (то, как Google видит ваш IP)
    - Признак загрузки интерфейса чата (BardChatUi и др.)
    - Признак региональной блокировки
    """
    text = raw_bytes.decode("utf-8", errors="ignore")

    result = {
        "country_code": None,
        "chat_ui_loaded": False,
        "geo_blocked": False,
        "raw_vxmutd": None,
        "status_ok": False,
    }

    # Проверка наличия компонентов чата
    ui_markers = ["BardChatUi", "chat-window", "input-area", "geminiweb-pa", "conversations"]
    result["chat_ui_loaded"] = any(m in text for m in ui_markers)

    # Извлечение vXmutd
    vx_idx = text.find("vXmutd")
    if vx_idx >= 0:
        snippet = text[vx_idx: vx_idx + 400]
        result["raw_vxmutd"] = snippet[:100]
        # Ищем 2-буквенный код в потоке escape-кода после vXmutd
        cc_matches = re.findall(r'\\+"([A-Z]{2})\\+"', snippet)
        if not cc_matches:
            cc_matches = re.findall(r'"([A-Z]{2})"', snippet)
        valid = [c for c in cc_matches if c != "ZZ"]
        if valid:
            result["country_code"] = valid[0]

    # Признаки блокировки
    blocked_phrases = [
        "isn't supported in your country",
        "not supported in your country",
        "isn’t supported in your country",
        "isn't available in your country",
        "not available in your country",
        "isn’t available in your country",
        "not currently supported",
        "location_unavailable",
        "/unavailable",
        "не поддерживается в вашей стране",
        "недоступен в вашей стране",
        "не поддерживается",
        "qo'llab-quvvatlanmaydi",
    ]
    text_lower = text.lower()
    for phrase in blocked_phrases:
        if phrase in text_lower:
            result["geo_blocked"] = True
            break

    is_restricted = bool(result["country_code"] and result["country_code"] in RESTRICTED_COUNTRIES)
    if is_restricted:
        result["geo_blocked"] = True
        result["status_ok"] = False
    else:
        country_ok = bool(result["country_code"])
        result["status_ok"] = not result["geo_blocked"] and (result["chat_ui_loaded"] or country_ok)
    return result

