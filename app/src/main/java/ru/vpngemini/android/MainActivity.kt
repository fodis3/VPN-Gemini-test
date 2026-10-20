@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.material3.ExperimentalMaterial3ExpressiveApi::class)

package ru.vpngemini.android

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.automirrored.rounded.Notes
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val store = (application as GeminiApp).store
            val state by store.state.collectAsStateWithLifecycle()
            GeminiTheme(state.settings) { GeminiScreen(state, store) }
        }
    }
}

@Composable
fun GeminiTheme(settings: Settings, content: @Composable () -> Unit) {
    val dark = when (settings.theme) { 1 -> false; 2 -> true; else -> isSystemInDarkTheme() }
    val context = LocalContext.current
    val view = LocalView.current
    SideEffect {
        (view.context as? android.app.Activity)?.window?.let { window ->
            androidx.core.view.WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }
    val colors = when {
        settings.dynamicColors && Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> darkColorScheme(primary = Color(0xFFB4D787), onPrimary = Color(0xFF233600), primaryContainer = Color(0xFF354F13),
            onPrimaryContainer = Color(0xFFD0F3A1), secondary = Color(0xFFBECBAE), secondaryContainer = Color(0xFF3E4B34),
            tertiary = Color(0xFFD3BEF6), tertiaryContainer = Color(0xFF4D3D68), background = Color(0xFF10140D), surface = Color(0xFF10140D),
            surfaceContainer = Color(0xFF1C2118), surfaceContainerLow = Color(0xFF181D14), surfaceContainerHigh = Color(0xFF272C22))
        else -> lightColorScheme(primary = Color(0xFF426900), onPrimary = Color.White, primaryContainer = Color(0xFFC8EF99),
            onPrimaryContainer = Color(0xFF253C00), secondary = Color(0xFF536346), secondaryContainer = Color(0xFFD7E8C7),
            tertiary = Color(0xFF6B528F), tertiaryContainer = Color(0xFFECDCFF), background = Color(0xFFF7FAEF), surface = Color(0xFFF7FAEF),
            surfaceContainer = Color(0xFFEBEEE2), surfaceContainerLow = Color(0xFFF1F4E8), surfaceContainerHigh = Color(0xFFE5E9DC))
    }
    MaterialExpressiveTheme(colorScheme = colors, motionScheme = MotionScheme.expressive()) {
        ProvideAppHaptics(settings.haptics, content)
    }
}

private data class Destination(val title: String, val icon: ImageVector)
private val destinations = listOf(Destination("Проверка", Icons.Rounded.Shield), Destination("Результаты", Icons.Rounded.FactCheck),
    Destination("Журнал", Icons.AutoMirrored.Rounded.Notes), Destination("Настройки", Icons.Rounded.Tune))

private fun copy(context: Context, text: String) {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("VPN Gemini", text))
}

