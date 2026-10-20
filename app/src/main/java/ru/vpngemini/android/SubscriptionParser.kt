package ru.vpngemini.android

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URLDecoder
import java.util.Base64

object SubscriptionParser {
    private fun decode(s: String): String = URLDecoder.decode(s.replace("+", "%2B"), "UTF-8")
    private fun b64(s: String): String {
        val text = s.trim().replace("-", "+").replace("_", "/")
        return String(Base64.getDecoder().decode(text + "=".repeat((4 - text.length % 4) % 4)), Charsets.UTF_8)
    }

    fun parse(text: String, depth: Int = 0): List<Server> {
        require(depth < 4) { "Слишком много вложенных кодировок" }
        val source = text.trim().removePrefix("\uFEFF")
        require(source.isNotBlank()) { "Пустая подписка" }
        if (source.startsWith("{") || source.startsWith("[")) {
            return try { json(source) } catch (e: Exception) {
                listOf(Server(name = "Ошибка JSON", protocol = "json", raw = source, error = "Некорректный JSON: ${e.message}"))
            }
        }
        if (!source.contains("://") && !source.contains('\n')) {
            val decoded = runCatching { b64(source) }.getOrNull()
            if (decoded != null && decoded != source && (decoded.contains("://") || decoded.trim().startsWith("{"))) return parse(decoded, depth + 1)
        }
        // Some subscriptions wrap base64 onto multiple lines.
        if (!source.contains("://") && source.matches(Regex("[A-Za-z0-9+/=_\\s-]+"))) {
            val decoded = runCatching { b64(source.filterNot(Char::isWhitespace)) }.getOrNull()
            if (decoded != null && decoded.contains("://")) return parse(decoded, depth + 1)
        }
        return source.lines().map(String::trim).filter { it.isNotBlank() && !it.startsWith("#") }.map { line ->
            try { uri(line) } catch (e: Exception) {
                Server(name = "Не удалось импортировать", protocol = line.substringBefore("://", "?"), raw = line,
                    error = if (e is java.net.URISyntaxException) "Некорректная URI-конфигурация: ${e.reason}" else e.message ?: "Некорректная запись")
            }
        }
    }

    private fun json(source: String): List<Server> {
        val array = if (source.startsWith("[")) JSONArray(source) else JSONArray().put(JSONObject(source))
        return buildList {
            for (i in 0 until array.length()) {
                val entry = array.get(i)
                if (entry is String) { addAll(parse(entry)); continue }
                val root = entry as? JSONObject ?: continue
                val outbounds = root.optJSONArray("outbounds") ?: JSONArray().put(root)
                for (j in 0 until outbounds.length()) {
                    val out = outbounds.getJSONObject(j)
                    val sing = out.has("type")
                    val p = out.optString(if (sing) "type" else "protocol", "unknown")
                    if (p in listOf("direct", "block", "dns", "freedom", "blackhole")) continue
                    val server = if (sing) out else out.optJSONObject("settings")?.let {
                        it.optJSONArray("vnext")?.optJSONObject(0) ?: it.optJSONArray("servers")?.optJSONObject(0)
                    }
                    add(Server(name = out.optString("tag").ifBlank { "JSON · ${p.uppercase()}" }, protocol = p,
                        host = server?.optString(if (sing) "server" else "address") ?: "",
                        port = server?.optInt(if (sing) "server_port" else "port") ?: 0,
                        raw = out.toString(), outbound = out, engine = if (sing) "singbox" else "xray",
                        error = if (p in listOf("selector", "urltest", "wireguard", "tun")) "Для этого outbound нужны зависимости полного профиля" else ""))
                }
            }
        }.also { require(it.isNotEmpty()) { "В JSON нет серверов" } }
    }

    private fun uri(raw: String): Server {
        val proto = raw.substringBefore("://").lowercase()
        require(raw.contains("://")) { "Ожидалась ссылка конфигурации" }
        if (proto == "vmess") {
            val obj = JSONObject(b64(raw.substringAfter("://").substringBefore('#')))
            val params = obj.keys().asSequence().associateWith { obj.optString(it) }.toMutableMap()
            params["type"] = obj.optString("net", "tcp")
            params["security"] = if (obj.optString("tls") == "tls") "tls" else "none"
            params["alterId"] = obj.optString("aid", "0")
            params["method"] = obj.optString("scy", "auto")
            return Server(name = obj.optString("ps").ifBlank { obj.getString("add") }, protocol = proto,
                host = obj.getString("add"), port = obj.getString("port").toInt(), user = obj.getString("id"),
                params = params, raw = raw).also(::validate)
        }
        val fragment = raw.substringAfter('#', "")
        var main = raw.substringBefore('#')
        if (proto == "ss" && !main.substringAfter("://").substringBefore('?').contains('@')) {
            main = "ss://" + b64(main.substringAfter("://").substringBefore('?')) +
                if (main.contains('?')) "?" + main.substringAfter('?') else ""
        }
        val u = URI(main)
        val params = u.rawQuery.orEmpty().split('&').filter { it.isNotEmpty() }.associate {
            decode(it.substringBefore('=')) to decode(it.substringAfter('=', ""))
        }.toMutableMap()
        val credentials = decode(u.rawUserInfo.orEmpty())
        var user = credentials
        var password = credentials
        if (proto == "ss") {
            val pair = if (credentials.contains(':')) credentials else b64(credentials)
            params["method"] = pair.substringBefore(':')
            password = pair.substringAfter(':')
            if (params.containsKey("plugin")) throw IllegalArgumentException("Shadowsocks plugin требует отдельного плагина")
        } else if (proto == "tuic") {
            user = credentials.substringBefore(':'); password = credentials.substringAfter(':', "")
        }
        if (proto in listOf("trojan", "hysteria2", "hy2", "tuic") && params["security"] == null) params["security"] = "tls"
        val known = proto in listOf("vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic")
        return Server(name = decode(fragment).ifBlank { u.host ?: proto.uppercase() }, protocol = proto,
            host = u.host?.removeSurrounding("[", "]").orEmpty(), port = if (u.port == -1 && proto in listOf("hysteria2", "hy2")) 443 else u.port,
            user = user, password = password, params = params, raw = raw,
            engine = if (proto in listOf("hy2", "hysteria2", "tuic")) "singbox" else "xray",
            error = if (known) "" else "Протокол $proto пока не поддерживается").also { if (known) validate(it) }
    }

    private fun validate(s: Server) {
        require(s.host.isNotBlank() && s.port in 1..65535) { "Не указан сервер или неверный порт" }
        require(s.user.isNotBlank() || s.password.isNotBlank()) { "Отсутствуют учётные данные" }
    }
}
