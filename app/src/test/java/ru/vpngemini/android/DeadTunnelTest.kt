package ru.vpngemini.android

import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.*
import java.util.concurrent.TimeUnit

class DeadTunnelTest {
    @Test fun realXrayAcknowledgesSocksEvenWhenRemoteServerIsDead() = runBlocking {
        val core = File("../../bin/xray.exe").canonicalFile
        assumeTrue(core.isFile)
        val inbound = ServerSocket(0).use { it.localPort }
        val closedRemote = ServerSocket(0).use { it.localPort }
        val server = Server(name = "Closed test endpoint", protocol = "vless", host = "127.0.0.1", port = closedRemote,
            user = "00000000-0000-4000-8000-000000000001", raw = "")
        val file = File.createTempFile("dead-tunnel-", ".json")
        var process: Process? = null
        var client: OkHttpClient? = null
        try {
            file.writeText(CoreConfig.build(server, inbound).toString())
            val sink = File(if (System.getProperty("os.name").orEmpty().startsWith("Windows")) "NUL" else "/dev/null")
            process = ProcessBuilder(core.path, "run", "-c", file.path).redirectOutput(sink).redirectError(sink).start()
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4)
            while (true) {
                if (runCatching { Socket().use { it.connect(InetSocketAddress("127.0.0.1", inbound), 100) }; true }.getOrDefault(false)) break
                check(System.nanoTime() < deadline) { "Xray did not start" }
                Thread.sleep(30)
            }
            // This succeeded in the broken implementation and was incorrectly displayed as remote ping.
            assertTrue(SocksAcknowledgement.measure(inbound, 2) >= 0)
            val latency = TunnelLatency()
            client = OkHttpClient.Builder().proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", inbound)))
                .eventListener(latency).callTimeout(2, TimeUnit.SECONDS).build()
            val failed = runCatching { GeminiPage.fetch(client) }
            assertTrue("A dead tunnel must never deliver a Gemini page", failed.isFailure)
            assertNull("SOCKS ACK must not produce a TLS latency", latency.millis)
        } finally {
            client?.dispatcher?.cancelAll(); client?.connectionPool?.evictAll(); client?.dispatcher?.executorService?.shutdown()
            process?.destroyForcibly()?.waitFor(3, TimeUnit.SECONDS)
            file.delete()
        }
    }
}
