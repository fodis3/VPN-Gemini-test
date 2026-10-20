package ru.vpngemini.android

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.*
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.*

class CheckService : Service() {
    private val store get() = (application as GeminiApp).store
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var wakeLock: PowerManager.WakeLock? = null
    override fun onBind(intent: Intent?) = null
    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel("checks", "Проверка серверов", NotificationManager.IMPORTANCE_LOW))
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "STOP") { store.stop(); stopSelf(); return START_NOT_STICKY }
        if (store.state.value.running) return START_NOT_STICKY
        ServiceCompat.startForeground(this, 4, notification("Подготовка проверки…"),
            if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0)
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VPNGemini:check").apply { acquire(60 * 60 * 1000L) }
        store.start(intent?.getBooleanExtra("direct", false) ?: false) { Handler(Looper.getMainLooper()).post { stopSelf() } }
        scope.launch { store.state.collect { state ->
            if (state.running) getSystemService(NotificationManager::class.java).notify(4, notification("${state.completed} из ${state.results.size} · доступно ${state.good}"))
        } }
        return START_NOT_STICKY
    }
    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, CheckService::class.java).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, "checks").setSmallIcon(R.drawable.ic_notification).setContentTitle("VPN Gemini · проверка")
            .setContentText(text).setContentIntent(open).setOngoing(true).addAction(0, "Остановить", stop).build()
    }
    override fun onTimeout(startId: Int, fgsType: Int) { store.stop(); stopSelf() }
    override fun onDestroy() {
        if (store.state.value.running) store.stop()
        scope.cancel(); wakeLock?.let { if (it.isHeld) it.release() }; wakeLock = null
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
