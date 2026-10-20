package ru.vpngemini.android

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class GeminiCountryTest {
    // Sanitized structural examples from the two user-supplied proxy responses.
    // Neither credentials nor full Google bootstrap tokens are fixtures.
    private fun page(country: String): String = "<title>Google Gemini</title><script>window.WIZ_global_data=" +
        JSONObject().put("vXmutd", "%.@.\"$country\",\"XX\",\"placeholder==\"]").put("unused", false) +
        ";</script><script>BardChatUi geminiweb-pa</script>"

    @Test fun encodedProtoSeparatesWorkingAndBlockedResponses() {
        val working = GeminiResponse.classify(200, "https://gemini.google.com/app", page("US"))
        val blocked = GeminiResponse.classify(200, "https://gemini.google.com/app", page("RU"))
        assertEquals("US", working.country); assertEquals(Status.OK, working.status)
        assertEquals("RU", blocked.country); assertEquals(Status.BLOCKED, blocked.status)
    }
    @Test fun directAndUnicodeEscapedCountryValuesStillWork() {
        assertEquals("DE", GeminiCountry.extract("""{"vXmutd":"DE"}"""))
        assertEquals("US", GeminiCountry.extract("""{"vXmutd":"%.@.\u0022US\u0022,\u0022XX\u0022]"}"""))
    }
    @Test fun adjacentCodesNeverReplaceAMissingCountry() {
        listOf("""{"vXmutd":null,"other":"US"}""", """{"vXmutd":"","other":"US"}""",
            """{"vXmutd":"%.@.null,\"US\"]","other":"DE"}""").forEach { assertEquals("", GeminiCountry.extract(it)) }
    }
    @Test fun unknownPlaceholderAndMalformedValuesFailClosed() {
        assertEquals("", GeminiCountry.extract(page("ZZ")))
        assertEquals("", GeminiCountry.extract("vXmutd malformed US"))
        assertEquals(Status.UNKNOWN, GeminiResponse.classify(200, "https://gemini.google.com/app", "BardChatUi geminiweb-pa").status)
    }
    @Test fun rawHtmlAndUnparsedRegionCannotInflateGoodCounter() {
        val server = Server(name = "Test", protocol = "vless", raw = "")
        val bogus = (1..20).map { Result(server, Status.OK, httpCode = 200) }
        assertEquals(0, UiState(results = bogus).good)
        assertEquals(1, UiState(results = bogus.mapIndexed { i, result -> result.copy(country = if (i == 0) "US" else "") }).good)
    }
}
