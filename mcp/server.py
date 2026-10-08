"""MCP-сервер "au": мост между Claude-агентами и модом AUBridge (по одному TCP-порту на место).

Запуск: python server.py  (stdio). Конкурентность: FastMCP обрабатывает каждый запрос
отдельной asyncio-задачей; на место заведено два соединения (команды и долгий опрос),
чтобы au_wait не блокировал au_act.
"""
import asyncio
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

ROOT = Path(os.environ.get("AU_ROOT", r"D:\AmongUs-tools"))
SEATS_FILE = ROOT / "bridge" / "seats.json"
TOKENS_DIR = ROOT / "bridge" / "tokens"
LOG_DIR = ROOT / "mcp" / "logs"
HOST = "127.0.0.1"
PORT_BASE = 47000

MAX_LINE = 256 * 1024        # максимум строки ответа моста
MAX_OUT = 48 * 1024          # максимум ответа агенту (символов)
MAX_ARGS_BYTES = 2048
MAX_REQ_BYTES = 6 * 1024     # у моста MaxLine = 8 КБ на запрос (Bridge.cs)
MAX_CHAT = 100
CMD_TIMEOUT = 15.0
CONNECT_TIMEOUT = 3.0
IDLE_CLOSE = 90.0

ACTIONS = {"move_to", "follow", "wander", "stay", "idle", "do_task", "report", "call_meeting",
           "vote", "chat", "kill", "vent", "sabotage", "fix"}
REFLEXES = {"kill_if_alone", "report_on_body", "flee_on_kill_seen", "stick_to_group",
            "avoid", "self_report"}
RESERVED = {"cmd", "token", "do", "set", "timeout", "since"}

LOG_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("au-mcp")
log.setLevel(logging.INFO)
_h = logging.FileHandler(LOG_DIR / f"mcp-{time.strftime('%Y%m%d')}.log", encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(_h)
log.propagate = False  # stdout/stderr заняты протоколом


class Conn:
    """Одно TCP-соединение к мосту места; запросы по нему идут строго по очереди."""

    def __init__(self, player: int):
        self.player = player
        self.lock = asyncio.Lock()
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.last_used = 0.0

    def _drop(self):
        if self.writer is not None:
            try:
                self.writer.close()
            except Exception:
                pass
        self.reader = self.writer = None

    async def _open(self):
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT_BASE + self.player, limit=MAX_LINE),
            CONNECT_TIMEOUT)

    async def request(self, payload: dict, timeout: float) -> dict:
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        async with self.lock:
            # давно простаивавшее соединение закрываем заранее
            if self.writer is not None and time.monotonic() - self.last_used > IDLE_CLOSE:
                self._drop()
            for attempt in (1, 2):
                reused = self.writer is not None
                try:
                    if self.writer is None:
                        await self._open()
                    self.writer.write(data)
                    await self.writer.drain()
                    line = await asyncio.wait_for(self.reader.readline(), timeout)
                    if not line:
                        raise ConnectionError("closed")
                    self.last_used = time.monotonic()
                    resp = json.loads(line.decode("utf-8", "replace"))
                    if not isinstance(resp, dict):
                        raise ValueError("not an object")
                    return resp
                except (asyncio.TimeoutError, TimeoutError):
                    self._drop()
                    return {"ok": False, "error": "bridge timeout"}
                except ValueError:
                    self._drop()
                    return {"ok": False, "error": "bad bridge response"}
                except (ConnectionError, OSError, asyncio.IncompleteReadError):
                    self._drop()
                    # Повтор только для старого соединения, которое мост мог закрыть по простою.
                    # Свежее соединение не повторяем: запрос мог уже дойти (двойной kill/chat/vote).
                    if not reused:
                        break
                except BaseException:
                    # отмена запроса клиентом (CancelledError) и прочее: ответ моста ещё в пути,
                    # соединение выбрасываем, иначе следующий запрос прочтёт чужой ответ
                    self._drop()
                    raise
            return {"ok": False, "error": "bridge offline"}


_conns: dict[tuple[int, str], Conn] = {}


def conn(player: int, kind: str) -> Conn:
    c = _conns.get((player, kind))
    if c is None:
        c = _conns[(player, kind)] = Conn(player)
    return c


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None


def check_seat(player: int, key: str):
    """Сверка ключа места за постоянное время. Любая ошибка даёт одно и то же сообщение."""
    expected = ""
    try:
        seats = json.loads(SEATS_FILE.read_text(encoding="utf-8-sig"))
        v = seats.get(str(player))
        if isinstance(v, str):
            expected = v
    except (OSError, ValueError, AttributeError):
        pass
    ok = hmac.compare_digest(expected.encode("utf-8"), key.encode("utf-8")[:512])
    if not ok or not expected:
        log.info("p%s DENIED", player)
        raise ToolError("access denied")


