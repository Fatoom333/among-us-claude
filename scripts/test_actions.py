"""Step 'Actions' live tests on N copies (run on the PC). Phases reuse a running game:
  setup N   lobby -> configure(impostors=1, short cooldowns) -> start
  bad N     wrong arguments / wrong role / wrong phase must all give ok:false
  vent N    impostor walks to a vent room, enters, moves on, exits
  sab N     impostor sabotages lights, a crew seat repairs it
  kill N    needs 5 seats: witness test, kill_if_alone, self_report, meeting 1 (chat, skip), flee_on_kill_seen, report_on_body, meeting 2 (vote out), game_ended
  react N   avoid + stick_to_group (no kills)
"""
import json, re, sys, time, threading
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
    try:
        return b.call(i, "act", **kw)
    except Exception as e:
        return {"ok": False, "error": "client: " + str(e)}


class Ev:
    """background long-poll collector per seat"""
    def __init__(self):
        self.ev = {i: [] for i in IDS}
        self.seq = {i: 0 for i in IDS}
        self.stop = False
        for i in IDS:
            threading.Thread(target=self.run, args=(i,), daemon=True).start()

    def run(self, i):
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
        r = b.call(1, "configure", impostors=1, killCooldown=10, discussion=5, voting=20, commonTasks=0, shortTasks=3, longTasks=0)
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
        g = game(i)
        m = g.get("me") or {}
        p(f"[{i}] {m.get('name')} role={m.get('role')} room={m.get('room')} pos={m.get('pos')} nav={g.get('body', {}).get('navStatus')}")


def walk(i, ev, **kw):
    t0 = time.time()
    r = act(i, do="move_to", **kw)
    if not r.get("ok"):
        p(f"  [{i}] move_to {kw} REFUSED: {r}")
        return None
    e = ev.wait(i, "arrived", 90, after=t0 - 0.01)
    if e is None:
        e = ev.find(i, "stuck", t0)
        m = me(i)
        p(f"  [{i}] move_to {kw} FAILED ({'stuck' if e else 'timeout'}) at {m.get('pos')} room={m.get('room')} body={game(i).get('body')}")
        return None
    dt = time.time() - t0
    m = me(i)
    p(f"  [{i}] move_to {kw} OK in {dt:.1f}s -> room={m.get('room')} pos={m.get('pos')}")
    return dt


def roles_map():
    r = {i: me(i) for i in IDS}
    imp = [i for i in IDS if r[i].get("role") == "impostor"]
    crew = [i for i in IDS if r[i].get("role") == "crewmate"]
    return imp, crew, {i: r[i].get("name") for i in IDS}


def ok(label, cond, extra=""):
    p(("PASS " if cond else "FAIL ") + label + (" | " + str(extra) if extra != "" else ""))
    return cond


def refused(r):
    return r.get("ok") is False and "error" in r


def bad():
    imp, crew, nm = roles_map()
    I, C = imp[0], crew[0]
    p("imp", I, "crew", crew, nm)
    r = act(C, do="kill", target=nm[I]); ok("kill by crew refused", refused(r), r.get("error"))
    r = act(I, do="kill"); ok("kill without target refused", refused(r), r.get("error"))
    r = act(I, do="kill", target="Nobody"); ok("kill unknown target refused", refused(r), r.get("error"))
    r = act(C, do="sabotage", type="lights"); ok("sabotage by crew refused", refused(r), r.get("error"))
    r = act(I, do="sabotage", type="coffee"); ok("sabotage bad type refused", refused(r), r.get("error"))
    r = act(C, do="vent", enter=True); ok("vent by crew refused", refused(r), r.get("error"))
    r = act(I, do="vent", enter=True); ok("vent by imp, nothing near, refused", refused(r), r.get("error"))
    r = act(C, do="vote", target="skip"); ok("vote outside meeting refused", refused(r), r.get("error"))
    r = act(C, do="chat", text="hi"); ok("chat outside meeting refused", refused(r), r.get("error"))
    r = act(C, do="report"); ok("report with no body refused", refused(r), r.get("error"))
    r = act(C, do="fix", type="lights"); ok("fix without sabotage refused", refused(r), r.get("error"))
    r = act(I, do="fix", type="lights"); ok("fix by impostor refused", refused(r), r.get("error"))
    r = act(C, do="dance"); ok("unknown action refused", refused(r), r.get("error"))
    r = act(C, do="enter"); ok("garbage action refused", refused(r), r.get("error"))
    r = act(C, do="vent", enter="yes"); ok("vent enter not bool refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "nope"}]); ok("bad reflex type refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "kill_if_alone"}]); ok("kill_if_alone for crew refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set="x"); ok("reflex set not array refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "avoid"}]); ok("avoid without target refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "avoid", "target": "Nobody"}]); ok("avoid unknown player refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "avoid", "target": nm[I], "distance": 999}]); ok("reflex bad distance refused", refused(r), r.get("error"))
    r = b.call(C, "reflex", set=[{"type": "report_on_body"}, {"type": "stick_to_group", "min": 2}])
    rf = (r.get("game") or {}).get("reflexes")
    ok("valid reflex set accepted", r.get("ok") and rf is not None and len(rf) == 2, rf if r.get("ok") else r)
    r = b.call(C, "reflex", set=[])
    ok("reflex cleared", r.get("ok") and (r.get("game") or {}).get("reflexes") == [])
    ok("game still alive", game(C).get("phase") == "tasks")


