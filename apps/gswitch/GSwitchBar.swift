// gswitch menu bar app. Lives in the status bar (no Dock icon); every action
// shells out to the `gswitch` script so there is one source of truth.
import AppKit

func gswitchPath() -> String {
    let home = NSHomeDirectory()
    for c in ["\(home)/.local/bin/gswitch", "\(home)/claude-toolkit/apps/gswitch/gswitch"]
    where FileManager.default.isExecutableFile(atPath: c) { return c }
    return ""
}

@discardableResult
func gswitch(_ args: [String]) -> String {
    let bin = gswitchPath()
    guard !bin.isEmpty else { return "gswitch script not found" }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: bin)
    p.arguments = args
    let pipe = Pipe()
    p.standardOutput = pipe; p.standardError = pipe
    do { try p.run() } catch { return "failed to run gswitch: \(error)" }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}

func notify(_ text: String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    p.arguments = ["-e", "display notification \(text.quotedForAppleScript()) with title \"GSwitch\""]
    try? p.run()
}

extension String {
    func quotedForAppleScript() -> String {
        "\"" + replacingOccurrences(of: "\\", with: "\\\\")
              .replacingOccurrences(of: "\"", with: "\\\"") + "\""
    }
}

final class App: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var statusItem: NSStatusItem!

    func applicationDidFinishLaunching(_ n: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu
        refreshIcon()
        Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in self.refreshIcon() }
    }

    func isUp() -> Bool { gswitch(["status"]).contains("server: UP") }

    func refreshIcon() {
        let up = isUp()
        if let b = statusItem.button {
            let name = up ? "externaldrive.badge.checkmark" : "externaldrive.badge.xmark"
            b.image = NSImage(systemSymbolName: name, accessibilityDescription: "GSwitch")
            b.image?.isTemplate = true
            b.toolTip = up ? "gswitch connector: running" : "gswitch connector: stopped"
        }
    }

    // Rebuild the menu each time it opens so the state line is never stale.
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let up = isUp()
        let head = NSMenuItem(title: up ? "● Connector running" : "○ Connector stopped",
                              action: nil, keyEquivalent: "")
        head.isEnabled = false
        menu.addItem(head)
        menu.addItem(.separator())

        if up {
            menu.addItem(mk("Restart connector", #selector(restart)))
            menu.addItem(mk("Stop connector", #selector(stop)))
        } else {
            menu.addItem(mk("Start connector", #selector(start)))
        }
        menu.addItem(.separator())
        menu.addItem(mk("Copy ChatGPT connector URL", #selector(copyURL)))
        menu.addItem(mk("Check setup…", #selector(doctor)))
        menu.addItem(mk("Open log", #selector(openLog)))
        menu.addItem(.separator())
        menu.addItem(mk("Quit GSwitch", #selector(quit)))
    }

    func mk(_ title: String, _ sel: Selector) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        i.target = self
        return i
    }

    @objc func start()   { notify("Starting…"); DispatchQueue.global().async { let o = gswitch(["start"]); DispatchQueue.main.async { notify(o); self.refreshIcon() } } }
    @objc func stop()    { DispatchQueue.global().async { _ = gswitch(["stop"]); DispatchQueue.main.async { notify("Connector stopped"); self.refreshIcon() } } }
    @objc func restart() { notify("Restarting…"); DispatchQueue.global().async { let o = gswitch(["restart"]); DispatchQueue.main.async { notify(o); self.refreshIcon() } } }

    @objc func copyURL() {
        let out = gswitch(["url"]).components(separatedBy: "\n").first ?? ""
        guard out.hasPrefix("https://") else { return alert("GSwitch", out) }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(out, forType: .string)
        alert("Copied to clipboard", out)
    }

    @objc func doctor()  { alert("GSwitch — setup check", gswitch(["doctor"])) }

    @objc func openLog() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-a", "Console", "\(NSHomeDirectory())/.gswitch/gswitch.log"]
        try? p.run()
    }

    @objc func quit() { NSApp.terminate(nil) }

    func alert(_ title: String, _ body: String) {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = title
        a.informativeText = body
        a.addButton(withTitle: "OK")
        a.runModal()
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)   // status bar only, no Dock icon
app.run()
