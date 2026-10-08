"""Step 'Move' live tests on N copies (run on the PC). Phases are independent so the game can be reused:
  python test_move.py setup  4      lobby -> configure -> start -> everybody in game, prints roles/nav
  python test_move.py moves  4      move_to Electrical / MedBay (timing), return
  python test_move.py leak   4      A stays in Cafeteria, B walks to Electrical and back: visibility + lost_player/saw_player
  python test_move.py tasks  4      do_task x2 on a crew seat, watch taskBar from another seat
  python test_move.py follow 4      one seat follows another that walks around
  python test_move.py auto   4 [s]  autopilot on all seats for s seconds
"""
import json, sys, time, threading
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b

sys.stdout.reconfigure(encoding="utf-8")
PH = sys.argv[1] if len(sys.argv) > 1 else "setup"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 4
IDS = list(range(1, N + 1))


def p(*a):
    print(*a, flush=True)


def st(i):
    try:
        return b.state(i)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def game(i):
    return (st(i) or {}).get("game") or {}


def me(i):
    return game(i).get("me") or {}


def act(i, **kw):
    return b.call(i, "act", **kw)


def roles():
    return {i: me(i).get("role") for i in IDS}


class Ev:
    """background long-poll collector per seat"""
    def __init__(self):
        self.ev = {i: [] for i in IDS}
        self.seq = {i: 0 for i in IDS}
        self.stop = False
        for i in IDS:
            threading.Thread(target=self.run, args=(i,), daemon=True).start()

    def run(self, i):
        # start from the current end of the buffer
        try:
            self.seq[i] = b._wait(i, 10**9, 0).get("seq", 0)
        except Exception:
            pass
        while not self.stop:
            try:
                r = b._wait(i, self.seq[i], 3)
                if r.get("ok"):
                    self.seq[i] = r["seq"]
                    for e in r["events"]:
                        e["_at"] = time.time()
                        self.ev[i].append(e)
            except Exception:
                time.sleep(0.5)

    def find(self, i, typ, after=0, **kw):
        for e in self.ev[i]:
            if e["type"] == typ and e["_at"] >= after and all(e.get(k) == v for k, v in kw.items()):
                return e
        return None

    def wait(self, i, typ, timeout, after=None, **kw):
        after = after or time.time() - 0.01
        t0 = time.time()
        while time.time() - t0 < timeout:
            e = self.find(i, typ, after, **kw)
            if e:
                return e
            time.sleep(0.1)
        return None


def setup():
    t0 = time.time()
    while True:
        s = st(1)
        if s.get("stage") == "lobby" and len(s.get("players", [])) >= N:
            break
        if s.get("stage") == "ingame":
            p("already in game"); break
        if time.time() - t0 > 400:
            p("TIMEOUT lobby"); sys.exit(2)
        time.sleep(3)
    p("lobby ready after %.0fs" % (time.time() - t0))
    if st(1).get("stage") == "lobby":
        r = b.call(1, "configure", impostors=1, killCooldown=30, discussion=5, voting=20, commonTasks=0, shortTasks=3, longTasks=0)
        p("configure ->", r.get("ok"), r.get("error"))
        r = b.call(1, "start"); p("start ->", r.get("ok"), r.get("error"))
    t0 = time.time()
    while time.time() - t0 < 120:
        g = {i: game(i) for i in IDS}
        if all(x.get("phase") == "tasks" and x.get("canMove") for x in g.values()):
            break
        time.sleep(1)
    p("all can move after %.0fs" % (time.time() - t0))
    time.sleep(3)
    for i in IDS:
        s = st(i); g = s.get("game") or {}
        m = g.get("me") or {}
        p(f"[{i}] {m.get('name')} role={m.get('role')} room={m.get('room')} pos={m.get('pos')} nav={g.get('body', {}).get('navStatus')} tasks={[(t['id'], t['name'], t['room']) for t in g.get('tasks', [])]}")
    r = b.call(1, "nav", dump=True); p("nav dump ->", r)


def walk(i, ev, **kw):
    t0 = time.time()
    r = act(i, do="move_to", **kw)
    if not r.get("ok"):
        p(f"  [{i}] move_to {kw} REFUSED: {r}")
        return None
    e = ev.wait(i, "arrived", 90, after=t0 - 0.01)
    s = None
    if e is None:
        e = ev.find(i, "stuck", t0)
        m = me(i)
        p(f"  [{i}] move_to {kw} FAILED ({'stuck' if e else 'timeout'}) at {m.get('pos')} room={m.get('room')} body={game(i).get('body')}")
        return None
    dt = time.time() - t0
    m = me(i)
    p(f"  [{i}] move_to {kw} OK in {dt:.1f}s -> room={m.get('room')} pos={m.get('pos')}")
    return dt


