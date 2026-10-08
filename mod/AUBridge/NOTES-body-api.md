# AUBridge v0.2 «тело»: заметки по API игры 17.4e (2026.6.5)

Источник: `ilspycmd` по `mod/refs/interop/Assembly-CSharp.dll` (проектная распаковка лежала в `%TEMP%\aucs`, по файлу на тип; `Assembly-CSharp-firstpass.dll` не нужен).
ВАЖНО: это interop-заглушки, **тел методов нет** — видны имена, поля, сигнатуры. «Что метод делает внутри» ниже — вывод по именам и знанию игры, на ПК не проверено; такие места помечены (?). Статические константы (`ReactorSystemType.AddUserOp` и т.п.) в заглушках без значений, но в рантайме читаются как обычные статические свойства — читать их, а не хардкодить числа.
Il2Cpp: списки — `Il2CppSystem.Collections.Generic.List<T>`; приведение типов — `obj.TryCast<T>()`; поиск объектов — `UnityEngine.Object.FindObjectsOfType<T>()`. Свойства-геттеры патчить как `[HarmonyPatch(typeof(X), nameof(X.Prop), MethodType.Getter)]`.
Enum `InnerNetClient.GameStates` (вложенный) = NotJoined, Joined, Started, Ended (как в Runner.cs). Отдельный `InnerNet.GameStates` (NotStarted/Started/Ended/Destroyed) — другой тип, не путать.

## 1. Видимость игрока/тела для локального игрока
Готового флага «этот игрок виден мне» **нет**. Чужие спрайты рисуются всегда, скрывает их тень: `ShadowCollab` (камера + квад, поля `ShadowCamera`, `ShadowQuad`, корутина `Run`), `LightSource` на локальном игроке (`PlayerControl.lightSource`; рейкасты по `Constants.ShadowMask`, словари `LightSource.NoShadows`/`OneWayShadows`). `SpriteRenderer.isVisible` бесполезен (это только отсечение камерой, тень он не учитывает). Игра сама «прячет» игрока только для вентов/фантома: `PlayerControl.Visible`, `inVent`, `invisibilityAlpha`, `CalculatedAlpha`.
Надёжный способ (считаем то же, что рисует свет):
- видим, если `me.Data.IsDead` (призрак видит всех живых/мёртвых игроков) ИЛИ (`dist <= radius` И нет стены между).
- `radius = ShipStatus.Instance.CalculateLightRadius(PlayerControl.LocalPlayer.Data)` (virtual float; учитывает саботаж света, CrewLightMod/ImpostorLightMod). Сверка: `PlayerControl.LocalPlayer.lightSource.ViewDistance` (должно совпасть; если нет — доверять lightSource, это то, что реально рисуется).
- стена: `!PhysicsHelpers.AnythingBetween(myTruePos, theirTruePos, Constants.ShadowMask, false)` (сигнатура `(Vector2 source, Vector2 target, int layerMask, bool useTriggers)`). Закрытые двери должны входить в ShadowMask через `PlainDoor.shadowCollider` (?) — проверить на ПК.
- исключить: `pc.inVent`, `!pc.Visible`, `pc.Data.IsDead` для живых-режима, себя, `pc.Data.Disconnected`; для тела: `DeadBody.TruePosition`, `!body.Reported`.
- позиция: `pc.GetTruePosition()` (центр ног, `Vector2`), у тела `DeadBody.TruePosition`.
```csharp
var me = PlayerControl.LocalPlayer; Vector2 a = me.GetTruePosition();
float r = ShipStatus.Instance.CalculateLightRadius(me.Data);
bool Vis(Vector2 b) => me.Data.IsDead || (Vector2.Distance(a,b) <= r && !PhysicsHelpers.AnythingBetween(a,b,Constants.ShadowMask,false));
foreach (var p in PlayerControl.AllPlayerControls) if (p!=me && !p.Data.Disconnected && !p.inVent && p.Visible && Vis(p.GetTruePosition())) ...
```
Риски: расхождение радиуса с экраном (сверять скриншотом); Phantom/невидимые роли нас не касаются (роли выключены). Утечка: НЕ брать `GameData.Instance.AllPlayers[i].Role` у чужих (см. раздел 5).

