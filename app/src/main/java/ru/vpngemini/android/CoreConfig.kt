// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import org.json.JSONArray
import org.json.JSONObject

fun obj(vararg pairs: Pair<String, Any?>) = JSONObject().apply { pairs.forEach { (k, v) -> if (v != null) put(k, v) } }
fun arr(vararg items: Any) = JSONArray().apply { items.forEach(::put) }

object CoreConfig {
    fun build(s: Server, port: Int, endpointAddresses: List<String> = emptyList(), quicCompatibility: Boolean = false): JSONObject =
        if (s.engine == "singbox") sing(s, port, endpointAddresses, quicCompatibility) else xray(s, port)

    private fun xray(s: Server, port: Int): JSONObject {
        val p = s.params
        val stream = obj("network" to (p["type"] ?: "tcp"))
        when (p["security"]) {
            "tls" -> stream.put("security", "tls").put("tlsSettings", obj(
                "serverName" to (p["sni"] ?: s.host), "allowInsecure" to insecure(p), "fingerprint" to p["fp"],
                "alpn" to p["alpn"]?.let { JSONArray(it.split(',')) }, "echConfigList" to (p["ech"] ?: p["echConfigList"])))
            "reality" -> stream.put("security", "reality").put("realitySettings", obj(
                "serverName" to (p["sni"] ?: s.host), "fingerprint" to (p["fp"] ?: "chrome"),
                "publicKey" to p["pbk"], "shortId" to (p["sid"] ?: ""), "spiderX" to (p["spx"] ?: ""), "mldsa65Verify" to p["pqv"]))
        }
        when (p["type"]) {
            "ws" -> stream.put("wsSettings", obj("path" to (p["path"] ?: "/"), "headers" to obj("Host" to (p["host"] ?: s.host))))
            "grpc" -> stream.put("grpcSettings", obj("serviceName" to (p["serviceName"] ?: p["path"]?.trimStart('/') ?: ""),
                "authority" to p["authority"], "multiMode" to (p["mode"] == "multi")))
            "xhttp", "splithttp" -> stream.put("network", "xhttp").put("xhttpSettings", obj(
                "host" to p["host"], "path" to (p["path"] ?: "/"), "mode" to (p["mode"] ?: "auto"),
                "extra" to p["extra"]?.let { JSONObject(it) }))
            "httpupgrade" -> stream.put("httpupgradeSettings", obj("host" to (p["host"] ?: s.host), "path" to (p["path"] ?: "/")))
            "h2", "http" -> stream.put("network", "h2").put("httpSettings", obj("host" to arr(p["host"] ?: s.host), "path" to (p["path"] ?: "/")))
            "tcp" -> if (p["headerType"] == "http") stream.put("tcpSettings", obj("header" to obj("type" to "http",
                "request" to obj("path" to arr(p["path"] ?: "/"), "headers" to obj("Host" to arr(p["host"] ?: s.host))))))
        }
        val outbound = if (s.outbound != null) JSONObject(s.outbound.toString()) else when (s.protocol) {
            "vless", "vmess" -> obj("protocol" to s.protocol, "settings" to obj("vnext" to arr(obj(
                "address" to s.host, "port" to s.port, "users" to arr(if (s.protocol == "vless")
                    obj("id" to s.user, "encryption" to (p["encryption"] ?: "none"), "flow" to (p["flow"] ?: ""))
                else obj("id" to s.user, "alterId" to (p["alterId"]?.toIntOrNull() ?: 0), "security" to (p["method"] ?: "auto")))))), "streamSettings" to stream)
            "trojan" -> obj("protocol" to "trojan", "settings" to obj("servers" to arr(obj("address" to s.host, "port" to s.port, "password" to s.password))), "streamSettings" to stream)
            "ss" -> obj("protocol" to "shadowsocks", "settings" to obj("servers" to arr(obj("address" to s.host, "port" to s.port, "password" to s.password, "method" to p["method"]))))
            else -> error("Не поддерживается: ${s.protocol}")
        }
        outbound.put("tag", "proxy")
        return obj("log" to obj("loglevel" to "error"), "inbounds" to arr(obj("listen" to "127.0.0.1", "port" to port,
            "protocol" to "socks", "settings" to obj("auth" to "noauth", "udp" to false))), "outbounds" to arr(outbound))
    }

    private fun insecure(p: Map<String, String>) = (p["insecure"] ?: p["allowInsecure"]) in listOf("1", "true")

    private fun sing(s: Server, port: Int, endpointAddresses: List<String>, quicCompatibility: Boolean): JSONObject {
        val p = s.params
        val tls = obj("enabled" to true, "server_name" to (p["sni"] ?: s.host), "insecure" to insecure(p),
            "alpn" to p["alpn"]?.let { JSONArray(it.split(',')) })
        val outbound = if (s.outbound != null) JSONObject(s.outbound.toString()) else when (s.protocol) {
            "hy2", "hysteria2" -> obj("type" to "hysteria2", "server" to s.host, "server_port" to s.port,
                "password" to s.password, "tls" to tls,
                "obfs" to p["obfs"]?.let { obj("type" to it, "password" to (p["obfs-password"] ?: p["obfs_password"] ?: "")) })
            "tuic" -> obj("type" to "tuic", "server" to s.host, "server_port" to s.port, "uuid" to s.user,
                "password" to s.password, "congestion_control" to (p["congestion_control"] ?: "bbr"), "tls" to tls)
            else -> error("Не поддерживается: ${s.protocol}")
        }
        outbound.put("tag", "proxy")
        if (quicCompatibility && outbound.optString("type") == "hysteria2") {
            // Chrome parroting overrides initial_packet_size, so all three are needed.
            outbound.put("disable_chrome_parrot", true)
                .put("initial_packet_size", 1200).put("disable_path_mtu_discovery", true)
        }
        // Standalone Android executables cannot obtain Android DNS via /etc/resolv.conf.
        // Resolve only the proxy endpoint with Android's resolver; Gemini stays inside the tunnel.
        val resolver = if (endpointAddresses.isEmpty()) obj("type" to "local", "tag" to "system")
            else obj("type" to "hosts", "tag" to "system",
                "predefined" to obj(s.host to JSONArray(endpointAddresses)))
        return obj("log" to obj("level" to "error"), "inbounds" to arr(obj("type" to "socks", "listen" to "127.0.0.1", "listen_port" to port)),
            "outbounds" to arr(outbound), "dns" to obj("servers" to arr(resolver)),
            "route" to obj("final" to "proxy", "default_domain_resolver" to "system"))
    }
}
