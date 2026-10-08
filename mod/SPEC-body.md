# AUBridge v0.2 — «тело» бота (ТЗ)

Продолжение `SPEC-bridge.md`. Тот же плагин, тот же протокол: newline-JSON по TCP 127.0.0.1:47000+id, в каждом запросе `"token"`, ответ `{"ok":true,...}` или `{"ok":false,"error":"..."}`. Все действия в игре идут через очередь в главном потоке (`Runner.Update`).

Главный принцип — **честность**. Мост отдаёт только то, что видит персонаж на своём экране. Сырые координаты чужих игроков вне поля зрения не выдаются никогда.

## 1. Хост (только при `mode=host`)
- `{"cmd":"configure","map":"skeld","impostors":2,"killCooldown":20,"discussion":15,"voting":60,"taskBarUpdates":"always","confirmEjects":true}` — пишет в `normalGameHostOptions` в лобби. Особые роли выключены (шанс 0). Поля необязательные, по умолчанию стоят значения из примера.
- `{"cmd":"start"}` — начать игру (`GameStartManager` / `AmongUsClient.StartGame`). Ошибка, если меньше 4 игроков или не всё загружено.
- `{"cmd":"autopilot","on":true}` — простой автопилот для копии без агента: ходит по своим задачам и выполняет их. На собраниях пропускает голос. Нужен для слота человека в тестах.

## 2. `state` (расширенный)
Состояние в лобби — как в v0.1. Во время игры добавляются поля:
```
"game": {
  "phase": "tasks|meeting|voting_result|ended",
  "me": {"name","color","alive":bool,"role":"crewmate|impostor|ghost_crew|ghost_imp",
         "pos":[x,y],"room":"Cafeteria|...|null","killCooldown":s,"canVent":bool,"inVent":bool,
         "partner":"<имя напарника-импостора или null>"},
  "tasks": [{"id":n,"name":"Fix Wiring","room":"Electrical","done":bool,"pos":[x,y]}],
  "taskBar": 0..1 (если игра его показывает),
  "visible": [{"name","color","pos":[x,y],"room","alive":true,"distance":m,"inVent":false}],
  "bodies":  [{"name","color","pos":[x,y],"room","distance":m}],
  "sabotage": {"active":"lights|reactor|o2|comms|null","timer":s},
  "meeting": {"caller","reportedBody","votes":{...},"chat":[{"from","text"}],"timeLeft":s} | null,
  "busy": "что тело делает сейчас: idle|moving|task|following|...",
  "reflexes": [...активные]
}
```
- **Видимость.** Игрок или тело попадают в `visible`/`bodies` только когда игра их сама рисует для локального игрока: `cosmetics`/`SpriteRenderer.enabled && isVisible`, учёт `ShadowCollab`/свет. Точный флаг найти в interop. Запасной вариант: `PhysicsHelpers.AnythingBetween(myPos, theirPos, Constants.ShadowMask)` плюс радиус зрения из `ShipStatus.CalculateLightRadius`.
- Призрак видит всех игроков (так и в игре) и не видит импосторов.
- `room` берётся из `ShipStatus.FastRooms`/`PlainShipRoom` по коллайдеру.

## 3. Действия (`{"cmd":"act","do":"...",...}`)
Каждое действие **заменяет** текущее занятие тела. Ответ приходит сразу: `{"ok":true,"accepted":"move_to"}`. Чем действие закончилось, сообщает событие.
- `move_to` `{"room":"Electrical"}` или `{"pos":[x,y]}` — навигация. Вариант А: PathfindingAPI/NavMesh, если работает на 17.4. Вариант Б: свой граф путевых точек Skeld (JSON в ресурсах плагина) + A*, движение через `PlayerControl.MyPhysics` (выставлять `body.velocity`/имитировать ввод `KeyboardJoystick`). Застревание: нет прогресса 2 с → объезд, 3 неудачи подряд → событие `stuck`.
- `follow` `{"target":"Имя","distance":1.5}` — держаться рядом, пока цель видна. Цель пропала из вида → событие `lost_sight`, тело идёт к последней видимой точке.
- `wander` `{"room":null}` — бродить по комнате или по случайным комнатам.
- `stay` — стоять. `idle` — то же самое.
- `do_task` `{"id":n}` или `{"next":true}` — дойти до консоли и стоять там `durationSec` (по типу задачи, 3–10 с). Затем засчитать задачу игровым вызовом: `PlayerTask.Complete()` / `NormalPlayerTask.NextStep()` с RPC `CompleteTask`. Многошаговые задачи доводятся до конца. Призрак-член экипажа тоже делает задачи.
- `report` — если тело в радиусе репорта: `CmdReportDeadBody`.
- `call_meeting` — дойти до кнопки в Cafeteria и нажать `CmdReportDeadBody(null)`.
- `vote` `{"target":"Имя"|"skip"}` — только в фазе голосования: `MeetingHud.CmdCastVote`.
- `chat` `{"text":"..."}` — до 100 символов. Отправлять можно на собрании, а также в лобби. Мёртвые пишут только в чат призраков (как в игре).
- Импостор:
  - `kill` `{"target":"Имя"}` — только если цель видна, в радиусе убийства и кулдаун = 0 (`CmdCheckMurder`);
  - `vent` `{"enter":true|false,"to":"<имя вента>"}`;
  - `sabotage` `{"type":"lights|reactor|o2|comms"}` (`ShipStatus.RpcUpdateSystem`/`RpcRepairSystem`);
  - `fix` `{"type":...}` — чинить саботаж, может любой член экипажа.

