#!/usr/bin/env python3
"""TypeBridge: phone -> laptop keystroke relay. Run: python server.py"""
import argparse
import hmac
import json
import re
import secrets
import socket
import sys
import threading
import time
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


def token_ok(header):
    return bool(header) and hmac.compare_digest(header, TOKEN)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def do_POST(self):
        if self.path not in ("/type", "/stop"):
            return self.send_error(404)
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
            text, delay = body["text"], body.get("delay")
            if delay is not None:
                float(delay)
        except (ValueError, KeyError, TypeError):
            return self.send_error(400, "expected JSON {\"text\": ..., \"delay\": seconds?}")
        if not isinstance(text, str) or len(text) > MAX_CHARS:
            return self.send_error(413, f"max {MAX_CHARS} chars")
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


def main():
    global TOKEN, DELAY
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5050)
    p.add_argument("--token", help="shared secret (default: token.txt, auto-created)")
    p.add_argument("--delay", type=float, default=DELAY, help="default seconds between keystrokes (client can override per request)")
    a = p.parse_args()
    TOKEN, DELAY = load_token(a.token), a.delay
    if sys.platform == "darwin":
        # pynput silently no-ops without Accessibility permission
        import ctypes
        ax = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        if not ax.AXIsProcessTrusted():
            print("WARNING: no Accessibility permission. System Settings > Privacy & Security > "
                  "Accessibility > enable your terminal app, then quit and relaunch it.")
    print(f"Open on phone:  http://{local_ip()}:{a.port}/?token={TOKEN}")
    print("Ctrl-C to stop.", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
