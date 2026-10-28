import Foundation
import SwiftUI

struct Server: Codable, Identifiable, Sendable {
    var id: String
    var name: String
    var `protocol`: String
    var host: String
    var port: Int
    var user: String
    var password: String
    var params: [String: String]?
    var raw: String
    var outbound: [String: JSONValue]?
    var engine: String
    var error: String
}

enum JSONValue: Codable, Sendable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
}

enum ProbeStatus: String, Codable, CaseIterable, Sendable {
    case pending = "PENDING", testing = "TESTING", ok = "OK", blocked = "BLOCKED", unknown = "UNKNOWN"
    case login = "LOGIN", captcha = "CAPTCHA", rateLimit = "RATE_LIMIT", timeout = "TIMEOUT", error = "ERROR", cancelled = "CANCELLED"
    var label: String {
        switch self {
        case .pending: "В очереди"
        case .testing: "Проверка"
        case .ok: "Доступен"
        case .blocked: "Ограничение"
        case .unknown: "Не определён"
        case .login: "Вход в Google"
        case .captcha: "CAPTCHA"
        case .rateLimit: "Лимит запросов"
        case .timeout: "Тайм-аут"
        case .error: "Ошибка"
        case .cancelled: "Остановлен"
        }
    }
    var symbol: String {
        switch self {
        case .ok: "checkmark.circle.fill"
        case .pending: "circle.dashed"
        case .testing: "arrow.triangle.2.circlepath"
        case .blocked: "hand.raised.circle.fill"
        case .unknown: "questionmark.circle.fill"
        case .login: "person.crop.circle.badge.exclamationmark"
        case .timeout: "clock.badge.exclamationmark"
        case .cancelled: "stop.circle"
        default: "exclamationmark.circle.fill"
        }
    }
    var color: Color {
        switch self {
        case .ok: .green
        case .testing: .accentColor
        case .pending, .cancelled, .unknown: .secondary
        case .login, .captcha, .rateLimit: .orange
        default: .red
        }
    }
}

struct ProbeResult: Codable, Identifiable, Sendable {
    var server: Server
    var status: ProbeStatus = .pending
    var country = ""
    var pingMs: Int64?
    var totalMs: Int64 = 0
    var detail = ""
    var httpCode = 0
    var finalUrl = ""
    var bytes = 0
    var title = ""
    var retried = false
    var id: String { server.id }
    var accessible: Bool { status == .ok && !country.isEmpty && (200...299).contains(httpCode) }
    var complete: Bool { status != .pending && status != .testing }
}

struct LogEntry: Identifiable { let id = UUID(); let date = Date(); let text: String }
enum AppTab: Hashable { case check, results, journal, settings }
