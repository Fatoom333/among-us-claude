"""Подготовка партии на ПК. Три режима:
  (по умолчанию)  ждёт лобби -> configure -> start -> ждёт phase=tasks -> autopilot для мест (партия без человека);
  --no-start      ждёт лобби -> configure -> печатает step=ready и выходит: старт и правку настроек делает человек;
  --after-start   ждёт, пока человек нажмёт старт (до --wait секунд) -> autopilot для мест; настройки не трогает.
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
mode = ap.add_mutually_exclusive_group()
mode.add_argument("--no-start", action="store_true")
mode.add_argument("--after-start", action="store_true")
mode = ap.add_mutually_exclusive_group()
mode.add_argument("--no-start", action="store_true")
mode.add_argument("--after-start", action="store_true")
a = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")


def out(ok, step, **kw):
    print(json.dumps({"ok": ok, "step": step, **kw}, ensure_ascii=False), flush=True)
    sys.exit(0 if ok else 1)


t0 = time.time()
players = []
while not a.after_start:
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
    if not a.after_start:
        r = b.call(1, "configure", impostors=a.impostors, killCooldown=25, discussion=30, voting=45,
                   commonTasks=1, shortTasks=3, longTasks=0)
        if not r.get("ok"):
            out(False, "configure", error=r.get("error"))
    if a.no_start:
        out(True, "ready", players=players, impostors=a.impostors,
            note="lobby full and configured; the human host changes settings and presses Start")
    if not a.after_start:
        r = b.call(1, "start")
        if not r.get("ok"):
            out(False, "start", error=r.get("error"))
except Exception as e:
    out(False, "bridge", error=type(e).__name__)

t1 = time.time()
phase = None
start_wait = a.wait if a.after_start else 120
while time.time() - t1 < start_wait:
    try:
        g = b.state(1).get("game") or {}
        phase = g.get("phase")
        if phase == "tasks":
            break
    except Exception:
        pass
    time.sleep(2)
else:
    out(False, "tasks", players=players, phase=phase, error=f"phase=tasks not reached in {start_wait}s")

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
