#!/bin/bash
# Build GSwitchBar.app (menu bar only, no Dock icon) and register it to run at login.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/GSwitchBar.app"
PLIST="$HOME/Library/LaunchAgents/com.nik.gswitchbar.plist"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O -o "$APP/Contents/MacOS/GSwitchBar" "$HERE/GSwitchBar.swift"

cat > "$APP/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key><string>GSwitchBar</string>
	<key>CFBundleDisplayName</key><string>GSwitch</string>
	<key>CFBundleIdentifier</key><string>com.nik.gswitchbar</string>
	<key>CFBundleExecutable</key><string>GSwitchBar</string>
	<key>CFBundleVersion</key><string>1.0</string>
	<key>CFBundleShortVersionString</key><string>1.0</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>LSMinimumSystemVersion</key><string>13.0</string>
	<key>LSUIElement</key><true/>
</dict>
</plist>
PLIST_EOF

codesign --force --sign - "$APP" 2>/dev/null || true
echo "built $APP"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>com.nik.gswitchbar</string>
	<key>ProgramArguments</key>
	<array><string>$APP/Contents/MacOS/GSwitchBar</string></array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "menu bar app running, and set to start at login"