def moves():
    ev = Ev(); time.sleep(1)
    cr = [i for i in IDS if me(i).get("role") != "impostor"] or IDS
    a, c = cr[0], cr[1] if len(cr) > 1 else cr[0]
    ths = []
    res = {}
    def go(i, room):
        res[(i, room)] = walk(i, ev, room=room)
    for i, room in ((a, "Electrical"), (c, "MedBay")):
        th = threading.Thread(target=go, args=(i, room)); th.start(); ths.append(th)
    for th in ths: th.join()
    # and back to the cafeteria, then a point
    ths = []
    for i in (a, c):
        th = threading.Thread(target=go, args=(i, "Cafeteria")); th.start(); ths.append(th)
    for th in ths: th.join()
    p("results:", {f"{k[0]}->{k[1]}": (round(v, 1) if v else v) for k, v in res.items()})
    # bad args
    p("bad room:", act(a, do="move_to", room="Narnia"))
    p("bad pos:", act(a, do="move_to", pos=[1]))
    p("unsupported:", act(a, do="kill", target="x"))
    ev.stop = True


def leak():
    ev = Ev(); time.sleep(1)
    cr = [i for i in IDS if me(i).get("role") != "impostor"] or IDS
    A, B = cr[0], cr[1]
    for i in IDS:
        if i not in (A, B):
            act(i, do="stay")
    act(A, do="stay")
    walk(A, ev, room="Cafeteria"); walk(B, ev, room="Cafeteria")
    time.sleep(1.5)
    nameA, nameB = me(A).get("name"), me(B).get("name")
    gA, gB = game(A), game(B)
    p(f"start: A sees {[v['name'] for v in gA['visible']]} ; B sees {[v['name'] for v in gB['visible']]}")
    t0 = time.time()
    act(B, do="move_to", room="Electrical")
    gone_at = None; seenA = []; seenB_of_A = []
    t_arr = None
    while time.time() - t0 < 90:
        va = [v["name"] for v in game(A).get("visible", [])]
        vb = [v["name"] for v in game(B).get("visible", [])]
        inroom = me(B).get("room")
        seenA.append((round(time.time() - t0, 1), nameB in va, inroom))
        if nameB not in va and gone_at is None:
            gone_at = time.time() - t0
        if inroom == "Electrical":
            seenB_of_A.append(nameA in vb)
            if t_arr is None:
                t_arr = time.time() - t0
            if time.time() - t0 > t_arr + 4:
                break
        time.sleep(0.4)
    lost = ev.find(A, "lost_player", t0, name=nameB)
    p(f"B left A's view after {gone_at}s; lost_player event: {lost}")
    p(f"B in Electrical: A visible to B at any sample? {any(seenB_of_A)} ({len(seenB_of_A)} samples)")
    # leak scan: while B was in Electrical (far from A), was B ever visible to A?
    leaked = [x for x in seenA if x[2] == "Electrical" and x[1]]
    p("LEAK samples (B in Electrical but listed in A.visible):", leaked)
    t1 = time.time()
    act(B, do="move_to", room="Cafeteria")
    sa = ev.wait(A, "saw_player", 60, name=nameB, after=t1)
    p("B back: A saw_player event:", sa)
    p("A.visible now:", [v["name"] for v in game(A).get("visible", [])])
    ev.stop = True


def taskbar(i):
    return game(i).get("taskBar")


def tasks():
    ev = Ev(); time.sleep(1)
    cr = [i for i in IDS if me(i).get("role") != "impostor"] or IDS
    A = cr[0]; O = [i for i in IDS if i != A][0]
    gA = game(A)
    p("A tasks:", [(t["id"], t["name"], t["room"], t["pos"], t["done"], t.get("step"), t.get("steps")) for t in gA["tasks"]])
    p("taskBar before: A", taskbar(A), "other", taskbar(O))
    done = 0
    for n in range(2):
        t0 = time.time()
        r = act(A, do="do_task", next=True)
        p(f"do_task #{n+1} ->", r)
        if not r.get("ok"):
            break
        e = ev.wait(A, "task_done", 120, after=t0 - 0.01)
        dt = time.time() - t0
        time.sleep(1.5)
        p(f"  task_done event: {e} after {dt:.1f}s; taskBar A={taskbar(A)} other={taskbar(O)}; tasks done: {[t['done'] for t in game(A)['tasks']]}")
        if e: done += 1
    p("tasks completed via events:", done)
    ev.stop = True


