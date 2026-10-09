export const meta = {
  name: 'among-us-game',
  description: 'Партия Among Us: крупье готовит лобби и старт, 9 агентов-игроков (au-player, только MCP au) параллельно, затем летописец',
  whenToUse: 'Запуск одной партии на стенде; args — вывод node agents/game-args.mjs',
  phases: [
    { title: 'Setup', detail: 'крупье: лобби на 10, configure, autopilot, start', model: 'sonnet' },
    { title: 'Play', detail: 'игроки au-player: только инструменты MCP au_*', model: 'sonnet' },
    { title: 'Chronicle', detail: 'летописец: сводка партии и память', model: 'sonnet' },
  ],
}

const RESULT = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    role: { type: 'string' },
    alive_at_end: { type: 'boolean' },
    summary: { type: 'string' },
    notable: { type: 'array', items: { type: 'string' } },
    memory: { type: 'string', description: '3–8 строк на будущие партии' },
  },
  required: ['name', 'role', 'alive_at_end', 'summary', 'notable', 'memory'],
}
const SETUP = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, step: { type: 'string' }, detail: { type: 'string' } },
  required: ['ok', 'step'],
}
const CHRONICLE = {
  type: 'object',
  properties: { summaryPath: { type: 'string' }, recap: { type: 'string' } },
  required: ['summaryPath', 'recap'],
}

// args: {gameId, players:[{seat,name,key}], setup, impostors, autopilotSeats}; briefs (rules+personality+memory)
// are already on the PC — game-args.mjs put them there, players fetch their own with au_brief.
const { gameId, players, setup, impostors, autopilotSeats } = args
// everything below that reaches a command line is validated: plain integers and a plain game id only
if (!/^[A-Za-z0-9-]{1,40}$/.test(String(gameId))) throw new Error('bad gameId')
const IMP = Number.isInteger(impostors) && impostors >= 1 && impostors <= 3 ? impostors : 2
const AUTO = (autopilotSeats || []).filter(x => Number.isInteger(x) && x >= 1 && x <= 10)
for (const p of players) {
  if (!Number.isInteger(p.seat) || p.seat < 1 || p.seat > 10 || !/^[A-Za-z0-9_-]{1,20}$/.test(String(p.name)) || !/^[0-9a-f]{16,128}$/.test(String(p.key)))
    throw new Error('bad player entry for seat ' + p.seat)
}

// The same command runs on the PC directly and on the laptop through ssh.
const PY = 'D:/AmongUs-tools/mcp/.venv/Scripts/python.exe'
const WHERE = 'Узнай машину: Test-Path D:/AmongUs-tools/mcp/server.py. Есть (это ПК со стендом) — запускай команду напрямую; нет — через ssh pc "<команда>" (ssh только из инструмента PowerShell).'

if (setup) {
  phase('Setup')
  const cmd = PY + ' D:/AmongUs-tools/setup_game.py --expect 10 --impostors ' + IMP + ' --autopilot ' + AUTO.join(',') + ' --wait 420'
  const s = await agent([
    'Ты крупье партии Among Us (gameId ' + gameId + '). Выполни ОДНУ команду через инструмент PowerShell и верни результат.',
    WHERE,
    'Команда: ' + cmd,
    'Скрипт ждёт до 7 минут, пока в лобби соберутся все 10, настраивает партию, включает автопилот и стартует игру; в конце печатает одну строку JSON. Тайм-аут инструмента поставь 600000 мс.',
    'Если команда не завершилась за один вызов или вернула ok:false, не запускай её повторно и ничего не чини: верни ok:false, step и текст ошибки в detail. При ok:true верни step и в detail саму строку JSON.',
    'Ничего другого не делай, никакие файлы не читай.',
  ].join('\n'), { label: 'Крупье', phase: 'Setup', model: 'sonnet', schema: SETUP })
  log('Setup: ' + JSON.stringify(s))
  if (!s || !s.ok) return { aborted: true, setup: s }
}