Запрещено: телепорт, `noclip`, убийство издалека, чтение чужих ролей. Всё только через обычные игровые вызовы с их проверками.

## 4. Рефлексы (`{"cmd":"reflex","set":[...]}` полностью заменяет список; `[]` — снять все)
Рефлексы проверяются каждый кадр в моде, Claude их только включает.
- `{"type":"kill_if_alone","target":"Имя|any","maxWitnesses":0}` — убить, когда цель в радиусе, кулдаун 0 и вокруг видно не больше `maxWitnesses` других живых. Только для импостора.
- `{"type":"report_on_body"}` — увидел тело → подойти и зарепортить.
- `{"type":"flee_on_kill_seen"}` — увидел убийство → бежать к ближайшей группе (≥2 видимых) или в Cafeteria.
- `{"type":"stick_to_group","min":2}` — если рядом меньше `min` видимых, идти к ближайшему видимому, а если никого не видно — в Cafeteria. Работает поверх текущего действия, а не вместо него.
- `{"type":"avoid","target":"Имя","distance":4}` — держаться подальше.
- `{"type":"fix_sabotage","max":2}` (живой экипаж) — при саботаже lights/comms/o2/reactor и вне собрания идти чинить так же, как `act fix` (реактор: консоль 0/1 с меньшим числом видимых чинящих, затем ближайшая; O2: обе панели). Свет/связь: если у панели или ближе к ней, чем ты, уже ≥`max` других видимых (по умолчанию 2, 0 = без лимита) — не идти, но через 15 с активного саботажа идти всё равно. Реактор и O2 без лимита. После собрания срабатывает снова. Событие `reflex_fired` {reflex:"fix_sabotage"}.
- `{"type":"self_report"}` (импостор) — после своего убийства сразу зарепортить.
Каждое срабатывание рефлекса порождает событие `reflex_fired`.

## 5. События: `{"cmd":"wait_event","timeout":30,"since":<seq>}`
Длинный опрос. Ответ: `{"ok":true,"seq":<последний>,"events":[...]}`, `timeout` не больше 60. Сразу возвращает всё, что накопилось после `since`. Если событий нет, ждёт до первого или до таймаута, тогда `events` пустой. Буфер — последние 500 событий. Ждать нужно вне главного потока: соединение держит поток моста, ожидание через `ManualResetEventSlim`/монитор.

Типы событий, у каждого есть `seq` и `t` (секунды от начала игры):
- `game_started` {role, partner, tasks}, `game_ended` {winner:"crew|impostors", reason};
- `saw_player` {name, room}, `lost_player` {name, room} — вошёл в поле зрения или вышел (с гистерезисом 0,5 с, чтобы не мигало);
- `saw_body` {name, room}, `saw_kill` {killer, victim, room} — только если убийство было видно, `saw_vent` {name, vent} — видно, как кто-то залез в вент или вылез;
- `arrived` {room}, `stuck`, `lost_sight` {name}, `task_done` {id, name}, `tasks_all_done`;
- `meeting_started` {caller, body}, `chat` {from, text}, `voting_started`, `vote_cast` {from} (без цели, пока голосование не кончилось), `meeting_ended` {ejected, wasImpostor?(если включено confirmEjects)};
- `sabotage` {type}, `sabotage_fixed` {type};
- `you_died` {killer?: только если видел}, `reflex_fired` {type, detail};
- `room_changed` {room}.

## 6. Лог партии
Каждая копия пишет события в `D:\AmongUs-tools\games\<gameId>\p<id>.jsonl`; хост дополнительно пишет туда «глаз бога» (все позиции раз в секунду). Этот файл только для летописца **после** игры, мост его не отдаёт.

## 7. Проверка (готово, когда)
- На 3 копиях скриптом через мост: `configure` → `start` → `move_to` → `do_task` (задача засчитана, полоска растёт) → `kill` → `report` → `vote` → `meeting_ended`.
- **Тест на утечки:** игрок B стоит за стеной от A (разные комнаты, нет прямой видимости) → в `state` A его нет. Подходит в поле зрения → появляется и приходит `saw_player`.
- `wait_event` не блокирует игру: FPS не падает, другие команды обслуживаются.
- Ни одна команда не валит игру. Неверные аргументы дают `ok:false`.