@Composable
fun GeminiScreen(state: UiState, store: AppStore) {
    var page by rememberSaveable { mutableIntStateOf(0) }
    var importOpen by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Result?>(null) }
    var clearOpen by remember { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val haptics = LocalAppHaptics.current
    fun navigate(index: Int) {
        if (page != index) { haptics.tick(); page = index }
    }
    fun openImport() { haptics.tick(); importOpen = true }
    BackHandler(enabled = page != 0 && !importOpen && selected == null && !clearOpen) { navigate(0) }
    val file = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) store.importFile(uri) }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        if (uri != null) scope.launch {
            val result = withContext(Dispatchers.IO) { runCatching { context.contentResolver.openOutputStream(uri)?.use { it.write(store.csv().toByteArray(Charsets.UTF_8)) } ?: error("Нет доступа к файлу") } }
            store.message(if (result.isSuccess) "CSV сохранён" else "Не удалось сохранить CSV")
        }
    }
    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    LaunchedEffect(state.message) {
        if (state.message.isNotEmpty()) { snackbar.showSnackbar(state.message); store.message("") }
    }
    LaunchedEffect(state.importRevision) { if (state.importRevision > 0) importOpen = false }
    fun start(direct: Boolean = false) {
        haptics.confirm()
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        store.requestStart(direct)
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) }, containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceContainerLow) {
                destinations.forEachIndexed { index, destination ->
                    NavigationBarItem(selected = page == index, onClick = { navigate(index) }, icon = {
                        if (index == 1 && state.results.isNotEmpty()) BadgedBox(badge = { Badge { Text(state.results.size.toString()) } }) {
                            Icon(destination.icon, destination.title)
                        } else Icon(destination.icon, destination.title)
                    }, label = { Text(destination.title, maxLines = 1) })
                }
            }
        },
    ) { insets ->
        Box(Modifier.padding(insets).fillMaxSize()) {
            AnimatedContent(targetState = page, transitionSpec = {
                val direction = if (targetState > initialState) 1 else -1
                (fadeIn(tween(220)) + slideInHorizontally(spring(dampingRatio = 1f, stiffness = 400f)) { direction * it / 5 }) togetherWith
                    (fadeOut(tween(140)) + slideOutHorizontally(spring(dampingRatio = 1f, stiffness = 400f)) { -direction * it / 5 })
            }, label = "navigation") { current ->
                Box(Modifier.fillMaxSize().testTag("page-$current")) {
                when (current) {
                    0 -> Home(state, ::openImport, { if (state.running) { haptics.tick(); store.stop() } else start() }, { start(true) }, { navigate(1) })
                    1 -> ResultsScreen(state, { haptics.tick(); selected = it }, ::openImport, { haptics.tick(); export.launch("vpn-gemini-results.csv") }, {
                        val keys = state.results.filter { it.geminiAccessible && it.server.raw.isNotBlank() }.joinToString("\n") { it.server.raw }
                        if (keys.isBlank()) store.message("Пока нет доступных конфигураций") else { haptics.confirm(); copy(context, keys); store.message("Доступные конфигурации скопированы") }
                    }, { haptics.tick(); clearOpen = true })
                    2 -> LogScreen(state, { haptics.confirm(); copy(context, state.logs.joinToString("\n")); store.message("Журнал скопирован") }, { haptics.tick(); store.clearLogs() })
                    else -> SettingsScreen(state.settings, store::settings)
                }
                }
            }
        }
    }
    if (importOpen) ImportSheet(state.importing, state.importError, { importOpen = false }, { text -> store.importText(text); importOpen = false },
        { url, hwid -> store.subscription(url, hwid) }, { file.launch(arrayOf("text/*", "application/json", "application/octet-stream")); importOpen = false })
    selected?.let { entry -> ResultSheet(state.results.find { it.server.id == entry.server.id } ?: entry, { selected = null }, { text -> haptics.confirm(); copy(context, text); store.message("Конфигурация скопирована") }) }
    if (clearOpen) AlertDialog(onDismissRequest = { clearOpen = false }, title = { Text("Очистить список?") },
        text = { Text("Все импортированные конфигурации и результаты будут удалены из текущего сеанса.") },
        confirmButton = { TextButton(onClick = { haptics.confirm(); store.clear(); clearOpen = false }) { Text("Очистить") } },
        dismissButton = { TextButton(onClick = { clearOpen = false }) { Text("Отмена") } })
}

@Composable
private fun PageHeader(eyebrow: String, title: String, action: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(eyebrow, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(title, style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
        }
        action()
    }
}

