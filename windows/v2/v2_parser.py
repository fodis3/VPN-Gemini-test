"""
v2_parser.py - Парсеры VPN-ссылок и конфигурационных файлов.

Поддерживает форматы:
- vless://
- vmess://
- trojan://
- ss:// (Shadowsocks)
- hysteria2:// / hy2://
- tuic://
- JSON (xray / sing-box configs)
- Base64-кодированные списки (из подписок)
"""
import base64
import json
import re
import urllib.parse as up
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Единый объект конфигурации прокси
# ──────────────────────────────────────────────────────────────

class ProxyConfig:
    """Нормализованная конфигурация одного VPN-сервера."""

    __slots__ = (
        "protocol", "host", "port", "uuid", "password",
        "network", "security", "sni", "path", "host_header",
        "fingerprint", "flow", "method",  # ss method
        "remarks", "raw", "extra"
    )

    def __init__(self):
        self.protocol = ""
        self.host = ""
        self.port = 0
        self.uuid = ""
        self.password = ""
        self.network = "tcp"
        self.security = "none"
        self.sni = ""
        self.path = "/"
        self.host_header = ""
        self.fingerprint = ""
        self.flow = ""
        self.method = "aes-256-gcm"
        self.remarks = ""
        self.raw = ""
        self.extra = {}

    def label(self) -> str:
        return self.remarks or f"{self.protocol}://{self.host}:{self.port}"

    def __repr__(self):
        return f"<ProxyConfig {self.protocol} {self.host}:{self.port} [{self.remarks}]>"


# ──────────────────────────────────────────────────────────────
# Парсеры по протоколу
# ──────────────────────────────────────────────────────────────

def _decode_b64(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s).decode("utf-8", errors="replace")


def _transport_params(cfg, qs):
    """Preserve transport options from share links when generating engine JSON."""
    for name in ('serviceName', 'authority', 'mode', 'encryption', 'headerType', 'pqv',
                 'password', 'ech', 'echConfigList'):
        if name in qs:
            cfg.extra[name] = qs[name][0]
    if 'alpn' in qs:
        cfg.extra['alpn'] = [value.strip() for value in qs['alpn'][0].split(',') if value.strip()]
    if 'extra' in qs:
        try:
            value = json.loads(qs['extra'][0])
            if not isinstance(value, dict):
                raise ValueError()
            cfg.extra['xhttp_extra'] = value
        except (ValueError, TypeError):
            cfg.extra['import_error'] = 'Параметр extra должен содержать JSON-объект.'
    if 'insecure' in qs or 'allowInsecure' in qs:
        cfg.extra['insecure'] = qs.get('insecure', qs.get('allowInsecure'))[0].lower() in ('1', 'true')


def _parse_vless(url: str) -> Optional[ProxyConfig]:
    """vless://UUID@host:port?params#remarks"""
    try:
        p = up.urlparse(url)
        cfg = ProxyConfig()
        cfg.protocol = "vless"
        cfg.raw = url
        cfg.uuid = up.unquote(p.username or "")
        cfg.host = p.hostname or ""
        cfg.port = p.port or 443
        cfg.remarks = up.unquote(p.fragment or "")

        qs = up.parse_qs(p.query)
        cfg.network = qs.get("type", qs.get("net", ["tcp"]))[0]
        cfg.security = qs.get("security", ["none"])[0]
        cfg.sni = qs.get("sni", qs.get("serverName", qs.get("peer", [cfg.host])))[0]
        cfg.path = qs.get("path", ["/"])[0]
        cfg.host_header = qs.get("host", [""])[0]
        cfg.fingerprint = qs.get("fp", [""])[0]
        cfg.flow = qs.get("flow", [""])[0]
        _transport_params(cfg, qs)
        # REALITY-специфичные параметры
        cfg.extra["pbk"] = qs.get("pbk", qs.get("publicKey", [""]))[0]   # publicKey
        cfg.extra["sid"] = qs.get("sid", qs.get("shortId", qs.get("short-id", [""])))[0]   # shortId
        cfg.extra["spx"] = qs.get("spx", qs.get("spiderX", [""]))[0]   # spiderX
        return cfg
    except Exception:
        return None


def _parse_vmess(url: str) -> Optional[ProxyConfig]:
    """vmess://BASE64_JSON"""
    try:
        b64 = url[len("vmess://"):]
        data = json.loads(_decode_b64(b64))
        cfg = ProxyConfig()
        cfg.protocol = "vmess"
        cfg.raw = url
        cfg.uuid = data.get("id", "")
        cfg.host = data.get("add", "")
        cfg.port = int(data.get("port", 443))
        cfg.remarks = data.get("ps", "")
        cfg.network = data.get("net", "tcp")
        tls = data.get("tls", "")
        cfg.security = "tls" if tls == "tls" else "none"
        cfg.sni = data.get("sni", data.get("host", cfg.host))
        cfg.path = data.get("path", "/")
        cfg.host_header = data.get("host", "")
        cfg.fingerprint = data.get("fp", "")
        cfg.extra["alterId"] = int(data.get("aid", 0))
        return cfg
    except Exception:
        return None