def follow():
    ev = Ev(); time.sleep(1)
    cr = [i for i in IDS]
    L, F = cr[0], cr[1]
    walk(L, ev, room="Cafeteria"); walk(F, ev, room="Cafeteria")
    nameL = me(L).get("name")
    # F follows L (L must be visible)
    r = act(F, do="follow", target=nameL, distance=1.5)
    p("follow ->", r)
    t0 = time.time()
    act(L, do="move_to", room="Storage")
    dists = []
    while time.time() - t0 < 70:
        mL, mF = me(L), me(F)
        if mL.get("pos") and mF.get("pos"):
            d = ((mL["pos"][0] - mF["pos"][0]) ** 2 + (mL["pos"][1] - mF["pos"][1]) ** 2) ** 0.5
            dists.append((round(time.time() - t0, 1), round(d, 2), mL.get("room"), mF.get("room")))
        if ev.find(L, "arrived", t0) and time.time() - t0 > 5:
            time.sleep(4)
            break
        time.sleep(1)
    p("dist samples (t, dist, roomL, roomF):", dists[::3])
    p("final F room:", me(F).get("room"), "busy:", game(F).get("busy"), "events F:", [e["type"] for e in ev.ev[F] if e["_at"] > t0])
    # lose-sight test: L goes far while F is stopped?  F keeps following; make L run to MedBay
    act(L, do="move_to", room="MedBay")
    time.sleep(25)
    p("after L ran to MedBay: F room", me(F).get("room"), "busy", game(F).get("busy"), "events F:", [e["type"] for e in ev.ev[F] if e["_at"] > t0])
    ev.stop = True


def follow2():
    ev = Ev(); time.sleep(1)
    L, F = 1, 2
    walk(L, ev, room="Cafeteria"); walk(F, ev, room="Cafeteria")
    nameL = me(L).get("name")
    p("follow ->", act(F, do="follow", target=nameL, distance=1.5))
    p("wander ->", act(L, do="wander"))
    t0 = time.time(); rows = []
    while time.time() - t0 < 60:
        mL, mF = me(L), me(F)
        d = ((mL["pos"][0] - mF["pos"][0]) ** 2 + (mL["pos"][1] - mF["pos"][1]) ** 2) ** 0.5
        rows.append((round(time.time() - t0), round(d, 1), mL.get("room"), mF.get("room"), game(F).get("busy")))
        time.sleep(1.5)
    p("samples (t, dist, roomL, roomF, busyF):")
    for r in rows: p("  ", r)
    ds = [r[1] for r in rows]
    p("max dist %.1f, median %.1f; lost_sight events: %d; stuck: %d" % (max(ds), sorted(ds)[len(ds)//2], sum(1 for e in ev.ev[F] if e["type"] == "lost_sight"), sum(1 for i in IDS for e in ev.ev[i] if e["type"] == "stuck")))
    act(L, do="stay"); act(F, do="stay")
    ev.stop = True


def auto():
    secs = int(sys.argv[3]) if len(sys.argv) > 3 else 90
    ev = Ev(); time.sleep(1)
    for i in IDS:
        p(f"autopilot {i}:", b.call(i, "autopilot", on=True))
    t0 = time.time()
    pos = {i: [] for i in IDS}
    while time.time() - t0 < secs:
        for i in IDS:
            m = me(i); g = game(i)
            pos[i].append((m.get("room"), g.get("busy")))
        time.sleep(3)
    for i in IDS:
        g = game(i)
        rooms = []
        for r, bz in pos[i]:
            if not rooms or rooms[-1] != r: rooms.append(r)
        p(f"[{i}] role={me(i).get('role')} tasks done {[t['done'] for t in g.get('tasks', [])]} taskBar={g.get('taskBar')} rooms visited={rooms[:20]}")
        p("    events:", [e["type"] for e in ev.ev[i] if e["type"] in ("task_done", "task_faked", "stuck", "arrived", "tasks_all_done")])
    ev.stop = True


{"setup": setup, "moves": moves, "leak": leak, "tasks": tasks, "follow": follow, "follow2": follow2, "auto": auto}[PH]()
