import SwiftUI
import UniformTypeIdentifiers

struct ImportView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var mode = 0
    @State private var source = ""
    @State private var hwid = ""
    @State private var text = ""
    @State private var error = ""
    @State private var busy = false
    @State private var filePicker = false
    @FocusState private var focused: Field?
    enum Field { case url, hwid, text }
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Источник", selection: $mode) { Text("Подписка").tag(0); Text("Текст").tag(1) }.pickerStyle(.segmented)
                }
                if mode == 0 {
                    Section("Ссылка подписки") {
                        TextField("https://…", text: $source, axis: .vertical)
                            .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .focused($focused, equals: .url).privacySensitive()
                    }
                    Section {
                        TextField("HWID, если требуется", text: $hwid).textInputAutocapitalization(.never)
                            .autocorrectionDisabled().focused($focused, equals: .hwid).privacySensitive()
                        Button("Сгенерировать HWID", systemImage: "arrow.trianglehead.2.clockwise") {
                            hwid = UUID().uuidString.uppercased(); store.feedback()
                        }
                    } header: { Text("Идентификатор устройства") } footer: {
                        Text("Используй HWID, уже привязанный у поставщика. Новый идентификатор не заменяет существующую привязку.")
                    }
                } else {
                    Section("Конфигурации, Base64 или JSON") {
                        TextEditor(text: $text).frame(minHeight: 180).font(.system(.body, design: .monospaced))
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .focused($focused, equals: .text).privacySensitive()
                        Button("Выбрать файл", systemImage: "doc") { filePicker = true }
                    }
                }
                if !error.isEmpty { Section { Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.red).accessibilityIdentifier("importError") } }
                Section {
                    Button {
                        focused = nil; busy = true; error = ""
                        Task {
                            do {
                                let servers: [Server]
                                if mode == 0 { servers = try await NativeEngine.subscription(source.trimmingCharacters(in: .whitespacesAndNewlines), hwid: hwid) }
                                else { servers = try await NativeEngine.parse(text) }
                                store.add(servers); dismiss()
                            } catch { self.error = error.localizedDescription }
                            busy = false
                        }
                    } label: {
                        HStack { Spacer(); if busy { ProgressView() }; Text(busy ? "Импортируем…" : "Импортировать"); Spacer() }
                    }.disabled(busy || (mode == 0 ? source.isEmpty : text.isEmpty))
                }
            }
            .disabled(busy)
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Добавить маршруты").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Закрыть", systemImage: "xmark") { dismiss() }.disabled(busy) }
                ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Готово") { focused = nil } }
            }
            .interactiveDismissDisabled(busy)
            .fileImporter(isPresented: $filePicker, allowedContentTypes: [.plainText, .json, .data]) { result in
                do {
                    let url = try result.get(); let granted = url.startAccessingSecurityScopedResource()
                    defer { if granted { url.stopAccessingSecurityScopedResource() } }
                    let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                    guard size <= 8 * 1024 * 1024 else { throw NativeEngine.EngineError(message: "Файл превышает 8 МБ") }
                    text = try String(contentsOf: url, encoding: .utf8); mode = 1
                } catch { self.error = "Не удалось прочитать файл: \(error.localizedDescription)" }
            }
        }
    }
}