## 2. Движение
- В игре **нет** navmesh/pathfinding. `DummyBehaviour` — только голосование бота-пустышки (`PlayerIdToVoteFor`, `DoVote`, `voteTime`), никакой ходьбы. `ShipStatus.DummyLocations` — точки спавна пустышек.
- Как игра двигает локального игрока (?): `PlayerPhysics.FixedUpdate` берёт `HudManager.Instance.joystick.DeltaL` (`IVirtualJoystick`; на ПК это `KeyboardJoystick`, поле `del`, `Update()` читает Rewired), умножает на `PlayerPhysics.TrueSpeed` и пишет в `Rigidbody2D body.velocity`; только если `PlayerControl.CanMove`/`moveable`. `CustomNetworkTransform.FixedUpdate` (у владельца) сам шлёт позицию (sendQueue) — синхронизация по сети бесплатная. Запрещённые телепорты — `CustomNetworkTransform.RpcSnapTo/SnapTo`, не использовать.
- **Рекомендация А:** Harmony-патч геттера `KeyboardJoystick.DeltaL` (Postfix, `__result = botDir` пока бот управляет, иначе не трогать). Работает с анимацией и разворотом. Вектор нормировать до ≤1.
- Запасной Б: Postfix на `PlayerPhysics.FixedUpdate` для `myPlayer.AmOwner && CanMove`: `body.velocity = dir.normalized * TrueSpeed` (есть и готовый `PlayerPhysics.SetNormalizedVelocity(Vector2)`). `PlayerPhysics.WalkPlayerTo(Vector2, tolerance, speedMul, ignoreColliderOffset)` — корутина игры для скриптовых проходов (спавн), она тоже честно ходит, но без обхода стен.
- Скорость: `Speed`, `TrueSpeed = Speed*SpeedMod` (опция `PlayerSpeedMod`), у призрака `GhostSpeed`.
- **Данные для графа Skeld:** готового нет. Источники в рантайме:
  `ShipStatus.Instance.AllRooms/FastRooms` (центры `roomArea.bounds.center`), `AllConsoles` (позиции задач, `Console.Room`), `AllVents` (`Vent.Id`, `Left/Right/Center`), `AllDoors` (`OpenableDoor.Id/Room/IsOpen`, `PlainDoor.Open`, `myCollider`), `InitialSpawnCenter`, `MeetingSpawnCenter`, `EmergencyButton`.
- **Предложение (надёжнее и без внешних зависимостей):** на старте партии один раз построить сетку проходимости: шаг 0.25–0.3, область = bounds всех `roomArea` + запас; клетка проходима, если `!PhysicsHelpers.CircleContains(cell, radius≈0.25, Constants.ShipOnlyMask)` (радиус сверить с `PlayerControl.Collider`); соседние клетки связывать только если `!AnythingBetween(a,b,Constants.ShipOnlyMask,false)`; A* по сетке, упрощение пути (string-pulling через `AnythingBetween`), кеш в JSON рядом с плагином. Закрытые двери (`!door.IsOpen`) учитывать динамически повторной проверкой отрезка. Это вариант Б из SPEC без ручной разметки.
- PathfindingAPI (CallOfCreator): по research-2026-10-08 готовый A*, но нужна совместимость с 17.4 и Reactor у всех (он у нас есть). Не проверен; брать как запасной.
- Застревание: сравнивать `body.position` за 2 с; Skeld без лестниц/платформ (`Ladder` бывает только на Airship) — на Skeld они не нужны.

