export const meta = {
  name: 'review-branch',
  description: 'Параллельный multi-angle review текущей ветки vs base + adversarial-verify каждой находки',
  whenToUse: 'Перед PR/merge: быстрый широкий ревью ветки несколькими углами сразу, с отсевом ложных находок',
  phases: [
    { title: 'Review', detail: 'N измерений ревьюят diff параллельно' },
    { title: 'Verify', detail: 'каждая находка проверяется скептиком как только готова' },
  ],
}

// base ветка для diff: args.base | первый элемент args (строка) | origin/main
const base = (args && (args.base || (typeof args === 'string' ? args : args[0]))) || 'origin/main'

const DIMENSIONS = [
  { key: 'correctness', lens: 'Логические ошибки, баги, неверные граничные случаи, race conditions, ошибки обработки ошибок/null, регрессии поведения.' },
  { key: 'project-rules', lens: 'ZERO-tolerance правила проекта из CLAUDE.md/AGENTS.md (hardcoded цвета/hex вместо токенов, runtime-метрики, hardcode domain-значений, SEO-инварианты, UI entry points). Прочитай корневой CLAUDE.md проекта и проверь diff против КАЖДОГО его «запрещено/БЛОКЕР» правила.' },
  { key: 'security', lens: 'Auth bypass, injection (SQL/XSS/prompt), утечки секретов, небезопасные дефолты, недостающая авторизация, idempotency.' },
  { key: 'testing', lens: 'Покрытие изменённой логики тестами (TDD), пропущенные edge cases, flaky-паттерны (wait_for_timeout/sleep), тесты что не падают на сломанном коде.' },
  { key: 'simplify', lens: 'Дублирование, переусложнение, мёртвый код, возможность переиспользовать существующее, неоправданная сложность.' },
]

const FINDINGS = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'file', 'severity', 'detail'],
        properties: {
          title: { type: 'string' },
          file: { type: 'string', description: 'path:line' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          detail: { type: 'string', description: 'что не так и почему, со ссылкой на конкретный код' },
          suggestion: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT = {
  type: 'object',
  required: ['isReal', 'reason'],
  properties: {
    isReal: { type: 'boolean', description: 'находка реальна и стоит починки' },
    reason: { type: 'string' },
  },
}

log(`review-branch: diff vs ${base}, ${DIMENSIONS.length} измерений`)

const reviewed = await pipeline(
  DIMENSIONS,
  (d) => agent(
    `Ты ревьюишь git-ветку проекта. Сначала выполни сам: \`git --no-pager diff ${base}...HEAD\` (если пусто — \`git --no-pager diff ${base}\`). ` +
    `Используй graphify query для проверки связей, если граф есть. ` +
    `Угол ревью «${d.key}»: ${d.lens} ` +
    `Сообщай ТОЛЬКО реальные проблемы в изменённом коде, не стилистику. Для каждой — file:line и почему. Если проблем нет — верни пустой массив.`,
    { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS }
  ),
  (res, d) => parallel((res?.findings || []).map((f) => () =>
    agent(
      `Adversarially проверь находку code-review. Попробуй её ОПРОВЕРГНУТЬ — посмотри реальный код по ссылке. ` +
      `Находка [${f.severity}] «${f.title}» в ${f.file}: ${f.detail}. ` +
      `Это действительно проблема в текущем коде, или ложное срабатывание/уже обработано? По умолчанию isReal=false если сомневаешься.`,
      { label: `verify:${d.key}`, phase: 'Verify', schema: VERDICT }
    ).then((v) => ({ ...f, dimension: d.key, verdict: v }))
  ))
)

const confirmed = reviewed.flat().filter(Boolean).filter((f) => f.verdict?.isReal)
const order = { critical: 0, high: 1, medium: 2, low: 3 }
confirmed.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))

log(`Подтверждено находок: ${confirmed.length}`)
return {
  base,
  confirmed_count: confirmed.length,
  blockers: confirmed.filter((f) => f.severity === 'critical' || f.severity === 'high'),
  findings: confirmed,
}
