import AppKit
import SwiftUI
import UserNotifications

enum DefaultsKey {
    static let subscriptionKey = "gridSubscriptionKey"
    static let locationId = "gridLocationId"
    static let updateInterval = "gridUpdateIntervalSeconds"
}

struct GridResponse: Decodable {
    struct DataPayload: Decodable {
        let locationId: Int
        let locationName: String?
        let availability: String?
        let available: Int?
        let total: Int?
        let geoLocation: GeoLocation?
    }

    struct GeoLocation: Decodable {
        let address: String?
        let city: String?
    }

    let data: DataPayload
    let success: Bool
}

@MainActor
final class StatusController: NSObject {
    private var statusItem: NSStatusItem?
    private var statusMenuItem: NSMenuItem?
    private var timer: Timer?
    private var settingsWindow: NSWindow?
    private var lastSummary: String = "?"
    private var lastStatus: String = "unknown"

    func start() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = menuIcon()
        item.button?.image?.isTemplate = true
        item.button?.title = ""
        item.menu = buildMenu()
        statusItem = item

        requestNotificationPermissionsIfAvailable()
        scheduleTimer()
        refreshNow(nil)

        if subscriptionKey().isEmpty {
            showSettings(nil)
        }
    }

    private func buildMenu() -> NSMenu {
        let menu = NSMenu()

        let statusItem = NSMenuItem(title: "Status: ?", action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        statusMenuItem = statusItem
        menu.addItem(statusItem)
        menu.addItem(.separator())

        let refreshItem = NSMenuItem(
            title: "Refresh now",
            action: #selector(refreshNow(_:)),
            keyEquivalent: "r"
        )
        refreshItem.target = self
        menu.addItem(refreshItem)

        let openItem = NSMenuItem(
            title: "Open location",
            action: #selector(openLocation(_:)),
            keyEquivalent: "o"
        )
        openItem.target = self
        menu.addItem(openItem)

        let settingsItem = NSMenuItem(
            title: "Settings…",
            action: #selector(showSettings(_:)),
            keyEquivalent: ","
        )
        settingsItem.target = self
        menu.addItem(settingsItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(
            title: "Quit",
            action: #selector(quit(_:)),
            keyEquivalent: "q"
        )
        quitItem.target = self
        menu.addItem(quitItem)

        return menu
    }

    private func scheduleTimer() {
        timer?.invalidate()
        let interval = max(60, updateInterval())
        timer = Timer.scheduledTimer(
            timeInterval: TimeInterval(interval),
            target: self,
            selector: #selector(handleTimer(_:)),
            userInfo: nil,
            repeats: true
        )
    }

    @objc private func handleTimer(_ timer: Timer) {
        refreshNow(nil)
    }

    @objc private func refreshNow(_ sender: Any?) {
        Task {
            await updateStatus()
        }
    }

    private func updateStatus() async {
        guard !subscriptionKey().isEmpty else {
            updateMenu(title: "Key missing", tooltip: "Open settings to add key")
            return
        }

        do {
            let response = try await fetchGridStatus()
            let summary = buildSummary(from: response)
            let status = buildStatus(from: response)
            let tooltip = buildTooltip(from: response)
            if lastStatus == "bezet" && status == "vrij" {
                notifyAvailable(summary: summary)
            }
            lastSummary = summary
            lastStatus = status
            updateMenu(title: summary, tooltip: tooltip)
        } catch {
            updateMenu(title: "?", tooltip: "Error: \(error.localizedDescription)")
        }
    }

    private func buildSummary(from response: GridResponse) -> String {
        if let available = response.data.available,
           let total = response.data.total {
            let status = available == 0 ? "bezet" : "vrij"
            return "\(available)/\(total) \(status)"
        }
        if let availability = response.data.availability, !availability.isEmpty {
            return availability
        }
        return "unknown"
    }

    private func buildStatus(from response: GridResponse) -> String {
        if let available = response.data.available,
           let _ = response.data.total {
            return available == 0 ? "bezet" : "vrij"
        }
        if let availability = response.data.availability?.lowercased() {
            if availability.contains("available") {
                return "vrij"
            }
            if availability.contains("unavailable") {
                return "bezet"
            }
        }
        return "unknown"
    }

    private func buildTooltip(from response: GridResponse) -> String {
        var parts: [String] = []
        if let name = response.data.locationName {
            parts.append(name)
        }
        if let address = response.data.geoLocation?.address {
            parts.append(address)
        }
        if let city = response.data.geoLocation?.city {
            parts.append(city)
        }
        let updated = DateFormatter.localizedString(
            from: Date(),
            dateStyle: .short,
            timeStyle: .short
        )
        parts.append("Updated: \(updated)")
        return parts.joined(separator: " · ")
    }

    private func updateMenu(title: String, tooltip: String) {
        statusItem?.button?.toolTip = tooltip
        statusMenuItem?.title = "Status: \(title)"
    }

    private func menuIcon() -> NSImage? {
        let image = NSImage(systemSymbolName: "bolt.car", accessibilityDescription: "Laadpaal")
        return image
    }

    private func fetchGridStatus() async throws -> GridResponse {
        let locationId = locationIdValue()
        let baseUrl = "https://api.grid.com/charging/ChargingStations/location/\(locationId)"
        guard let url = URL(string: baseUrl) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.addValue(subscriptionKey(), forHTTPHeaderField: "Ocp-Apim-Subscription-Key")
        request.timeoutInterval = 10

        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw NSError(
                domain: "GridAPI",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode): \(body)"]
            )
        }
        let decoder = JSONDecoder()
        return try decoder.decode(GridResponse.self, from: data)
    }

    @objc private func showSettings(_ sender: Any?) {
        if settingsWindow == nil {
            settingsWindow = SettingsWindowController(onSave: { [weak self] in
                self?.scheduleTimer()
                self?.refreshNow(nil)
            }).window
        }

        if let window = settingsWindow {
            window.center()
            window.makeKeyAndOrderFront(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
    }

    @objc private func openLocation(_ sender: Any?) {
        let locationId = locationIdValue()
        let urlString = "https://app.grid.com/charginglocation/\(locationId)"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func quit(_ sender: Any?) {
        NSApplication.shared.terminate(nil)
    }

    private func subscriptionKey() -> String {
        UserDefaults.standard.string(forKey: DefaultsKey.subscriptionKey) ?? ""
    }

    private func locationIdValue() -> Int {
        let stored = UserDefaults.standard.integer(forKey: DefaultsKey.locationId)
        return stored == 0 ? 674202 : stored
    }

    private func updateInterval() -> Int {
        let stored = UserDefaults.standard.integer(forKey: DefaultsKey.updateInterval)
        return stored == 0 ? 900 : stored
    }

    private func requestNotificationPermissionsIfAvailable() {
        guard isRunningInAppBundle() else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    private func notifyAvailable(summary: String) {
        guard isRunningInAppBundle() else { return }
        let content = UNMutableNotificationContent()
        content.title = "Laadpaal vrij"
        content.body = summary
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request, withCompletionHandler: nil)
    }

    private func isRunningInAppBundle() -> Bool {
        Bundle.main.bundleURL.pathExtension == "app"
    }
}

final class SettingsWindowController: NSWindowController {
    init(onSave: @escaping () -> Void) {
        let view = SettingsView(onSave: onSave)
        let hostingController = NSHostingController(rootView: view)
        let window = NSWindow(contentViewController: hostingController)
        window.title = "Laadpaal Settings"
        window.styleMask = [.titled, .closable]
        window.setContentSize(NSSize(width: 360, height: 220))
        super.init(window: window)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

struct SettingsView: View {
    @State private var subscriptionKey: String =
        UserDefaults.standard.string(forKey: DefaultsKey.subscriptionKey) ?? ""
    @State private var locationId: String =
        UserDefaults.standard.integer(forKey: DefaultsKey.locationId) == 0
        ? "674202"
        : String(UserDefaults.standard.integer(forKey: DefaultsKey.locationId))
    @State private var updateInterval: String =
        UserDefaults.standard.integer(forKey: DefaultsKey.updateInterval) == 0
        ? "900"
        : String(UserDefaults.standard.integer(forKey: DefaultsKey.updateInterval))

    let onSave: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Grid API Key").font(.headline)
            TextField("Subscription key", text: $subscriptionKey)
                .textFieldStyle(.roundedBorder)

            Text("Location ID")
                .font(.headline)
            TextField("Location ID", text: $locationId)
                .textFieldStyle(.roundedBorder)

            Text("Update Interval (seconds)")
                .font(.headline)
            TextField("900", text: $updateInterval)
                .textFieldStyle(.roundedBorder)

            HStack {
                Spacer()
                Button("Save") {
                    save()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
    }

    private func save() {
        UserDefaults.standard.set(subscriptionKey.trimmingCharacters(in: .whitespacesAndNewlines),
                                  forKey: DefaultsKey.subscriptionKey)
        UserDefaults.standard.set(Int(locationId) ?? 674202, forKey: DefaultsKey.locationId)
        UserDefaults.standard.set(Int(updateInterval) ?? 900, forKey: DefaultsKey.updateInterval)
        onSave()
    }
}

@main
struct LaadpaalMenubarApp {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let controller = StatusController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        controller.start()
    }
}
