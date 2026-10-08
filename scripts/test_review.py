"""Review checks (v0.4.1): auth is mandatory, nav debug input is strict, probe hides players, sabotage cooldown hidden from crew."""
import json, socket, sys
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b

sys.stdout.reconfigure(encoding="utf-8")


def raw(i, msg):
    s = socket.create_connection(("127.0.0.1", 47000 + i), timeout=5)
    s.sendall((json.dumps(msg) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        data += s.recv(65536)
    s.close()
    return json.loads(data)


def ok(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label, extra if not cond else "", flush=True)


ok("no token -> unauthorized", raw(1, {"cmd": "state"}).get("error") == "unauthorized")
ok("wrong token -> unauthorized", raw(1, {"cmd": "state", "token": "x" * 64}).get("error") == "unauthorized")
r = b.call(1, "nav", mask="nt..\\..\\x")
ok("nav mask traversal refused", r.get("ok") is False, r)
r = b.call(1, "nav", mask="nt4608")
ok("nav mask nt4608 accepted", r.get("ok") is True, r)
r = b.call(1, "nav", probe=[0, 0], r=50)
ok("probe radius capped", r.get("ok") is False, r)
# probe right on top of another player: no Player colliders in the answer
g2 = b.state(2)["game"]["me"]["pos"]
r = b.call(1, "nav", probe=g2, r=1)
names = r.get("probe") or []
ok("probe hides players", r.get("ok") and not any("layer=8" in x for x in names), names)
for i in (1, 2, 3, 4):
    g = b.state(i)["game"]
    role = g["me"]["role"]
    cd = g["sabotage"]["cooldown"]
    print(f"[{i}] role={role} sabotage.cooldown={cd} visible={[v['name'] for v in g['visible']]}")
