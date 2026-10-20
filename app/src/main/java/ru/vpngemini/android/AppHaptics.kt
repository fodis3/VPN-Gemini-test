// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

import android.os.SystemClock
import android.view.View
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalView
import androidx.core.view.HapticFeedbackConstantsCompat
import androidx.core.view.ViewCompat

/** System-tuned effects respect Android's touch feedback setting and the device motor. */
class AppHaptics(private val view: View, private val enabled: () -> Boolean) {
    private var lastFeedback = -100L
    fun tick() = perform(HapticFeedbackConstantsCompat.SEGMENT_TICK)
    fun fineTick() = perform(HapticFeedbackConstantsCompat.SEGMENT_FREQUENT_TICK)
    fun confirm() = perform(HapticFeedbackConstantsCompat.CONFIRM)
    private fun perform(effect: Int) {
        val now = SystemClock.uptimeMillis()
        if (!enabled() || now - lastFeedback < 45L) return
        lastFeedback = now
        ViewCompat.performHapticFeedback(view, effect)
    }
}

val LocalAppHaptics = staticCompositionLocalOf<AppHaptics> { error("Haptics provider missing") }

@Composable
fun ProvideAppHaptics(enabled: Boolean, content: @Composable () -> Unit) {
    val view = LocalView.current
    val currentEnabled = rememberUpdatedState(enabled)
    val feedback = remember(view) { AppHaptics(view) { currentEnabled.value } }
    CompositionLocalProvider(LocalAppHaptics provides feedback, content = content)
}
