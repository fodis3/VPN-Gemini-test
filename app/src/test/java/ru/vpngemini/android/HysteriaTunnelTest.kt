package ru.vpngemini.android

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.*
import java.util.concurrent.TimeUnit
import java.io.Closeable
import kotlin.concurrent.thread

class HysteriaTunnelTest {
    @Test fun realQuicTunnelUsesBootstrapAddressesAndRejectsWrongPassword() = exercise(false)
    @Test fun reducedPacketModeWorksWhenLargerUdpPacketsAreDropped() = exercise(true)

    private fun exercise(restrictMtu: Boolean) {
        val core = File("../../bin/sing-box.exe").canonicalFile
        assumeTrue(core.isFile)
        val directory = java.nio.file.Files.createTempDirectory("hy2-regression-").toFile()
        val processes = mutableListOf<Process>()
        fun start(config: org.json.JSONObject, name: String): Process {
            val file = File(directory, "$name.json").apply { writeText(config.toString()) }
            return ProcessBuilder(core.path, "run", "-c", file.path)
                .redirectOutput(File(directory, "$name.log")).redirectErrorStream(true).start().also { processes.add(it) }
        }
        try {
            val cert = HeldCertificate.Builder().commonName("hy.example.invalid").build()
            File(directory, "cert.pem").writeText(cert.certificatePem())
            File(directory, "key.pem").writeText(cert.privateKeyPkcs8Pem())
            val quicPort = DatagramSocket(0).use { it.localPort }
            start(obj("log" to obj("level" to "error"), "inbounds" to arr(obj(
                "type" to "hysteria2", "listen" to "127.0.0.1", "listen_port" to quicPort,
                "users" to arr(obj("password" to "test-auth")),
                "obfs" to obj("type" to "salamander", "password" to "test-obfs"),
                "tls" to obj("enabled" to true, "certificate_path" to File(directory, "cert.pem").path,
                    "key_path" to File(directory, "key.pem").path))),
                "outbounds" to arr(obj("type" to "direct"))), "upstream")
            MockWebServer().use { web ->
                web.start(InetAddress.getByName("127.0.0.1"), 0)
                web.enqueue(MockResponse().setBody("through-real-hysteria2"))
                web.enqueue(MockResponse().setBody("through-real-hysteria2"))
                for ((password, compatibility) in listOf("test-auth" to false, "test-auth" to true, "wrong-auth" to true)) {
                    val socksPort = ServerSocket(0).use { it.localPort }
                    val relay = if (restrictMtu) PacketRelay(quicPort) else null
                    val endpointPort = relay?.port ?: quicPort
                    val server = SubscriptionParser.parse("hy2://$password@hy.example.invalid:$endpointPort/?insecure=1&obfs=salamander&obfs-password=test-obfs").single()
                    val process = start(CoreConfig.build(server, socksPort, listOf("127.0.0.1"), compatibility), "$password-$compatibility")
                    val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
                    while (runCatching { Socket("127.0.0.1", socksPort).close() }.isFailure) {
                        check(process.isAlive && System.nanoTime() < deadline) { "Test core failed to start" }
                        Thread.sleep(30)
                    }
                    val client = OkHttpClient.Builder().proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", socksPort)))
                        .callTimeout(3, TimeUnit.SECONDS).build()
                    try {
                        val response = runCatching { client.newCall(okhttp3.Request.Builder().url(web.url("/")).build()).execute().use { it.body!!.string() } }
                        if (password == "test-auth" && (!restrictMtu || compatibility))
                            assertEquals("through-real-hysteria2", response.getOrThrow())
                        else assertTrue("Invalid auth or oversized QUIC packets must fail", response.isFailure)
                        if (restrictMtu && !compatibility) assertTrue("Baseline must hit the simulated MTU limit", relay!!.dropped > 0)
                        if (restrictMtu && compatibility) assertEquals("1200-byte QUIC + salamander must fit", 0, relay!!.dropped)
                    } finally {
                        client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown()
                        process.destroyForcibly().waitFor(3, TimeUnit.SECONDS)
                        relay?.close()
                    }
                }
            }
        } finally {
            processes.forEach { it.destroyForcibly().waitFor(3, TimeUnit.SECONDS) }
            directory.deleteRecursively()
        }
    }

    /** Limit client-to-server packets; preserve complete UDP datagrams and salamander framing. */
    private class PacketRelay(upstreamPort: Int) : Closeable {
        private val front = DatagramSocket(0, InetAddress.getByName("127.0.0.1"))
        private val back = DatagramSocket(0, InetAddress.getByName("127.0.0.1")).apply {
            connect(InetAddress.getByName("127.0.0.1"), upstreamPort)
        }
        val port = front.localPort
        @Volatile var dropped = 0
        @Volatile private var client: SocketAddress? = null
        init {
            thread(isDaemon = true) { runCatching {
                while (!front.isClosed) {
                    val packet = DatagramPacket(ByteArray(65535), 65535)
                    front.receive(packet); client = packet.socketAddress
                    if (packet.length > 1220) { dropped++; continue }
                    back.send(DatagramPacket(packet.data, packet.length))
                }
            } }
            thread(isDaemon = true) { runCatching {
                while (!back.isClosed) {
                    val packet = DatagramPacket(ByteArray(65535), 65535)
                    back.receive(packet)
                    client?.let { front.send(DatagramPacket(packet.data, packet.length, it)) }
                }
            } }
        }
        override fun close() { front.close(); back.close() }
    }
}
