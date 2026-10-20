// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class QuicRetryTest {
    private val server = SubscriptionParser.parse("hy2://testpassword@example.org:443?obfs=salamander&obfs-password=test-obfs").single()
    @Test fun mtuFailureRestartsOnceAndUsesOnlyVerifiedSecondVerdict() = runBlocking {
        val modes = mutableListOf<Boolean>()
        val result = QuicRetry.run(server, {}) { compatibility ->
            modes.add(compatibility)
            if (!compatibility) Result(server, Status.ERROR, totalMs = 200, detail = "quic: read udp: message too long")
            else Result(server, Status.OK, country = "PL", httpCode = 200, totalMs = 500, pingMs = 400)
        }
        assertEquals(listOf(false, true), modes)
        assertEquals(700L, result.totalMs)
        assertTrue(result.geminiAccessible)
        assertEquals(400L, result.pingMs)
    }
    @Test fun repeatedTimeoutIsStillTimeoutWithOnlyTwoAttempts() = runBlocking {
        var calls = 0
        val result = QuicRetry.run(server, {}) { calls++; Result(server, Status.TIMEOUT) }
        assertEquals(2, calls)
        assertEquals(Status.TIMEOUT, result.status)
        assertFalse(result.geminiAccessible)
    }
    @Test fun httpVerdictsAuthenticationErrorsAndOtherProtocolsDoNotRetry() = runBlocking {
        val cases = listOf(Result(server, Status.BLOCKED, httpCode = 200), Result(server, Status.RATE_LIMIT, httpCode = 429),
            Result(server, Status.ERROR, detail = "authentication failed"),
            Result(server.copy(protocol = "vless", engine = "xray"), Status.TIMEOUT))
        cases.forEach { first ->
            var calls = 0
            assertEquals(first, QuicRetry.run(first.server, {}) { calls++; first })
            assertEquals(1, calls)
        }
    }
    @Test fun cancellationDoesNotStartCompatibilityAttempt() = runBlocking {
        var calls = 0
        try {
            QuicRetry.run(server, {}) { calls++; throw CancellationException("cancelled") }
            fail("Cancellation must propagate")
        } catch (_: CancellationException) { assertEquals(1, calls) }
    }
    @Test fun nativeDiagnosticHasNoAnsiCodesOrCredentials() {
        val text = "\u001B[31mERROR\u001B[0m read: message too long password=testpassword obfs=test-obfs"
        assertEquals("ERROR read: message too long password=*** obfs=***", CoreDiagnostics.clean(text, server))
        assertEquals("ERROR", CoreDiagnostics.clean("ERROR", server.copy(raw = "", user = "", password = "")))
    }
}
