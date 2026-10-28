import SwiftUI
import UniformTypeIdentifiers

@MainActor @Observable final class AppStore {
    var results: [ProbeResult] = []
    var logs: [LogEntry] = []
    var selectedTab: AppTab = .check
    var running = false
    var importing = false
    var notice: String?
    var parallel: Int { didSet { UserDefaults.standard.set(parallel, forKey: "parallel") } }
    var timeout: Int { didSet { UserDefaults.standard.set(timeout, forKey: "timeout") } }
    var haptics: Bool { didSet { UserDefaults.standard.set(haptics, forKey: "haptics") } }
    var appearance: Int { didSet { UserDefaults.standard.set(appearance, forKey: "appearance") } }
    private var checkTask: Task<Void, Never>?
    private var activeJobs: Set<String> = []
    var completed: Int { results.filter(\.complete).count }
    var good: Int { results.filter(\.accessible).count }
    var progress: Double { results.isEmpty ? 0 : Double(completed) / Double(results.count) }

    init() {
        let p = UserDefaults.standard.integer(forKey: "parallel")
        let t = UserDefaults.standard.integer(forKey: "timeout")
        parallel = (1...4).contains(p) ? p : 2
        timeout = (5...60).contains(t) ? t : 15
        haptics = UserDefaults.standard.object(forKey: "haptics") as? Bool ?? true
        appearance = UserDefaults.standard.integer(forKey: "appearance")
        log("VPN Gemini 4.0 · iOS готов к работе")
    }
    func log(_ text: String) { logs.append(LogEntry(text: text)); if logs.count > 1000 { logs.removeFirst(logs.count - 1000) } }
    func feedback(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .soft) {
        if haptics { UIImpactFeedbackGenerator(style: style).impactOccurred() }
    }
    func add(_ servers: [Server]) {
        results.append(contentsOf: servers.map { ProbeResult(server: $0, status: $0.error.isEmpty ? .pending : .error, detail: $0.error) })
        log("Импортировано: \(servers.count). С ошибками: \(servers.filter { !$0.error.isEmpty }.count)")
        feedback()
    }
    func direct() {
        let s = Server(id: UUID().uuidString, name: "Текущее соединение", protocol: "direct", host: "", port: 0,
                       user: "", password: "", params: [:], raw: "", engine: "direct", error: "")
        add([s])
    }
    func clear() { guard !running else { return }; results.removeAll(); feedback() }
    func start() {
        guard !running, !results.isEmpty else { return }
        running = true; feedback(); log("Проверка началась")
        results = results.map { ProbeResult(server: $0.server) }
        let servers = results.map(\.server), limit = parallel, seconds = timeout
        checkTask = Task { [weak self] in
            guard let self else { return }
            await withTaskGroup(of: (String, ProbeResult).self) { group in
                var next = 0
                @MainActor func schedule() {
                    guard next < servers.count, !Task.isCancelled else { return }
                    let server = servers[next]; next += 1
                    let job = UUID().uuidString; self.activeJobs.insert(job)
                    self.update(ProbeResult(server: server, status: .testing))
                    group.addTask { (job, await NativeEngine.probe(server, timeout: seconds, id: job)) }
                }
                for _ in 0..<min(limit, servers.count) { schedule() }
                for await (job, result) in group {
                    activeJobs.remove(job); update(result)
                    log("\(result.server.name.prefix(60)) · \(result.status.label)" + (result.httpCode > 0 ? " · HTTP \(result.httpCode)" : "") + (result.country.isEmpty ? "" : " · Google \(result.country)"))
                    if result.retried { log("Hysteria2: выполнен повтор с пакетами 1200 байт") }
                    if Task.isCancelled { group.cancelAll() } else { schedule() }
                }
            }
            results = results.map { value in
                var r = value; if r.status == .pending || r.status == .testing { r.status = .cancelled }; return r
            }
            running = false; activeJobs.removeAll(); log("Проверка завершена · доступны \(good) из \(results.count)"); feedback()
        }
    }
    private func update(_ result: ProbeResult) { if let i = results.firstIndex(where: { $0.id == result.id }) { results[i] = result } }
    func stop() { guard running else { return }; checkTask?.cancel(); activeJobs.forEach(NativeEngine.cancel); feedback(); log("Остановка проверки…") }
    func csv() -> String {
        func quote(_ s: String) -> String {
            var text = s
            if let c = text.first, "=+-@\t\r".contains(c) { text = "'" + text }
            return "\"" + text.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        return "Имя,Протокол,Статус,Регион Google,TLS мс,Время мс,HTTP,URL,Описание\n" + results.map {
            [$0.server.name, $0.server.protocol, $0.status.label, $0.country, $0.pingMs.map(String.init) ?? "", String($0.totalMs), String($0.httpCode), $0.finalUrl, $0.detail].map(quote).joined(separator: ",")
        }.joined(separator: "\n")
    }
}

struct CSVDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.commaSeparatedText] }
    var text: String
    init(text: String) { self.text = text }
    init(configuration: ReadConfiguration) throws { text = String(decoding: configuration.file.regularFileContents ?? Data(), as: UTF8.self) }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: Data(("\u{FEFF}" + text).utf8)) }
}
