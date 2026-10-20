// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.io.Closeable
import java.io.DataInputStream
import java.net.*
import java.util.Collections
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class GeminiNetworkTest {
    @Test fun tcpSuccessCannotReplaceGeminiHttpsCheck() = runBlocking {
        val cert = HeldCertificate.Builder().commonName("gemini.google.com").addSubjectAlternativeName("gemini.google.com").build()
        val serverTls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        MockWebServer().use { web ->
            web.useHttps(serverTls.sslSocketFactory(), false)
            web.protocols = listOf(Protocol.HTTP_1_1)
            web.start()
            SocksRelay(web.port, 180).use { socks ->
                val ping = SocksAcknowledgement.measure(socks.port, 3)
                assertTrue(ping >= 0)
                val latency = TunnelLatency()
                val client = OkHttpClient.Builder().proxy(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", socks.port))).eventListener(latency)
                    .sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager).protocols(listOf(Protocol.HTTP_1_1))
                    .callTimeout(5, TimeUnit.SECONDS).build()
                try {
                    web.enqueue(MockResponse().setChunkedBody("<title>Gemini</title>{\"vXmutd\":\"DE\"} BardChatUi geminiweb-pa", 5))
                    val available = GeminiPage.fetch(client)
                    assertEquals(Status.OK, available.verdict.status)
                    assertTrue("TLS measurement must include the remote connection delay, not local SOCKS ACK", latency.millis!! >= 150)
                    assertEquals("DE", available.verdict.country)
                    assertTrue(available.bytes > 20)
                    assertEquals("/app", web.takeRequest(3, TimeUnit.SECONDS)!!.path)
                    // TCP remains reachable, but an explicit Gemini restriction must change the verdict.
                    web.enqueue(MockResponse().setBody("Gemini isn't currently supported in your country"))
                    assertEquals(Status.BLOCKED, GeminiPage.fetch(client).verdict.status)
                    web.enqueue(MockResponse().setResponseCode(429).setBody("Try again later"))
                    assertEquals(Status.RATE_LIMIT, GeminiPage.fetch(client).verdict.status)
                    assertEquals("gemini.google.com:443", socks.destinations.poll(3, TimeUnit.SECONDS))
                    assertEquals("gemini.google.com:443", socks.destinations.poll(3, TimeUnit.SECONDS))
                } finally { client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
            }
        }
    }

    private class SocksRelay(private val upstreamPort: Int, private val upstreamDelay: Long = 0) : Closeable {
        private val server = ServerSocket(0, 20, InetAddress.getByName("127.0.0.1"))
        val port = server.localPort
        val destinations = LinkedBlockingQueue<String>()
        private val sockets = Collections.synchronizedList(mutableListOf<Socket>())
        init {
            thread(isDaemon = true) {
                var number = 0
                while (!server.isClosed) {
                    val socket = runCatching { server.accept() }.getOrNull() ?: break
                    sockets.add(socket)
                    val pingOnly = number++ == 0
                    thread(isDaemon = true) { runCatching {
                        socket.soTimeout = 5000
                        val input = DataInputStream(socket.getInputStream())
                        check(input.readUnsignedByte() == 5)
                        input.readFully(ByteArray(input.readUnsignedByte()))
                        val output = socket.getOutputStream()
                        output.write(5); output.flush(); output.write(0); output.flush()
                        val header = ByteArray(4); input.readFully(header)
                        check(header[3].toInt() == 3)
                        val name = ByteArray(input.readUnsignedByte()); input.readFully(name)
                        val remotePort = input.readUnsignedShort()
                        destinations.put("${String(name, Charsets.US_ASCII)}:$remotePort")
                        byteArrayOf(5, 0, 0, 1, 127, 0, 0, 1, 0, 0).forEach { output.write(it.toInt()); output.flush() }
                        if (!pingOnly) {
                        if (upstreamDelay > 0) Thread.sleep(upstreamDelay)
                        Socket("127.0.0.1", upstreamPort).use { remote ->
                            sockets.add(remote)
                            thread(isDaemon = true) { runCatching { input.copyTo(remote.getOutputStream()) }; runCatching { remote.shutdownOutput() } }
                            remote.getInputStream().copyTo(output)
                        }
                        }
                    }; socket.close() }
                }
            }
        }
        override fun close() { server.close(); synchronized(sockets) { sockets.forEach { runCatching { it.close() } } } }
    }
}
