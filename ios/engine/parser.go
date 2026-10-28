package engine

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

func decode64(s string) (string, error) {
	s = strings.Join(strings.Fields(s), "")
	for _, enc := range []*base64.Encoding{base64.RawURLEncoding, base64.URLEncoding, base64.RawStdEncoding, base64.StdEncoding} {
		if b, e := enc.DecodeString(s); e == nil {
			return string(b), nil
		}
	}
	return "", fmt.Errorf("Некорректный Base64")
}
func str(v any) string {
	if v == nil {
		return ""
	}
	return fmt.Sprint(v)
}
func asMap(v any) map[string]any { m, _ := v.(map[string]any); return m }
func list(v any) []any           { a, _ := v.([]any); return a }
func first(v any) map[string]any {
	a := list(v)
	if len(a) == 0 {
		return nil
	}
	return asMap(a[0])
}
func parse(text string, depth int) ([]Server, error) {
	if depth > 3 {
		return nil, fmt.Errorf("Слишком много вложенных кодировок")
	}
	text = strings.TrimSpace(strings.TrimPrefix(text, "\ufeff"))
	if text == "" {
		return nil, fmt.Errorf("Пустая подписка")
	}
	if strings.HasPrefix(text, "{") || strings.HasPrefix(text, "[") {
		return parseJSON(text)
	}
	if !strings.Contains(text, "://") {
		if d, e := decode64(text); e == nil && d != text && (strings.Contains(d, "://") || strings.HasPrefix(strings.TrimSpace(d), "{")) {
			return parse(d, depth+1)
		}
	}
	var result []Server
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		s, e := parseURI(line)
		if e != nil {
			s = Server{ID: uuid(), Name: "Не удалось импортировать", Protocol: strings.Split(line, "://")[0], Raw: line, Engine: "xray", Params: map[string]string{}, Error: e.Error()}
		}
		result = append(result, s)
	}
	return result, nil
}
func Parse(text string) string {
	servers, err := parse(text, 0)
	if err != nil {
		return failure(err)
	}
	return encoded(map[string]any{"servers": servers})
}
func parseURI(raw string) (Server, error) {
	s := Server{ID: uuid(), Raw: raw, Params: map[string]string{}, Engine: "xray"}
	proto, _, ok := strings.Cut(raw, "://")
	if !ok {
		return s, fmt.Errorf("Ожидалась ссылка конфигурации")
	}
	s.Protocol = strings.ToLower(proto)
	if s.Protocol == "vmess" {
		d, e := decode64(strings.Split(strings.Split(raw, "://")[1], "#")[0])
		if e != nil {
			return s, e
		}
		var m map[string]any
		if e = json.Unmarshal([]byte(d), &m); e != nil {
			return s, fmt.Errorf("Некорректный VMess JSON")
		}
		s.Host = str(m["add"])
		s.Port, _ = strconv.Atoi(str(m["port"]))
		s.User = str(m["id"])
		s.Name = str(m["ps"])
		for k, v := range m {
			s.Params[k] = str(v)
		}
		s.Params["type"] = str(m["net"])
		s.Params["alterId"] = str(m["aid"])
		s.Params["method"] = str(m["scy"])
		if str(m["tls"]) == "tls" {
			s.Params["security"] = "tls"
		}
		return validate(s)
	}
	if s.Protocol == "ss" {
		main, frag, _ := strings.Cut(raw, "#")
		body := strings.TrimPrefix(main, "ss://")
		base, query, hasQ := strings.Cut(body, "?")
		if !strings.Contains(base, "@") {
			d, e := decode64(base)
			if e != nil {
				return s, e
			}
			raw = "ss://" + d
			if hasQ {
				raw += "?" + query
			}
			if frag != "" {
				raw += "#" + frag
			}
		}
	}
	u, e := url.Parse(raw)
	if e != nil {
		return s, fmt.Errorf("Некорректная URI-конфигурация")
	}
	s.Host = u.Hostname()
	s.Port, _ = strconv.Atoi(u.Port())
	if s.Port == 0 && (s.Protocol == "hy2" || s.Protocol == "hysteria2") {
		s.Port = 443
	}
	s.Name = u.Fragment
	for k, v := range u.Query() {
		if len(v) > 0 {
			s.Params[k] = strings.ReplaceAll(v[0], " ", "+")
		}
	}
	// QueryUnescape must preserve literal '+' in secrets and paths.
	s.Params = map[string]string{}
	for _, pair := range strings.Split(u.RawQuery, "&") {
		k, v, _ := strings.Cut(pair, "=")
		if k == "" {
			continue
		}
		k, _ = url.PathUnescape(k)
		v, _ = url.PathUnescape(v)
		s.Params[k] = v
	}
	credentials := ""
	if u.User != nil {
		credentials = u.User.Username()
		if p, ok := u.User.Password(); ok {
			credentials += ":" + p
		}
	}
	s.User = credentials
	s.Password = credentials
	switch s.Protocol {
	case "ss":
		if !strings.Contains(credentials, ":") {
			credentials, e = decode64(credentials)
			if e != nil {
				return s, e
			}
		}
		method, password, found := strings.Cut(credentials, ":")
		if !found {
			return s, fmt.Errorf("Отсутствует пароль Shadowsocks")
		}
		s.Params["method"] = method
		s.Password = password
		if s.Params["plugin"] != "" {
			return s, fmt.Errorf("Shadowsocks plugin требует отдельного плагина")
		}
	case "tuic":
		s.User, s.Password, _ = strings.Cut(credentials, ":")
		s.Engine = "singbox"
	case "hy2", "hysteria2":
		s.Engine = "singbox"
	case "vless", "trojan":
	default:
		s.Error = "Протокол " + s.Protocol + " пока не поддерживается"
		return s, nil
	}
	if s.Protocol == "trojan" && s.Params["security"] == "" {
		s.Params["security"] = "tls"
	}
	return validate(s)
}
func validate(s Server) (Server, error) {
	if s.Host == "" || s.Port < 1 || s.Port > 65535 {
		return s, fmt.Errorf("Не указан сервер или неверный порт")
	}
	if s.User == "" && s.Password == "" {
		return s, fmt.Errorf("Отсутствуют учётные данные")
	}
	if s.Name == "" {
		s.Name = s.Host
	}
	return s, nil
}
func parseJSON(text string) ([]Server, error) {
	var value any
	if e := json.Unmarshal([]byte(text), &value); e != nil {
		return nil, fmt.Errorf("Некорректный JSON")
	}
	entries := list(value)
	if entries == nil {
		entries = []any{value}
	}
	var result []Server
	for _, entry := range entries {
		if uri, ok := entry.(string); ok {
			r, e := parse(uri, 1)
			if e != nil {
				return nil, e
			}
			result = append(result, r...)
			continue
		}
		m := asMap(entry)
		if m == nil {
			result = append(result, Server{ID: uuid(), Name: "Ошибка JSON", Raw: encoded(entry), Protocol: "json", Engine: "xray", Params: map[string]string{}, Error: "Ожидался outbound или ссылка"})
			continue
		}
		outs := list(m["outbounds"])
		if outs == nil {
			outs = []any{m}
		}
		for _, v := range outs {
			out := asMap(v)
			p := str(out["protocol"])
			eng := "xray"
			host := ""
			port := 0
			if t := str(out["type"]); t != "" {
				p = t
				eng = "singbox"
				host = str(out["server"])
				port, _ = strconv.Atoi(str(out["server_port"]))
			} else {
				settings := asMap(out["settings"])
				remote := first(settings["vnext"])
				if remote == nil {
					remote = first(settings["servers"])
				}
				host = str(remote["address"])
				port, _ = strconv.Atoi(str(remote["port"]))
			}
			if p == "direct" || p == "block" || p == "dns" || p == "freedom" || p == "blackhole" {
				continue
			}
			s := Server{ID: uuid(), Name: str(out["tag"]), Protocol: p, Host: host, Port: port, Params: map[string]string{}, Raw: encoded(out), Outbound: out, Engine: eng}
			if s.Name == "" {
				s.Name = "JSON · " + strings.ToUpper(p)
			}
			if p == "selector" || p == "urltest" || p == "wireguard" || p == "tun" || host == "" {
				s.Error = "Для outbound нужны зависимости полного профиля"
			}
			result = append(result, s)
		}
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("В JSON нет серверов")
	}
	return result, nil
}
