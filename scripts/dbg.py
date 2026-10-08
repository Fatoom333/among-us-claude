import json, sys, time
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b
sys.stdout.reconfigure(encoding="utf-8")
i = int(sys.argv[1]); dur = float(sys.argv[2])
args = {}
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1)
    try: args[k] = json.loads(v)
    except Exception: args[k] = v
print(b.call(i, "act", **args))
t0 = time.time()
while time.time() - t0 < dur:
    g = b.state(i)["game"]; m = g["me"]
    print(round(time.time() - t0, 1), m["pos"], m["room"], g["busy"], g["canMove"], g["body"]["action"], g["body"]["stuck"], g["body"]["pathLeft"], flush=True)
    time.sleep(0.5)
