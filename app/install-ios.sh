#!/bin/sh
# Rebuild and reinstall the app on the plugged-in iPhone (free Apple ID builds expire after 7 days).
set -e
cd "$(dirname "$0")"
UDID=$(xcrun devicectl list devices 2>/dev/null | grep physical | grep -oE '[0-9A-F]{8}-[0-9A-F]{16}' | head -1)
[ -n "$UDID" ] || { echo "no iPhone connected (USB, unlocked, trusted)"; exit 1; }
npx cap sync ios
xcodebuild -workspace ios/App/App.xcworkspace -scheme App -destination "id=$UDID" -allowProvisioningUpdates -quiet build
APP=$(ls -td ~/Library/Developer/Xcode/DerivedData/App-*/Build/Products/Debug-iphoneos/App.app | head -1)
xcrun devicectl device install app --device "$UDID" "$APP"
xcrun devicectl device process launch --device "$UDID" --terminate-existing dev.typebridge.app
