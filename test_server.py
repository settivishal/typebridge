import server

assert server.segments("a\r\nb\tc\n") == ["a", "\n", "b", "\t", "c", "\n"]
assert server.segments("") == []
assert server.segments("ab\b\bc\x11\x12") == ["ab", "\b", "\b", "c", "\x11", "\x12"]
server.TOKEN = "abc"
assert server.token_ok("abc") and not server.token_ok("abd") and not server.token_ok(None)
print("ok")