def vent():
    ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]
    ok("canVent for impostor", me(I).get("canVent"))
    vl = b.call(I, "nav", vents=True).get("vents") or []
    p("all vents:", vl)
    mm = [re.search(r"pos=\(([-\d.]+),([-\d.]+)\)", v) for v in vl if "room=Electrical" in v]
    pos = [float(mm[0].group(1)), float(mm[0].group(2))] if mm and mm[0] else None
    if pos: walk(I, ev, pos=pos)
    else: walk(I, ev, room="Electrical")
    g = game(I)
    p("vents visible to imp:", g.get("vents"))
    r = act(I, do="vent", enter=True); p("vent enter ->", r)
    time.sleep(1.5)
    m = me(I); p("inVent:", m.get("inVent"))
    ok("entered vent", m.get("inVent") is True)
    g = game(I); p("vents info inside:", g.get("vents"))
    cur = [v for v in g.get("vents", []) if "current" in v]
    if cur:
        for side in ("left", "right", "center"):
            if cur[0].get(side) is not None:
                r = act(I, do="vent", to=side); p("vent to", side, "->", r)
                time.sleep(1.5); p("moved:", game(I).get("vents")); break
    r = act(I, do="vent", enter=False); p("vent exit ->", r)
    time.sleep(1.5)
    ok("left vent", me(I).get("inVent") is False)
    p("events:", [e["type"] for e in ev.ev[I]])
    ev.stop = True


def sab():
    ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]; C = crew[0]
    for _ in range(60):
        cd = (game(I).get("sabotage") or {}).get("cooldown", 0)
        if cd <= 0.05: break
        time.sleep(1)
    t0 = time.time()
    r = act(I, do="sabotage", type="lights"); p("sabotage lights ->", r)
    e = ev.wait(C, "sabotage", 8, after=t0 - 1)
    ok("sabotage event at crew", e is not None, e)
    ok("state.sabotage active=lights", (game(C).get("sabotage") or {}).get("active") == "lights", game(C).get("sabotage"))
    r = act(I, do="sabotage", type="comms"); ok("second sabotage refused", refused(r), r.get("error"))
    time.sleep(1)
    r = act(C, do="fix", type="lights"); p("fix lights ->", r)
    t1 = time.time()
    e = ev.wait(C, "sabotage_fixed", 60, after=t1 - 0.01)
    ok("sabotage_fixed after fix", e is not None, e)
    p("fix_finished:", ev.find(C, "fix_finished", t1))
    p("sab state now:", game(C).get("sabotage"))
    if e: p("fixed in %.1fs" % (time.time() - t1))
    ev.stop = True


