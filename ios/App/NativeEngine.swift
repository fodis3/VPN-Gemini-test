import Foundation
import GeminiCore

enum NativeEngine {
    private struct ImportResponse: Decodable { var servers: [Server]?; var error: String? }
    private struct ErrorResponse: Decodable { var error: String? }
    private struct Request: Encodable { let id: String; let server: Server; let timeout: Int }
    struct EngineError: LocalizedError { let message: String; var errorDescription: String? { message } }

    static func parse(_ text: String) async throws -> [Server] {
        guard text.utf8.count <= 8 * 1024 * 1024 else { throw EngineError(message: "Содержимое превышает 8 МБ") }
        let json: String? = await Task.detached { EngineParse(text) }.value
        return try imported(json)
    }
    static func subscription(_ address: String, hwid: String) async throws -> [Server] {
        let json: String? = await Task.detached { EngineSubscription(address, hwid) }.value
        return try imported(json)
    }
    private static func imported(_ json: String?) throws -> [Server] {
        let response = try JSONDecoder().decode(ImportResponse.self, from: Data((json ?? "{}").utf8))
        if let error = response.error { throw EngineError(message: error) }
        guard let servers = response.servers, !servers.isEmpty else { throw EngineError(message: "В подписке нет конфигураций") }
        return servers
    }
    static func probe(_ server: Server, timeout: Int, id: String) async -> ProbeResult {
        do {
            try Task.checkCancellation()
            let request = String(decoding: try JSONEncoder().encode(Request(id: id, server: server, timeout: timeout)), as: UTF8.self)
            let work = Task.detached(priority: .userInitiated) { () -> String in
                let json: String? = EngineProbe(request)
                return json ?? "{}"
            }
            let json = await withTaskCancellationHandler { await work.value } onCancel: { EngineCancel(id) }
            if Task.isCancelled { return ProbeResult(server: server, status: .cancelled) }
            if let result = try? JSONDecoder().decode(ProbeResult.self, from: Data(json.utf8)) { return result }
            let message = (try? JSONDecoder().decode(ErrorResponse.self, from: Data(json.utf8)))?.error ?? "Некорректный ответ ядра"
            return ProbeResult(server: server, status: .error, detail: message)
        } catch is CancellationError { return ProbeResult(server: server, status: .cancelled) }
        catch { return ProbeResult(server: server, status: .error, detail: "Не удалось запустить проверку") }
    }
    static func cancel(_ id: String) { EngineCancel(id) }
}