## 3. Задачи
- `PlayerControl.LocalPlayer.myTasks : List<PlayerTask>`. `PlayerTask`: `Id` (uint), `Index`, `TaskType` (enum `TaskTypes`), `StartAt` (`SystemTypes` комнаты), `IsComplete`, `TaskStep`, `HasLocation`, `Locations : List<Vector2>` (позиции консолей текущего шага), `FindConsoles()`, `FindConsolesPos()`, `FindValidConsolesPositions()`, `Owner`.
- Обычные: `task.TryCast<NormalPlayerTask>()` → `taskStep`, `MaxStep`, `Length` (enum Common/Short/Long), `Data` (byte[], у проводки хранит ids консолей), `NextStep()`, `Complete()`, `IsComplete`. В списке есть и саботажные задачи (`SabotageTask`, `ReactorTask`, `HeliSabotage...`) — фильтровать по `TryCast<NormalPlayerTask>() != null` и `TaskType` (ResetReactor, FixLights, FixComms, RestoreOxy... — это саботаж).
- Консоль: `Console` (`ConsoleId`, `Room`, `TaskTypes[]`, `ValidTasks`, `usableDistance`/`UsableDistance`, `checkWalls`, `onlySameRoom`, `AllowImpostor`, `GhostsIgnored`), `ValidConsole(console)` у задачи, `Console.CanUse(NetworkedPlayerInfo pc, out bool canUse, out bool couldUse)` возвращает расстояние (float), `canUse` — в зоне. Проверка «стою у консоли»: `console.CanUse(me.Data, out var can, out _) ; can == true`.
- Засчитать без мини-игры (?): однозначный путь — `task.Complete()` (в игре его зовёт закрытие мини-игры; внутри — `Owner.RpcCompleteTask(Id)`). Запасной: `PlayerControl.LocalPlayer.RpcCompleteTask(task.Id)` (локально отрабатывает `CompleteTask(uint)`, который ищет задачу в myTasks по Id, помечает `NetworkedPlayerInfo.Tasks[i].Complete`, хост пересчитывает `GameData.CompletedTasks/TotalTasks`).
- Многошаговые (скан-загрузка, топливо, DivertPower, проводка): цикл «дойти до `task.Locations[0]` → ждать → `task.NextStep()`» до `task.IsComplete`; последний `NextStep` сам вызывает Complete (?).
- Импостору задачи фальшивые: `Complete()` не звать (честная имитация — стоять у консоли и всё). Призракам-экипажу задачи делать можно (`GhostsDoTasks`).
- Полоска: `GameData.Instance.CompletedTasks / TotalTasks`; показывать по `GameManager.Instance.LogicOptions.GetTaskBarMode()` (`TaskBarMode`: Normal, MeetingOnly, Invisible).
```csharp
foreach (var t in PlayerControl.LocalPlayer.myTasks) { var n=t.TryCast<NormalPlayerTask>(); if(n==null||t.IsComplete) continue; /* id=t.Id, room=t.StartAt, pos=t.Locations[0] */ }
task.Complete();   // или PlayerControl.LocalPlayer.RpcCompleteTask(task.Id);
```

