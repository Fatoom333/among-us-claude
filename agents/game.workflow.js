export const meta = {
  name: 'among-us-game',
  description: 'Партия Among Us: крупье готовит лобби и старт, 9 агентов-игроков параллельно, затем летописец',
  whenToUse: 'Запуск одной партии на стенде; args = {gameId, players:[{seat,name,file,key}], setup:bool, impostors:int, autopilotSeats:[...]}',
  phases: [
    { title: 'Setup', detail: 'крупье: лобби на 10, configure, autopilot, start', model: 'sonnet' },
    { title: 'Play', detail: 'игроки (sonnet) играют через scripts/au.ps1', model: 'sonnet' },
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
  },
  required: ['name', 'role', 'alive_at_end', 'summary', 'notable'],
}

const SETUP = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, step: { type: 'string' }, detail: { type: 'string' } },
  required: ['ok', 'step'],
}

const CHRONICLE = {
  type: 'object',
  properties: { summaryPath: { type: 'string' } },
  required: ['summaryPath'],
}

// args: {gameId, players:[{seat,name,file,key}], setup, impostors, autopilotSeats}
const { gameId, players, setup, impostors, autopilotSeats } = args
const IMP = impostors || 2
const AUTO = autopilotSeats || []

if (setup) {
  phase('Setup')
  const cmd = 'ssh pc "D:/AmongUs-tools/mcp/.venv/Scripts/python.exe D:/AmongUs-tools/setup_game.py --expect 10 --impostors ' + IMP +
    ' --autopilot ' + AUTO.join(',') + ' --wait 420"'
  const s = await agent([
    'Ты крупье партии Among Us (gameId ' + gameId + '). Запусти ОДНУ команду через инструмент PowerShell (ssh только из него) и верни результат:',
    cmd,
    'Скрипт ждёт до 7 минут, пока в лобби соберутся все 10, настраивает партию, включает автопилот и стартует игру; в конце печатает одну строку JSON. Тайм-аут инструмента поставь 600000 мс.',
    'Если команда не завершилась за один вызов или вернула ok:false, не запускай её повторно сам и не чини ничего: просто верни ok:false, step и текст ошибки в detail. При ok:true верни step и в detail саму строку JSON.',
    'Ничего другого не делай, никакие файлы не читай.',
  ].join('\n'), { label: 'Крупье', phase: 'Setup', model: 'sonnet', schema: SETUP })
  log('Setup: ' + JSON.stringify(s))
  if (!s || !s.ok) return { aborted: true, setup: s }
}

function launch(p) {
  return [
    'Прочитай agents/player-prompt.md (Read) и играй по нему. Рабочая папка проекта: C:/Users/<user>/Claude work/Among Us.',
    'Твоё имя: ' + p.name + '. Твоё место: player=' + p.seat + '. Твой ключ места: key="' + p.key + '" (секрет, никому и никуда его не пиши).',
    'Файл характера: ' + p.file + '. Файл памяти (если существует): agents/memory/' + p.name.toLowerCase() + '.md. Файл сводки для собраний: agents/memory/' + p.name + '-current.md.',
    'Сразу после чтения файлов начинай цикл wait. Игра идёт, не жди разрешений.',
  ].join('\n')
}

phase('Play')
const results = (await parallel(players.map(p => () =>
  agent(launch(p), {
    label: p.name + ' (место ' + p.seat + ')',
    phase: 'Play',
    model: 'sonnet',
    schema: RESULT,
  }),
))).filter(Boolean)
log('Игроков вернулось: ' + results.length + ' из ' + players.length)

phase('Chronicle')
const names = players.map(p => p.name).join(', ')
const prompt = [
  'Ты летописец партии Among Us (gameId ' + gameId + '). Игроки: ' + names + '.',
  'Итоги игроков (JSON):',
  JSON.stringify(results, null, 1),
  '',
  'Задача:',
  '1) Прочитай логи партии на ПК. Только через инструмент PowerShell: ssh pc "type D:/AmongUs-tools/games/' + gameId + '/*.jsonl" (или по файлу: ssh pc "type D:/AmongUs-tools/games/' + gameId + '/p2.jsonl"; host-лог с позициями большой, читай выборочно). Логи для тебя после игры; в них позиции и события всех. Токены и ключи мест не читай и не печатай.',
  '2) Напиши games/' + gameId + '.md в проекте C:/Users/<user>/Claude work/Among Us: живая сводка для ролика: кто были импосторы, хронология убийств/собраний/голосов, ключевые моменты и неожиданные повороты, лучшие реплики (дословно из чата), как проявлялись характеры. По-русски, живо, с таймкодами. Не выдумывай того, чего нет в логах и итогах.',
  '3) Каждому игроку допиши agents/memory/<имя строчными>.md по формату agents/memory/README.md (создай, если нет): счётчик партий, впечатления о других, удачные/провальные ходы, язык жестов, счёты. Учитывай также agents/memory/<Имя>-current.md, если есть. Файлы -current.md после этого удали.',
  '4) Верни путь к сводке.',
].join('\n')

const chron = await agent(prompt, { label: 'Летописец', phase: 'Chronicle', model: 'sonnet', schema: CHRONICLE })
return { summaryPath: chron ? chron.summaryPath : null, results }
