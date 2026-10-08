"""Самопроверка на ПК: поддельный мост на месте 10 (порт 47010) + настоящий клиент MCP по stdio.
Запуск: .venv\\Scripts\\python.exe selftest.py   (не трогает игру; временный токен p10.txt удаляется)."""
import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(r"D:\AmongUs-tools")
TOKEN = "testtoken-" + "x" * 20
tok_file = ROOT / "bridge" / "tokens" / "p10.txt"
seen = []


async def fake_bridge(reader, writer):
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            req = json.loads(line)
            seen.append(req)
            if req.get("token") != TOKEN:
                resp = {"ok": False, "error": "unauthorized"}
            elif req["cmd"] == "wait_event":
                await asyncio.sleep(min(req["timeout"], 3))
                resp = {"ok": True, "seq": 1, "events": []}
            elif req["cmd"] == "state":
                resp = {"ok": True, "stage": "lobby"}
            else:
                resp = {"ok": True, "accepted": req.get("do", req["cmd"])}
            writer.write((json.dumps(resp) + "\n").encode())
            await writer.drain()
    finally:
        writer.close()


async def main():
    seats = json.loads((ROOT / "bridge" / "seats.json").read_text(encoding="utf-8-sig"))
    key = seats["10"]
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp" / "server.py")])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = await s.list_tools()
        print("tools:", sorted(t.name for t in tools.tools))

        async def call(name, **a):
            res = await s.call_tool(name, a)
            txt = res.content[0].text if res.content else ""
            return ("ERR " if res.isError else "") + txt[:160]

        print("offline  :", await call("au_state", player=10, key=key))
        tok_file.write_text(TOKEN)
        server = await asyncio.start_server(fake_bridge, "127.0.0.1", 47010)
        try:
            print("state    :", await call("au_state", player=10, key=key))
            print("badkey   :", await call("au_state", player=10, key="0" * 64))
            print("badplayer:", (await call("au_state", player=11, key=key))[:80])
            print("badaction:", (await call("au_act", player=10, key=key, do="teleport"))[:80])
            print("longchat :", (await call("au_act", player=10, key=key, do="chat", args={"text": "a" * 101}))[:80])
            print("reserved :", (await call("au_act", player=10, key=key, do="stay", args={"token": "x"}))[:80])
            print("act      :", await call("au_act", player=10, key=key, do="move_to", args={"room": "Electrical"}))
            print("reflex   :", await call("au_reflex", player=10, key=key, set=[{"type": "report_on_body"}]))
            print("badreflex:", (await call("au_reflex", player=10, key=key, set=[{"type": "x"}]))[:80])
            print("timeout60:", (await call("au_wait", player=10, key=key, timeout=60))[:80])
            # конкурентность: 3 ожидания (3 с каждое) + команды параллельно
            t0 = time.time()
            res = await asyncio.gather(*[call("au_wait", player=10, key=key, timeout=3) for _ in range(1)],
                                       *[call("au_state", player=10, key=key) for _ in range(5)])
            print("parallel : %.1fs" % (time.time() - t0), res[1])
            # состояние не блокируется ожиданием
            t0 = time.time()
            wait_task = asyncio.create_task(call("au_wait", player=10, key=key, timeout=3))
            await asyncio.sleep(0.3)
            await call("au_state", player=10, key=key)
            print("state during wait: %.1fs (должно быть < 1)" % (time.time() - t0 - 0.3))
            await wait_task
        finally:
            server.close()
            tok_file.unlink(missing_ok=True)
        leaked = [q for q in seen if key in json.dumps(q)]
        print("key leaked to bridge:", bool(leaked), "| requests seen:", len(seen))
        print("reconnect after bridge death:", await call("au_state", player=10, key=key))


asyncio.run(main())