## 4. Действия
- **Убийство.** `PlayerControl.LocalPlayer.CmdCheckMurder(PlayerControl target)` (клиент просит хоста; хост проверяет дистанцию/кулдаун и шлёт `RpcMurderPlayer(target, didSucceed)` → у всех `MurderPlayer(target, MurderResultFlags)`). Дистанция: `GameManager.Instance.LogicOptions.GetKillDistance()` (float; опция `KillDistance` — индекс в `NormalGameOptionsV10.KillDistances`). Кулдаун: `PlayerControl.killTimer` (float), `SetKillTimer`, `GetKillCooldown()`. Законная цель: `me.Data.Role.FindClosestTarget()` (учитывает дальность/стены/роль) или `GetPlayersInAbilityRangeSorted(list)`; `Role.GetAbilityDistance()`. Как кнопка: `KillButton.CheckClick(target)`. Событие убийства — Postfix `PlayerControl.MurderPlayer` (идёт на всех клиентах).
- **Репорт.** `PlayerControl.LocalPlayer.CmdReportDeadBody(NetworkedPlayerInfo target)`; `target = GameData.Instance.GetPlayerById(body.ParentId)`. Радиус `PlayerControl.MaxReportDistance`. Тела: `FindObjectsOfType<DeadBody>()` (`ParentId`, `Reported`, `TruePosition`, `bodyRenderers`). Готовый вариант «как кнопка»: `PlayerControl.LocalPlayer.ReportClosest()` (сам выбирает тело в радиусе). Кнопка собрания: `ShipStatus.Instance.EmergencyButton` (`SystemConsole`, `UsableDistance`, `SafePositionLocal`); дойти и `CmdReportDeadBody(null)`; лимиты `PlayerControl.RemainingEmergencies`, `ShipStatus.EmergencyCooldown` (хост проверяет) (?).
- **Голос.** Состояние: `MeetingHud.Instance.state` (`VoteStates`: Animating, Discussion, NotVoted, Voted, Results, Proceeding). Голос: `MeetingHud.Instance.CmdCastVote(byte voterId, byte suspectId)`; `voterId = me.PlayerId`, `suspectId = target.PlayerId` или статик `PlayerVoteArea.SkippedVote` (также `HasNotVoted`, `MissedVote`, `DeadVote` — значения читать в рантайме). UI-путь: `PlayerVoteArea.VoteForMe()` / `MeetingHud.Select(idx)`+`Confirm(byte)`. Состояния голосов: `MeetingHud.playerStates[i]` (`TargetPlayerId`, `DidVote`, `VotedFor`, `AmDead`, `DidReport`), `amDead`, `reporterId`, `discussionTimer`, `exiledPlayer`, `wasTie`. Итог: Postfix `MeetingHud.VotingComplete(VoterState[] states, NetworkedPlayerInfo exiled, bool tie)`; кто вылетел и была ли роль: `ExileController.Instance.initData` (в пределах опции `ConfirmImpostor`).
- **Чат.** `PlayerControl.LocalPlayer.RpcSendChat(string)` (bool); входящие: Postfix `ChatController.AddChat(PlayerControl source, string text, bool censor)`. `ChatController.MAX_CHAT_SEND_RATE` (статик, ограничение частоты). Риск: если у аккаунта режим «быстрый чат», свободный `RpcSendChat` может не пройти (`AmongUs.Data.DataManager.Settings.Multiplayer.ChatMode` — проверить); есть `RpcSendQuickChat`. Мёртвые/живые разделение делает сама игра.
- **Венты.** Игровой путь: `Vent.Use()` (для локального игрока); прямой: `me.MyPhysics.RpcEnterVent(vent.Id)` / `RpcExitVent(vent.Id)`; переход: `vent.TryMoveToVent(other, out err)` (`ClickLeft/Right/Center`). Допуск: `vent.CanUse(me.Data, out can, out could)`, `me.Data.Role.CanVent`. Соседи: `Vent.NearbyVents`, `Left/Right/Center`. Статус: `me.inVent`, `Vent.currentVent`. «Видно, как залез/вылез» — Postfix `Vent.EnterVent(PlayerControl)` / `Vent.ExitVent(PlayerControl)` + проверка видимости.
- **Саботаж** (`ShipStatus.RpcUpdateSystem(SystemTypes, byte)`; на хосте `UpdateSystem`). Запуск (?): `RpcUpdateSystem(SystemTypes.Sabotage, (byte)SystemTypes.Reactor | Electrical (свет) | LifeSupp (O2) | Comms)`; кулдаун `((SabotageSystemType)Systems[SystemTypes.Sabotage]).Timer`/`PercentCool`/`AnyActive`. Двери: `ShipStatus.RpcCloseDoorsOfType(SystemTypes room)`.
  Починка (?; значения опкодов читать из статиков):
  - Свет: система `SwitchSystem` в `Systems[Electrical]` (`ExpectedSwitches`, `ActualSwitches`, `Level`, `NumSwitches`=5); починка — для каждого бита, где Expected≠Actual: `RpcUpdateSystem(Electrical, (byte)i)`.
  - Реактор: `ReactorSystemType` (`UserConsolePairs`, `Countdown`, `AddUserOp`, `RemoveUserOp`, `RequiredUserCount`=2 → нужны ДВА человека одновременно на консолях 0 и 1): `RpcUpdateSystem(Reactor, (byte)(AddUserOp | consoleId))`, снять `RemoveUserOp | id`.
  - O2: `LifeSuppSystemType` (`CompletedConsoles`, `Countdown`): каждая из двух консолей по отдельности `RpcUpdateSystem(LifeSupp, (byte)(AddUserOp | consoleId))`.
  - Связь: `HudOverrideSystemType` (`IsActive`): починка вероятно `RpcUpdateSystem(Comms, 0)` после мини-игры.
  Активные саботажи для `state.sabotage`: у каждой системы `IsActive`, у реактора/O2 `Countdown`.
