// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

object GeminiResponse {
    // Google web-app availability, checked 2026-10-20 (not the different mobile-app list).
    // https://support.google.com/gemini/answer/13575153?hl=en
    private val unsupportedRegions = setOf("AF", "BY", "CU", "IR", "KP", "RU", "SY")
    data class Verdict(val status: Status, val country: String, val detail: String, val title: String, val url: String = "")
    fun classify(code: Int, url: String, html: String): Verdict {
        val title = Regex("<title[^>]*>(.*?)</title>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
            .find(html)?.groupValues?.get(1)?.replace(Regex("\\s+"), " ")?.take(160).orEmpty()
        val country = GeminiCountry.extract(html)
        val lower = html.replace(Regex("<(script|style)\\b[^>]*>.*?</\\1>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL)), " ").lowercase()
        val host = runCatching { java.net.URI(url).host }.getOrNull().orEmpty()
        val status: Status
        val detail: String
        when {
            code == 429 -> { status = Status.RATE_LIMIT; detail = "Google ограничил частоту запросов. Повторите позже." }
            url.contains("/sorry/") || lower.contains("our systems have detected unusual traffic") -> { status = Status.CAPTCHA; detail = "Google запросил проверку CAPTCHA." }
            host == "accounts.google.com" -> { status = Status.LOGIN; detail = "Google перенаправил на вход в аккаунт." }
            code !in 200..299 -> { status = Status.ERROR; detail = "HTTP $code · $title" }
            url.contains("/unavailable") ||
                Regex("(?:isn['’]t|not|is not)(?: currently)? (?:supported|available) in your country").containsMatchIn(lower) ||
                lower.contains("недоступен в вашей стране") || lower.contains("не поддерживается в вашей стране") -> {
                status = Status.BLOCKED; detail = "На странице явно указано региональное ограничение." }
            host != "gemini.google.com" -> { status = Status.UNKNOWN; detail = "Вместо Gemini получен ответ другого сайта. Проверьте конечный URL." }
            country in unsupportedRegions -> {
                status = Status.BLOCKED
                detail = "Google определил регион $country. Он отсутствует в списке доступности веб-версии Gemini (проверен 20.10.2026). HTTP-соединение работает, но региональный доступ ограничен; доступ аккаунта не проверялся."
            }
            country == "CN" -> { status = Status.LOGIN; detail = "Google определил CN: по справке Google веб-версия здесь доступна только для Workspace. Доступ конкретного аккаунта не проверялся." }
            country.isNotBlank() -> {
                status = Status.OK; detail = "Google определил регион $country. Ответ Gemini получен, признаков ограничения нет. Проверка по алгоритму настольной версии: HTTPS + регион Google. Доступ аккаунта и генерация ответа модели не проверялись."
            }
            html.contains("BardChatUi") || html.contains("geminiweb-pa") -> {
                status = Status.UNKNOWN; detail = "Страница Gemini получена, но регион Google из vXmutd не извлечён. Одна HTML-оболочка не подтверждает доступность."
            }
            else -> { status = Status.UNKNOWN; detail = "Страница получена, но признаков чата или явного ограничения нет. Это не означает блокировку." }
        }
        return Verdict(status, country, detail, title, url)
    }
}
