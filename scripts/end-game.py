"""Orchestrator command: abort the running match on every seat (runs on the PC, next to bridgecli.py).
Usage: python end-game.py [N]     N = number of seats (default 10). Prints {"ok":..,"aborted":[ids],"failed":{id:error}}.
Host (seat 1) goes last so the clients already got the event before the host sends everybody back to the lobby.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridgecli


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    aborted, failed = [], {}
    for i in list(range(2, n + 1)) + [1]:
        try:
            r = bridgecli.call(i, "abort", timeout=10)
            if r.get("ok"):
                aborted.append(i)
            else:
                failed[i] = r.get("error", "error")
        except Exception as e:
            failed[i] = type(e).__name__
    print(json.dumps({"ok": bool(aborted) and 1 in aborted, "aborted": sorted(aborted), "failed": failed}))


if __name__ == "__main__":
    main()