```csharp
ShipStatus.Instance.RpcUpdateSystem(SystemTypes.Sabotage, (byte)SystemTypes.Electrical);
me.CmdCheckMurder(target); me.CmdReportDeadBody(GameData.Instance.GetPlayerById(body.ParentId));
MeetingHud.Instance.CmdCastVote(me.PlayerId, PlayerVoteArea.SkippedVote);
```

## 5. Старт, опции, роли, конец
- Старт (хост): `GameStartManager.Instance.BeginGame()` — то же, что кнопка (проверка числа игроков, обратный отсчёт `countDownTimer`, затем `ReallyBegin/FinallyBegin` → `AmongUsClient.Instance.SendStartGame()`, корутина `CoStartGame`). Поля: `startState`, `MinPlayers`, `LastPlayerCount`. Запасной: `AmongUsClient.Instance.SendStartGame()` (минуя отсчёт; ломает проверки — только если BeginGame не сработал). **Риск:** минимум игроков зависит от числа импостеров: `NormalGameOptionsV10.MinPlayers[numImpostors]` (статик, массив) — для 2 импостеров нужно больше 4 игроков. Для теста на 3–4 копиях ставить `impostors=1`.
- Опции: `var o = GameOptionsManager.Instance.normalGameHostOptions` (`NormalGameOptionsV10`); задавать через `o.SetInt(Int32OptionNames.NumImpostors/DiscussionTime/VotingTime/KillDistance/TaskBarMode/NumCommonTasks/NumShortTasks/NumLongTasks/NumEmergencyMeetings/EmergencyCooldown, v)`, `o.SetFloat(FloatOptionNames.KillCooldown/PlayerSpeedMod/CrewLightMod/ImpostorLightMod, v)`, `o.SetBool(BoolOptionNames.ConfirmImpostor/VisualTasks/AnonymousVotes/GhostsDoTasks, v)`, `o.SetByte(ByteOptionNames.MapId, 0)`. Поле `NumImpostors` у V10 только геттер — писать через SetInt. Роли: `o.roleOptions.SetRoleRate(RoleTypes.X, 0, 0)` для Scientist, Engineer, GuardianAngel, Shapeshifter, Noisemaker, Phantom, Tracker, Detective, Viper (`RoleOptionsCollectionV10`, `AnyRolesEnabled()` для проверки). Рассылка: `GameManager.Instance.LogicOptions.SetGameOptions(o)` + `SyncOptions()` (внутри `RpcSyncSettings`), сохранить `GameOptionsManager.Instance.SaveNormalHostOptions()`. Применённые в лобби — `GameOptionsManager.Instance.CurrentGameOptions` / `currentNormalGameOptions`.
- Роль локального: `me.Data.Role.Role` (`RoleTypes`: Crewmate0, Impostor1, CrewmateGhost6, ImpostorGhost7, ...), `me.Data.RoleType`, `me.Data.Role.IsImpostor`, `me.Data.IsDead`, `Role.CanVent/CanUseKillButton`. Маппинг в `crewmate|impostor|ghost_crew|ghost_imp`.
- **Утечка ролей:** у хоста в памяти есть роли всех (`GameData.Instance.AllPlayers[i].Role`), у остальных чужие роли обычно не заполнены (?). Правило моста: `partner` отдавать только если у локального `IsImpostor`, а чужие роли не читать вообще (даже на хосте).
- Конец игры: Postfix `AmongUsClient.OnGameEnd(EndGameResult)` (или `EndGameManager.Start`); причина `EndGameResult.CachedGameOverReason` / `GameOverReason`: CrewmatesByVote, CrewmatesByTask, CrewmateDisconnect → crew; ImpostorsByVote, ImpostorsByKill, ImpostorsBySabotage, ImpostorDisconnect → impostors. Хост завершает через `GameManager.Instance.RpcEndGame(reason, showAd)`.
- Фаза: `MeetingHud.Instance != null` → meeting (`state`: Discussion → «meeting», NotVoted/Voted → «voting», Results/Proceeding → «voting_result»); `ExileController.Instance != null` → итог; `ShipStatus.Instance != null && GameState==Started` → tasks; `EndGameManager` в сцене → ended. Заставка: `HudManager.Instance.IsIntroDisplayed`; готовность двигаться: `me.CanMove`. Старт собрания: Postfix `PlayerControl.StartMeeting(NetworkedPlayerInfo target)` (target null = кнопка).

