# TypeBridge

Type on your phone, keystrokes land on your laptop — real simulated key presses into whatever field has focus, not clipboard paste. Works in fields that block pasting.

Laptop: Windows / macOS / Linux. Phone: iPhone or Android browser, installable as a home-screen app. Both on the same Wi-Fi.

## 1. Install (laptop)

```bash
cd typebridge
python3 -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Only dependency is [`pynput`](https://pypi.org/project/pynput/) — sends Unicode keystrokes on all three OSes, so accents, punctuation and symbols work regardless of keyboard layout.

## 2. OS-specific permissions

### macOS
- **System Settings → Privacy & Security → Accessibility** → enable the app that runs the server (Terminal, iTerm, VS Code…). Without this, keystrokes silently do nothing.
  - This is **Accessibility**, not Input Monitoring (a different pane). Open it directly: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`
  - The permission is read at launch: after enabling it, **quit and relaunch the terminal app**, then start the server again.
  - The server prints `WARNING: no Accessibility permission` on startup if it's missing.
- If macOS also asks for **Input Monitoring**, enable that too.
- First run may show a firewall prompt: **Allow** incoming connections for Python.

### Windows
- Normal apps: no admin needed.
- To type into **elevated** windows (admin PowerShell, UAC dialogs, installers), run the terminal **as Administrator** — Windows blocks input injection from a lower-privilege process.
- Windows Defender Firewall prompt on first run: allow Python on **Private** networks.

### Linux
- **X11**: works out of the box. If `pip install` fails building `python-xlib`, `sudo apt install python3-xlib` (or your distro's equivalent).
- **Wayland**: `pynput` cannot inject into native Wayland apps. Check with `echo $XDG_SESSION_TYPE`. Options: pick an **"X11 / Xorg"** session at the login screen, or target apps running under XWayland. (`ydotool` is the Wayland alternative; not wired in.)

## 3. Run

```bash
python server.py            # default port 5050 (5000 is taken by AirPlay on macOS)
python server.py --port 8080 --delay 0.02   # optional
```

Output:

```
Open on phone:  http://192.168.1.42:5050/?token=Xk3...
Ctrl-C to stop.
```

The token is generated on first run and saved in `token.txt` (stable across restarts). Override with `--token yourSecret`.

### Finding the laptop's IP manually
- macOS: `ipconfig getifaddr en0` (Wi-Fi; try `en1` if empty)
- Windows: `ipconfig` → "IPv4 Address" under your Wi-Fi adapter
- Linux: `hostname -I` or `ip -4 addr`

## 4. Use

1. Click into the field on the laptop you want to type into.
2. On the phone, open the URL from the server output (the `?token=` part saves the token in the page).
3. Type, tap **Send**. Newlines become Enter, tabs become Tab.
4. **Speed** picks the per-character delay on the laptop — useful when you paste a block and want it to appear as if typed by hand.
5. **Stop** aborts whatever the laptop is currently typing.
6. Or tick **Live** — each keystroke is sent as you type (edits anywhere in the box are replayed on the laptop with arrow keys + Backspace). **Send** then just clears the box.

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

## 6. Security — read this

- This server lets anyone who can reach it **type anything into whatever has focus on your laptop** — including a terminal. Treat it accordingly.
- Every send requires the token (`X-Token` header, constant-time compared). Wrong/missing token → 401.
- Traffic is **plain HTTP**: the token is visible to anyone sniffing your Wi-Fi. Fine on a home network you control; don't use on public/hotel/office Wi-Fi.
- Run it only while you need it (Ctrl-C). Never port-forward it or expose it beyond the LAN.
- Requests are capped at 20,000 characters and typed one at a time, so a stray send can't tie up the laptop indefinitely — but a 20k paste still takes ~3–4 minutes at the default delay — tap **Stop** on the phone to abort. Change the token (`--token` or delete `token.txt`) if you think it leaked.

## Test

```bash
python test_server.py
```
