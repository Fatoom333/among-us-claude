"""Подготовка партии на ПК (запускает «крупье»): ждёт лобби -> configure -> autopilot для мест -> start -> ждёт phase=tasks.
Токены читает bridgecli.py из файлов, на экран не выводит.
Запуск (на ПК):  python D:/AmongUs-tools/setup_game.py --impostors 2 --autopilot 2,3 [--expect 10] [--wait 420]
Печатает одну строку JSON: {"ok":bool,"step":...,"players":[...],...}
"""
import argparse
import json
import sys
import time

sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b

ap = argparse.ArgumentParser()
ap.add_argument("--expect", type=int, default=10)
ap.add_argument("--impostors", type=int, default=2)
ap.add_argument("--autopilot", default="")
ap.add_argument("--wait", type=int, default=420)
a = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")


def out(ok, step, **kw):
    print(json.dumps({"ok": ok, "step": step, **kw}, ensure_ascii=False), flush=True)
    sys.exit(0 if ok else 1)


t0 = time.time()
players = []
while True:
    try:
        st = b.state(1)
        players = [x["name"] for x in st.get("players", [])]
        if st.get("stage") == "lobby" and len(players) >= a.expect:
            break
    except Exception:
        pass
    if time.time() - t0 > a.wait:
        out(False, "lobby", players=players, error="timeout waiting for lobby")
    time.sleep(3)

try:
    r = b.call(1, "configure", impostors=a.impostors, killCooldown=25, discussion=30, voting=45,
               commonTasks=1, shortTasks=3, longTasks=0)
    if not r.get("ok"):
        out(False, "configure", error=r.get("error"))
    r = b.call(1, "start")
    if not r.get("ok"):
        out(False, "start", error=r.get("error"))
except Exception as e:
    out(False, "bridge", error=type(e).__name__)

t1 = time.time()
phase = None
while time.time() - t1 < 120:
    try:
        g = b.state(1).get("game") or {}
        phase = g.get("phase")
        if phase == "tasks":
            break
    except Exception:
        pass
    time.sleep(2)
else:
    out(False, "tasks", players=players, phase=phase, error="phase=tasks not reached in 120s")

# автопилот можно включить только когда корабль уже создан
seats = [int(x) for x in a.autopilot.split(",") if x.strip()]
pending = set(seats)
t2 = time.time()
while pending and time.time() - t2 < 60:
    for s in sorted(pending):
        try:
            if b.call(s, "autopilot", on=True).get("ok"):
                pending.discard(s)
        except Exception:
            pass
    time.sleep(1)
if pending:
    out(False, "autopilot", seats=sorted(pending), error="autopilot not enabled")
out(True, "playing", players=players, impostors=a.impostors, phase=phase, autopilot=seats)
