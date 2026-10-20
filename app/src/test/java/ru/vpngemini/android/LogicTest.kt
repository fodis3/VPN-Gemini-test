// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import org.junit.Assert.*
import org.junit.Test
import java.util.Base64

class LogicTest {
    private val id = "00000000-0000-4000-8000-000000000001"
    private fun encode(s: String) = Base64.getEncoder().withoutPadding().encodeToString(s.toByteArray())
    @Test fun allEightyRecordsSurviveBase64IncludingUnsupported() {
        val lines = (1..75).map { "vless://$id@example.org:443?security=tls#Server$it" } +
            (76..80).map { "unsupported://token@example.org:443#Server$it" }
        val parsed = SubscriptionParser.parse(encode(lines.joinToString("\n")))
        assertEquals(80, parsed.size)
        assertEquals(5, parsed.count { it.error.isNotEmpty() })
    }
    @Test fun brokenLinesAndDuplicatesArePreserved() {
        val uri = "vless://$id@example.org:443"
        val parsed = SubscriptionParser.parse("$uri\n$uri\ninvalid-server")
        assertEquals(3, parsed.size)
        assertTrue(parsed.last().error.isNotBlank())
        assertNotEquals(parsed[0].id, parsed[1].id)
    }
    @Test fun vlessRealityXhttpRetainsTransportParameters() {
        val s = SubscriptionParser.parse("vless://$id@example.org:443?type=xhttp&security=reality&sni=example.com&pbk=public&sid=abcd&mode=packet-up&host=cdn.example.com&path=%2Fapi&extra=%7B%22noSSEHeader%22%3Atrue%7D&encryption=none#Test").single()
        val c = CoreConfig.build(s, 1080).getJSONArray("outbounds").getJSONObject(0)
        val stream = c.getJSONObject("streamSettings")
        assertEquals("public", stream.getJSONObject("realitySettings").getString("publicKey"))
        val x = stream.getJSONObject("xhttpSettings")
        assertEquals("/api", x.getString("path")); assertEquals("packet-up", x.getString("mode"))
        assertTrue(x.getJSONObject("extra").getBoolean("noSSEHeader"))
    }
    @Test fun shadowsocksBothEncodingsAndPlusPassword() {
        val u1 = "ss://${encode("aes-128-gcm:p+a:ss")}@example.org:8388#A"
        val u2 = "ss://${encode("aes-128-gcm:p+a:ss@example.org:8388")}#B"
        listOf(u1, u2).forEach {
            val s = SubscriptionParser.parse(it).single()
            assertEquals("p+a:ss", s.password)
            assertEquals("aes-128-gcm", s.params["method"])
        }
    }
    @Test fun hysteriaAndTuicUseSingboxWithVerifiedTlsByDefault() {
        val parsed = SubscriptionParser.parse("hy2://secret@example.org:443?obfs=salamander&obfs-password=other#HY\ntuic://$id:secret@example.org:443?congestion_control=cubic#TUIC")
        assertEquals(2, parsed.size)
        parsed.forEach { s ->
            assertEquals("singbox", s.engine)
            val out = CoreConfig.build(s, 1080).getJSONArray("outbounds").getJSONObject(0)
            assertFalse(out.getJSONObject("tls").getBoolean("insecure"))
        }
    }
    @Test fun singboxBootstrapUsesAndroidAddressesWithoutChangingSniOrCredentials() {
        val s = SubscriptionParser.parse("hysteria2://testpass@hy.example.invalid:25801/?insecure=1&obfs=salamander&obfs-password=test-obfs&sni=tls.example.invalid").single()
        val c = CoreConfig.build(s, 1080, listOf("192.0.2.1", "2001:db8::1"))
        val dns = c.getJSONObject("dns").getJSONArray("servers").getJSONObject(0)
        assertEquals("hosts", dns.getString("type"))
        assertEquals(2, dns.getJSONObject("predefined").getJSONArray(s.host).length())
        val out = c.getJSONArray("outbounds").getJSONObject(0)
        assertEquals(s.host, out.getString("server"))
        assertEquals("tls.example.invalid", out.getJSONObject("tls").getString("server_name"))
        assertTrue(out.getJSONObject("tls").getBoolean("insecure"))
        assertEquals("testpass", out.getString("password"))
        assertEquals("test-obfs", out.getJSONObject("obfs").getString("password"))
    }
    @Test fun jsonOutboundsRetainExtraSettings() {
        val s = SubscriptionParser.parse("""{"outbounds":[{"protocol":"vless","tag":"Keep","settings":{"vnext":[{"address":"example.org","port":443,"users":[{"id":"$id","encryption":"none"}]}]},"streamSettings":{"network":"xhttp","xhttpSettings":{"mode":"auto","extra":{"xmux":{"maxConcurrency":12}}}}},{"protocol":"freedom"}]}""").single()
        val out = CoreConfig.build(s, 1080).getJSONArray("outbounds").getJSONObject(0)
        assertEquals(12, out.getJSONObject("streamSettings").getJSONObject("xhttpSettings").getJSONObject("extra").getJSONObject("xmux").getInt("maxConcurrency"))
    }
    @Test fun countryExtractionDoesNotMatchNearbyRandomTwoLetterStrings() {
        assertEquals("", GeminiResponse.classify(200, "https://gemini.google.com/app", "vXmutd random US text").country)
        assertEquals("DE", GeminiResponse.classify(200, "https://gemini.google.com/app", "{\"vXmutd\":\"DE\"}").country)
    }
    @Test fun unknownPageIsNotBlockedOrAccessible() {
        val r = GeminiResponse.classify(200, "https://gemini.google.com/app", "<title>Gemini</title>unavailable field RU")
        assertEquals(Status.UNKNOWN, r.status)
    }
    @Test fun successfulHtmlAndPingDoNotOverrideUnsupportedGoogleRegion() {
        val html = """{"vXmutd":"RU"} BardChatUi geminiweb-pa"""
        assertEquals(Status.BLOCKED, GeminiResponse.classify(200, "https://gemini.google.com/app", html).status)
        assertEquals(Status.OK, GeminiResponse.classify(200, "https://gemini.google.com/app", html.replace("RU", "HK")).status)
        assertEquals(Status.LOGIN, GeminiResponse.classify(200, "https://gemini.google.com/app", html.replace("RU", "CN")).status)
    }
    @Test fun loginCaptchaRateLimitAndHttpErrorsAreDistinct() {
        assertEquals(Status.LOGIN, GeminiResponse.classify(200, "https://accounts.google.com/signin", "").status)
        assertEquals(Status.CAPTCHA, GeminiResponse.classify(200, "https://www.google.com/sorry/index", "").status)
        assertEquals(Status.RATE_LIMIT, GeminiResponse.classify(429, "https://gemini.google.com", "").status)
        assertEquals(Status.ERROR, GeminiResponse.classify(503, "https://gemini.google.com", "BardChatUi geminiweb-pa").status)
    }
    @Test fun pageMarkersAndExplicitGeoBannerHaveSeparateResults() {
        assertEquals(Status.UNKNOWN, GeminiResponse.classify(200, "https://gemini.google.com", "BardChatUi geminiweb-pa").status)
        assertEquals(Status.BLOCKED, GeminiResponse.classify(200, "https://gemini.google.com", "Gemini isn't currently supported in your country").status)
    }
    @Test fun generatedProfilesPassRealCoreConfigValidation() {
        val root = java.io.File("../..").canonicalFile
        org.junit.Assume.assumeTrue(java.io.File(root, "bin/xray.exe").exists())
        val vmess = encode("""{"v":"2","ps":"VMess","add":"example.org","port":"443","id":"$id","aid":"0","net":"ws","path":"/ws","tls":"tls"}""")
        val links = listOf("vless://$id@example.org:443?security=tls&type=grpc&serviceName=api",
            "trojan://testpassword@example.org:443?security=tls", "vmess://$vmess",
            "ss://${encode("aes-128-gcm:testpassword")}@example.org:8388",
            "hy2://testpassword@example.org:443", "tuic://$id:testpassword@example.org:443")
        links.forEach { uri ->
            val server = SubscriptionParser.parse(uri).single()
            val file = java.io.File.createTempFile("validate-core-", ".json")
            try {
                file.writeText(CoreConfig.build(server, 19999, listOf("192.0.2.1", "2001:db8::1"), true).toString())
                val core = java.io.File(root, if (server.engine == "xray") "bin/xray.exe" else "bin/sing-box.exe")
                val args = if (server.engine == "xray") listOf("run", "-test", "-c", file.path) else listOf("check", "-c", file.path)
                val process = ProcessBuilder(listOf(core.path) + args).redirectErrorStream(true).start()
                val output = process.inputStream.bufferedReader().readText()
                assertTrue("Core config validation timed out", process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS))
                assertEquals("${server.protocol}: $output", 0, process.exitValue())
            } finally { file.delete() }
        }
    }
}