def clean_args(args: dict | None) -> dict:
    args = args or {}
    if not isinstance(args, dict):
        raise ToolError("args must be an object")
    if len(json.dumps(args, ensure_ascii=False).encode("utf-8")) > MAX_ARGS_BYTES:
        raise ToolError("args too large")
    for k in args:
        if not isinstance(k, str) or k in RESERVED or len(k) > 40:
            raise ToolError("bad arg name")
    return args


def finish(resp: dict, token: str) -> dict:
    s = json.dumps(resp, ensure_ascii=False)
    if token in s:  # мост не должен эхом возвращать токен; на всякий случай не отдаём
        log.info("bridge response contained token; dropped")
        return {"ok": False, "error": "bad bridge response"}
    if len(s) > MAX_OUT:
        return {"ok": False, "error": "response too large", "size": len(s)}
    return resp


async def call_bridge(player: int, kind: str, payload: dict, timeout: float = CMD_TIMEOUT) -> dict:
    token = _read_text(TOKENS_DIR / f"p{player}.txt")
    if not token:
        return {"ok": False, "error": "bridge offline"}
    payload = dict(payload, token=token)
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_REQ_BYTES:
        raise ToolError("request too large")
    return finish(await conn(player, kind).request(payload, timeout), token)


mcp = FastMCP("au", log_level="WARNING", instructions="Управление персонажем Among Us через мод-мост. "
              "Нужны номер места (player) и ваш ключ места (key).")

Player = Annotated[int, Field(ge=1, le=10, description="номер места 1..10")]
Key = Annotated[str, Field(min_length=8, max_length=128, description="ключ места")]


@mcp.tool()
async def au_state(player: Player, key: Key) -> dict:
    """Текущее состояние персонажа: что он видит, задачи, фаза игры."""
    check_seat(player, key)
    log.info("p%s state", player)
    return await call_bridge(player, "cmd", {"cmd": "state"})


@mcp.tool()
async def au_wait(player: Player, key: Key,
                  timeout: Annotated[int, Field(ge=0, le=55)] = 30,
                  since: Annotated[int, Field(ge=0, le=2**53)] = 0) -> dict:
    """Долгий опрос событий: вернуть {seq, events[]} после seq=since; ждёт до timeout секунд (макс. 55)."""
    check_seat(player, key)
    log.info("p%s wait t=%s since=%s", player, timeout, since)
    return await call_bridge(player, "wait",
                             {"cmd": "wait_event", "timeout": timeout, "since": since},
                             timeout + 10.0)


@mcp.tool()
async def au_act(player: Player, key: Key, do: str, args: dict[str, Any] | None = None) -> dict:
    """Действие тела: move_to, follow, wander, stay, do_task, report, call_meeting, vote, chat,
    kill, vent, sabotage, fix. Параметры в args (см. SPEC-body §3). Заменяет текущее занятие."""
    check_seat(player, key)
    if do not in ACTIONS:
        raise ToolError("unknown action; allowed: " + ", ".join(sorted(ACTIONS)))
    args = clean_args(args)
    if do == "chat":
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ToolError("chat needs args.text")
        if len(text) > MAX_CHAT:
            raise ToolError(f"chat text longer than {MAX_CHAT}")
    log.info("p%s act %s %s", player, do, json.dumps(args, ensure_ascii=False)[:300])
    return await call_bridge(player, "cmd", {**args, "cmd": "act", "do": do})


@mcp.tool()
async def au_reflex(player: Player, key: Key, set: list[dict[str, Any]]) -> dict:
    """Рефлексы тела (SPEC-body §4). Полный список заменяет прежний; [] снимает все."""
    check_seat(player, key)
    if len(set) > 10:
        raise ToolError("too many reflexes (max 10)")
    for r in set:
        t = r.get("type")
        if not isinstance(t, str) or t not in REFLEXES:
            raise ToolError("unknown reflex type; allowed: " + ", ".join(sorted(REFLEXES)))
        clean_args({k: v for k, v in r.items() if k != "type"})
    log.info("p%s reflex %s", player, json.dumps(set, ensure_ascii=False)[:300])
    return await call_bridge(player, "cmd", {"cmd": "reflex", "set": set})


if __name__ == "__main__":
    mcp.run("stdio")
