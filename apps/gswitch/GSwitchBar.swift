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

func logLine(_ s: String) {
    let path = "\(NSHomeDirectory())/.gswitch/menubar.log"
    let line = "\(Date()) \(s)\n"
    if let h = FileHandle(forWritingAtPath: path) {
        h.seekToEndOfFile(); h.write(line.data(using: .utf8)!); try? h.close()
    } else {
        try? line.write(toFile: path, atomically: true, encoding: .utf8)
    }
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
        logLine("didFinishLaunching")
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu
        logLine("statusItem created, button=\(statusItem.button != nil)")
        refreshIcon()
        Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in self.refreshIcon() }
    }

    func isUp() -> Bool { gswitch(["status"]).contains("server: UP") }

    // Always set a text title: if the SF Symbol fails to load the button would
    // otherwise have zero width and be invisible while the app looks healthy.
    func refreshIcon() {
        let up = isUp()
        guard let b = statusItem.button else { logLine("refreshIcon: no button"); return }
        let name = up ? "externaldrive.badge.checkmark" : "externaldrive.badge.xmark"
        let img = NSImage(systemSymbolName: name, accessibilityDescription: "GSwitch")
        img?.isTemplate = true
        b.image = img
        b.imagePosition = .imageLeading
        b.title = up ? " GS" : " GS✗"
        b.toolTip = up ? "gswitch connector: running" : "gswitch connector: stopped"
        let f = b.window?.frame ?? .zero
        logLine("refreshIcon up=\(up) image=\(img != nil) visible=\(statusItem.isVisible) len=\(statusItem.length) btnW=\(b.frame.width) win=\(b.window != nil) winFrame=\(f)")
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
