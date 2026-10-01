// Prototype: a Grammarly-style badge that sits above Claude's prompt box, in
// the desktop app (Code and Chat tabs) and on claude.ai in a browser.
//
// Claude and Chromium browsers only build an Accessibility tree for web
// content once someone sets AXManualAccessibility on them. We do, then poll
// the focused element ten times a second: if it is an editable text area in
// Claude -- or on a claude.ai page -- the badge parks above it; otherwise it
// hides.
//
// Read-only, like menubar.py: it reads state.json and never records, so the
// status line's "since your last prompt" delta survives.

import AppKit
import ApplicationServices

let CLAUDE_BUNDLE = "com.anthropic.claudefordesktop"
// In these, the badge shows only when the focused field is on claude.ai.
let BROWSERS: Set<String> = [
    "com.google.Chrome", "com.google.Chrome.canary", "com.apple.Safari",
    "company.thebrowser.Browser", "com.microsoft.edgemac", "com.brave.Browser",
    "org.mozilla.firefox",
]
let STATE = (NSString(string: "~/.claude/revenge-o-meter/state.json").expandingTildeInPath)

// Anthropic's palette: the clay orange is the accent, cream and near-black
// carry the surface. Bands borrow the brand's secondary hues, warming from
// olive through blue and kraft to clay and crail as the score climbs.
extension NSColor {
    convenience init(hex: Int) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xff) / 255,
                  green: CGFloat((hex >> 8) & 0xff) / 255,
                  blue: CGFloat(hex & 0xff) / 255, alpha: 1)
    }
}

let CLAY = NSColor(hex: 0xD97757)

struct Palette {
    let surface, border, text, muted: NSColor

    static let light = Palette(surface: NSColor(hex: 0xFAF9F5), border: NSColor(hex: 0xE3DACC),
                               text: NSColor(hex: 0x141413), muted: NSColor(hex: 0x87867F))
    static let dark = Palette(surface: NSColor(hex: 0x262624), border: NSColor(hex: 0x3E3D39),
                              text: NSColor(hex: 0xFAF9F5), muted: NSColor(hex: 0xB0AEA5))

    static func current(_ appearance: NSAppearance) -> Palette {
        appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? .dark : .light
    }
}

let BANDS: [(Int, String, NSColor)] = [
    (20, "Negligible", NSColor(hex: 0x788C5D)),
    (40, "Low", NSColor(hex: 0x6A9BCC)),
    (60, "Elevated", NSColor(hex: 0xD4A27F)),
    (78, "Substantial", CLAY),
    (92, "Severe", NSColor(hex: 0xC15F3C)),
    (101, "Terminal", NSColor(hex: 0xBF4D43)),
]

func band(_ score: Int) -> (String, NSColor) {
    for (limit, name, colour) in BANDS where score < limit { return (name, colour) }
    return (BANDS.last!.1, BANDS.last!.2)
}

struct Standing {
    var score: Int?
    var peak: Int
}

func readStanding() -> Standing {
    guard let data = FileManager.default.contents(atPath: STATE),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return Standing(score: nil, peak: 0) }
    return Standing(score: obj["last_score"] as? Int, peak: obj["peak"] as? Int ?? 0)
}

// MARK: - Accessibility

func ax<T>(_ el: AXUIElement, _ attr: String) -> T? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(el, attr as CFString, &value) == .success else { return nil }
    return value as? T
}

func frame(of el: AXUIElement) -> CGRect? {
    guard let p: AXValue = ax(el, kAXPositionAttribute), let s: AXValue = ax(el, kAXSizeAttribute)
    else { return nil }
    var origin = CGPoint.zero, size = CGSize.zero
    AXValueGetValue(p, .cgPoint, &origin)
    AXValueGetValue(s, .cgSize, &size)
    return CGRect(origin: origin, size: size)
}

func isPromptBox(_ el: AXUIElement) -> Bool {
    let role: String? = ax(el, kAXRoleAttribute)
    // A contenteditable comes through Chromium as AXTextArea; a plain
    // <textarea> too. Search boxes are AXTextField, which we skip.
    guard role == kAXTextAreaRole else { return false }
    guard let f = frame(of: el) else { return false }
    return f.width >= 240  // rename fields and the like are narrower
}

