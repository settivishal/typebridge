#!/usr/bin/env python3
"""TypeBridge: any browser -> this laptop's keyboard, or -> any browser's inbox. Run: ./run.sh"""
import argparse
import hmac
import html
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
TOKEN_FILE = HERE / "token.txt"
MAX_CHARS = 20_000

TOKEN = ""
DELAY = 0.01
LOCK = threading.Lock()  # ponytail: one typing job at a time, no queue
STOP = threading.Event()  # set by POST /stop; aborts the current typing job

# Inbox: messages for browsers in Receive mode (phones can't inject keys, so they copy instead).
INBOX = []  # [(id, text)], newest last, capped
INBOX_MAX = 50
COND = threading.Condition()
PAIR_URL = ""
PIN = ""  # 4-digit app pairing code, new each run
PAIR_TRIES = 5  # wrong PINs left before pairing locks until restart


# Control chars the client may embed in text; everything else is typed literally.
KEYS = {"\n": "enter", "\t": "tab", "\x08": "backspace", "\x11": "left", "\x12": "right"}
SPLIT = re.compile("([%s])" % "".join(KEYS))


def segments(text):
    """Split into typed runs and control keys: 'a\\r\\nb\\tc' -> ['a','\\n','b','\\t','c']."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [s for s in SPLIT.split(text) if s]


def type_text(text, delay=None):
    from pynput.keyboard import Controller, Key

    delay = DELAY if delay is None else min(max(float(delay), 0), 1)
    kb = Controller()
    STOP.clear()
    for seg in segments(text):
        if seg in KEYS:
            kb.tap(getattr(Key, KEYS[seg]))
        else:
            for ch in seg:
                if STOP.is_set():
                    return
                kb.type(ch)
                time.sleep(delay)


MODS = ("ctrl", "alt", "shift", "cmd")


def press_key(name, mods):
    """Tap one key (pynput Key name like 'left', 'esc', 'f5', or a single char) with modifiers held."""
    from pynput.keyboard import Controller, Key

    key = name if len(name) == 1 else getattr(Key, name, None)
    if not key or any(m not in MODS for m in mods):
        raise ValueError(name)
    kb = Controller()
    with kb.pressed(*[getattr(Key, m) for m in mods]):
        kb.tap(key)


def token_ok(header):
    return bool(header) and hmac.compare_digest(header, TOKEN)


def pair(pin):
    """Return TOKEN for the right PIN, None for wrong; raises PermissionError once locked."""
    global PAIR_TRIES
    if PAIR_TRIES <= 0:
        raise PermissionError
    if hmac.compare_digest(str(pin), PIN):
        return TOKEN
    PAIR_TRIES -= 1
    return None


def inbox_add(text):
    with COND:
        INBOX.append(((INBOX[-1][0] + 1) if INBOX else 1, text))
        del INBOX[:-INBOX_MAX]
        COND.notify_all()


def sse_events(after):
    """Yield SSE frames for inbox entries with id > after, then block; ': ping' on 20 s idle."""
    while True:
        with COND:
            new = [(i, t) for i, t in INBOX if i > after]
            if not new and not COND.wait(20):
                yield ": ping\n\n"
                continue
        for i, t in new:
            after = i
            yield f"id: {i}\ndata: {json.dumps(t)}\n\n"


def qr_svg(url):
    import qrcode
    import qrcode.image.svg

    return qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12).to_string().decode()


def pair_page():
    return f"""<!doctype html><meta charset=utf-8><title>Pair TypeBridge</title>
