package ru.vpngemini.android

import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.*
import java.io.File
import java.io.IOException
import java.net.*
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

suspend fun Call.await(): Response = suspendCancellableCoroutine { continuation ->
    continuation.invokeOnCancellation { cancel() }
    enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) { if (continuation.isActive) continuation.resumeWithException(e) }
        override fun onResponse(call: Call, response: Response) {
            continuation.resume(response) { _, value, _ -> value.close() }
        }
    })
}

class Probe(private val context: Context, private val log: (String) -> Unit = {}) {
    suspend fun run(server: Server, timeout: Int): Result =
        QuicRetry.run(server, log) { compatibility -> runAttempt(server, timeout, compatibility) }

    private suspend fun runAttempt(server: Server, timeout: Int, quicCompatibility: Boolean): Result {
        val start = System.nanoTime()
        fun elapsed() = (System.nanoTime() - start) / 1_000_000
        if (server.error.isNotEmpty()) return Result(server, Status.ERROR, detail = server.error)
        var process: Process? = null
        var config: File? = null
        var client: OkHttpClient? = null
        var stage = "Запуск ядра"
        val errors = StringBuilder()
        var outputReader: Thread? = null
        var ping: Long? = null
        try {
            val port = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { it.localPort }
            config = File.createTempFile("probe-", ".json", context.cacheDir)
            val addresses = if (server.engine == "singbox") {
                stage = "DNS сервера через Android"
                runInterruptible(Dispatchers.IO) { InetAddress.getAllByName(server.host).mapNotNull { it.hostAddress } }
            } else emptyList()
            stage = "Запуск ядра"
            config.writeText(CoreConfig.build(server, port, addresses, quicCompatibility).toString())
            val binary = File(context.applicationInfo.nativeLibraryDir, "lib${server.engine}.so")
            check(binary.isFile && binary.canExecute()) { "Ядро ${server.engine} недоступно для этой архитектуры" }
            val command = mutableListOf(binary.absolutePath, "run", "-c", config.absolutePath)
            if (server.engine == "singbox") command.add("--disable-color")
            process = ProcessBuilder(command).redirectErrorStream(true).start()
            val runningProcess = process
            outputReader = thread(name = "core-output", isDaemon = true) {
                runCatching { runningProcess.inputStream.bufferedReader().useLines { lines -> lines.forEach { line ->
                    synchronized(errors) { if (errors.length < 2500) errors.append(line.take(500)).append('\n') }
                } } }
            }
            var ready = false
            repeat(80) {
                currentCoroutineContext().ensureActive()
                if (!runningProcess.isAlive) error("Ядро отклонило конфигурацию. " + synchronized(errors) { errors.toString().take(1200) })
                if (!ready) {
                    ready = runCatching { Socket().use { it.connect(InetSocketAddress("127.0.0.1", port), 60) }; true }.getOrDefault(false)
                    if (!ready) delay(50)
                }
            }
            check(ready) { "Локальный SOCKS5 не запустился" }
            stage = "HTTPS Gemini через ${server.engine}"
            val latency = TunnelLatency()
            client = OkHttpClient.Builder().proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", port)))
                .connectTimeout(timeout.toLong(), TimeUnit.SECONDS).readTimeout(timeout.toLong(), TimeUnit.SECONDS)
                .callTimeout(timeout.toLong(), TimeUnit.SECONDS)
                .eventListener(latency).build()
            val page = GeminiPage.fetch(client)
            ping = latency.millis
            log("${server.name.take(60)} · TLS ${ping?.let { "$it мс" } ?: "—"} · Gemini HTTP ${page.http} · страна ${page.verdict.country.ifBlank { "—" }} · ${page.verdict.status.label}")
            return Result(server, page.verdict.status, page.verdict.country, ping, elapsed(), page.verdict.detail, page.http, page.url, page.bytes, page.verdict.title)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) {
            currentCoroutineContext().ensureActive()
            val status = if (e is java.io.InterruptedIOException) Status.TIMEOUT else Status.ERROR
            // SOCKS replies hide the upstream cause (DNS, QUIC, auth or TLS).
            // Stop the process and drain its output before presenting the diagnostic.
            process?.destroy()
            process?.waitFor(300, TimeUnit.MILLISECONDS)
            outputReader?.join(300)
            val coreError = synchronized(errors) { errors.toString().trim() }
            val message = CoreDiagnostics.clean((e.message ?: e.javaClass.simpleName) +
                if (coreError.isBlank()) "" else "\nЯдро: $coreError", server)
            return Result(server, status, pingMs = ping, totalMs = elapsed(), detail = "$stage: ${message.take(1500)}")
        } finally {
            client?.dispatcher?.cancelAll(); client?.connectionPool?.evictAll(); client?.dispatcher?.executorService?.shutdown()
            process?.destroy()
            if (process?.waitFor(300, TimeUnit.MILLISECONDS) == false) process.destroyForcibly()
            config?.delete()
        }
    }
}
