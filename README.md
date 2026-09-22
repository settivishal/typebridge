# TypeBridge

Type on any device, text lands on another — over your Wi-Fi, no cloud.

| From \ To | **Laptop** (real keystrokes) | **Phone / any browser** (inbox + copy) |
|---|---|---|
| Phone browser | types into whatever field has focus | live feed, one-tap copy |
| Laptop browser | same (open the URL on any laptop) | live feed, one-tap copy |

- **Laptop as target**: simulated key presses via [`pynput`](https://pypi.org/project/pynput/) — works in fields that block pasting. Windows / macOS / Linux.
- **Phone as target**: browsers can't inject keys into other apps, so the page has a **Receive** mode: messages arrive live, tap **Copy**, paste anywhere. iPhone / Android / any browser.
- The server runs on one laptop (the one that should receive keystrokes, or any laptop as a relay for phone→phone).

## 1. Start (laptop)

```bash
./run.sh        # macOS / Linux
run.bat         # Windows
```

Creates `.venv`, installs deps (`pynput`, `qrcode`), starts the server. Extra args pass through: `./run.sh --port 8080 --delay 0.02`.

## 2. OS-specific permissions

### macOS
- **System Settings → Privacy & Security → Accessibility** → enable the app that runs the server (Terminal, iTerm, VS Code…). Without this, keystrokes silently do nothing.
  - This is **Accessibility**, not Input Monitoring (a different pane). Open it directly: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`
  - The permission is read at launch: after enabling it, **quit and relaunch the terminal app**, then start the server again.
  - The server prints `WARNING: no Accessibility permission` on startup and opens the pane for you if it's missing.
- If macOS also asks for **Input Monitoring**, enable that too.
- First run may show a firewall prompt: **Allow** incoming connections for Python.

### Windows
- Normal apps: no admin needed.
- To type into **elevated** windows (admin PowerShell, UAC dialogs, installers), run the terminal **as Administrator** — Windows blocks input injection from a lower-privilege process.
- Windows Defender Firewall prompt on first run: allow Python on **Private** networks.

### Linux
- **X11**: works out of the box. If `pip install` fails building `python-xlib`, `sudo apt install python3-xlib` (or your distro's equivalent).
- **Wayland**: `pynput` cannot inject into native Wayland apps. Check with `echo $XDG_SESSION_TYPE`. Options: pick an **"X11 / Xorg"** session at the login screen, or target apps running under XWayland. (`ydotool` is the Wayland alternative; not wired in.)

## 3. Pair a device

The terminal prints a QR code and two URLs:

```
Scan the QR, or open:  http://192.168.1.42:5050/?token=Xk3...
       or by name:     http://my-laptop.local:5050/?token=Xk3...
Big QR on this laptop: http://127.0.0.1:5050/pair
Phone app pairing PIN: 4821
Ctrl-C to stop.
```

Scan the QR with the phone camera (or open `/pair` in the laptop browser for a bigger one — loopback only, so nobody else on the LAN can read your token). The `?token=` part saves the token in the page, nothing to type. The `.local` name works on macOS, Windows 10+, and Linux with Avahi.

The token is generated on first run and saved in `token.txt` (stable across restarts). Override with `--token yourSecret`.

## 4. Use

1. Click into the field on the laptop you want to type into.
2. On the phone, scan the QR (section 3).
3. Type, tap **Send**. Newlines become Enter, tabs become Tab.
4. **⚙ Speed** picks the per-character delay on the laptop — useful when you paste a block and want it to appear as if typed by hand.
5. Key rows send Esc/Tab/Home/arrows/End/⌫/Del (Enter = newline in the box). Tap **Ctrl/Alt/Shift/Cmd** first to hold it for the next key (e.g. Ctrl + ← for word jump).
6. **Stop** aborts whatever the laptop is currently typing.
7. Or tap **Live** — each keystroke is sent as you type (edits anywhere in the box are replayed on the laptop with arrow keys + Backspace). **Send** becomes **Clear**.

### Sending to a phone (or any browser)

1. On the receiving device, open the same URL and tap **Receive**. It listens for messages.
2. On the sending device, **⚙ → Send to: Inbox**, type, **Send**.
3. The message appears on the receiver; tap **Copy**, paste wherever you like. The last 50 messages are kept while the server runs.

Phone→phone works the same way: both phones talk to the laptop running the server.

## 5. Install as a home-screen app (PWA)

### iPhone (Safari)
Open the URL **with `?token=`** in Safari → Share → **Add to Home Screen** → Add. Opens full-screen, no browser chrome. (The home-screen app has its own storage, so open it via the token URL, or paste the token into the token field once inside the app.)

### Android (Chrome)
Chrome only offers a real "Install app" on HTTPS. This server is plain HTTP on a LAN IP, so do a one-time flag change:

1. Open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. Set to **Enabled** and enter `http://<laptop-ip>:5050`
3. Relaunch Chrome, open the URL with `?token=`
4. Menu ⋮ → **Install app** (or **Add to Home screen**)

Without the flag, "Add to Home screen" still works but opens as a normal browser tab.

## 6. Phone app (finds the laptop by itself)

No QR, no IP: the app lists every laptop on the Wi-Fi running TypeBridge (mDNS `_typebridge._tcp`), you tap one, type the 4-digit PIN from the terminal once, and it opens the same web UI. Thin [Capacitor](https://capacitorjs.com) shell around the existing page — `app/www/index.html` is the whole app.

```bash
cd app
npm install
npx cap sync
npx cap open ios       # Xcode → pick your iPhone → Run (free Apple ID works; re-sign every 7 days)
npx cap open android   # Android Studio → Run on a real device (emulators don't see LAN mDNS)
```

Requirements: Node 18+, Xcode + CocoaPods (`brew install cocoapods`) for iOS, Android Studio for Android.

iPhone, first time: plug in via USB, tap **Trust**, enable **Settings → Privacy & Security → Developer Mode** (reboots). First app launch asks for **Local Network** permission — allow it (otherwise no laptops are found; fix later under Settings → Apps → TypeBridge). Without Xcode's GUI you can also build + install from the terminal:

```bash
xcrun devicectl list devices                      # get your iPhone's UDID
xcodebuild -workspace ios/App/App.xcworkspace -scheme App -destination 'id=<UDID>' -allowProvisioningUpdates build
xcrun devicectl device install app --device <UDID> ~/Library/Developer/Xcode/DerivedData/App-*/Build/Products/Debug-iphoneos/App.app
```

- The PIN pairs as soon as the 4th digit is typed. PIN changes every server start; 5 wrong tries lock pairing until restart. Already-paired phones keep working (they hold the token).
- Paired laptops stay in the list when offline (greyed); tap to retry. **✕ → Forget?** unpairs. The app auto-reconnects to the last laptop on open.
- **⇄ Laptop** in the top bar goes back to the list.
- **Connect by address** (`ip:port`) for networks that block mDNS (some corporate/guest Wi-Fi).
- `app/www/capacitor.js` is a copy of `@capacitor/core`'s browser bundle (no bundler in this project); refresh it after `npm update`.

## 7. Security — read this

- This server lets anyone who can reach it **type anything into whatever has focus on your laptop** — including a terminal. Treat it accordingly.
- The app pairs with a 4-digit PIN (per run, 5 attempts) and receives the token; after that, every request requires the token (`X-Token` header; `?token=` query for the `/inbox` event stream), constant-time compared. Wrong/missing token → 401.
- Inbox messages are held in memory (last 50) and visible to anyone with the token; they vanish when the server stops.
- Traffic is **plain HTTP**: the token is visible to anyone sniffing your Wi-Fi. Fine on a home network you control; don't use on public/hotel/office Wi-Fi.
- Run it only while you need it (Ctrl-C). Never port-forward it or expose it beyond the LAN.
- Requests are capped at 20,000 characters and typed one at a time, so a stray send can't tie up the laptop indefinitely — but a 20k paste still takes ~3–4 minutes at the default delay — tap **Stop** on the phone to abort. Change the token (`--token` or delete `token.txt`) if you think it leaked.

## Test

```bash
python test_server.py
```
