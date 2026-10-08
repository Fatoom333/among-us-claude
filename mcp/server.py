"""MCP-сервер "au": мост между Claude-агентами и модом AUBridge (по одному TCP-порту на место).

Запуск: python server.py  (stdio). Вся логика проверок и доступа к мосту - в core.py (её же использует cli.py).
Конкурентность: FastMCP обрабатывает каждый запрос отдельной asyncio-задачей; на место заведено два
соединения (команды и долгий опрос), чтобы au_wait не блокировал au_act.
"""
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

import core
from core import AuError

mcp = FastMCP("au", log_level="WARNING", instructions="Управление персонажем Among Us через мод-мост. "
              "Нужны номер места (player) и ваш ключ места (key).")

Player = Annotated[int, Field(ge=1, le=10, description="номер места 1..10")]
Key = Annotated[str, Field(min_length=8, max_length=128, description="ключ места")]


async def _run(coro):
    try:
        return await coro
    except AuError as e:
        raise ToolError(str(e))


@mcp.tool()
async def au_state(player: Player, key: Key) -> dict:
    """Текущее состояние персонажа: что он видит, задачи, фаза игры."""
    return await _run(core.op_state(player, key))


@mcp.tool()
async def au_wait(player: Player, key: Key,
                  timeout: Annotated[int, Field(ge=0, le=55)] = 30,
                  since: Annotated[int, Field(ge=0, le=2**53)] = 0) -> dict:
    """Долгий опрос событий: вернуть {seq, events[]} после seq=since; ждёт до timeout секунд (макс. 55)."""
    return await _run(core.op_wait(player, key, timeout, since))


@mcp.tool()
async def au_act(player: Player, key: Key, do: str, args: dict[str, Any] | None = None) -> dict:
    """Действие тела: move_to, follow, wander, stay, do_task, report, call_meeting, vote, chat,
    kill, vent, sabotage, fix. Параметры в args (см. SPEC-body §3). Заменяет текущее занятие."""
    return await _run(core.op_act(player, key, do, args))


@mcp.tool()
async def au_reflex(player: Player, key: Key, set: list[dict[str, Any]]) -> dict:
    """Рефлексы тела (SPEC-body §4). Полный список заменяет прежний; [] снимает все."""
    return await _run(core.op_reflex(player, key, set))


if __name__ == "__main__":
    mcp.run("stdio")
