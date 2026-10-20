// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import okhttp3.Request
import org.json.JSONObject

class SubscriptionException(message: String) : Exception(message)

object SubscriptionHttp {
    fun request(url: String, hwid: String): Request {
        if (!url.startsWith("https://", true)) throw SubscriptionException("Укажите HTTPS-ссылку подписки")
        // Match the desktop client's legacy HWID contract as well as modern x-hwid providers.
        return Request.Builder().url(url).header("User-Agent", "v2rayN/6.67" + if (hwid.isNotBlank()) " HWID/$hwid" else "")
            .header("Accept", "text/plain, application/json, */*").header("Accept-Language", "en-US,en;q=0.9")
            .apply { if (hwid.isNotBlank()) {
                header("x-hwid", hwid); header("x-device-os", "Android")
            } }.build()
    }

    fun validate(code: Int, body: String): String {
        val content = body.trim().removePrefix("\uFEFF")
        val lower = content.lowercase()
        if (lower.contains("cloudflare") && Regex("(?:error\\s*(?:code\\s*)?[:=]?\\s*|<span[^>]*>)1002", RegexOption.IGNORE_CASE).containsMatchIn(content))
            throw SubscriptionException("Cloudflare 1002: DNS подписки указывает на запрещённый IP. Это ошибка на стороне поставщика; исправить её в приложении нельзя.")
        val json = if (content.startsWith("{")) runCatching { JSONObject(content) }.getOrNull() else null
        if (json != null && !json.has("outbounds") && !json.has("protocol") && !json.has("type")) {
            val errorCode = listOf("code", "errorCode", "statusCode").firstNotNullOfOrNull { key -> json.opt(key)?.toString()?.takeIf { it.matches(Regex("[A-Za-z0-9_-]{1,32}")) } }
            if (errorCode != null || json.has("error") || json.optBoolean("success", true) == false) {
                throw SubscriptionException("Поставщик отклонил подписку" + (errorCode?.let { " · код $it" } ?: "") +
                    ". Проверьте срок подписки, привязанный HWID и лимит устройств. Новый случайный HWID не заменяет уже зарегистрированный.")
            }
        }
        if (code !in 200..299) throw SubscriptionException("Подписка ответила HTTP $code. " + when (code) {
            401, 403 -> "Проверьте доступ к подписке, HWID и лимит устройств."
            404 -> "Ссылка не найдена или больше не действует."
            429 -> "Слишком много запросов. Повторите позже."
            in 500..599 -> "Ошибка сервера поставщика. Повторите позже."
            else -> "Проверьте ссылку и настройки поставщика."
        })
        if (content.isBlank()) throw SubscriptionException("Сервер вернул пустую подписку")
        if (lower.startsWith("<!doctype html") || lower.startsWith("<html") || lower.contains("<body"))
            throw SubscriptionException("Вместо конфигураций получена веб-страница. Используйте ссылку импорта, проверьте HWID и защиту сайта поставщика.")
        if (content.length < 1500 && Regex("(?:error|ошибка)\\s*[:=]?\\s*1002", RegexOption.IGNORE_CASE).containsMatchIn(content))
            throw SubscriptionException("Поставщик подписки вернул ошибку 1002. Требуется проверить условия доступа у поставщика; это не HTTP-код. Если ошибка показана и на сайте, смена приложения её не устранит.")
        return content
    }
}
