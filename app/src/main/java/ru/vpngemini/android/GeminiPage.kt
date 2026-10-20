package ru.vpngemini.android

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import okhttp3.OkHttpClient
import okhttp3.Request

object GeminiPage {
    // Same web endpoint and browser profile as the desktop tester.
    const val USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    data class Page(val verdict: GeminiResponse.Verdict, val http: Int, val url: String, val bytes: Long)
    suspend fun fetch(client: OkHttpClient): Page {
        val request = Request.Builder().url("https://gemini.google.com/app").header("User-Agent", USER_AGENT)
            .header("Accept-Language", "en-US,en;q=0.9").header("Cache-Control", "no-cache").build()
        return client.newCall(request).await().use { response ->
            val body = response.body ?: error("Пустой HTTP-ответ Gemini")
            val source = body.source()
            val max = 8L * 1024 * 1024
            source.request(max + 1)
            check(source.buffer.size <= max) { "Ответ Gemini превышает 8 МБ" }
            val data = source.readByteArray()
            currentCoroutineContext().ensureActive()
            val html = String(data, body.contentType()?.charset(Charsets.UTF_8) ?: Charsets.UTF_8)
            Page(GeminiResponse.classify(response.code, response.request.url.toString(), html), response.code, response.request.url.toString(), data.size.toLong())
        }
    }
}