def react():
    ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]
    A, B = crew[0], crew[1]
    others = [i for i in IDS if i not in (I, A, B)]
    for i in others + [A]: act(i, do="stay")
    walk(A, ev, room="Cafeteria")
    for i in others: walk(i, ev, room="Cafeteria")
    # --- stick_to_group: B alone in MedBay, everybody else in the cafeteria
    walk(B, ev, room="MedBay")
    act(B, do="stay")
    t0 = time.time()
    r = b.call(B, "reflex", set=[{"type": "stick_to_group", "min": 2}]); ok("stick_to_group accepted", r.get("ok"), r.get("error"))
    e = ev.wait(B, "reflex_fired", 8, after=t0 - 0.01)
    ok("stick_to_group fired", e is not None, e)
    busy = None
    for _ in range(10):
        busy = game(B).get("busy")
        if busy == "grouping": break
        time.sleep(0.5)
    ok("busy=grouping while joining", busy == "grouping", busy)
    t1 = time.time(); room = None
    while time.time() - t1 < 40:
        room = me(B).get("room")
        if room == "Cafeteria": break
        time.sleep(0.5)
    ok("B reached the group in the cafeteria", room == "Cafeteria", f"room={room} after {time.time() - t1:.1f}s")
    time.sleep(3)
    g = game(B)
    ok("override over, back to the old occupation (stay)", g.get("busy") == "idle", g.get("busy"))
    b.call(B, "reflex", set=[])
    # --- avoid: A avoids the impostor, the impostor follows A
    walk(I, ev, room="Cafeteria")
    t2 = time.time()
    b.call(A, "reflex", set=[{"type": "avoid", "target": nm[I], "distance": 4}])
    r = act(I, do="follow", target=nm[A], distance=1.0); p("imp follows A ->", r)
    e = ev.wait(A, "reflex_fired", 15, after=t2 - 0.01)
    ok("avoid fired", e is not None, e)
    seen_avoiding = False; mx = 0
    for _ in range(24):
        g = game(A)
        if g.get("busy") == "avoiding": seen_avoiding = True
        d = [v["distance"] for v in g.get("visible", []) if v["name"] == nm[I]]
        if d: mx = max(mx, d[0])
        time.sleep(0.5)
    ok("busy=avoiding seen", seen_avoiding)
    p("max distance to the impostor while avoiding:", mx)
    b.call(A, "reflex", set=[]); act(I, do="stay"); act(A, do="stay")
    ev.stop = True


def watcher(i, secs=300):
    last = None; t0 = time.time()
    while time.time() - t0 < secs:
        ph = game(i).get("phase")
        if ph != last:
            p(f"   [phase seat {i}] {time.time() - t0:6.1f}s {ph}"); last = ph
        time.sleep(0.3)


