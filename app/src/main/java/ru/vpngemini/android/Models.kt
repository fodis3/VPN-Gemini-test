package ru.vpngemini.android

import org.json.JSONObject
import java.util.UUID

data class Server(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val protocol: String,
    val host: String = "",
    val port: Int = 0,
    val user: String = "",
    val password: String = "",
    val params: Map<String, String> = emptyMap(),
    val raw: String,
    val outbound: JSONObject? = null,
    val engine: String = "xray",
    val error: String = "",
)

enum class Status(val label: String) {
    PENDING("В очереди"), TESTING("Проверка"), OK("Доступен"), BLOCKED("Ограничение"),
    UNKNOWN("Не определён"), LOGIN("Вход в Google"), CAPTCHA("Капча"),
    RATE_LIMIT("Лимит запросов"), TIMEOUT("Тайм-аут"), ERROR("Ошибка"), CANCELLED("Остановлен")
}

data class Result(
    val server: Server,
    val status: Status = Status.PENDING,
    val country: String = "",
    val pingMs: Long? = null,
    val totalMs: Long = 0,
    val detail: String = "",
    val httpCode: Int? = null,
    val finalUrl: String = "",
    val bytes: Long = 0,
    val title: String = "",
) {
    val geminiAccessible get() = status == Status.OK && country.isNotBlank() && httpCode?.let { it in 200..299 } == true
}

data class Settings(val parallel: Int = 2, val timeout: Int = 15, val dynamicColors: Boolean = true, val theme: Int = 0, val haptics: Boolean = true)
data class UiState(
    val results: List<Result> = emptyList(), val logs: List<String> = emptyList(),
    val running: Boolean = false, val importing: Boolean = false,
    val settings: Settings = Settings(), val message: String = "", val importError: String = "", val importRevision: Int = 0,
) {
    val completed get() = results.count { it.status !in listOf(Status.PENDING, Status.TESTING) }
    val good get() = results.count { it.geminiAccessible }
}