## 6. Комната по позиции
- `ShipStatus.Instance.FastRooms : Dictionary<SystemTypes, PlainShipRoom>`, `PlainShipRoom.RoomId`, `.roomArea : Collider2D`. Определение: перебрать `FastRooms`, `room.roomArea.OverlapPoint(pos)`; не попал — коридор (`null`/"Hallway").
- Имя: `RoomId.ToString()` (Cafeteria, Weapons, Nav, Shields, Comms, Storage, Admin, Electrical, LowerEngine, UpperEngine, Security, Reactor, MedBay, LifeSupp...). Локализованное — `RoomTracker.Instance.GetRoomForPlayer(NetworkedPlayerInfo)`, `RoomTracker.LastRoom`; для моста лучше enum-имя без локали.
```csharp
foreach (var kv in ShipStatus.Instance.FastRooms) if (kv.Value.roomArea.OverlapPoint(pos)) return kv.Key.ToString();
```
Для задач/консолей: `Console.Room` (SystemTypes).

## Не нашёл / не проверено
- Флаг «виден» от игры — нет (только расчёт по свету+стенам). Navmesh — нет. Значения статических констант опкодов систем — в заглушках нет.
- Тела методов недоступны: `Complete()`, `ReportClosest()`, `Vent.Use()`, коды `RpcUpdateSystem` — проверять на ПК.
## Главные риски
1. Радиус/стены: расчёт видимости может расходиться с экраном (особенно двери и тень) — калибровать скриншотом.
2. Окна без фокуса (10 копий): идёт ли `FixedUpdate`/физика в фоне (`runInBackground`) — проверить.
3. Хост знает все роли — не отдавать; `partner` только импосторам.
4. Починка реактора требует двух игроков одновременно; опкоды саботажей — читать из статиков.
5. Минимум игроков для старта зависит от числа импостеров; в тестах `impostors=1`.
6. Сетка проходимости нужна своя (PathfindingAPI не проверен на 17.4); свободный чат может быть запрещён настройкой аккаунта.