def _parse_trojan(url: str) -> Optional[ProxyConfig]:
    """trojan://password@host:port?params#remarks"""
    try:
        p = up.urlparse(url)
        cfg = ProxyConfig()
        cfg.protocol = "trojan"
        cfg.raw = url
        cfg.password = up.unquote(p.username or "")
        cfg.host = p.hostname or ""
        cfg.port = p.port or 443
        cfg.remarks = up.unquote(p.fragment or "")

        qs = up.parse_qs(p.query)
        cfg.network = qs.get("type", ["tcp"])[0]
        cfg.security = qs.get("security", ["tls"])[0]
        cfg.sni = qs.get("sni", qs.get("serverName", [cfg.host]))[0]
        cfg.path = qs.get("path", ["/"])[0]
        cfg.host_header = qs.get("host", [""])[0]
        cfg.fingerprint = qs.get("fp", [""])[0]
        _transport_params(cfg, qs)
        cfg.extra['pbk'] = qs.get('pbk', qs.get('publicKey', ['']))[0]
        cfg.extra['sid'] = qs.get('sid', qs.get('shortId', ['']))[0]
        cfg.extra['spx'] = qs.get('spx', [''])[0]
        return cfg
    except Exception:
        return None


def _parse_ss(url: str) -> Optional[ProxyConfig]:
    """
    ss://BASE64(method:password)@host:port#remarks
    или ss://BASE64(method:password@host:port)#remarks  (старый формат)
    """
    try:
        p = up.urlsplit(url)
        cfg = ProxyConfig()
        cfg.protocol = "ss"
        cfg.raw = url
        cfg.remarks = up.unquote(p.fragment or "")

        payload = url[5:].split('#', 1)[0].split('?', 1)[0].rstrip('/')
        if '@' in payload:
            auth, address = payload.rsplit('@', 1)
            auth = up.unquote(auth)
            if ':' not in auth:
                auth = _decode_b64(auth)
        else:
            auth, address = _decode_b64(payload).rsplit('@', 1)
        cfg.method, cfg.password = auth.split(':', 1)
        endpoint = up.urlsplit('ss://' + address)
        cfg.host, cfg.port = endpoint.hostname or '', endpoint.port or 443
        if up.parse_qs(p.query).get('plugin'):
            cfg.extra['import_error'] = 'Shadowsocks с внешним plugin пока не поддерживается.'
        return cfg
    except Exception:
        return None


def _parse_hysteria2(url: str) -> Optional[ProxyConfig]:
    """hysteria2://password@host:port?params#remarks"""
    try:
        p = up.urlparse(url)
        cfg = ProxyConfig()
        cfg.protocol = "hysteria2"
        cfg.raw = url
        cfg.password = up.unquote(p.netloc.rsplit('@', 1)[0]) if '@' in p.netloc else ''
        cfg.host = p.hostname or ""
        cfg.port = p.port or 443
        cfg.remarks = up.unquote(p.fragment or "")

        qs = up.parse_qs(p.query)
        cfg.sni = qs.get("sni", [cfg.host])[0]
        cfg.fingerprint = qs.get("insecure", ["0"])[0]
        cfg.extra["obfs"] = qs.get("obfs", [""])[0]
        cfg.extra["obfs_password"] = qs.get("obfs-password", [""])[0]
        _transport_params(cfg, qs)
        return cfg
    except Exception:
        return None


def _parse_tuic(url: str) -> Optional[ProxyConfig]:
    """tuic://UUID:password@host:port?params#remarks"""
    try:
        p = up.urlparse(url)
        cfg = ProxyConfig()
        cfg.protocol = "tuic"
        cfg.raw = url
        cfg.uuid = up.unquote(p.username or "")
        cfg.password = up.unquote(p.password or "")
        cfg.host = p.hostname or ""
        cfg.port = p.port or 443
        cfg.remarks = up.unquote(p.fragment or "")

        qs = up.parse_qs(p.query)
        cfg.sni = qs.get("sni", [cfg.host])[0]
        cfg.extra["congestion_control"] = qs.get("congestion_control", ["bbr"])[0]
        _transport_params(cfg, qs)
        return cfg
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Парсинг JSON конфигов (xray/sing-box)
# ──────────────────────────────────────────────────────────────