/// The focused element is only the text line; the rounded box Claude draws
/// around it is an ancestor a few levels up. Take the first one that adds
/// padding on top without being the whole pane.
func composerFrame(around el: AXUIElement, text: CGRect) -> CGRect {
    var node = el
    for _ in 0..<6 {
        guard let parent: AXUIElement = ax(node, kAXParentAttribute) else { break }
        node = parent
        guard let f = frame(of: node) else { continue }
        let padTop = text.minY - f.minY  // AX y grows downward
        if padTop >= 6 && f.height <= text.height + 160 && f.width <= text.width + 240 {
            return f
        }
        if f.height > text.height + 160 { break }
    }
    // No box found: assume Claude's usual 12pt of padding.
    return text.insetBy(dx: -12, dy: -12)
}

/// The Code tab draws a branch bar just above the prompt box; the badge
/// centres on it. The bar itself isn't an AX element of its own, but its
/// contents are: the branch name at the left end, Create PR at the right.
/// Hit-test both; if each finds a small control ending just above the box and
/// they share a centre line, that line is the bar's. The Chat tab has nothing
/// there (its greeting sits well higher), so both probes miss.
func barFrame(in app: AXUIElement, above box: CGRect, log: ((String) -> Void)? = nil) -> CGRect? {
    let y = box.minY - 20
    var mids: [CGFloat] = []
    var sawButton = false
    for x in [box.minX + 40, box.maxX - 60] {
        var hit: AXUIElement?
        guard AXUIElementCopyElementAtPosition(app, Float(x), Float(y), &hit) == .success, let el = hit,
              let f = frame(of: el)
        else { log?("miss"); continue }
        let role: String = ax(el, kAXRoleAttribute) ?? "?"
        log?("\(role) \(Int(f.minX)),\(Int(f.minY)) \(Int(f.width))x\(Int(f.height))")
        if role != "AXGroup", f.height <= 36, f.maxY <= box.minY, f.maxY >= box.minY - 32 {
            mids.append(f.midY)
            sawButton = sawButton || role == "AXButton"
        }
    }
    // Create PR must be one of them: transcript text right above a Chat
    // box could otherwise pass for the branch name.
    guard mids.count == 2, sawButton, abs(mids[0] - mids[1]) <= 4 else { return nil }
    let mid = (mids[0] + mids[1]) / 2
    return CGRect(x: box.minX, y: mid - 1, width: box.width, height: 2)
}

/// The address of the web page an element belongs to: the URL its enclosing
/// AXWebArea reports. Chromium, Safari and Firefox all expose it.
func pageHost(of el: AXUIElement) -> String? {
    var node = el
    for _ in 0..<40 {
        let role: String? = ax(node, kAXRoleAttribute)
        if role == "AXWebArea" {
            let url: NSURL? = ax(node, kAXURLAttribute)
            return url?.host
        }
        guard let parent: AXUIElement = ax(node, kAXParentAttribute) else { return nil }
        node = parent
    }
    return nil
}

/// AX frames are top-left-origin global coordinates; AppKit's are
/// bottom-left of the primary screen.
func toCocoa(_ r: CGRect) -> CGRect {
    let h = NSScreen.screens.first?.frame.height ?? 0
    return CGRect(x: r.minX, y: h - r.maxY, width: r.width, height: r.height)
}

// MARK: - Badge

