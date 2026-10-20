package ru.vpngemini.android

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/** A bounded transport retry; HTTP verdicts never trigger it. */
object QuicRetry {
    suspend fun run(server: Server, log: (String) -> Unit, attempt: suspend (Boolean) -> Result): Result {
        val first = attempt(false)
        val hysteria = server.engine == "singbox" && (server.protocol in listOf("hy2", "hysteria2") ||
            server.outbound?.optString("type") == "hysteria2")
        val mtuError = listOf("message too long", "packet too large", "datagram too large", "EMSGSIZE")
            .any { first.detail.contains(it, ignoreCase = true) }
        val quicTimeout = listOf("quic: timeout", "timeout: no recent network activity", "handshake timeout")
            .any { first.detail.contains(it, ignoreCase = true) }
        if (!hysteria || first.httpCode != null ||
            !(first.status == Status.TIMEOUT || first.status == Status.ERROR && (mtuError || quicTimeout))) return first
        currentCoroutineContext().ensureActive()
        log("Hysteria2: повтор через QUIC с пакетами 1200 байт после ${if (mtuError) "ошибки размера UDP" else "тайм-аута"}")
        val second = attempt(true)
        return second.copy(totalMs = first.totalMs + second.totalMs,
            detail = "Повтор QUIC: 1200 байт, без PMTU и Chrome QUIC. ${second.detail}")
    }
}