def _parse_json_config(text: str) -> list:
    """Preserve each outbound intact, including engine-specific transport options."""
    def visit(data):
        if isinstance(data, str):
            return parse_text_block(data)
        if isinstance(data, list):
            configs = []
            for entry in data:
                try:
                    configs.extend(visit(entry))
                except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                    configs.append(_unparsed_config(json.dumps({'outbounds': [entry]}, ensure_ascii=False),
                                   'Повреждённая JSON-конфигурация.', 'json'))
            return configs
        if not isinstance(data, dict):
            return []
        if 'outbounds' in data:
            return visit(data['outbounds'])
        proto = data.get('protocol') or data.get('type')
        if proto in ('freedom', 'blackhole', 'direct', 'block', 'dns', 'selector', 'urltest'):
            return []
        if not isinstance(proto, str):
            return [_unparsed_config(json.dumps(data, ensure_ascii=False),
                    'Неизвестный формат JSON: ожидается исходящее подключение Xray или sing-box.', 'json')]
        cfg = ProxyConfig()
        cfg.protocol = 'ss' if proto == 'shadowsocks' else proto
        cfg.remarks = data.get('tag', '')
        cfg.extra['raw_outbound'] = data
        cfg.extra['engine'] = 'xray' if 'protocol' in data else 'sing-box'
        cfg.raw = json.dumps({'outbounds': [data]}, ensure_ascii=False)
        if cfg.extra['engine'] == 'sing-box':
            cfg.host = data.get('server', '')
            cfg.port = data.get('server_port', 443)
            cfg.network = data.get('transport', {}).get('type', 'tcp')
        else:
            settings = data.get('settings', {})
            servers = settings.get('vnext') or settings.get('servers') or [settings]
            server = servers[0]
            cfg.host, cfg.port = server.get('address', ''), server.get('port', 443)
            cfg.network = data.get('streamSettings', {}).get('network', 'tcp')
        return [cfg]
    try:
        return visit(json.loads(text))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return []


# ──────────────────────────────────────────────────────────────
# Главный публичный парсер
# ──────────────────────────────────────────────────────────────

PARSERS = {
    "vless://": _parse_vless,
    "vmess://": _parse_vmess,
    "trojan://": _parse_trojan,
    "ss://": _parse_ss,
    "hysteria2://": _parse_hysteria2,
    "hy2://": _parse_hysteria2,
    "tuic://": _parse_tuic,
}


def parse_proxy_link(link: str) -> Optional[ProxyConfig]:
    """Автоматически определяет протокол и парсит VPN-ссылку."""
    link = link.strip()
    for prefix, parser in PARSERS.items():
        if link.lower().startswith(prefix):
            cfg = parser(link)
            if cfg and cfg.host and 0 < int(cfg.port) < 65536:
                return cfg
            return None
    return None


def _unparsed_config(raw, reason, scheme='unknown'):
    cfg = ProxyConfig()
    cfg.raw, cfg.protocol = raw, scheme.lower()
    try:
        cfg.remarks = up.unquote(up.urlsplit(raw).fragment)
    except ValueError:
        pass
    if not cfg.remarks:
        cfg.remarks = f'Нераспознанная запись ({cfg.protocol})'
    cfg.extra['import_error'] = reason
    return cfg


def parse_text_block(text: str, _depth=0) -> list:
    """
    Парсит произвольный текст с VPN-ключами.
    Поддерживает:
    - Одна ссылка на строку (vless://, vmess://, ...)
    - JSON конфиги (xray или sing-box)
    - Base64-кодированный текст (стандартный формат подписки)
    - Смешанный текст
    """
    text = text.lstrip('\ufeff').strip()
    if not text:
        return []
    if _depth < 2 and '://' not in text and not text.startswith(('{', '[')):
        try:
            encoded = re.sub(r'\s+', '', text)
            if re.fullmatch(r'[A-Za-z0-9_+/=-]+', encoded):
                decoded = _decode_b64(encoded)
                if '://' in decoded or decoded.lstrip().startswith(('{', '[')):
                    return parse_text_block(decoded, _depth + 1)
        except (ValueError, UnicodeError):
            pass
    if text.startswith(('{', '[')):
        try:
            json.loads(text)
        except ValueError:
            pass
        else:
            return _parse_json_config(text)
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '//')):
            continue
        if line.startswith(('{', '[')):
            configs = _parse_json_config(line)
            results.extend(configs or [_unparsed_config(line, 'Не удалось разобрать JSON-конфигурацию.', 'json')])
            continue
        # Support several links on a line without splitting spaces in display names.
        matches = list(re.finditer(r'(?:^|\s)([a-zA-Z][\w+.-]*)://', line))
        for i, match in enumerate(matches):
            scheme = match.group(1).lower()
            if scheme in ('http', 'https'):
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            raw = line[match.start(1):end].strip()
            cfg = parse_proxy_link(raw)
            if cfg is None:
                reason = (f'Протокол {scheme} пока не поддерживается.' if scheme + '://' not in PARSERS
                          else f'Повреждённая ссылка {scheme}: проверьте адрес, порт и данные авторизации.')
                cfg = _unparsed_config(raw, reason, scheme)
            results.append(cfg)
    return results
