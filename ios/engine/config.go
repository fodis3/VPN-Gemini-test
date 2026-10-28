package engine

import (
	"encoding/json"
	"strconv"
	"strings"
)

func m(pairs ...any) map[string]any {
	r := map[string]any{}
	for i := 0; i < len(pairs); i += 2 {
		if pairs[i+1] != nil {
			r[pairs[i].(string)] = pairs[i+1]
		}
	}
	return r
}
func a(items ...any) []any { return items }
func fallback(v, def string) string {
	if v == "" {
		return def
	}
	return v
}
func insecure(p map[string]string) bool {
	v := fallback(p["insecure"], p["allowInsecure"])
	return v == "1" || strings.EqualFold(v, "true")
}
func coreConfig(s Server, addresses []string, compat bool) []byte {
	p := s.Params
	var outbound map[string]any
	if s.Outbound != nil {
		json.Unmarshal([]byte(encoded(s.Outbound)), &outbound)
	}
	if s.Engine == "singbox" {
		if outbound == nil {
			tls := m("enabled", true, "server_name", fallback(p["sni"], s.Host), "insecure", insecure(p))
			if p["alpn"] != "" {
				tls["alpn"] = strings.Split(p["alpn"], ",")
			}
			typ := s.Protocol
			if typ == "hy2" {
				typ = "hysteria2"
			}
			outbound = m("type", typ, "server", s.Host, "server_port", s.Port, "password", s.Password, "tls", tls)
			if typ == "hysteria2" && p["obfs"] != "" {
				outbound["obfs"] = m("type", p["obfs"], "password", fallback(p["obfs-password"], p["obfs_password"]))
			}
			if typ == "tuic" {
				outbound["uuid"] = s.User
				outbound["congestion_control"] = fallback(p["congestion_control"], "bbr")
			}
		}
		outbound["tag"] = "proxy"
		if compat && str(outbound["type"]) == "hysteria2" {
			outbound["disable_chrome_parrot"] = true
			outbound["initial_packet_size"] = 1200
			outbound["disable_path_mtu_discovery"] = true
		}
		dns := m("type", "local", "tag", "system")
		if len(addresses) > 0 {
			dns = m("type", "hosts", "tag", "system", "predefined", m(s.Host, addresses))
		}
		return []byte(encoded(m("log", m("disabled", true), "outbounds", a(outbound), "dns", m("servers", a(dns)), "route", m("final", "proxy", "default_domain_resolver", "system"))))
	}
	if outbound == nil {
		stream := m("network", fallback(p["type"], "tcp"))
		switch p["security"] {
		case "tls":
			settings := m("serverName", fallback(p["sni"], s.Host), "allowInsecure", insecure(p), "fingerprint", fallback(p["fp"], "chrome"))
			if p["alpn"] != "" {
				settings["alpn"] = strings.Split(p["alpn"], ",")
			}
			if p["ech"] != "" {
				settings["echConfigList"] = p["ech"]
			}
			stream["security"] = "tls"
			stream["tlsSettings"] = settings
		case "reality":
			stream["security"] = "reality"
			stream["realitySettings"] = m("serverName", fallback(p["sni"], s.Host), "fingerprint", fallback(p["fp"], "chrome"), "publicKey", p["pbk"], "shortId", p["sid"], "spiderX", p["spx"])
		}
		switch p["type"] {
		case "ws":
			stream["wsSettings"] = m("path", fallback(p["path"], "/"), "headers", m("Host", fallback(p["host"], s.Host)))
		case "grpc":
			stream["grpcSettings"] = m("serviceName", fallback(p["serviceName"], strings.TrimPrefix(p["path"], "/")), "authority", p["authority"], "multiMode", p["mode"] == "multi")
		case "xhttp", "splithttp":
			stream["network"] = "xhttp"
			x := m("host", p["host"], "path", fallback(p["path"], "/"), "mode", fallback(p["mode"], "auto"))
			if p["extra"] != "" {
				var extra any
				if json.Unmarshal([]byte(p["extra"]), &extra) == nil {
					x["extra"] = extra
				}
			}
			stream["xhttpSettings"] = x
		case "httpupgrade":
			stream["httpupgradeSettings"] = m("host", fallback(p["host"], s.Host), "path", fallback(p["path"], "/"))
		case "h2", "http":
			stream["network"] = "h2"
			stream["httpSettings"] = m("host", a(fallback(p["host"], s.Host)), "path", fallback(p["path"], "/"))
		case "tcp":
			if p["headerType"] == "http" {
				stream["tcpSettings"] = m("header", m("type", "http", "request", m("path", a(fallback(p["path"], "/")), "headers", m("Host", a(fallback(p["host"], s.Host))))))
			}
		}
		switch s.Protocol {
		case "vless", "vmess":
			user := m("id", s.User, "encryption", fallback(p["encryption"], "none"), "flow", p["flow"])
			if s.Protocol == "vmess" {
				aid, _ := strconv.Atoi(p["alterId"])
				user = m("id", s.User, "alterId", aid, "security", fallback(p["method"], "auto"))
			}
			outbound = m("protocol", s.Protocol, "settings", m("vnext", a(m("address", s.Host, "port", s.Port, "users", a(user)))), "streamSettings", stream)
		case "trojan":
			outbound = m("protocol", "trojan", "settings", m("servers", a(m("address", s.Host, "port", s.Port, "password", s.Password))), "streamSettings", stream)
		case "ss":
			outbound = m("protocol", "shadowsocks", "settings", m("servers", a(m("address", s.Host, "port", s.Port, "password", s.Password, "method", p["method"]))))
		}
	}
	if outbound == nil {
		return nil
	}
	outbound["tag"] = "proxy"
	return []byte(encoded(m("log", m("loglevel", "none"), "outbounds", a(outbound))))
}
