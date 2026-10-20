package ru.vpngemini.android

import okhttp3.Call
import okhttp3.EventListener
import okhttp3.Handshake
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.concurrent.atomic.AtomicLong

/** SOCKS can acknowledge CONNECT optimistically. Only a verified remote TLS handshake counts. */
class TunnelLatency : EventListener() {
    private val started = AtomicLong(0)
    private val finished = AtomicLong(0)
    override fun connectStart(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy) {
        started.compareAndSet(0, System.nanoTime())
    }
    override fun secureConnectEnd(call: Call, handshake: Handshake?) {
        val start = started.get()
        if (handshake != null && start > 0) finished.compareAndSet(0, System.nanoTime() - start)
    }
    val millis: Long? get() = finished.get().takeIf { it > 0 }?.let { (it + 999_999) / 1_000_000 }
}
