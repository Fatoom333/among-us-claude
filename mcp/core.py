"""Общее ядро для server.py (MCP) и cli.py: проверка ключа места, валидация, доступ к мосту AUBridge.

Ничего не знает про MCP: ошибки проверок - AuError (server.py превращает их в ToolError, cli.py в JSON).
Ключи мест и токены моста нигде не пишутся (ни в лог, ни в ответ).
"""
import asyncio
import hmac
import json
import logging
import os
import time
from pathlib import Path

ROOT = Path(os.environ.get("AU_ROOT", r"D:\AmongUs-tools"))
SEATS_FILE = ROOT / "bridge" / "seats.json"
TOKENS_DIR = ROOT / "bridge" / "tokens"
LOG_DIR = ROOT / "mcp" / "logs"
BRIEFS_DIR = ROOT / "briefs"
MAX_BRIEF = 40 * 1024        # символов; должно влезать в MAX_OUT вместе с обёрткой
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
            "avoid", "self_report", "fix_sabotage"}
RESERVED = {"cmd", "token", "do", "set", "timeout", "since"}

LOG_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("au-mcp")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.FileHandler(LOG_DIR / f"mcp-{time.strftime('%Y%m%d')}.log", encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(_h)
log.propagate = False  # stdout/stderr заняты протоколом


class AuError(Exception):
    """Ошибка проверки/доступа; текст безопасен для показа агенту."""


class Conn:
    """Одно TCP-соединение к мосту места; запросы по нему идут строго по очереди."""

    def __init__(self, player: int):
        self.player = player
        self.lock = asyncio.Lock()
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.last_used = 0.0

    def drop(self):
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
        data = (json.dumps(payload, ensure_ascii=True) + "\n").encode("ascii")
        async with self.lock:
            # давно простаивавшее соединение закрываем заранее
            if self.writer is not None and time.monotonic() - self.last_used > IDLE_CLOSE:
                self.drop()
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
                    self.drop()
                    return {"ok": False, "error": "bridge timeout"}
                except ValueError:
                    self.drop()
                    return {"ok": False, "error": "bad bridge response"}
                except (ConnectionError, OSError, asyncio.IncompleteReadError):
                    self.drop()
                    # Повтор только для старого соединения, которое мост мог закрыть по простою.
                    # Свежее соединение не повторяем: запрос мог уже дойти (двойной kill/chat/vote).
                    if not reused:
                        break
                except BaseException:
                    # отмена запроса клиентом (CancelledError) и прочее: ответ моста ещё в пути,
                    # соединение выбрасываем, иначе следующий запрос прочтёт чужой ответ
                    self.drop()
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


def check_seat(player, key):
    """Сверка ключа места за постоянное время. Любая ошибка даёт одно и то же сообщение."""
    if isinstance(player, bool) or not isinstance(player, int) or not 1 <= player <= 10 \
            or not isinstance(key, str) or not 8 <= len(key) <= 128:
        log.info("p%s DENIED", player if isinstance(player, int) else "?")
        raise AuError("access denied")
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
        raise AuError("access denied")


def clean_args(args) -> dict:
    args = args or {}
    if not isinstance(args, dict):
        raise AuError("args must be an object")
    if len(json.dumps(args, ensure_ascii=False).encode("utf-8")) > MAX_ARGS_BYTES:
        raise AuError("args too large")
    for k in args:
        if not isinstance(k, str) or k in RESERVED or len(k) > 40:
            raise AuError("bad arg name")
    return args


def check_wait(timeout, since) -> tuple:
    for v in (timeout, since):
        if isinstance(v, bool) or not isinstance(v, int):
            raise AuError("timeout and since must be integers")
    if not 0 <= timeout <= 55:
        raise AuError("timeout must be 0..55")
    if not 0 <= since <= 2**53:
        raise AuError("bad since")
    return timeout, since


def check_act(do, args) -> dict:
    if not isinstance(do, str) or do not in ACTIONS:
        raise AuError("unknown action; allowed: " + ", ".join(sorted(ACTIONS)))
    args = clean_args(args)
    if do == "chat":
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise AuError("chat needs args.text")
        if len(text) > MAX_CHAT:
            raise AuError(f"chat text longer than {MAX_CHAT}")
    return args


def check_reflexes(rset) -> list:
    if not isinstance(rset, list):
        raise AuError("set must be a list")
    if len(rset) > 10:
        raise AuError("too many reflexes (max 10)")
    for r in rset:
        if not isinstance(r, dict):
            raise AuError("reflex must be an object")
        t = r.get("type")
        if not isinstance(t, str) or t not in REFLEXES:
            raise AuError("unknown reflex type; allowed: " + ", ".join(sorted(REFLEXES)))
        clean_args({k: v for k, v in r.items() if k != "type"})
        if "eagerness" in r:
            e = r["eagerness"]
            if isinstance(e, bool) or not isinstance(e, (int, float)) or e != e or not 0 <= e <= 1:
                raise AuError("eagerness must be a number 0..1")
        # "max" (старый лимит чинящих) больше не используется: принимается и игнорируется
    return rset


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
        raise AuError("request too large")
    return finish(await conn(player, kind).request(payload, timeout), token)


# ---- общие операции (их вызывают и MCP-инструменты, и CLI) ----

async def op_state(player, key) -> dict:
    check_seat(player, key)
    log.info("p%s state", player)
    return await call_bridge(player, "cmd", {"cmd": "state"})


async def op_wait(player, key, timeout=30, since=0, quiet=False) -> dict:
    check_seat(player, key)
    timeout, since = check_wait(timeout, since)
    log.info("p%s wait t=%s since=%s", player, timeout, since)
    return await call_bridge(player, "wait", {"cmd": "wait_event", "timeout": timeout, "since": since, "quiet": bool(quiet)},
                             timeout + 10.0)


async def op_act(player, key, do, args=None) -> dict:
    check_seat(player, key)
    args = check_act(do, args)
    log.info("p%s act %s %s", player, do, json.dumps(args, ensure_ascii=False)[:300])
    return await call_bridge(player, "cmd", {**args, "cmd": "act", "do": do})


async def op_brief(player, key) -> dict:
    """Бриф своего места: правила + характер + память. Его раскладывает agents/game-args.mjs перед партией."""
    check_seat(player, key)
    log.info("p%s brief", player)
    text = _read_text(BRIEFS_DIR / f"p{player}.md")
    if not text:
        raise AuError("no brief for this seat; run agents/game-args.mjs before the game")
    if len(text) > MAX_BRIEF:
        raise AuError("brief too large")
    return {"ok": True, "brief": text}


async def op_reflex(player, key, rset) -> dict:
    check_seat(player, key)
    rset = check_reflexes(rset)
    log.info("p%s reflex %s", player, json.dumps(rset, ensure_ascii=False)[:300])
    return await call_bridge(player, "cmd", {"cmd": "reflex", "set": rset})
