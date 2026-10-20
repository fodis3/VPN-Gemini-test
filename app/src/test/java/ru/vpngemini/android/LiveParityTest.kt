package ru.vpngemini.android

import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.*
import java.util.concurrent.TimeUnit

/** Opt-in live comparison. Credentials arrive only through the build process environment. */
class LiveParityTest {
    @Test fun userKnownWorkingAndBlockedProxiesMatchAndroidClassifier() = runBlocking {
        val cases = System.getenv("VPN_GEMINI_LIVE_CASES")
        val core = File("../../bin/xray.exe").canonicalFile
        assumeTrue("Live cases are opt-in and not stored in the project", cases != null && core.isFile)
        val entries = JSONArray(cases)
        for (i in 0 until entries.length()) {
            val entry = entries.getJSONObject(i)
            val server = SubscriptionParser.parse(entry.getString("uri")).single()
            assertEquals("", server.error)
            val port = java.net.ServerSocket(0).use { it.localPort }
            val config = File.createTempFile("gemini-live-parity-", ".json")
            var process: Process? = null
            var client: OkHttpClient? = null
            try {
                val addresses = if (server.engine == "singbox") InetAddress.getAllByName(server.host).mapNotNull { it.hostAddress } else emptyList()
                config.writeText(CoreConfig.build(server, port, addresses, entry.optBoolean("quicCompatibility")).toString())
                val sink = File(if (System.getProperty("os.name").orEmpty().startsWith("Windows")) "NUL" else "/dev/null")
                val executable = if (server.engine == "singbox") File("../../bin/sing-box.exe").canonicalFile else core
                val command = mutableListOf(executable.path, "run", "-c", config.path)
                if (server.engine == "singbox") command.add("--disable-color")
                process = ProcessBuilder(command).redirectOutput(sink).redirectError(sink).start()
                val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4)
                while (true) {
                    if (runCatching { Socket().use { it.connect(InetSocketAddress("127.0.0.1", port), 100) }; true }.getOrDefault(false)) break
                    check(System.nanoTime() < deadline) { "Core startup timed out" }
                    Thread.sleep(30)
                }
                val latency = TunnelLatency()
                client = OkHttpClient.Builder().proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", port)))
                    .eventListener(latency).callTimeout(20, TimeUnit.SECONDS).build()
                val page = GeminiPage.fetch(client)
                println("Live case ${entry.getString("name")}: HTTP ${page.http}, Google region ${page.verdict.country}, verdict ${page.verdict.status}, TLS ${latency.millis} ms")
                assertEquals(entry.getString("expected"), page.verdict.status.name)
                assertTrue(page.verdict.country.matches(Regex("[A-Z]{2}")))
                assertNotNull(latency.millis)
            } finally {
                client?.dispatcher?.cancelAll(); client?.connectionPool?.evictAll(); client?.dispatcher?.executorService?.shutdown()
                process?.destroyForcibly()?.waitFor(3, TimeUnit.SECONDS)
                config.delete()
            }
        }
    }
}
