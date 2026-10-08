"""Quick bridge call: python bc.py <ids|all> <cmd> key=jsonvalue ...   e.g. bc.py 1,2 nav mask='"shipobj"' rebuild=true"""
import json, sys
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b
sys.stdout.reconfigure(encoding="utf-8")
ids = range(1, 11) if sys.argv[1] == "all" else [int(x) for x in sys.argv[1].split(",")]
cmd = sys.argv[2]
args = {}
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1)
    try: args[k] = json.loads(v)
    except Exception: args[k] = v
for i in ids:
    try:
        r = b.call(i, cmd, **args)
        if cmd == "state" and "game" in r:
            g = r.get("game") or {}
            r = {"stage": r.get("stage"), "me": g.get("me"), "busy": g.get("busy"), "body": g.get("body"), "vis": [v["name"] for v in g.get("visible", [])], "bar": g.get("taskBar")}
        print(i, json.dumps(r, ensure_ascii=False)[:1500])
    except Exception as e:
        print(i, "ERR", e)
