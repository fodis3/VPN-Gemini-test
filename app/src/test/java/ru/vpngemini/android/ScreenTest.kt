package ru.vpngemini.android

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.SemanticsActions
import org.junit.Assert.*
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.semantics.ProgressBarRangeInfo

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "ru-rRU-w412dp-h915dp-420dpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ScreenTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun navigationImportSettingsAndScreenshots() {
        compose.runOnIdle { (compose.activity.application as GeminiApp).store.settings(Settings(dynamicColors = false)) }
        compose.onNodeWithText("Проверим связь").assertIsDisplayed()
        capture("home-light")
        compose.onNodeWithText("Добавить серверы").performScrollTo().performClick()
        compose.onNodeWithText("Сгенерировать HWID").performClick()
        val hwidField = compose.onNode(hasSetTextAction() and hasText("HWID, если требуется"))
        val firstHwid = hwidField.fetchSemanticsNode().config[SemanticsProperties.EditableText].text
        assertTrue(firstHwid.matches(Regex("[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}")))
        compose.onNodeWithText("Сгенерировать HWID").performClick()
        assertNotEquals(firstHwid, hwidField.fetchSemanticsNode().config[SemanticsProperties.EditableText].text)
        compose.onNodeWithText("Конфигурации").performClick()
        compose.onNodeWithText("Ссылки, Base64 или JSON").performTextInput("vless://00000000-0000-4000-8000-000000000001@example.org:443?security=tls#Test")
        compose.onNodeWithText("Импортировать").performClick()
        compose.onAllNodesWithText("Результаты").onLast().performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("Test").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("Test").assertIsDisplayed()
        capture("results")
        compose.onNodeWithText("Test").performClick()
        compose.onNodeWithText("Копировать конфигурацию").assertExists()
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitForIdle()
        compose.onNodeWithText("Настройки").performClick()
        compose.onNodeWithText("Параллельные серверы").assertIsDisplayed()
        compose.onNodeWithText("Тёмная").performScrollTo().performClick()
        capture("settings-dark")
    }
    @Test fun tabsAnimateInBothDirectionsAndBackReturnsHome() {
        compose.onNodeWithText("Проверим связь").assertIsDisplayed()
        compose.mainClock.autoAdvance = false
        compose.onNodeWithText("Настройки").performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.waitUntil(5000) {
            compose.mainClock.advanceTimeByFrame()
            compose.onAllNodesWithTag("page-3").fetchSemanticsNodes().isNotEmpty()
        }
        compose.mainClock.advanceTimeBy(64)
        assertTrue("Next tab must enter from the right", compose.onNodeWithTag("page-3").getUnclippedBoundsInRoot().left.value > 0f)
        compose.mainClock.advanceTimeBy(1500)
        compose.onNode(hasText("Проверка") and hasClickAction()).performSemanticsAction(SemanticsActions.OnClick) { it() }
        compose.waitUntil(5000) {
            compose.mainClock.advanceTimeByFrame()
            compose.onAllNodesWithTag("page-0").fetchSemanticsNodes().isNotEmpty()
        }
        compose.mainClock.advanceTimeBy(64)
        assertTrue("Previous tab must enter from the left", compose.onNodeWithTag("page-0").getUnclippedBoundsInRoot().left.value < 0f)
        compose.mainClock.advanceTimeBy(1500)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithText("Настройки").performClick()
        compose.onNodeWithText("Параллельные серверы").assertIsDisplayed()
        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitUntil(5000) { runCatching { compose.onNodeWithText("Проверим связь").assertIsDisplayed() }.isSuccess }
    }
    @Test fun failedSubscriptionKeepsFormAndShowsReason() {
        compose.onNodeWithText("Добавить серверы").performScrollTo().performClick()
        val field = compose.onNode(hasSetTextAction() and hasText("HTTPS-ссылка подписки"))
        field.performTextInput("http://example.invalid/subscription")
        compose.onNodeWithText("Загрузить подписку").performScrollTo().performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("Укажите HTTPS-ссылку подписки").fetchSemanticsNodes().isNotEmpty() }
        field.assertTextContains("http://example.invalid/subscription")
        compose.onNodeWithText("Загрузить подписку").assertIsEnabled()
    }
    @Test fun wavyProgressTracksCompletedChecksAndFinishesAtOne() {
        val servers = (1..20).map { Server(name = "Test $it", protocol = "vless", raw = "") }
        fun state(done: Int) = UiState(running = true, results = servers.mapIndexed { index, server ->
            Result(server, if (index < done) Status.OK else Status.PENDING, country = if (index < done) "DE" else "", httpCode = if (index < done) 200 else null)
        })
        val display = mutableStateOf(state(10))
        compose.activityRule.scenario.onActivity { activity -> activity.setContent {
            GeminiTheme(Settings(dynamicColors = false)) { GeminiScreen(display.value, (activity.application as GeminiApp).store) }
        } }
        compose.onNodeWithTag("check-progress").assertRangeInfoEquals(ProgressBarRangeInfo(.5f, 0f..1f))
        capture("progress-50")
        compose.runOnIdle { display.value = state(19) }
        compose.onNodeWithTag("check-progress").assertRangeInfoEquals(ProgressBarRangeInfo(.95f, 0f..1f))
        capture("progress-95")
        compose.runOnIdle { display.value = state(20) }
        compose.onNodeWithTag("check-progress").assertRangeInfoEquals(ProgressBarRangeInfo(1f, 0f..1f))
    }
    private fun capture(name: String) {
        compose.waitForIdle()
        val directory = File("build/screenshots").apply { mkdirs() }
        compose.runOnIdle {
            val view = compose.activity.window.decorView
            val bitmap = android.graphics.Bitmap.createBitmap(view.width, view.height, android.graphics.Bitmap.Config.ARGB_8888)
            view.draw(android.graphics.Canvas(bitmap))
            File(directory, "$name.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        }
    }
}