<body style="margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
gap:24px;background:#111827;color:#e5e7eb;font:18px system-ui">
<h1 style="margin:0">Scan with your phone</h1>
<div style="background:#fff;padding:16px;border-radius:16px">{qr_svg(PAIR_URL)}</div>
<code style="font-size:15px;user-select:all">{html.escape(PAIR_URL)}</code></body>"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def end_headers(self):
        # The phone app's WebView origin is capacitor://localhost (iOS) / http://localhost (Android).
        if self.headers.get("Origin") in ("capacitor://localhost", "http://localhost"):
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        super().end_headers()

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/ping":
            self.send_response(204)
            return self.end_headers()
        if url.path == "/pair":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                return self.send_error(403, "open /pair on the laptop itself")
            return self.send_html(pair_page())
        if url.path == "/inbox":
            q = parse_qs(url.query)
            if not token_ok(q.get("token", [""])[0]):
                return self.send_error(401, "bad token")
            after = int(q.get("after", [self.headers.get("Last-Event-ID") or 0])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for frame in sse_events(after):
                    self.wfile.write(frame.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        return super().do_GET()

    def send_html(self, body):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in ("/type", "/stop", "/key", "/pair"):
            return self.send_error(404)
        if self.path == "/pair":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                token = pair(body["pin"])
            except (ValueError, KeyError, TypeError):
                return self.send_error(400, "expected JSON {\"pin\": \"1234\"}")
            except PermissionError:
                return self.send_error(423, "pairing locked; restart the server")
            if not token:
                return self.send_error(401, "wrong PIN")
            data = json.dumps({"token": token}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if not token_ok(self.headers.get("X-Token")):
            return self.send_error(401, "bad token")
        if self.path == "/stop":
            STOP.set()
            self.send_response(204)
            return self.end_headers()
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_CHARS * 4:
            return self.send_error(413)
        try:
            body = json.loads(self.rfile.read(length))
            if self.path == "/key":
                with LOCK:
                    press_key(str(body["key"]), [str(m) for m in body.get("mods", [])])
                self.send_response(204)
                return self.end_headers()
            text, delay, to = body["text"], body.get("delay"), body.get("to", "keys")
            if delay is not None:
                float(delay)
        except (ValueError, KeyError, TypeError, AttributeError):
            return self.send_error(400, "expected JSON {\"text\": ..., \"delay\": seconds?, \"to\": \"keys\"|\"inbox\"} or {\"key\": ..., \"mods\": [...]}")
        if not isinstance(text, str) or len(text) > MAX_CHARS:
            return self.send_error(413, f"max {MAX_CHARS} chars")
        if to == "inbox":
            inbox_add(text)
        else:
            with LOCK:
                type_text(text, delay)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        if self.command == "POST":
            super().log_message(fmt, *args)


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packet sent; picks the LAN-facing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def load_token(cli):
    if cli:
        return cli
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    t = secrets.token_urlsafe(16)
    TOKEN_FILE.write_text(t)
    return t


def check_platform():
    if sys.platform == "darwin":
        # pynput silently no-ops without Accessibility permission
        import ctypes
        ax = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        if not ax.AXIsProcessTrusted():
            print("WARNING: no Accessibility permission. Opening the pane: enable your terminal app "
                  "(iTerm/Terminal/VS Code), then quit and relaunch it.")
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
    elif sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("WARNING: Wayland session. Keystrokes only reach XWayland apps; log in with an X11 session for full support.")


def advertise(port):
    """Announce _typebridge._tcp on the LAN so the phone app can list this laptop. Returns (zc, info)."""
    from zeroconf import ServiceInfo, Zeroconf

    host = socket.gethostname().split(".")[0]
    info = ServiceInfo("_typebridge._tcp.local.", f"{host}._typebridge._tcp.local.",
                       addresses=[socket.inet_aton(local_ip())], port=port, properties={"name": host})
    zc = Zeroconf()
    zc.register_service(info)
    return zc, info


def print_qr(url):
    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)


def main():
    global TOKEN, DELAY, PAIR_URL, PIN
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5050)
    p.add_argument("--token", help="shared secret (default: token.txt, auto-created)")
    p.add_argument("--delay", type=float, default=DELAY, help="default seconds between keystrokes (client can override per request)")
    a = p.parse_args()
    TOKEN, DELAY = load_token(a.token), a.delay
    check_platform()
    PAIR_URL = f"http://{local_ip()}:{a.port}/?token={TOKEN}"
    print_qr(PAIR_URL)
    print(f"Scan the QR, or open:  {PAIR_URL}")
    print(f"       or by name:     http://{socket.gethostname().split('.')[0]}.local:{a.port}/?token={TOKEN}")
    print(f"Big QR on this laptop: http://127.0.0.1:{a.port}/pair")
    PIN = f"{secrets.randbelow(10000):04d}"
    print(f"Phone app pairing PIN: {PIN}")
    print("Ctrl-C to stop.", flush=True)
    zc, info = advertise(a.port)
    try:
        ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        zc.unregister_service(info)
        zc.close()


if __name__ == "__main__":
    main()
