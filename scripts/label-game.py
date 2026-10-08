"""Orchestrator command: tell every seat the name of the next match (log folder D:/AmongUs-tools/games/<id>/).
Usage: python label-game.py <gameId> [N]   gameId: [A-Za-z0-9-], max 40; N seats (default 10).
Prints {"ok":..,"labeled":[ids],"failed":{id:error}}. Run before the match starts (agents/game-args.mjs does it).
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridgecli


def main():
    if len(sys.argv) < 2 or not re.fullmatch(r"[A-Za-z0-9-]{1,40}", sys.argv[1]):
        print(json.dumps({"ok": False, "error": "bad gameId"})); sys.exit(2)
    gid = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    labeled, failed = [], {}
    for i in range(1, n + 1):
        try:
            r = bridgecli.call(i, "label", id=gid, timeout=10)
            if r.get("ok"): labeled.append(i)
            else: failed[i] = r.get("error", "error")
        except Exception as e:
            failed[i] = type(e).__name__
    print(json.dumps({"ok": not failed, "labeled": labeled, "failed": failed}))


if __name__ == "__main__":
    main()
