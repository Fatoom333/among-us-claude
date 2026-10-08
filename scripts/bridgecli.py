"""Tiny client for the AUBridge sockets (runs on the PC). Tokens are read from files and never printed.
Usage: python bridgecli.py <id> <cmd> [json-args]     e.g.  bridgecli.py 1 configure '{"impostors":1}'
       python bridgecli.py <id> wait_event '{"since":0,"timeout":10}'
"""
import json, socket, sys, time

TOK = r"D:\AmongUs-tools\bridge\tokens\p%d.txt"


def token(i):
    with open(TOK % i, encoding="ascii") as f:
        return f.read().strip()


def call(i, cmd, timeout=15, **args):
    """Send one command to seat i, return the parsed reply dict."""
    msg = {"cmd": cmd, "token": token(i)}
    msg.update(args)
    s = socket.create_connection(("127.0.0.1", 47000 + i), timeout=timeout)
    try:
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8"))
    finally:
        s.close()


def state(i):
    return call(i, "state")


def wait_event(i, since=0, timeout=30):
    return _wait(i, since, timeout)


def _wait(i, since, timeout):
    msg = {"cmd": "wait_event", "token": token(i), "since": since, "timeout": timeout}
    s = socket.create_connection(("127.0.0.1", 47000 + i), timeout=timeout + 15)
    try:
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8"))
    finally:
        s.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    i, cmd = int(sys.argv[1]), sys.argv[2]
    args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    if cmd == "wait_event":
        print(json.dumps(_wait(i, args.get("since", 0), args.get("timeout", 30)), ensure_ascii=False))
    else:
        print(json.dumps(call(i, cmd, **args), ensure_ascii=False))
