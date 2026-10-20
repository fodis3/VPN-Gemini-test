// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import org.json.JSONTokener

/** Decode the vXmutd value itself; never guess a country from adjacent bootstrap fields. */
object GeminiCountry {
    private val field = Regex("""["']vXmutd["']\s*:\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")
    private val firstField = Regex("""^\s*\[?\s*["']([A-Z]{2})["']\s*(?:,|]|$)""")
    fun extract(html: String): String {
        val at = html.indexOf("vXmutd")
        if (at < 0) return ""
        // Google currently encodes a serialized proto in a JSON string:
        // "vXmutd":"%.@.\"US\",\"...\",\"...\"]"
        var fragment = html.substring(maxOf(0, at - 12), minOf(html.length, at + 4096))
        repeat(3) {
            val match = field.find(fragment)
            if (match != null) {
                val value = runCatching { JSONTokener(match.groupValues[1]).nextValue() as? String }.getOrNull().orEmpty()
                val country = if (value.matches(Regex("[A-Z]{2}"))) value else {
                    val proto = value.removePrefix("%.@.")
                    firstField.find(proto)?.groupValues?.get(1).orEmpty()
                }
                return country.takeUnless { it in setOf("ZZ", "XX") }.orEmpty()
            }
            fragment = fragment.replace("\\\"", "\"").replace("\\'", "'")
        }
        return ""
    }
}
