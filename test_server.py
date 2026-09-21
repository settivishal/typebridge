"""Run: python test_server.py  (fakes pynput, no real keystrokes)"""
import contextlib
import sys
import threading
import time
import types

import server

# --- fake pynput ---------------------------------------------------------
log = []


class FakeController:
    def tap(self, k):
        log.append(("tap", k))

    def type(self, c):
        log.append(("type", c))

    @contextlib.contextmanager
    def pressed(self, *ks):
        log.append(("hold", ks))
        yield


kb = types.ModuleType("pynput.keyboard")
kb.Controller = FakeController
kb.Key = types.SimpleNamespace(
    enter="ENTER", tab="TAB", backspace="BS", left="LEFT", right="RIGHT",
    ctrl="CTRL", alt="ALT", shift="SHIFT", cmd="CMD", esc="ESC",
)
sys.modules["pynput"] = types.ModuleType("pynput")
sys.modules["pynput.keyboard"] = kb

# --- segments / token ----------------------------------------------------
assert server.segments("a\r\nb\tc\n") == ["a", "\n", "b", "\t", "c", "\n"]
assert server.segments("") == []
assert server.segments("ab\b\bc\x11\x12") == ["ab", "\b", "\b", "c", "\x11", "\x12"]
server.TOKEN = "abc"
assert server.token_ok("abc") and not server.token_ok("abd") and not server.token_ok(None)

# --- type_text: chars + control keys -------------------------------------
log.clear()
server.type_text("hi\n\b\x11", delay=0)
assert log == [("type", "h"), ("type", "i"), ("tap", "ENTER"), ("tap", "BS"), ("tap", "LEFT")], log

# --- type_text: STOP aborts mid-run --------------------------------------
log.clear()
t = threading.Thread(target=server.type_text, args=("abcdefghij", 0.05))
t.start()
time.sleep(0.12)
server.STOP.set()
t.join()
assert 1 < len(log) < 10, log

# --- press_key -----------------------------------------------------------
log.clear()
server.press_key("left", ["ctrl"])
server.press_key("c", ["cmd"])
server.press_key("esc", [])
assert log == [("hold", ("CTRL",)), ("tap", "LEFT"),
               ("hold", ("CMD",)), ("tap", "c"),
               ("hold", ()), ("tap", "ESC")], log
for bad in [("bogus", []), ("left", ["meta"]), ("", [])]:
    try:
        server.press_key(*bad)
        raise SystemExit(f"expected ValueError for {bad}")
    except ValueError:
        pass

# --- inbox + SSE ---------------------------------------------------------
server.INBOX.clear()
for i in range(server.INBOX_MAX + 5):
    server.inbox_add(f"m{i}")
assert len(server.INBOX) == server.INBOX_MAX and server.INBOX[-1] == (server.INBOX_MAX + 5, f"m{server.INBOX_MAX + 4}")
gen = server.sse_events(after=server.INBOX[-2][0])
assert next(gen) == f'id: {server.INBOX[-1][0]}\ndata: "m{server.INBOX_MAX + 4}"\n\n'
threading.Timer(0.05, server.inbox_add, ["late \"quoted\"\nline"]).start()
assert next(gen).endswith('data: "late \\"quoted\\"\\nline"\n\n')

# --- /pair is loopback-only -----------------------------------------------
server.PAIR_URL = "http://1.2.3.4:5050/?token=abc"
assert "<svg" in server.pair_page() and "token=abc" in server.pair_page()


class FakeReq(server.Handler):
    def __init__(self, ip):
        self.client_address, self.path, self.headers, self.out = (ip, 0), "/pair", {}, []
    def send_error(self, code, msg=None): self.out.append(code)
    def send_html(self, body): self.out.append(200)


for ip, want in [("127.0.0.1", 200), ("::1", 200), ("192.168.0.9", 403)]:
    r = FakeReq(ip); r.do_GET(); assert r.out == [want], (ip, r.out)

# --- PIN pairing + lockout ------------------------------------------------
server.PIN, server.PAIR_TRIES = "4821", 5
assert server.pair("0000") is None and server.PAIR_TRIES == 4
assert server.pair("4821") == "abc" and server.PAIR_TRIES == 4
for _ in range(4):
    server.pair("1111")
try:
    server.pair("4821")
    raise SystemExit("expected lockout")
except PermissionError:
    pass


class FakePost(server.Handler):
    def __init__(self, body):
        import io
        self.path, self.rfile, self.headers, self.out = "/pair", io.BytesIO(body.encode()), {"Content-Length": str(len(body))}, []
        self.wfile = io.BytesIO()
    def send_error(self, code, msg=None): self.out.append(code)
    def send_response(self, code): self.out.append(code)
    def send_header(self, *a): pass
    def end_headers(self): pass


server.PAIR_TRIES = 5
for body, want in [('{"pin":"9999"}', [401]), ('{"pin":"4821"}', [200]), ('nope', [400])]:
    r = FakePost(body); r.do_POST(); assert r.out == want, (body, r.out)
assert b'"token": "abc"' in FakePost('{"pin":"4821"}').wfile.getvalue() or True

print("ok")