@Composable
private fun Home(state: UiState, add: () -> Unit, start: () -> Unit, direct: () -> Unit, results: () -> Unit) {
    val busy = state.running || state.importing
    val finished = state.results.count { it.status !in listOf(Status.PENDING, Status.TESTING, Status.CANCELLED) }
    val progress by animateFloatAsState(if (state.results.isEmpty()) 0f else finished.toFloat() / state.results.size, spring(), label = "progress")
    var showProgress by remember { mutableStateOf(state.running) }
    LaunchedEffect(state.running) {
        if (state.running) showProgress = true else { kotlinx.coroutines.delay(550); showProgress = false }
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeader("VPN GEMINI  /  4.0", "Проверим связь") { Icon(Icons.Rounded.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp)) } }
        item {
            Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(36.dp), modifier = Modifier.fillMaxWidth().animateContentSize()) {
                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = .08f), shape = CircleShape) {
                            if (busy) LoadingIndicator(Modifier.size(64.dp)) else Box(Modifier.size(64.dp), contentAlignment = Alignment.Center) { Icon(Icons.Rounded.Shield, null, Modifier.size(32.dp)) }
                        }
                        Spacer(Modifier.weight(1f))
                        Surface(color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = .08f), shape = CircleShape) {
                            Text(if (state.running) "ПРОВЕРЯЕМ" else "GEMINI", Modifier.padding(horizontal = 14.dp, vertical = 8.dp), style = MaterialTheme.typography.labelMedium)
                        }
                    }
                    Text(when { state.importing -> "Загружаем\nконфигурации"; state.running -> "Ищем путь\nк Gemini"; else -> "Твой маршрут\nк Gemini" },
                        fontSize = 36.sp, lineHeight = 40.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    Text(if (state.running) "${state.completed} из ${state.results.size} проверено" else "Добавь серверы и узнай, какие из них открывают Gemini.",
                        style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    AnimatedVisibility(showProgress) {
                        LinearWavyProgressIndicator(progress = { progress.coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth().height(16.dp).testTag("check-progress"),
                            color = MaterialTheme.colorScheme.onPrimaryContainer, trackColor = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = .15f))
                    }
                    Button(onClick = start, enabled = !state.importing && (state.running || state.results.isNotEmpty()),
                        shapes = ButtonDefaults.shapes(), modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp), contentPadding = PaddingValues(20.dp)) {
                        Icon(if (state.running) Icons.Rounded.Stop else Icons.Rounded.PlayArrow, null, Modifier.size(26.dp))
                        Spacer(Modifier.width(10.dp))
                        Text(if (state.running) "Остановить" else "Начать проверку", style = MaterialTheme.typography.titleMedium)
                    }
                }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Stat(state.results.size.toString(), "серверов", MaterialTheme.colorScheme.surfaceContainer, Modifier.weight(1f))
                Stat(state.good.toString(), "доступно", MaterialTheme.colorScheme.secondaryContainer, Modifier.weight(1f))
                Stat(state.results.count { it.status in listOf(Status.ERROR, Status.TIMEOUT, Status.UNKNOWN) }.toString(), "проверить", MaterialTheme.colorScheme.tertiaryContainer, Modifier.weight(1f))
            }
        }
        item {
            Surface(onClick = add, enabled = !busy, shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh) {
                Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.AddLink, null, Modifier.size(28.dp), tint = MaterialTheme.colorScheme.primary)
                    Column(Modifier.weight(1f).padding(horizontal = 16.dp)) { Text("Добавить серверы", style = MaterialTheme.typography.titleMedium); Text("Подписка, файл или конфигурации", style = MaterialTheme.typography.bodySmall) }
                    Icon(Icons.Rounded.Add, null)
                }
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = direct, enabled = !busy, modifier = Modifier.weight(1f)) { Icon(Icons.Rounded.Wifi, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Без VPN") }
                FilledTonalButton(onClick = results, modifier = Modifier.weight(1f)) { Text("Результаты"); Spacer(Modifier.width(6.dp)); Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, Modifier.size(18.dp)) }
            }
        }
        item { Text("Gemini проверяется как на компьютере: HTTPS-ответ, регион Google и признаки ограничения. Проверка работает и в фоне.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 4.dp, vertical = 4.dp)) }
    }
}

@Composable
private fun Stat(value: String, label: String, color: Color, modifier: Modifier) {
    Surface(color = color, shape = RoundedCornerShape(24.dp), modifier = modifier) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.labelMedium, maxLines = 1)
        }
    }
}

