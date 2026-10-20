// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import java.io.DataInputStream
import java.net.InetSocketAddress
import java.net.Socket

/** Negative-control diagnostic only: a local SOCKS ACK does not prove a remote connection. */
object SocksAcknowledgement {
    fun measure(port: Int, timeoutSeconds: Int): Long = Socket().use { socket ->
        socket.soTimeout = timeoutSeconds * 1000
        socket.connect(InetSocketAddress("127.0.0.1", port), timeoutSeconds * 1000)
        val input = DataInputStream(socket.getInputStream())
        val output = socket.getOutputStream()
        output.write(byteArrayOf(5, 1, 0)); output.flush()
        check(input.readUnsignedByte() == 5 && input.readUnsignedByte() == 0) { "SOCKS5 отклонил соединение" }
        val domain = "gemini.google.com".toByteArray(Charsets.US_ASCII)
        val start = System.nanoTime()
        output.write(byteArrayOf(5, 1, 0, 3, domain.size.toByte()) + domain + byteArrayOf(1, 187.toByte())); output.flush()
        check(input.readUnsignedByte() == 5) { "Некорректный ответ SOCKS5" }
        val reply = input.readUnsignedByte()
        input.readUnsignedByte()
        val size = when (input.readUnsignedByte()) { 1 -> 4; 4 -> 16; 3 -> input.readUnsignedByte(); else -> error("Неверный адрес SOCKS5") }
        input.readFully(ByteArray(size + 2))
        check(reply == 0) { "SOCKS5 отклонил запрос: код $reply" }
        (System.nanoTime() - start) / 1_000_000
    }
}
