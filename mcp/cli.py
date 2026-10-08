"""CLI к тому же ядру (core.py), что и MCP-сервер: один JSON-запрос из stdin, один JSON-ответ в stdout.

Запрос: {"op":"state|wait|act|reflex","player":n,"key":"...", ...}
  state:  -
  wait:   timeout (0..55, по умолчанию 30), since (по умолчанию 0)
  act:    do, args (объект)
  reflex: set (список рефлексов)
Ключи и токены в вывод и лог не попадают. Ошибки: {"ok":false,"error":"..."}.
"""
import asyncio
import json
import sys

import core
from core import AuError


async def handle(req) -> dict:
    if not isinstance(req, dict):
        raise AuError("request must be a JSON object")
    op, player, key = req.get("op"), req.get("player"), req.get("key")
    if op == "state":
        return await core.op_state(player, key)
    if op == "wait":
        return await core.op_wait(player, key, req.get("timeout", 30), req.get("since", 0), req.get("quiet", False) is True)
    if op == "act":
        return await core.op_act(player, key, req.get("do"), req.get("args"))
    if op == "reflex":
        return await core.op_reflex(player, key, req.get("set"))
    raise AuError("unknown op; allowed: state, wait, act, reflex")


def main():
    sys.stdin.reconfigure(encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = sys.stdin.read()
        if len(raw.encode("utf-8")) > 16 * 1024:
            raise AuError("request too large")
        try:
            req = json.loads(raw)
        except ValueError:
            raise AuError("bad json")
        resp = asyncio.run(handle(req))
    except AuError as e:
        resp = {"ok": False, "error": str(e)}
    except Exception:
        core.log.exception("cli internal error")
        resp = {"ok": False, "error": "internal error"}
    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
