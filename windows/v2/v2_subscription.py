"""
v2_subscription.py - Импорт прокси-конфигов из подписок (subscription links).

Поддерживает:
- HTTP/HTTPS URLs возвращающие Base64 (стандарт v2ray/xray подписок)
- Кастомный User-Agent (для подписок с защитой по HWID/UID)
- Случайная генерация или ручной ввод HWID
"""

import urllib.request
import base64
import uuid
import re
import json
from typing import List, Optional
from v2_parser import parse_text_block, ProxyConfig


def generate_hwid() -> str:
    """Генерирует случайный HWID в формате UUID4."""
    return str(uuid.uuid4()).upper()


def fetch_subscription(
    url: str,
    hwid: Optional[str] = None,
    timeout: float = 12.0,
    extra_headers: Optional[dict] = None,
) -> List[ProxyConfig]:
    """
    Загружает подписку по URL и парсит все VPN конфиги.
    
    Args:
        url: URL подписки (http/https)
        hwid: Кастомный HWID для User-Agent (если подписка его требует).
              Если None, используется стандартный User-Agent.
        timeout: Таймаут запроса в секундах
        extra_headers: Дополнительные заголовки HTTP
    
    Returns:
        Список ParsedProxyConfig
    """
    if hwid:
        user_agent = f"v2rayN/6.67 HWID/{hwid}"
    else:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if extra_headers:
        headers.update(extra_headers)

    import ssl
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        ctx = None

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw_bytes = resp.read()
    except Exception as e:
        raise ConnectionError(f"Не удалось загрузить подписку: {e}")

    # Декодируем содержимое
    content = raw_bytes.decode("utf-8", errors="replace").strip()
    return parse_text_block(content)


def load_from_text(text: str) -> List[ProxyConfig]:
    """Парсит текст с VPN-ключами (одна ссылка на строку, JSON, или Base64 подписка)."""
    return parse_text_block(text)
