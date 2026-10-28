import SwiftUI

// Keep OS-specific decoration separate from shared navigation and probe actions.
extension View {
    @ViewBuilder func adaptiveTabBehavior() -> some View {
        if #available(iOS 26.0, *) {
            self.tabBarMinimizeBehavior(.onScrollDown)
        } else {
            self
        }
    }

    @ViewBuilder func adaptiveBottomBar<Bar: View>(@ViewBuilder content: () -> Bar) -> some View {
        if #available(iOS 26.0, *) {
            self.safeAreaBar(edge: .bottom, content: content)
        } else {
            self.safeAreaInset(edge: .bottom, spacing: 0) {
                content().background(.bar)
            }
        }
    }
}
