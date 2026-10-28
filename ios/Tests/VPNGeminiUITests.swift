import XCTest

final class VPNGeminiUITests: XCTestCase {
    @MainActor func testDarkAppearance() {
        let app = XCUIApplication()
        app.launchArguments = ["-appearance", "2"]
        app.launch()
        XCTAssertTrue(app.buttons["Добавить конфигурации"].waitForExistence(timeout: 15))
        capture("05-dark-check", app: app)
        app.tabBars.buttons["Настройки"].tap()
        let theme = app.buttons["appearancePicker"]
        XCTAssertTrue(theme.waitForExistence(timeout: 5))
        XCTAssertTrue(theme.label.contains("Тёмная") || (theme.value as? String)?.contains("Тёмная") == true)
    }
    @MainActor func testImportNavigationAndNativeSettings() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.buttons["Добавить конфигурации"].waitForExistence(timeout: 15))
        capture("01-check", app: app)
        app.buttons["Добавить конфигурации"].tap()
        app.segmentedControls.buttons["Текст"].tap()
        let editor = app.textViews.firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 5))
        editor.tap()
        editor.press(forDuration: 1.2)
        let paste = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@ OR label == %@", "Paste", "Вставить")).firstMatch
        XCTAssertTrue(paste.waitForExistence(timeout: 5))
        paste.tap()
        if app.buttons["Готово"].exists { app.buttons["Готово"].tap() }
        app.buttons["Импортировать"].tap()
        let resultsTab = app.tabBars.buttons["Результаты"]
        XCTAssertTrue(resultsTab.waitForExistence(timeout: 10))
        resultsTab.tap()
        XCTAssertTrue(app.staticTexts["Test"].waitForExistence(timeout: 10))
        capture("02-results", app: app)
        app.tabBars.buttons["Настройки"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "hapticsToggle").firstMatch.waitForExistence(timeout: 5))
        capture("03-settings", app: app)
        app.tabBars.buttons["Проверка"].tap()
        app.buttons["Добавить конфигурации"].tap()
        app.buttons["Сгенерировать HWID"].tap()
        let field = app.textFields["HWID, если требуется"]
        XCTAssertEqual((field.value as? String)?.count, 36)
        capture("04-import-hwid", app: app)
        app.buttons["Закрыть"].tap()
        app.buttons["Проверить Gemini"].tap()
        app.tabBars.buttons["Результаты"].tap()
        let failed = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Ошибка")).firstMatch
        XCTAssertTrue(failed.waitForExistence(timeout: 20), "A closed proxy endpoint must fail, without direct fallback")
        capture("06-native-failed-tunnel", app: app)
    }
    @MainActor private func capture(_ name: String, app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