def kill():
    ev = Ev(); time.sleep(1)
    threading.Thread(target=watcher, args=(3,), daemon=True).start()
    imp, crew, nm = roles_map(); I = imp[0]
    if len(crew) < 4:
        p("need 5 seats (4 crew)"); sys.exit(2)
    V, W, X, Y = crew[:4]
    p("impostor", nm[I], "victim", nm[V], "witness", nm[W], "flee-watcher", nm[X], "second victim", nm[Y])
    for i in crew: act(i, do="stay")
    walk(V, ev, room="Cafeteria"); walk(W, ev, room="Cafeteria"); walk(X, ev, room="Reactor"); walk(Y, ev, room="Storage")
    act(V, do="stay"); act(W, do="stay")
    walk(I, ev, room="Cafeteria")
    g = game(I)
    for _ in range(40):
        g = game(I)
        if nm[V] in [v["name"] for v in g.get("visible", [])] and g["me"]["killCooldown"] <= 0.05: break
        time.sleep(0.5)
    p("imp sees", [v["name"] for v in g.get("visible", [])], "cooldown", g["me"]["killCooldown"], "killRange", g["me"].get("killRange"))
    r = act(I, do="follow", target=nm[V], distance=1.0); p("follow ->", r)
    time.sleep(4)
    r = b.call(I, "reflex", set=[{"type": "kill_if_alone", "target": "any", "maxWitnesses": 0}, {"type": "self_report"}])
    ok("kill_if_alone + self_report accepted", r.get("ok"), r.get("error"))
    t0 = time.time()
    time.sleep(10)
    g = game(I)
    p("after 10 s with a witness: visible", [(v["name"], v["distance"]) for v in g["visible"]], "cooldown", g["me"]["killCooldown"])
    ok("NO kill while a witness is in sight", ev.find(I, "kill_done", t0) is None and ev.find(I, "reflex_fired", t0) is None)
    t1 = time.time()
    act(W, do="move_to", room="MedBay")
    e = ev.wait(I, "kill_done", 40, after=t1 - 0.01)
    ok("kill fires once the witness is out of sight", e is not None, e)
    e = ev.wait(I, "reflex_fired", 5, after=t1 - 0.01)
    ok("reflex_fired(kill_if_alone)", e is not None and e.get("reflex") == "kill_if_alone", e)
    ok("victim died (you_died at victim)", ev.wait(V, "you_died", 6, after=t1 - 0.01) is not None, ev.find(V, "you_died", t1))
    e = ev.wait(I, "reflex_fired", 8, after=t1 + 0.0, reflex="self_report")
    ok("self_report fired", e is not None, e)
    ms = {i: ev.wait(i, "meeting_started", 20, after=t1 - 0.01) for i in IDS}
    ok("meeting_started everywhere (called by the impostor)", all(ms.values()) and ms[I].get("caller") == nm[I], {i: (m or {}).get("caller") for i, m in ms.items()})
    # --- meeting 1: russian chat + everybody skips
    for _ in range(40):
        if game(W).get("phase") in ("meeting", "voting"): break
        time.sleep(0.25)
    txt = "Я видел тело в столовой, это был Синий!"
    t3 = time.time()
    r = act(W, do="chat", text=txt); p("chat ->", r)
    for i in IDS:
        e = ev.wait(i, "chat", 8, after=t3 - 0.01)
        ok(f"chat arrived at seat {i}", e is not None and e.get("text") == txt, (e or {}).get("text"))
    r = act(X, do="chat", text="x" * 101); ok("chat >100 refused", refused(r), r.get("error"))
    r = act(X, do="vote", target="skip"); p("early vote (discussion) ->", r.get("ok"), r.get("error"))
    ph = None
    for _ in range(80):
        ph = game(I).get("phase")
        if ph == "voting": break
        time.sleep(0.25)
    ok("phase becomes voting", ph == "voting", ph)
    alive = [i for i in IDS if i != V]
    t4 = time.time()
    for i in alive:
        r = act(i, do="vote", target="skip")
        p(f"vote seat {i} -> skip:", r.get("ok"), r.get("error"))
    time.sleep(0.5)
    r = act(W, do="vote", target="skip"); ok("second vote refused", refused(r), r.get("error"))
    r = act(V, do="vote", target="skip"); ok("dead cannot vote", refused(r), r.get("error"))
    e = ev.wait(I, "meeting_ended", 40, after=t4 - 0.01)
    ok("meeting 1 ended (nobody ejected)", e is not None and e.get("ejected") is None, e)
    p("vote_cast events at imp:", len([x for x in ev.ev[I] if x["type"] == "vote_cast" and x["_at"] >= t4]))
    round2(ev)


def round2(ev=None):
    """flee_on_kill_seen + report_on_body + vote out the impostor. Needs: 1 impostor, 3 living crew."""
    if ev is None:
        ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]
    W, X, Y = crew[:3]
    p("round2: impostor", nm[I], "reporter", nm[W], "watcher", nm[X], "victim", nm[Y])
    time.sleep(3)
    p("positions after meeting:", {i: (me(i).get("room"), me(i).get("alive")) for i in IDS})
    b.call(I, "reflex", set=[])
    b.call(X, "reflex", set=[{"type": "flee_on_kill_seen"}])
    b.call(W, "reflex", set=[{"type": "report_on_body"}])
    act(I, do="stay")
    for i in (X, Y): act(i, do="stay")
    walk(W, ev, room="MedBay")
    walk(I, ev, room="Cafeteria")
    r = act(I, do="follow", target=nm[Y], distance=1.0); p("imp follows Y ->", r.get("ok"), r.get("error"))
    for _ in range(40):
        g = game(I)
        if g["me"]["killCooldown"] <= 0.05: break
        time.sleep(0.5)
    t5 = time.time()
    seesX = nm[X] in [v["name"] for v in game(I).get("visible", [])]
    p("imp sees X (watcher)?", seesX, "cooldown", game(I)["me"]["killCooldown"])
    r = {}
    for _ in range(40):
        r = act(I, do="kill", target=nm[Y])
        if r.get("ok"): break
        if "range" not in str(r.get("error")): break
        time.sleep(0.25)
    p("kill Y ->", r)
    act(W, do="move_to", room="Cafeteria")
    e = ev.wait(Y, "you_died", 6, after=t5 - 0.01)
    ok("second victim died", e is not None, e)
    e = ev.wait(X, "saw_kill", 6, after=t5 - 0.01)
    ok("X saw the kill", e is not None, e)
    e = ev.wait(X, "reflex_fired", 6, after=t5 - 0.01)
    ok("flee_on_kill_seen fired", e is not None and e.get("reflex") == "flee_on_kill_seen", e)
    act(I, do="move_to", room="Storage")
    t6 = t5
    e = ev.wait(W, "reflex_fired", 40, after=t6 - 0.01, reflex="report_on_body")
    ok("report_on_body fired", e is not None, e)
    e = ev.find(W, "saw_body", t6)
    ok("W saw the body", e is not None, e)
    ms = {i: ev.wait(i, "meeting_started", 30, after=t6 - 0.01) for i in IDS}
    ok("meeting 2 started everywhere (caller W)", all(ms.values()) and ms[I].get("caller") == nm[W], {i: (m or {}).get("caller") for i, m in ms.items()})
    vote_out(ev, I, [I, W, X], nm, t6)