/// A skull drawn as a shape, so it takes the clay colour and sits on the
/// badge's centre line -- the font glyph can come back as a colour emoji and
/// rides high on its baseline. Drawn in a 14pt box, y down.
func drawSkull(in r: NSRect, ink: NSColor, cutout: NSColor) {
    let s = r.width / 14
    func rect(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> NSRect {
        NSRect(x: r.minX + x * s, y: r.minY + y * s, width: w * s, height: h * s)
    }
    ink.setFill()
    NSBezierPath(ovalIn: rect(1, 0.5, 12, 10.5)).fill()                       // cranium
    NSBezierPath(roundedRect: rect(3.5, 7.5, 7, 6), xRadius: 1.6 * s, yRadius: 1.6 * s).fill()  // jaw

    cutout.setFill()
    NSBezierPath(ovalIn: rect(3.1, 4.4, 3.1, 3.3)).fill()                     // eyes
    NSBezierPath(ovalIn: rect(7.8, 4.4, 3.1, 3.3)).fill()
    let nose = NSBezierPath()
    nose.move(to: NSPoint(x: r.minX + 7 * s, y: r.minY + 8.0 * s))
    nose.line(to: NSPoint(x: r.minX + 6.2 * s, y: r.minY + 9.6 * s))
    nose.line(to: NSPoint(x: r.minX + 7.8 * s, y: r.minY + 9.6 * s))
    nose.close()
    nose.fill()
    for x in [5.55, 7.65] as [CGFloat] { NSBezierPath(rect: rect(x, 11.3, 0.8, 2.2)).fill() }  // teeth
}

final class BadgeView: NSView {
    var expanded = false
    var standing = Standing(score: nil, peak: 0)
    var onResize: (() -> Void)?

    // Metrics, in points. Everything hangs off one centre line.
    let height: CGFloat = 26
    let padX: CGFloat = 10
    let skull: CGFloat = 14
    let gapSkull: CGFloat = 6     // skull to score
    let gapRule: CGFloat = 9      // either side of a divider
    let gapDot: CGFloat = 5       // dot to band name
    let dot: CGFloat = 6

    let figure = NSFont.monospacedDigitSystemFont(ofSize: 12.5, weight: .semibold)
    let small = NSFont.systemFont(ofSize: 11.5, weight: .regular)

    override var isFlipped: Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.cornerRadius = height / 2
        layer?.borderWidth = 1
    }
    required init?(coder: NSCoder) { fatalError() }

    override func viewDidChangeEffectiveAppearance() { render() }

    private var pal: Palette { Palette.current(effectiveAppearance) }

    private struct Segment { let text: String; let font: NSFont; let colour: NSColor }

    /// The run after the skull: score, then band, then (expanded) peak, each
    /// boxed off by a hairline rule.
    private func segments() -> [[Segment]] {
        guard let s = standing.score else { return [[Segment(text: "No score yet", font: small, colour: pal.muted)]] }
        var out = [[Segment(text: "\(s)%", font: figure, colour: pal.text)],
                   [Segment(text: band(s).0, font: small, colour: pal.muted)]]
        if expanded {
            out.append([Segment(text: "Peak ", font: small, colour: pal.muted),
                        Segment(text: "\(standing.peak)%", font: figure, colour: pal.text)])
        }
        return out
    }

    private func width(_ seg: [Segment]) -> CGFloat {
        seg.reduce(0) { $0 + ($1.text as NSString).size(withAttributes: [.font: $1.font]).width }
    }

    func render() {
        layer?.backgroundColor = pal.surface.cgColor
        layer?.borderColor = pal.border.cgColor
        let segs = segments()
        var w = padX + skull + gapSkull
        for (i, seg) in segs.enumerated() {
            if i > 0 { w += gapRule * 2 + 1 }
            if i == 1 && standing.score != nil { w += dot + gapDot }
            w += width(seg)
        }
        w += padX
        setFrameSize(NSSize(width: ceil(w), height: height))
        needsDisplay = true
        onResize?()
    }

    override func draw(_ dirty: NSRect) {
        let mid = height / 2
        var x = padX
        drawSkull(in: NSRect(x: x, y: mid - skull / 2, width: skull, height: skull), ink: CLAY, cutout: pal.surface)
        x += skull + gapSkull

        for (i, seg) in segments().enumerated() {
            if i > 0 {
                x += gapRule
                pal.border.setFill()
                NSRect(x: x, y: mid - 6, width: 1, height: 12).fill()
                x += 1 + gapRule
            }
            if i == 1, let s = standing.score {
                band(s).1.setFill()
                NSBezierPath(ovalIn: NSRect(x: x, y: mid - dot / 2, width: dot, height: dot)).fill()
                x += dot + gapDot
            }
            for part in seg {
                // Centre on cap height, not the line box, so digits, the
                // skull and the dot share one optical middle.
                let baseline = mid + part.font.capHeight / 2
                let str = NSAttributedString(string: part.text, attributes: [.font: part.font, .foregroundColor: part.colour])
                str.draw(at: NSPoint(x: x, y: baseline - part.font.ascender))
                x += str.size().width
            }
        }
    }

    override func mouseDown(with event: NSEvent) {
        expanded.toggle()
        render()
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class Overlay: NSObject {
    let panel: NSPanel
    let badge = BadgeView(frame: .zero)
    var target: CGRect?
    var bar: CGRect?
    var primedPids = Set<pid_t>()

    override init() {
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        super.init()
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false  // it sits on Claude's chrome, not over content
        panel.becomesKeyOnlyIfNeeded = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.contentView = badge
        badge.onResize = { [weak self] in self?.place() }

        refreshStanding()
        Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.refreshStanding() }
    }

    func refreshStanding() {
        let s = readStanding()
        if s.score != badge.standing.score || s.peak != badge.standing.peak {
            badge.standing = s
            badge.render()
        }
    }

    func tick() {
        guard let app = NSWorkspace.shared.frontmostApplication,
              let id = app.bundleIdentifier, id == CLAUDE_BUNDLE || BROWSERS.contains(id)
        else { return hide() }
        let inBrowser = id != CLAUDE_BUNDLE

        let axApp = AXUIElementCreateApplication(app.processIdentifier)
        if !primedPids.contains(app.processIdentifier) {
            // Electron only builds its AX tree for web content on request.
            // Retried until it takes: before the grant it fails.
            let err = AXUIElementSetAttributeValue(axApp, "AXManualAccessibility" as CFString, kCFBooleanTrue)
            if err == .success { primedPids.insert(app.processIdentifier) }
        }
        var raw: CFTypeRef?
        let err = AXUIElementCopyAttributeValue(axApp, kAXFocusedUIElementAttribute as CFString, &raw)
        let focused = err == .success ? (raw as! AXUIElement) : nil
        currentApp = axApp
        trace(focused, why: "trusted=\(AXIsProcessTrusted()) axerr=\(err.rawValue)")
        guard let focused, isPromptBox(focused), let f = frame(of: focused)
        else { return hide() }
        if inBrowser {
            guard let host = pageHost(of: focused), host == "claude.ai" || host.hasSuffix(".claude.ai")
            else { return hide() }
        }

        let box = composerFrame(around: focused, text: f)
        target = toCocoa(box)
        bar = barFrame(in: axApp, above: box).map(toCocoa)
        place()
        if !panel.isVisible { panel.orderFrontRegardless() }
    }

    func place() {
        guard let t = target else { return }
        let size = badge.frame.size
        // Centred on the box. In the Code tab, vertically centred in the
        // branch bar's empty middle; elsewhere, floating just clear of the
        // box's top border.
        let y = bar.map { $0.midY - size.height / 2 } ?? t.maxY + 8
        let origin = NSPoint(x: (t.midX - size.width / 2).rounded(), y: y.rounded())
        panel.setFrame(NSRect(origin: origin, size: size), display: true)
    }

    /// Prototype diagnostics: what Chromium actually reports as focused, so a
    /// badge that never appears says why. Logs only on change.
    var lastTrace = ""
    var currentApp: AXUIElement?
    func trace(_ el: AXUIElement?, why: String) {
        var line = "focused: none (\(why))"
        if let el {
            let role: String = ax(el, kAXRoleAttribute) ?? "?"
            let sub: String = ax(el, kAXSubroleAttribute) ?? "-"
            let f = frame(of: el).map { "\(Int($0.minX)),\(Int($0.minY)) \(Int($0.width))x\(Int($0.height))" } ?? "no frame"
            line = "focused: \(role) \(sub) \(f) prompt=\(isPromptBox(el))"
            if isPromptBox(el), let t = frame(of: el) {
                let c = composerFrame(around: el, text: t)
                line += " host=\(pageHost(of: el) ?? "-")"
                line += " box=\(Int(c.minX)),\(Int(c.minY)) \(Int(c.width))x\(Int(c.height))"
                var chain: [String] = []
                let b = currentApp.flatMap { barFrame(in: $0, above: c) { chain.append($0) } }
                line += " probe=[\(chain.joined(separator: " | "))]"
                line += b.map { " bar=\(Int($0.minX)),\(Int($0.minY)) \(Int($0.width))x\(Int($0.height))" } ?? " bar=none"
            }
        }
        guard line != lastTrace else { return }
        lastTrace = line
        let path = NSString(string: "~/.claude/revenge-o-meter/overlay.log").expandingTildeInPath
        if !FileManager.default.fileExists(atPath: path) { FileManager.default.createFile(atPath: path, contents: nil) }
        if let h = FileHandle(forWritingAtPath: path) {
            h.seekToEndOfFile()
            h.write("\(Date()) \(line)\n".data(using: .utf8)!)
            h.closeFile()
        }
    }

    func hide() {
        target = nil
        bar = nil
        if panel.isVisible { panel.orderOut(nil) }
    }
}

// MARK: - Main

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
if !AXIsProcessTrustedWithOptions(opts) {
    FileHandle.standardError.write(
        "Grant Accessibility to RevengeOverlay in System Settings, then relaunch.\n".data(using: .utf8)!)
}

let overlay = Overlay()
app.run()
