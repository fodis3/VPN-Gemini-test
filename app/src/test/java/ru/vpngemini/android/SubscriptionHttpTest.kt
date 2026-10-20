// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import org.junit.Assert.*
import org.junit.Test

class SubscriptionHttpTest {
    @Test fun hwidIsSentUsingBothDesktopAndHeaderContracts() {
        val request = SubscriptionHttp.request("https://example.org/sub", "TEST-HWID")
        assertEquals("TEST-HWID", request.header("x-hwid"))
        assertEquals("v2rayN/6.67 HWID/TEST-HWID", request.header("User-Agent"))
        assertEquals("Android", request.header("x-device-os"))
    }
    @Test fun cloudflare1002IsReportedAsServerDnsFailure() {
        val error = assertThrows(SubscriptionException::class.java) {
            SubscriptionHttp.validate(403, "<html>Cloudflare <h1>Error 1002</h1>DNS points to prohibited IP</html>")
        }
        assertTrue(error.message!!.contains("DNS"))
    }
    @Test fun providerErrorCodeIsNotImportedAsProxyConfig() {
        val error = assertThrows(SubscriptionException::class.java) {
            SubscriptionHttp.validate(200, """{"success":false,"code":1002,"message":"private URL https://example.org/secret-token"}""")
        }
        assertTrue(error.message!!.contains("1002")); assertFalse(error.message!!.contains("secret-token"))
    }
    @Test fun htmlChallengeIsNotImportedAsServers() {
        assertThrows(SubscriptionException::class.java) { SubscriptionHttp.validate(200, "<!DOCTYPE html><html>Just a moment</html>") }
    }
    @Test fun validSubscriptionIsPreservedAndBadHttpIsDistinct() {
        val text = "vless://key@example.org:443#Test"
        assertEquals(text, SubscriptionHttp.validate(200, text))
        assertTrue(assertThrows(SubscriptionException::class.java) { SubscriptionHttp.validate(429, "") }.message!!.contains("429"))
    }
}