def vote_out(ev, I, voters, nm, since):
    X = [i for i in voters if i != I][-1]
    W = [i for i in voters if i != I][0]
    for _ in range(100):
        ph = game(I).get("phase")
        if ph == "voting": break
        time.sleep(0.25)
    ok("phase becomes voting", ph == "voting", ph)
    t7 = time.time()
    for i in voters:
        tgt = nm[I] if i != I else nm[X]
        r = act(i, do="vote", target=tgt); p(f"vote seat {i} -> {tgt}:", r.get("ok"), r.get("error"))
    e = ev.wait(I, "meeting_ended", 40, after=t7 - 0.01)
    ok("meeting ended with the impostor ejected", e is not None and e.get("ejected") == nm[I], e)
    p("vote_cast events at W:", [x.get("from") for x in ev.ev[W] if x["type"] == "vote_cast" and x["_at"] >= t7])
    ge = ev.wait(W, "game_ended", 30, after=t7 - 0.01)
    ok("game_ended (crew wins)", ge is not None and ge.get("winner") == "crew", ge)
    ev.stop = True


def meet2():
    ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]
    alive = [i for i in IDS if me(i).get("alive")]
    voters = [I] + [i for i in alive if i != I]
    W = [i for i in alive if i != I][0]
    p("alive", alive, "caller", nm[W])
    t0 = time.time()
    r = act(W, do="call_meeting"); p("call_meeting ->", r)
    e = ev.wait(W, "button_pressed", 60, after=t0 - 0.01)
    ok("button pressed", e is not None, e)
    ms = {i: ev.wait(i, "meeting_started", 30, after=t0 - 0.01) for i in alive}
    ok("meeting started everywhere (caller W)", all(ms.values()) and ms[I].get("caller") == nm[W], {i: (m or {}).get("caller") for i, m in ms.items()})
    vote_out(ev, I, voters, nm, t0)


def sab2():
    ev = Ev(); time.sleep(1)
    imp, crew, nm = roles_map(); I = imp[0]; C, D = crew[0], crew[1]
    def wait_cd():
        for _ in range(80):
            if (game(I).get("sabotage") or {}).get("cooldown", 0) <= 0.05: return
            time.sleep(1)
    for typ in ("comms", "o2", "reactor"):
        wait_cd()
        t0 = time.time()
        r = act(I, do="sabotage", type=typ); p(f"== sabotage {typ} ->", r)
        e = ev.wait(C, "sabotage", 8, after=t0 - 0.5); ok(f"{typ}: sabotage event", e is not None and e.get("kind") == typ, e)
        time.sleep(1)
        t1 = time.time()
        if typ == "reactor":
            r1 = act(C, do="fix", type="reactor", id=0); r2 = act(D, do="fix", type="reactor", id=1)
            p("fix reactor ->", r1, r2)
        else:
            r1 = act(C, do="fix", type=typ); p(f"fix {typ} ->", r1)
        e = ev.wait(C, "sabotage_fixed", 70, after=t1 - 0.01)
        ok(f"{typ}: sabotage_fixed", e is not None, e)
        if e: p("  fixed in %.1fs" % (time.time() - t1))
        else: p("  state:", game(C).get("sabotage"), "tasks:", [(t["name"], t["done"]) for t in game(C).get("tasks", [])][:5])
        act(C, do="stay"); act(D, do="stay")
        if (game(I).get("phase") == "ended"): break
    ev.stop = True


{"setup": setup, "bad": bad, "vent": vent, "sab": sab, "react": react, "kill": kill, "meet2": meet2, "round2": round2, "sab2": sab2}[PH]()
