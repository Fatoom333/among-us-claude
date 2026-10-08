export const meta = {
  name: 'among-us-game',
  description: 'Партия Among Us: 9 агентов-игроков параллельно, затем летописец',
  whenToUse: 'Запуск одной партии на стенде; args = {roster, seats, gameId, personalities, memories, playerPrompt}',
  phases: [
    { title: 'Play', detail: '9 игроков (sonnet) играют через MCP au', model: 'sonnet' },
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

const CHRONICLE = {
  type: 'object',
  properties: { summaryPath: { type: 'string' } },
  required: ['summaryPath'],
}

const { roster, seats, gameId, personalities, memories, playerPrompt } = args

function fill(tpl, r) {
  const map = {
    PERSONALITY: personalities[r.name] || '',
    MEMORY: (memories && memories[r.name]) || '(пока нет: это твоя первая партия)',
    PLAYER: String(r.seat),
    KEY: seats[String(r.seat)],
    NAME: r.name,
  }
  return tpl.replace(/\{\{(\w+)\}\}/g, (m, k) => (k in map ? map[k] : m))
}

phase('Play')
const results = (await parallel(roster.map(r => () =>
  agent(fill(playerPrompt, r), {
    label: r.name + ' (место ' + r.seat + ')',
    phase: 'Play',
    model: 'sonnet',
    schema: RESULT,
  }),
))).filter(Boolean)
log('Игроков вернулось: ' + results.length + ' из ' + roster.length)

phase('Chronicle')
const names = roster.map(r => r.name).join(', ')
const prompt = [
  'Ты летописец партии Among Us (gameId ' + gameId + '). Игроки: ' + names + '.',
  'Итоги игроков (JSON):',
  JSON.stringify(results, null, 1),
  '',
  'Задача:',
  '1) Прочитай логи партии на ПК. Только через инструмент PowerShell: ssh pc "type D:/AmongUs-tools/games/' + gameId + '/*.jsonl" (или по файлу: ssh pc "type D:/AmongUs-tools/games/' + gameId + '/p2.jsonl"; host-лог с позициями большой, читай выборочно). Логи для тебя после игры; в них позиции и события всех.',
  '2) Напиши games/' + gameId + '.md в проекте C:/Users/<user>/Claude work/Among Us: живая сводка для ролика: кто были импосторы, хронология убийств/собраний/голосов, ключевые моменты и неожиданные повороты, лучшие реплики (дословно из чата), как проявлялись характеры. По-русски, живо, с таймкодами. Не выдумывай того, чего нет в логах и итогах.',
  '3) Каждому игроку допиши agents/memory/<имя строчными>.md по формату agents/memory/README.md (создай, если нет): счётчик партий, впечатления о других, удачные/провальные ходы, язык жестов, счёты. Учитывай также agents/memory/<Имя>-current.md, если есть. Файлы -current.md после этого удали.',
  '4) Верни путь к сводке.',
].join('\n')

const chron = await agent(prompt, { label: 'Летописец', phase: 'Chronicle', model: 'sonnet', schema: CHRONICLE })
return { summaryPath: chron ? chron.summaryPath : null, results }
