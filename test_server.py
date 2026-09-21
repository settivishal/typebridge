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

print("ok")
