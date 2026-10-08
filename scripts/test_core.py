"""Step 'Core' live test on N copies: wait lobby -> configure(impostors=1) -> start -> check state/events. Run on the PC."""
import json, sys, time, threading
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b

N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
sys.stdout.reconfigure(encoding="utf-8")
ids = list(range(1, N + 1))

def p(*a): print(*a, flush=True)

t0 = time.time()
while True:
    try:
        st = b.state(1)
        if st.get("stage") == "lobby" and len(st.get("players", [])) >= N:
            break
    except Exception as e:
        pass
    if time.time() - t0 > 400:
        p("TIMEOUT waiting for lobby"); sys.exit(2)
    time.sleep(3)
p("lobby ready, players:", [x["name"] for x in st["players"]], "after %.0fs" % (time.time() - t0))

r = b.call(1, "configure", impostors=1, killCooldown=10, discussion=5, voting=20, commonTasks=0, shortTasks=2, longTasks=0)
p("configure ->", r.get("ok"), r.get("error"), json.dumps(r.get("options")))
r = b.call(1, "configure", impostors=9)
p("configure bad ->", r)
r = b.call(1, "start")
p("start ->", r.get("ok"), r.get("error"), "stage", r.get("stage"))

evs = {i: [] for i in ids}
seqs = {i: 0 for i in ids}
stop = False
def poll(i):
    while not stop:
        try:
            r = b._wait(i, seqs[i], 5)
            if r.get("ok"):
                seqs[i] = r["seq"]; evs[i] += r["events"]
        except Exception as e:
            time.sleep(1)
ths = [threading.Thread(target=poll, args=(i,), daemon=True) for i in ids]
for t in ths: t.start()

t0 = time.time(); got = {}
while time.time() - t0 < 90:
    for i in ids:
        try:
            g = b.state(i).get("game")
        except Exception:
            g = None
        if g and g.get("me") and g["phase"] == "tasks" and i not in got:
            got[i] = g
    if len(got) == N: break
    time.sleep(2)
p("seats in game:", sorted(got), "after %.0fs" % (time.time() - t0))
roles = {i: g["me"]["role"] for i, g in got.items()}
p("roles:", roles, "impostors:", sum(1 for r in roles.values() if r == "impostor"))
for i, g in sorted(got.items()):
    m = g["me"]
    p(f"[{i}] {m['name']} role={m['role']} partner={m['partner']} room={m['room']} pos={m['pos']} tasks={len(g['tasks'])} "
      f"light={g['lightRadius']}/{g['lightView']} visible={[v['name'] for v in g['visible']]} intro={g['intro']} canMove={g['canMove']}")
    for t in g["tasks"][:3]: p("     task", json.dumps(t))
# --- protocol checks
import socket
def raw(i, line):
    s = socket.create_connection(("127.0.0.1", 47000 + i), timeout=10); s.sendall((line + chr(10)).encode()); d = s.recv(65536); s.close(); return d.decode()[:120]
p("unauthorized:", raw(2, '{"cmd":"state","token":"x"}'))
tk = b.token(2)
p("bad timeout:", raw(2, json.dumps({"cmd": "wait_event", "token": tk, "timeout": "x"})))
p("bad since:", raw(2, json.dumps({"cmd": "wait_event", "token": tk, "since": "x"})))
p("configure on non-host:", b.call(2, "configure", impostors=1))
p("start on non-host:", b.call(2, "start"))
cur = seqs[2]
lat = []
def longpoll():
    t = time.time(); r = b._wait(2, cur + 1000, 4); p("empty wait took %.1fs events=%d" % (time.time() - t, len(r["events"])))
th = threading.Thread(target=longpoll); th.start()
for _ in range(8):
    t = time.time(); b.state(2); lat.append(time.time() - t); time.sleep(0.4)
th.join()
p("state latency during long-poll: max %.3fs avg %.3fs" % (max(lat), sum(lat) / len(lat)))
time.sleep(10)
stop = True
for i in ids:
    p(f"--- events seat {i}")
    for e in evs[i]: p("   ", json.dumps(e, ensure_ascii=False))
