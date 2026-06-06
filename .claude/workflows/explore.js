export const meta = {
  name: 'explore',
  description: 'Параллельная разведка подсистем по теме перед планированием — fan-out по модулям, затем синтез карты',
  whenToUse: 'Фаза @analyst/research: быстро собрать контекст по теме из нескольких частей кодовой базы сразу',
  phases: [
    { title: 'Scope', detail: 'определить релевантные подсистемы' },
    { title: 'Probe', detail: 'каждую подсистему исследует свой агент' },
    { title: 'Synthesize', detail: 'собрать единую карту' },
  ],
}

// тема разведки: args.topic | args (строка)
const topic = (args && (args.topic || (typeof args === 'string' ? args : args[0]))) || null
if (!topic) {
  log('explore: не передана тема. Запускай: Workflow({name:"explore", args:"<тема/вопрос>"})')
  return { error: 'no topic' }
}

const AREAS = {
  type: 'object',
  required: ['areas'],
  properties: {
    areas: {
      type: 'array',
      description: '3-7 конкретных подсистем/модулей/слоёв релевантных теме',
      items: {
        type: 'object',
        required: ['name', 'why'],
        properties: {
          name: { type: 'string', description: 'имя модуля/слоя/директории' },
          why: { type: 'string', description: 'чем релевантна теме' },
        },
      },
    },
  },
}

const PROBE = {
  type: 'object',
  required: ['area', 'summary', 'key_files', 'entrypoints'],
  properties: {
    area: { type: 'string' },
    summary: { type: 'string', description: 'как устроено, ключевые абстракции, потоки данных' },
    key_files: { type: 'array', items: { type: 'string', description: 'path:line с короткой пометкой' } },
    entrypoints: { type: 'array', items: { type: 'string' } },
    gotchas: { type: 'array', items: { type: 'string' }, description: 'риски/неочевидности для будущей правки' },
  },
}

phase('Scope')
const scope = await agent(
  `Тема разведки: «${topic}». Определи 3-7 подсистем/модулей/слоёв кодовой базы, которые надо исследовать чтобы спланировать работу по этой теме. ` +
  `Используй graphify query (если граф есть) и структуру репо. Не исследуй глубоко — только назови области и чем каждая релевантна.`,
  { label: 'scope', phase: 'Scope', schema: AREAS }
)

const areas = (scope?.areas || []).slice(0, 7)
log(`Областей к разведке: ${areas.length}`)

phase('Probe')
const probes = await parallel(areas.map((a) => () =>
  agent(
    `Исследуй подсистему «${a.name}» (${a.why}) в контексте темы «${topic}». ` +
    `graphify-first: \`graphify explain\`/\`graphify query\`/\`graphify path\`, Read — только точечно по найденным файлам. ` +
    `Верни: как устроено, ключевые файлы (path:line), точки входа, и gotchas для будущей правки.`,
    { label: `probe:${a.name}`, phase: 'Probe', schema: PROBE }
  )
))

const found = probes.filter(Boolean)

phase('Synthesize')
const map = await agent(
  `Собери единую карту разведки по теме «${topic}» из результатов по подсистемам. ` +
  `Дай: (1) общую картину как части связаны, (2) где именно лежит работа по теме, (3) порядок/зависимости для плана, (4) топ-риски. ` +
  `Данные подсистем (JSON):\n${JSON.stringify(found)}`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { topic, areas: found, map }
