import SwiftUI

@main struct VPNGeminiApp: App {
    @State private var store = AppStore()
    @Environment(\.scenePhase) private var scenePhase
    var body: some Scene {
        WindowGroup {
            ContentView().environment(store)
                .tint(.blue)
                .preferredColorScheme(store.appearance == 1 ? .light : store.appearance == 2 ? .dark : nil)
                .onChange(of: scenePhase) { _, phase in
                    if phase == .background && store.running {
                        store.stop(); store.log("Проверка остановлена при сворачивании. Запустите её снова после возврата.")
                    }
                }
        }
    }
}