## Шаг Core (v0.2.0) — что проверено вживую на 4 копиях
- `configure` / `start` / `wait_event` / расширенный `state` / лог партии работают (`scripts/test_core.py`, клиент `scripts/bridgecli.py`).
- `CalculateLightRadius` совпадает с `lightSource.ViewDistance` (экипаж 5, импостор 7.5 при ImpostorLightMod 1.5).
- Фаза `intro` (до `game_started`): роль ещё не назначена, поэтому `state.game` отдаёт только `{phase:"intro"}`; потом `phase:"tasks"` + `intro:true`, пока идёт заставка.
- `task.id` — индекс в списке задач игрока (0,1,…), не глобальный.
- Файлы лога из песочницы пишутся прямо в `D:\AmongUs-tools\games\` (в `Sandboxie.ini` для AU2..AU10 добавлен `OpenFilePath`). Размер открытого файла в `dir` показывает 0 — это задержка NTFS, содержимое на месте.
- `join` принимает только 127.0.0.1 и 10/8, 172.16/12, 192.168/16, loopback предпочитается; Tailscale 100.64/10, 198.18/15, Radmin 26/8, публичные пропускаются.
- Не проверено вживую: meeting_*/vote_cast/chat/sabotage/saw_kill/you_died/saw_vent/game_ended, `lost_player` с гистерезисом, видимость за стеной (нужны движение и действия — шаги Move и дальше).

## Шаг Move (v0.3.0) — что проверено вживую на 4 копиях
- Движение: Harmony Postfix на `PlayerPhysics.FixedUpdate` (для локального игрока при `CanMove`: `body.velocity = Desired * TrueSpeed`) + Postfix на геттер `KeyboardJoystick.DeltaL` (для анимации). Позицию шлёт `CustomNetworkTransform` сам. Телепорта нет. Скорость ~3 ед/с.
- Сетка проходимости (`Nav.cs`): шаг 0.25, область = рамка комнат/консолей + 2.5, клетка свободна, если `Physics2D.OverlapCircleAll(p, r+0.06, 4608)` не находит НЕ-триггерных коллайдеров (слои 9 «Ship» = 512 и 12 = 4096). Слой 12 — столы, `EmergencyConsole` и т.п.; `ShipOnlyMask` их НЕ видит, поэтому игрок упирался в стол кафетерия. Маска `ShipAndAllObjectsMask` через `CircleContains` ломается (считает триггеры). Данные: 3357 проходимых клеток из 197x122. Заливка от точки появления (пустота за стенами не попадает). Кэш: `D:\AmongUs-tools\games\nav\skeld_nt4608_*.nav`, построение ~40–110 мс, чтение из кэша ~7 мс. Отладка: команда моста `nav` (`mask`, `rebuild`, `dump` — ASCII-картинка, `probe:[x,y] r` — какие коллайдеры в точке).
- Слои: Players=8; `Constants.ShipOnlyMask`=512, `ShipAndObjectsMask`=2560, `ShipAndAllObjectsMask`=6656, `ShadowMask`=11264, `PlayersOnlyMask`=16640.
- A* по 8 соседям со штрафом у стен (до 4 клеток), потом «натягивание нити» по `Los` на сетке. Следование: пропуск точек пути при прямой видимости, замедление у цели. Анти-застревание: 2 с без сдвига >0.15 → запрет клеток впереди и перепланирование; 3 подряд → событие `stuck` и действие снимается.
- Действия: `stay|idle`, `move_to {room|pos}`, `follow {target,distance}`, `wander {room?}`, `do_task {id|next, durationSec?}`; команда моста `autopilot {on}`. Остальное (`kill`, `vote`...) пока `ok:false "action not supported yet"`. Любое явное действие выключает автопилот. Собрание снимает занятие.
- `do_task`: идёт к `task.Locations[0]` (ближайшая), стоит 3–6 с, зовёт `NormalPlayerTask.NextStep()`; многошаговые идут к следующей консоли и повторяют. Серверная часть сама: `RpcCompleteTask`, у другого клиента полоска растёт (0.11 → 0.22 при 9 задачах). Импостор: просто стоит и шлёт `task_faked`, `Complete` не зовёт.
- События: `arrived {room,pos}` (или `{reason:last_seen}` у follow), `stuck`, `lost_sight {name}`, `task_faked`; `task_done`/`tasks_all_done` дают наблюдатель.
- `state.game.busy`: `idle|moving|task|moving_to_task|following|wandering`; `state.game.body`: action, autopilot, nav, navStatus, stuck, desired, applied, vel, pathLeft, goal, task.
- Не сделано: закрытые двери саботажа в сетке (только анти-застревание), рефлексы, `report/kill/vote/chat/vent/sabotage`.
