import SwiftUI

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section("Проверка") {
                    Stepper("Одновременно: \(store.parallel)", value: $store.parallel, in: 1...4).disabled(store.running)
                    Stepper("Тайм-аут попытки: \(store.timeout) с", value: $store.timeout, in: 5...60, step: 5).disabled(store.running)
                }
                Section("Оформление") {
                    Picker("Тема", selection: $store.appearance) { Text("Системная").tag(0); Text("Светлая").tag(1); Text("Тёмная").tag(2) }
                        .accessibilityIdentifier("appearancePicker")
                    Toggle("Тактильный отклик", isOn: $store.haptics)
                }
                Section("О приложении") {
                    LabeledContent("VPN Gemini", value: "4.0.0 · iOS")
                    Text("Проверяет доступ к веб-версии Gemini через каждый сервер. Показывает регион Google и время защищённого соединения. При сетевой ошибке Hysteria2 пробует совместимый режим.")
                    Text("Конфигурации, HWID, результаты и журнал хранятся в памяти сеанса. В файл попадает только экспорт, который ты создашь сам.")
                    NavigationLink("Открытые компоненты") { NoticesView() }
                    Link("Доступность Gemini по странам", destination: URL(string: "https://support.google.com/gemini/answer/13575153?hl=en")!)
                }
                Section {
                    Text("Проверка выполняется, пока приложение открыто. При сворачивании она останавливается.")
                        .foregroundStyle(.secondary)
                }
            }.navigationTitle("Настройки")
        }
    }
}

struct JournalView: View {
    @Environment(AppStore.self) private var store
    var body: some View {
        NavigationStack {
            List {
                ForEach(store.logs) { entry in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(entry.date, style: .time).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        Text(entry.text).font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
                    }.padding(.vertical, 4)
                }
            }.navigationTitle("Журнал")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button("Копировать журнал", systemImage: "doc.on.doc") { UIPasteboard.general.string = store.logs.map(\.text).joined(separator: "\n") }
                            Button("Очистить", systemImage: "trash", role: .destructive) { store.logs.removeAll() }
                        } label: { Image(systemName: "ellipsis") }
                    }
                }
        }
    }
}

struct NoticesView: View {
    var body: some View {
        List {
            Section("Сетевые ядра") {
                Link("Xray-core 26.3.27 · MPL 2.0", destination: URL(string: "https://github.com/XTLS/Xray-core/tree/v26.3.27")!)
                Link("sing-box 1.14.3 · GPL 3.0", destination: URL(string: "https://github.com/SagerNet/sing-box/tree/v1.14.3")!)
                Text("Исходники приложения и инструкции сборки поставляются под GPL-3.0-or-later с сохранением лицензий зависимостей.")
            }
            if let url = Bundle.main.url(forResource: "NOTICES", withExtension: "txt"), let text = try? String(contentsOf: url, encoding: .utf8) {
                Section("Лицензии") { Text(text).font(.caption).textSelection(.enabled) }
            }
        }.navigationTitle("Компоненты")
    }
}
