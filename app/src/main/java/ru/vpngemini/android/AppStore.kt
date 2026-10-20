// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import android.app.Application
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.Proxy
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class GeminiApp : Application() {
    lateinit var store: AppStore
    override fun onCreate() { super.onCreate(); store = AppStore(this) }
}

class AppStore(private val context: Context) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val mutable = MutableStateFlow(UiState(settings = Settings(
        prefs.getInt("parallel", 2).coerceIn(1, 4), prefs.getInt("timeout", 15).coerceIn(5, 60),
        prefs.getBoolean("dynamic", true), prefs.getInt("theme", 0), prefs.getBoolean("haptics", true))))
    val state = mutable.asStateFlow()
    private var checkJob: Job? = null
    private var importJob: Job? = null
    init {
        context.cacheDir.listFiles()?.filter { it.name.startsWith("probe-") && it.name.endsWith(".json") }?.forEach { it.delete() }
        log("VPN Gemini 4.0 · Android готов к работе")
    }
    fun log(message: String) {
        val time = SimpleDateFormat("HH:mm:ss", Locale.ROOT).format(Date())
        mutable.update { it.copy(logs = (it.logs + "$time  $message").takeLast(1500)) }
    }
    fun message(value: String) { mutable.update { it.copy(message = value) } }
    fun settings(value: Settings) {
        prefs.edit().putInt("parallel", value.parallel).putInt("timeout", value.timeout)
            .putBoolean("dynamic", value.dynamicColors).putInt("theme", value.theme).putBoolean("haptics", value.haptics).apply()
        mutable.update { it.copy(settings = value) }
    }
    fun clear() { if (!state.value.running && !state.value.importing) mutable.update { it.copy(results = emptyList()) } }
    fun clearLogs() { mutable.update { it.copy(logs = emptyList()) } }

    fun importText(text: String) {
        if (state.value.running || state.value.importing) return
        mutable.update { it.copy(importing = true) }
        importJob = scope.launch {
            try { append(SubscriptionParser.parse(text)) }
            catch (e: Exception) { message(e.message ?: "Ошибка импорта"); log("Ошибка импорта: ${e.message}") }
            finally { mutable.update { it.copy(importing = false) } }
        }
    }
    fun importFile(uri: android.net.Uri) {
        if (state.value.running || state.value.importing) return
        mutable.update { it.copy(importing = true) }
        importJob = scope.launch {
            try {
                val data = context.contentResolver.openInputStream(uri)?.use { input ->
                    val out = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        require(out.size() + count <= 8 * 1024 * 1024) { "Файл превышает 8 МБ" }
                        out.write(buffer, 0, count)
                    }
                    out.toByteArray()
                } ?: error("Файл не удалось открыть")
                require(data.size <= 8 * 1024 * 1024) { "Файл превышает 8 МБ" }
                append(SubscriptionParser.parse(String(data, Charsets.UTF_8)))
            } catch (e: Exception) { message(e.message ?: "Ошибка чтения файла") }
            finally { mutable.update { it.copy(importing = false) } }
        }
    }
    private fun append(servers: List<Server>) {
        require(servers.isNotEmpty()) { "Не найдено конфигураций" }
        val results = servers.map { Result(it, if (it.error.isBlank()) Status.PENDING else Status.ERROR, detail = it.error) }
        mutable.update { it.copy(results = it.results + results, importRevision = it.importRevision + 1, importError = "") }
        val bad = servers.count { it.error.isNotBlank() }
        log("Добавлено ${servers.size} записей; с ошибкой импорта: $bad. Записи сохранены без удаления дубликатов.")
        message("Добавлено ${servers.size} · с ошибкой $bad")
    }
    fun subscription(url: String, hwid: String) {
        if (state.value.running || state.value.importing) return
        mutable.update { it.copy(importing = true, importError = "") }
        importJob = scope.launch {
            var client: OkHttpClient? = null
            try {
                log("Загрузка подписки…")
                client = OkHttpClient.Builder().proxy(Proxy.NO_PROXY).callTimeout(30, TimeUnit.SECONDS).followSslRedirects(false).build()
                val request = SubscriptionHttp.request(url, hwid)
                client.newCall(request).await().use { r ->
                    val source = r.body?.source() ?: throw SubscriptionException("Пустая подписка")
                    source.request(8L * 1024 * 1024 + 1)
                    if (source.buffer.size > 8L * 1024 * 1024) throw SubscriptionException("Подписка превышает 8 МБ")
                    append(SubscriptionParser.parse(SubscriptionHttp.validate(r.code, source.readUtf8())))
                }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                // Only controlled diagnostic messages may enter UI/logs; raw exception URLs contain tokens.
                val detail = when (e) {
                    is SubscriptionException -> e.message ?: "Ошибка подписки"
                    is javax.net.ssl.SSLException -> "Не удалось проверить TLS-соединение с подпиской. Проверьте дату, время и сертификат сайта."
                    is java.net.UnknownHostException -> "Не удалось найти сервер подписки через DNS. Проверьте сеть и домен."
                    is java.io.InterruptedIOException -> "Истекло время загрузки подписки. Проверьте сеть и повторите."
                    is IllegalArgumentException -> "Некорректная ссылка или содержимое подписки. Проверьте ссылку импорта."
                    else -> "Не удалось загрузить подписку. Проверьте подключение и доступность поставщика."
                }
                mutable.update { it.copy(importError = detail) }
                log(detail); message(detail)
            } finally {
                client?.dispatcher?.cancelAll(); client?.connectionPool?.evictAll(); client?.dispatcher?.executorService?.shutdown()
                mutable.update { it.copy(importing = false) }
            }
        }
    }
    fun requestStart(direct: Boolean = false) {
        if (state.value.running || state.value.importing) return
        if (!direct && state.value.results.isEmpty()) { message("Сначала добавьте серверы"); return }
        ContextCompat.startForegroundService(context, Intent(context, CheckService::class.java).putExtra("direct", direct))
    }
    fun start(direct: Boolean, onDone: () -> Unit) {
        if (checkJob?.isActive == true) return
        val settings = state.value.settings
        val list = if (direct) listOf(Result(Server(name = "Без VPN", protocol = "direct", raw = ""))) else state.value.results.map { Result(it.server) }
        mutable.update { it.copy(running = true, results = if (direct) it.results.filterNot { r -> r.server.protocol == "direct" } + list else list) }
        log(if (direct) "Проверка прямого подключения" else "Проверка ${list.size} серверов · параллельно ${settings.parallel}")
        checkJob = scope.launch {
            try {
                val semaphore = Semaphore(settings.parallel)
                coroutineScope {
                    list.map { entry -> launch {
                        semaphore.withPermit {
                            update(entry.copy(status = Status.TESTING))
                            val result = if (entry.server.protocol == "direct") DirectProbe.run(settings.timeout, entry.server) else Probe(context, ::log).run(entry.server, settings.timeout)
                            update(result)
                            log("${result.server.name.take(70)} · ${result.status.label}" +
                                (result.httpCode?.let { " · HTTP $it" } ?: "") +
                                (if (result.status in listOf(Status.ERROR, Status.TIMEOUT)) " · ${result.detail.take(400)}" else ""))
                        }
                    } }.joinAll()
                }
                log("Проверка завершена · Gemini доступен: ${state.value.good}")
            } finally {
                mutable.update { state -> state.copy(running = false, results = state.results.map {
                    if (it.status in listOf(Status.PENDING, Status.TESTING)) it.copy(status = Status.CANCELLED) else it
                }) }
                onDone()
            }
        }
    }
    private fun update(result: Result) { mutable.update { it.copy(results = it.results.map { old -> if (old.server.id == result.server.id) result else old }) } }
    fun stop() { checkJob?.cancel(); log("Проверка остановлена") }
    fun csv(): String = buildString {
        append('\uFEFF').append("Название,Протокол,Статус,Страна,TLS мс,Время мс,HTTP,Описание\r\n")
        state.value.results.forEach { r ->
            append(listOf(r.server.name, r.server.protocol, r.status.label, r.country, r.pingMs?.toString().orEmpty(), r.totalMs.toString(),
                r.httpCode?.toString().orEmpty(), r.detail).joinToString(",") { value ->
                // Neutralize spreadsheet formulas in imported server names and diagnostics.
                val safe = if (value.trimStart().firstOrNull() in listOf('=', '+', '-', '@')) "'$value" else value
                "\"${safe.replace("\"", "\"\"")}\""
            }).append("\r\n")
        }
    }
}

object DirectProbe {
    suspend fun run(timeout: Int, server: Server): Result {
        val start = System.nanoTime()
        val latency = TunnelLatency()
        val client = OkHttpClient.Builder().proxy(Proxy.NO_PROXY).callTimeout(timeout.toLong(), TimeUnit.SECONDS)
            .eventListener(latency).build()
        try {
            val page = GeminiPage.fetch(client)
            val v = page.verdict
            return Result(server, v.status, v.country, latency.millis, (System.nanoTime() - start) / 1_000_000, v.detail, page.http, page.url, page.bytes, v.title)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { return Result(server, if (e is java.io.InterruptedIOException) Status.TIMEOUT else Status.ERROR, detail = "HTTPS: ${e.message}") }
        finally { client.dispatcher.cancelAll(); client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
    }
}