// Human host (setup=false): the lobby was prepared beforehand with setup_game.py --no-start; the human changes
// settings and presses Start. Autopilot seats can only be switched on after the ship exists, so a croupier waits
// for the start in parallel with the players.
function afterStart() {
  const cmd = PY + ' D:/AmongUs-tools/setup_game.py --after-start --autopilot ' + AUTO.join(',') + ' --wait 1500'
  return agent([
    'Ты крупье партии Among Us (gameId ' + gameId + '). Выполни ОДНУ команду через инструмент PowerShell и верни результат.',
    WHERE,
    'Команда: ' + cmd,
    'Скрипт ждёт до 25 минут, пока человек-хост нажмёт «Старт», потом включает автопилот на местах ' + AUTO.join(',') + '; в конце печатает одну строку JSON. Запусти его в фоне (run_in_background) и дождись завершения, не перезапуская.',
    'При ok:false ничего не чини: верни ok:false, step и ошибку в detail. При ok:true верни step и строку JSON в detail. Ничего другого не делай, файлы не читай.',
  ].join('\n'), { label: 'Крупье (автопилот)', phase: 'Play', model: 'sonnet', schema: SETUP })
}

function launch(p) {
  return [
    'Ты игрок Among Us: имя ' + p.name + ', место player=' + p.seat + ', ключ места key="' + p.key + '" (секрет: не пиши его в чат игры).',
    'Первым делом вызови au_brief(player=' + p.seat + ', key=...) — там правила, твой характер и память — и дальше играй строго по нему. ' +
      (setup ? 'Игра уже идёт, разрешений не жди.' : 'Вы в лобби: игра начнётся, когда хост нажмёт «Старт». До game_started просто жди через au_wait (timeout 55), ничего не делая и не комментируя.'),
  ].join('\n')
}
phase('Play')
const croupier = !setup && AUTO.length ? [() => afterStart().then(s => { log('Автопилот: ' + JSON.stringify(s)); return null })] : []
const results = (await parallel([...croupier, ...players.map(p => () =>
  agent(launch(p), {
    label: p.name + ' (место ' + p.seat + ')',
    phase: 'Play',
    agentType: 'au-player',
    model: 'sonnet',
    schema: RESULT,
  }),
)])).filter(Boolean)
log('Игроков вернулось: ' + results.length + ' из ' + players.length)

phase('Chronicle')
const names = players.map(p => p.name).join(', ')
const prompt = [
  'Ты летописец партии Among Us (gameId ' + gameId + '). Игроки: ' + names + '.',
  'Итоги игроков (JSON; поле memory — что игрок сам хочет помнить):',
  JSON.stringify(results, null, 1),
  '',
  'Задача:',
  '1) Прочитай логи партии: папка D:/AmongUs-tools/games/' + gameId + '/ (p<id>.jsonl и god.jsonl с позициями — большой, читай выборочно). ' + WHERE + ' Пример: Get-Content D:/AmongUs-tools/games/' + gameId + '/p2.jsonl. Токены, ключи мест и seats.json не читай.',
  '2) Напиши games/' + gameId + '.md в корне проекта (рабочая папка): живая сводка для ролика — кто были импосторы, хронология убийств/собраний/голосов, ключевые моменты и повороты, лучшие реплики (дословно из чата), как проявлялись характеры. По-русски, с таймкодами. Не выдумывай того, чего нет в логах и итогах.',
  '3) Каждому игроку допиши agents/memory/<имя строчными>.md по формату agents/memory/README.md (создай, если нет): счётчик партий, впечатления о других, удачные/провальные ходы, язык жестов, счёты. Опирайся на поле memory из его итога и на логи.',
  '4) Верни путь к сводке и recap: пересказ партии для Тарти в чат, 8–15 строк по-русски простым языком — кто были предатели и как их (не) вычислили, кто кого убил, ключевые собрания и выбросы, 2–3 лучшие реплики дословно, чем запомнился каждый бот (по строчке на заметных). Без таблиц.',
].join('\n')

const chron = await agent(prompt, { label: 'Летописец', phase: 'Chronicle', model: 'sonnet', schema: CHRONICLE })
return { summaryPath: chron ? chron.summaryPath : null, recap: chron ? chron.recap : null, results: results.map(r => ({ name: r.name, role: r.role, alive_at_end: r.alive_at_end, summary: r.summary })) }
