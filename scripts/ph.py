"""Show phase / meeting / sabotage of every seat: python ph.py [N]"""
import sys, json
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b
sys.stdout.reconfigure(encoding="utf-8")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
for i in range(1, n + 1):
    try:
        g = (b.state(i) or {}).get("game") or {}
        m = g.get("meeting")
        if m: m = {k: m[k] for k in ("caller", "reportedBody", "voted", "votes", "timeLeft") if k in m}
        print(i, g.get("phase"), "canMove", g.get("canMove"), "alive", (g.get("me") or {}).get("alive"), "meeting", json.dumps(m, ensure_ascii=False), "busy", g.get("busy"))
    except Exception as e:
        print(i, "ERR", e)
