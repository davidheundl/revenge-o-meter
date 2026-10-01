#!/bin/sh
# Builds RevengeOverlay.app next to this script. A real .app bundle (not a bare
# binary) so the Accessibility grant attaches to it, not to whichever terminal
# launched it. Ad-hoc signed: every rebuild changes the signature, so macOS
# will ask for Accessibility again after each one.
set -e
cd "$(dirname "$0")"
APP=build/RevengeOverlay.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O -swift-version 5 -o "$APP/Contents/MacOS/RevengeOverlay" main.swift
cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>dev.revenge-o-meter.overlay</string>
  <key>CFBundleName</key><string>RevengeOverlay</string>
  <key>CFBundleExecutable</key><string>RevengeOverlay</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
EOF
codesign --force --sign - "$APP"
echo "built $APP"
