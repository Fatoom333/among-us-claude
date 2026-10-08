"""Print the last events of a seat: python evdump.py <seat> [count]"""
import sys, json
sys.path.insert(0, r"D:\AmongUs-tools")
import bridgecli as b
sys.stdout.reconfigure(encoding="utf-8")
i = int(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
r = b._wait(i, 0, 0)
for e in r["events"][-n:]:
    print(json.dumps(e, ensure_ascii=False))
