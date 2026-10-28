import SwiftUI

struct ResultsView: View {
    @Environment(AppStore.self) private var store
    @State private var search = ""
    @State private var filter = 0
    @State private var sort = 0
    @State private var exporting = false
    @State private var copied = false
    private var visible: [ProbeResult] {
        let list = store.results.filter { r in
            (search.isEmpty || (r.server.name + " " + r.country + " " + r.server.host).localizedCaseInsensitiveContains(search)) &&
            (filter == 0 || filter == 1 && r.accessible || filter == 2 && [.error, .timeout, .blocked].contains(r.status) || filter == 3 && [.unknown, .login, .captcha, .rateLimit].contains(r.status))
        }
        if sort == 1 { return list.sorted { ($0.pingMs ?? Int64.max) < ($1.pingMs ?? Int64.max) } }
        if sort == 2 { return list.sorted { $0.server.name.localizedStandardCompare($1.server.name) == .orderedAscending } }
        return list
    }
    var body: some View {
        NavigationStack {
            Group {
                if store.results.isEmpty {
                    ContentUnavailableView("Здесь будут маршруты", systemImage: "point.3.connected.trianglepath.dotted",
                                           description: Text("Добавь конфигурации на вкладке «Проверка»."))
                } else {
                    List {
                        Section {
                            Picker("Показать", selection: $filter) {
                                Text("Все").tag(0); Text("Доступны \(store.good)").tag(1)
                                Text("Ошибки").tag(2); Text("Не определены").tag(3)
                            }.pickerStyle(.menu)
                        }
                        if visible.isEmpty { ContentUnavailableView.search(text: search) }
                        ForEach(visible) { result in
                            NavigationLink { ResultDetail(result: result) } label: { ResultRow(result: result) }
                                .contextMenu {
                                    Button("Копировать конфигурацию", systemImage: "doc.on.doc") {
                                        UIPasteboard.general.string = result.server.raw; store.feedback()
                                    }.disabled(result.server.raw.isEmpty)
                                }
                        }
                    }.listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Результаты")
            .searchable(text: $search, prompt: "Сервер или регион Google")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Picker("Сортировка", selection: $sort) { Text("Порядок импорта").tag(0); Text("TLS-время").tag(1); Text("По имени").tag(2) }
                        Button("Экспорт CSV", systemImage: "square.and.arrow.up") { exporting = true }.disabled(store.results.isEmpty)
                        Button("Копировать доступные", systemImage: "doc.on.doc") {
                            UIPasteboard.general.string = store.results.filter(\.accessible).map(\.server.raw).filter { !$0.isEmpty }.joined(separator: "\n")
                            store.feedback(); copied = true
                        }.disabled(store.good == 0)
                    } label: { Image(systemName: "ellipsis") }
                }
            }
            .fileExporter(isPresented: $exporting, document: CSVDocument(text: store.csv()), contentType: .commaSeparatedText, defaultFilename: "VPN-Gemini-results") { outcome in
                if case .failure = outcome { store.log("Не удалось экспортировать CSV") }
            }
            .alert("Конфигурации скопированы", isPresented: $copied) { Button("Готово", role: .cancel) {} }
        }
    }
}

struct ResultRow: View {
    let result: ProbeResult
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Group {
                if result.status == .testing { ProgressView().frame(width: 34, height: 34) }
                else { Image(systemName: result.status.symbol).font(.system(size: 28)).foregroundStyle(result.status.color).frame(width: 34, height: 34) }
            }.accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(result.server.name).font(.headline).lineLimit(2)
                Text(result.status.label).font(.subheadline).foregroundStyle(result.status.color)
                HStack(spacing: 14) {
                    Text(result.server.protocol.uppercased())
                    if !result.country.isEmpty { Text("Google: \(result.country)") }
                    Spacer(minLength: 0)
                    if let ping = result.pingMs { Text("\(ping) мс").monospacedDigit() }
                }.font(.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical, 8)
            .accessibilityElement(children: .combine)
    }
}

struct ResultDetail: View {
    @Environment(AppStore.self) private var store
    let result: ProbeResult
    var body: some View {
        let result = store.results.first(where: { $0.id == self.result.id }) ?? self.result
        Form {
            Section {
                Label(result.status.label, systemImage: result.status.symbol).font(.title2.bold()).foregroundStyle(result.status.color)
                Text(result.detail.isEmpty ? "Проверка ещё не завершена" : result.detail).textSelection(.enabled)
            }
            Section("Соединение") {
                LabeledContent("Протокол", value: result.server.protocol.uppercased())
                LabeledContent("Сервер", value: result.server.host)
                LabeledContent("Регион Google", value: result.country.isEmpty ? "Не определён" : result.country)
                LabeledContent("TLS-время", value: result.pingMs.map { "\($0) мс" } ?? "—")
                LabeledContent("Полное время", value: String(format: "%.1f с", Double(result.totalMs) / 1000))
                if result.httpCode > 0 { LabeledContent("HTTP", value: "\(result.httpCode)") }
                if result.retried { LabeledContent("Повтор Hysteria2", value: "QUIC 1200 байт") }
            }
            if !result.finalUrl.isEmpty {
                Section("Ответ Gemini") {
                    Text(result.finalUrl).font(.footnote).textSelection(.enabled)
                    if !result.title.isEmpty { LabeledContent("Заголовок", value: result.title) }
                    LabeledContent("Размер", value: ByteCountFormatter.string(fromByteCount: Int64(result.bytes), countStyle: .file))
                }
            }
            Section {
                Button("Копировать конфигурацию", systemImage: "doc.on.doc") { UIPasteboard.general.string = result.server.raw }
                    .disabled(result.server.raw.isEmpty)
            } footer: { Text("Проверяется HTTPS-ответ и регион Google. Доступ конкретного аккаунта и генерация ответа модели не проверяются.") }
        }
        .navigationTitle(result.server.name).navigationBarTitleDisplayMode(.inline)
    }
}
