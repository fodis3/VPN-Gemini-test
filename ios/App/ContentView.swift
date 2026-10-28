import SwiftUI

struct ContentView: View {
    @Environment(AppStore.self) private var store
    var body: some View {
        @Bindable var store = store
        TabView(selection: $store.selectedTab) {
            CheckView().tabItem { Label("Проверка", systemImage: "shield.lefthalf.filled") }.tag(AppTab.check)
            ResultsView().tabItem { Label("Результаты", systemImage: "checklist") }.tag(AppTab.results)
                .badge(store.results.count)
            JournalView().tabItem { Label("Журнал", systemImage: "text.alignleft") }.tag(AppTab.journal)
            SettingsView().tabItem { Label("Настройки", systemImage: "slider.horizontal.3") }.tag(AppTab.settings)
        }
        .adaptiveTabBehavior()
        .onChange(of: store.selectedTab) { _, _ in store.feedback() }
    }
}

struct CheckView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var importing = false
    @State private var showClear = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    VStack(alignment: .leading, spacing: 14) {
                        Image(systemName: "globe.europe.africa.fill")
                            .font(.system(size: 64, weight: .light)).foregroundStyle(.blue.gradient)
                            .symbolEffect(.pulse, options: .repeating, isActive: store.running && !reduceMotion)
                            .accessibilityHidden(true)
                        Text("Найди свой\nмаршрут к Gemini")
                            .font(.system(.largeTitle, design: .rounded, weight: .bold))
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Проверь конфигурации и узнай, какой регион видит Google.")
                            .font(.title3).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: 12) {
                        MetricTile(value: "\(store.results.count)", label: "маршрутов", symbol: "point.3.connected.trianglepath.dotted", color: .blue)
                        MetricTile(value: "\(store.good)", label: "доступны", symbol: "checkmark.shield", color: .green)
                    }
                    if store.running || store.completed > 0 {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack { Text(store.running ? "Проверяем маршруты" : "Проверка завершена").font(.headline); Spacer(); Text("\(store.completed)/\(store.results.count)").monospacedDigit().foregroundStyle(.secondary) }
                            ProgressView(value: store.progress).accessibilityLabel("Прогресс проверки")
                            Text(store.running ? "Оставь приложение открытым до завершения." : "Подробности и доступные конфигурации — в результатах.")
                                .font(.footnote).foregroundStyle(.secondary)
                        }
                        .padding(20).background(.background.secondary, in: .rect(cornerRadius: 24))
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Как устроена проверка", systemImage: "info.circle").font(.headline)
                        Text("HTTPS через выбранный сервер → ответ Gemini → регион Google. HTTP 200 без определённого региона не считается успехом.")
                        Text("Проверка не входит в аккаунт Google и не отправляет запросы модели.")
                    }.font(.footnote).foregroundStyle(.secondary)
                }.padding(24)
            }
            .adaptiveBottomBar { actions.padding(.horizontal, 24).padding(.vertical, 12) }
            .navigationTitle("Проверка")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("Добавить текущее соединение", systemImage: "wifi") { store.direct() }.disabled(store.running)
                        Button("Очистить конфигурации", systemImage: "trash", role: .destructive) { showClear = true }.disabled(store.running || store.results.isEmpty)
                    } label: { Image(systemName: "ellipsis") }
                }
            }
            .confirmationDialog("Удалить все конфигурации и результаты?", isPresented: $showClear, titleVisibility: .visible) {
                Button("Очистить", role: .destructive) { store.clear() }
            }
            .sheet(isPresented: $importing) { ImportView() }
        }
    }
    @ViewBuilder private var actions: some View {
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: 14) {
                VStack(spacing: 14) {
                    startButton.buttonStyle(.glassProminent)
                    importButton.buttonStyle(.glass)
                }
            }
        } else {
            VStack(spacing: 14) {
                startButton.buttonStyle(.borderedProminent)
                importButton.buttonStyle(.bordered)
            }
        }
    }
    private var startButton: some View {
        Button {
            if store.running { store.stop() } else { store.start() }
        } label: {
            Label(store.running ? "Остановить проверку" : "Проверить Gemini", systemImage: store.running ? "stop.fill" : "play.fill")
                .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 8)
        }
        .controlSize(.large).disabled(store.results.isEmpty && !store.running)
    }
    private var importButton: some View {
        Button { importing = true; store.feedback() } label: {
            Label("Добавить конфигурации", systemImage: "plus").frame(maxWidth: .infinity).padding(.vertical, 6)
        }
        .controlSize(.large).disabled(store.running)
    }

}

struct MetricTile: View {
    let value: String; let label: String; let symbol: String; let color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: symbol).font(.title3).foregroundStyle(color)
            Text(value).font(.system(.largeTitle, design: .rounded, weight: .semibold)).monospacedDigit()
            Text(label).font(.subheadline).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(.background.secondary, in: .rect(cornerRadius: 24))
    }
}