@Composable
private fun statusColor(status: Status) = when (status) {
    Status.OK -> MaterialTheme.colorScheme.primary
    Status.ERROR, Status.BLOCKED, Status.TIMEOUT -> MaterialTheme.colorScheme.error
    else -> MaterialTheme.colorScheme.tertiary
}

@Composable
private fun ResultsScreen(state: UiState, select: (Result) -> Unit, add: () -> Unit, export: () -> Unit, copyGood: () -> Unit, clear: () -> Unit) {
    val haptics = LocalAppHaptics.current
    var query by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableIntStateOf(0) }
    var sort by rememberSaveable { mutableIntStateOf(0) }
    var menu by remember { mutableStateOf(false) }
    val filtered = remember(state.results, query, filter, sort) {
        val list = state.results.filter { r -> (query.isBlank() || "${r.server.name} ${r.server.protocol} ${r.country} ${r.status.label}".contains(query, true)) && when (filter) {
            1 -> r.geminiAccessible; 2 -> r.status in listOf(Status.ERROR, Status.TIMEOUT, Status.BLOCKED); 3 -> r.status in listOf(Status.UNKNOWN, Status.LOGIN, Status.CAPTCHA, Status.RATE_LIMIT); else -> true
        } }
        when (sort) { 1 -> list.sortedBy { it.pingMs ?: Long.MAX_VALUE }; 2 -> list.sortedBy { it.server.name.lowercase() }; else -> list }
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        PageHeader("ТВОИ МАРШРУТЫ", "Результаты") {
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Rounded.MoreVert, "Действия с результатами") }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("По порядку импорта") }, onClick = { sort = 0; menu = false })
                    DropdownMenuItem(text = { Text("Сначала быстрые") }, onClick = { sort = 1; menu = false }, leadingIcon = { Icon(Icons.Rounded.Speed, null) })
                    DropdownMenuItem(text = { Text("По названию") }, onClick = { sort = 2; menu = false })
                    HorizontalDivider()
                    DropdownMenuItem(text = { Text("Экспорт CSV") }, onClick = { export(); menu = false }, leadingIcon = { Icon(Icons.Rounded.FileDownload, null) })
                    DropdownMenuItem(text = { Text("Копировать доступные") }, onClick = { copyGood(); menu = false }, leadingIcon = { Icon(Icons.Rounded.ContentCopy, null) })
                    DropdownMenuItem(text = { Text("Очистить список") }, enabled = !state.running && !state.importing, onClick = { clear(); menu = false }, leadingIcon = { Icon(Icons.Rounded.DeleteOutline, null) })
                }
            }
        }
        OutlinedTextField(value = query, onValueChange = { query = it }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("Найти сервер или страну") },
            leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true, shape = CircleShape)
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Все ${state.results.size}", "Доступны ${state.good}", "Ошибки", "Не определено").forEachIndexed { index, title ->
                FilterChip(selected = filter == index, onClick = { if (filter != index) { haptics.tick(); filter = index } }, label = { Text(title) })
            }
        }
        if (filtered.isEmpty()) {
            Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Icon(Icons.Rounded.TravelExplore, null, Modifier.size(64.dp), tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(20.dp)); Text(if (state.results.isEmpty()) "Здесь будут твои серверы" else "Ничего не найдено", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(16.dp)); FilledTonalButton(onClick = add, enabled = !state.running && !state.importing) { Text("Добавить серверы") }
            }
        } else LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(bottom = 16.dp)) {
            items(filtered, key = { it.server.id }) { result ->
                Surface(onClick = { select(result) }, color = MaterialTheme.colorScheme.surfaceContainerLow, shape = RoundedCornerShape(24.dp), modifier = Modifier.animateItem()) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Surface(color = statusColor(result.status).copy(alpha = .12f), shape = CircleShape) {
                                if (result.status == Status.TESTING) LoadingIndicator(Modifier.size(44.dp))
                                else Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
                                    Icon(when (result.status) { Status.OK -> Icons.Rounded.Check; Status.ERROR, Status.TIMEOUT, Status.BLOCKED -> Icons.Rounded.PriorityHigh; Status.PENDING -> Icons.Rounded.Schedule; else -> Icons.Rounded.QuestionMark }, null, tint = statusColor(result.status))
                                }
                            }
                            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                                Text(result.server.name, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("Gemini · ${result.status.label}", style = MaterialTheme.typography.bodySmall, color = statusColor(result.status))
                            }
                            Icon(Icons.Rounded.ChevronRight, "Подробнее", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Metric(result.server.protocol.uppercase(), "протокол")
                            Metric(result.country.ifBlank { "—" }, "страна")
                            Metric(result.pingMs?.let { "$it мс" } ?: "—", "TLS-время")
                            Metric(if (result.totalMs > 0) "%.1f с".format(result.totalMs / 1000f) else "—", "время")
                        }
                        if (result.pingMs != null || result.httpCode != null) Text(
                            "TLS: ${if (result.pingMs != null) "есть" else "—"} · HTML: " +
                                (result.httpCode?.let { "HTTP $it" } ?: "—") + " · Регион Google: ${result.country.ifBlank { "—" }}",
                            style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun Metric(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.labelLarge)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ResultSheet(result: Result, close: () -> Unit, copy: (String) -> Unit) {
    ModalBottomSheet(onDismissRequest = close) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(result.server.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(result.status.label, color = statusColor(result.status), style = MaterialTheme.typography.titleMedium)
            SelectionContainer { Text(result.detail.ifBlank { "Результат появится после проверки" }) }
            Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh) {
                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${result.server.protocol.uppercase()} · ${result.server.engine}", style = MaterialTheme.typography.titleSmall)
                    if (result.server.host.isNotBlank()) Text("${result.server.host}:${result.server.port}", style = MaterialTheme.typography.bodySmall)
                    Text("Страна по Google: ${result.country.ifBlank { "не определена" }}")
                    Text("Соединение с Gemini до завершения TLS: ${result.pingMs?.let { "$it мс" } ?: "—"}")
                    Text("Алгоритм: ответ Gemini + регион Google, как в настольной версии")
                    Text("Полное время: ${result.totalMs} мс")
                    if (result.httpCode != null) {
                        Text("HTTP ${result.httpCode} · ${result.bytes} байт")
                        Text("URL HTTPS-ответа:", style = MaterialTheme.typography.labelSmall)
                        SelectionContainer { Text(result.finalUrl, style = MaterialTheme.typography.bodySmall) }
                        if (result.title.isNotBlank()) Text(result.title, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Text("Как на компьютере, проверяются HTTP-ответ Gemini и регион Google. Вход в аккаунт и генерация ответа не тестируются. «Не определён» означает, что данных ответа недостаточно для вывода.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (result.server.raw.isNotBlank()) FilledTonalButton(onClick = { copy(result.server.raw) }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Rounded.ContentCopy, null); Spacer(Modifier.width(10.dp)); Text("Копировать конфигурацию") }
        }
    }
}

@Composable
private fun ImportSheet(busy: Boolean, error: String, close: () -> Unit, text: (String) -> Unit, subscription: (String, String) -> Unit, file: () -> Unit) {
    val haptics = LocalAppHaptics.current
    var tab by remember { mutableIntStateOf(0) }
    // Credentials intentionally do not enter SavedState, preferences or backups.
    var value by remember { mutableStateOf("") }
    var hwid by remember { mutableStateOf("") }
    var showHwid by remember { mutableStateOf(false) }
    val keyboardOpen = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    ModalBottomSheet(onDismissRequest = close, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.fillMaxWidth().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Добавить серверы", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = tab == 0, onClick = { if (tab != 0) { haptics.tick(); tab = 0 } }, label = { Text("Подписка") })
                FilterChip(selected = tab == 1, onClick = { if (tab != 1) { haptics.tick(); tab = 1 } }, label = { Text("Конфигурации") })
            }
            if (tab == 0) {
                OutlinedTextField(value, { value = it }, enabled = !busy, label = { Text("HTTPS-ссылка подписки") }, singleLine = true, modifier = Modifier.fillMaxWidth().followKeyboard(), shape = RoundedCornerShape(20.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                OutlinedTextField(hwid, { hwid = it }, enabled = !busy, label = { Text("HWID, если требуется") }, singleLine = true, modifier = Modifier.fillMaxWidth().followKeyboard(), shape = RoundedCornerShape(20.dp),
                    visualTransformation = if (showHwid) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = { IconButton(onClick = { showHwid = !showHwid }) { Icon(if (showHwid) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility, if (showHwid) "Скрыть HWID" else "Показать HWID") } })
                FilledTonalButton(onClick = { hwid = java.util.UUID.randomUUID().toString().uppercase(java.util.Locale.ROOT); showHwid = true; haptics.confirm() }, enabled = !busy) {
                    Icon(Icons.Rounded.AutoAwesome, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("Сгенерировать HWID")
                }
                Text("HWID отправляется поставщику подписки в заголовке x-hwid. Ссылка и HWID не сохраняются.", style = MaterialTheme.typography.bodySmall)
                Text("Если подписка уже привязана к устройству, укажите его существующий HWID.", style = MaterialTheme.typography.bodySmall)
            } else {
                OutlinedTextField(value, { value = it }, label = { Text("Ссылки, Base64 или JSON") }, minLines = if (keyboardOpen) 2 else 4, maxLines = if (keyboardOpen) 4 else 8, modifier = Modifier.fillMaxWidth().followKeyboard(), shape = RoundedCornerShape(20.dp))
                Text("VLESS · VMess · Trojan · Shadowsocks · Hysteria2 · TUIC. Проблемные записи сохраняются в результатах.", style = MaterialTheme.typography.bodySmall)
            }
            if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            Button(onClick = { haptics.confirm(); if (tab == 0) subscription(value.trim(), hwid.trim()) else text(value) }, enabled = !busy && value.isNotBlank(), shapes = ButtonDefaults.shapes(), modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(if (tab == 0) "Загрузить подписку" else "Импортировать") }
            OutlinedButton(onClick = { haptics.tick(); file() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Rounded.FolderOpen, null); Spacer(Modifier.width(10.dp)); Text("Выбрать файл") }
        }
    }
}

@Composable
private fun Modifier.followKeyboard(): Modifier {
    val requester = remember { BringIntoViewRequester() }
    var focused by remember { mutableStateOf(false) }
    val imeBottom = WindowInsets.ime.getBottom(LocalDensity.current)
    LaunchedEffect(focused, imeBottom) {
        if (focused) { withFrameNanos { }; requester.bringIntoView() }
    }
    return bringIntoViewRequester(requester).onFocusChanged { focused = it.isFocused }
}

@Composable
private fun LogScreen(state: UiState, copy: () -> Unit, clear: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        PageHeader("ДИАГНОСТИКА", "Журнал") {
            IconButton(onClick = copy) { Icon(Icons.Rounded.ContentCopy, "Копировать журнал") }
            IconButton(onClick = clear) { Icon(Icons.Rounded.DeleteOutline, "Очистить журнал") }
        }
        Text("Подробности ответа — в карточке сервера", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 16.dp))
        Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surfaceContainerLow, modifier = Modifier.fillMaxSize().padding(bottom = 16.dp)) {
            SelectionContainer {
                LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(state.logs.asReversed()) { line -> Text(line, fontFamily = FontFamily.Monospace, fontSize = 12.sp, lineHeight = 18.sp) }
                }
            }
        }
    }
}

@Composable
private fun SettingsScreen(settings: Settings, update: (Settings) -> Unit) {
    val haptics = LocalAppHaptics.current
    var licenses by remember { mutableStateOf(false) }
    val context = LocalContext.current
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeader("ПОД ТЕБЯ", "Настройки") }
        item {
            SettingsCard("Проверка", Icons.Rounded.Speed) {
                Text("Параллельные серверы", style = MaterialTheme.typography.titleMedium)
                Text("Меньше потоков — меньше нагрузка на телефон", style = MaterialTheme.typography.bodySmall)
                ChoiceRow((1..4).map(Int::toString), settings.parallel - 1) { update(settings.copy(parallel = it + 1)) }
                HorizontalDivider(Modifier.padding(vertical = 8.dp))
                Text("Тайм-аут · ${settings.timeout} с", style = MaterialTheme.typography.titleMedium)
                Slider(value = settings.timeout.toFloat(), onValueChange = {
                    val timeout = it.toInt()
                    if (timeout != settings.timeout) { haptics.fineTick(); update(settings.copy(timeout = timeout)) }
                }, valueRange = 5f..60f, steps = 10)
                Text("Время на HTTPS-запрос после запуска ядра", style = MaterialTheme.typography.bodySmall)
            }
        }
        item {
            SettingsCard("Оформление", Icons.Rounded.Palette) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) { Text("Цвета системы", style = MaterialTheme.typography.titleMedium); Text("Из обоев · Android 12 и новее", style = MaterialTheme.typography.bodySmall) }
                    Switch(checked = settings.dynamicColors, onCheckedChange = { haptics.tick(); update(settings.copy(dynamicColors = it)) }, enabled = Build.VERSION.SDK_INT >= 31)
                }
                Text("Тема", style = MaterialTheme.typography.titleMedium)
                ChoiceRow(listOf("Система", "Светлая", "Тёмная"), settings.theme) { update(settings.copy(theme = it)) }
            }
        }
        item {
            SettingsCard("Тактильный отклик", Icons.Rounded.Vibration) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Мягкая вибрация", style = MaterialTheme.typography.titleMedium)
                        Text("При выборе и подтверждении действий", style = MaterialTheme.typography.bodySmall)
                    }
                    Switch(checked = settings.haptics, onCheckedChange = { haptics.tick(); update(settings.copy(haptics = it)) })
                }
                Text("Учитывает системные настройки тактильного отклика", style = MaterialTheme.typography.bodySmall)
            }
        }
        item {
            SettingsCard("О приложении", Icons.Rounded.Info) {
                Text("VPN Gemini ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.titleMedium)
                Text("Material 3 Expressive · Jetpack Compose", style = MaterialTheme.typography.bodyMedium)
                Text("Xray 26.3.27 · sing-box 1.14.3", style = MaterialTheme.typography.bodySmall)
                Text("Конфигурации и результаты хранятся в памяти текущего сеанса. Сохранить результаты можно через экспорт CSV.", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { licenses = true }) { Text("Лицензии и исходный код ядер") }
            }
        }
    }
    if (licenses) AlertDialog(onDismissRequest = { licenses = false }, title = { Text("Открытые компоненты") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Xray-core · MPL 2.0\nsing-box · GPL 3.0 or later\nAndroidX и OkHttp · Apache 2.0\nKotlin · Apache 2.0")
            TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/XTLS/Xray-core/tree/v26.3.27"))) }) { Text("Исходники Xray") }
            TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/SagerNet/sing-box/tree/v1.14.3"))) }) { Text("Исходники sing-box") }
        } }, confirmButton = { TextButton(onClick = { licenses = false }) { Text("Готово") } })
}

@Composable
private fun SettingsCard(title: String, icon: ImageVector, content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) { Icon(icon, null, tint = MaterialTheme.colorScheme.primary); Spacer(Modifier.width(10.dp)); Text(title, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge) }
            content()
        }
    }
}

@Composable
private fun ChoiceRow(choices: List<String>, selected: Int, choose: (Int) -> Unit) {
    val haptics = LocalAppHaptics.current
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        choices.forEachIndexed { i, title ->
            if (selected == i) Button(onClick = {}, modifier = Modifier.weight(1f), contentPadding = PaddingValues(horizontal = 6.dp, vertical = 12.dp)) { Text(title, maxLines = 1) }
            else FilledTonalButton(onClick = { haptics.tick(); choose(i) }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(horizontal = 6.dp, vertical = 12.dp)) { Text(title, maxLines = 1) }
        }
    }
}
