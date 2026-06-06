# Aroma Trends Bot — инструкции для Claude

---

## Graphify — обязательный первый инструмент исследования

ЛЮБОЙ ответ на «где X / что использует Y / как связаны A и B / найди вызовы Z» НАЧИНАЕТСЯ с `graphify query`. Grep/Read/find — ТОЛЬКО fallback после графа.

```bash
graphify query "<вопрос>"
graphify path "NodeA" "NodeB"
graphify explain "NodeName"
# явный --graph если CLI не находит graphify-out/:
graphify query "<вопрос>" --graph "$(git rev-parse --show-toplevel)/graphify-out/graph.json"
```

Auto-update через tracked `.githooks/post-commit` / `.githooks/post-checkout` (code-only re-extract, без LLM). Активируются один раз: `bash scripts/graphify-bootstrap.sh` (ставит `core.hooksPath=.githooks` + строит граф; idempotent). Если граф отсутствует → запустить bootstrap. Линза графа настроена `.graphifyignore` (исключает .venv/data/assets/n8n — держим AST-граф кода `bot/`+`miniapp/`+`db/`).

---

## Режим работы: Software Factory (единственный)

**Режим один. Других нет. Любая задача — фича, баг, мелкая правка, опечатка — проходит через pipeline. Без исключений.**

Человек участвует ТОЛЬКО в двух точках:
1. Утверждение UX-варианта (если выбор из нескольких дизайнов)
2. Утверждение критериев приёмки (что считать "готово")

Всё остальное — полностью автономно:
- Написать план → **не ждать подтверждения**, сразу реализовывать
- Создать ветку → написать тесты → написать код → прогнать тесты → создать PR
- Дождаться зелёного CI → **смержить PR самостоятельно**
- После мержа: `git push origin main` → проверить деплой

**Пользователь НЕ проверяет и НЕ апрувит PR.** PR мержится автоматически после зелёного CI.

---

### Pipeline: последовательность этапов

Каждая задача проходит **полный** pipeline. PM (@pm) определяет scope, но НЕ может пропустить этап — каждый агент явно подтверждает "N/A для данной задачи" или выполняет свою работу.

```
Этап 1: @analyst           — требования, AC, scope, затрагиваемые компоненты
Этап 2: @product-designer  — user flow, wireframes, UX-варианты
         @architect          — техническое решение, API-контракты, декомпозиция
         (параллельно)
Этап 3: @backend/@frontend  — TDD: сначала тесты (RED), потом код (GREEN), рефакторинг
         @designer           — CSS, темизация, визуальная консистентность
         (параллельно)
Этап 4: @code-reviewer      — ревью кода, стандарты проекта, безопасность
         /codex:adversarial-review — второе мнение, максимально придирчивое
         (параллельно)
Этап 5: @qa                 — ВСЕ тесты зелёные (backend + UI + image QA)
Этап 6: @ux-reviewer        — проверка UI во всех 6 темах
Этап 7: @deploy             — PR, CI, мерж, push, проверка production
```

**Что значит N/A:** Агент получает задачу, смотрит scope и выносит вердикт:
- "N/A: задача не затрагивает UI, дизайн-ревью не требуется" — это ОК
- Пропустить этап молча без вердикта агента — **ЗАПРЕЩЕНО**

Примеры:
- Баг в API: @product-designer = N/A, @designer = N/A, @ux-reviewer = N/A
- Опечатка в UI: @architect = N/A (если нет архитектурных изменений)
- Новый экран: все этапы полностью, без N/A

---

### TDD: Test-Driven Development (обязательно)

Разработчик (@backend/@frontend) работает строго по TDD:

1. **RED** — написать тест, который падает (описывает ожидаемое поведение)
2. **GREEN** — написать минимальный код, чтобы тест прошёл
3. **REFACTOR** — улучшить код, сохраняя зелёные тесты

**Порядок работы разработчика:**
1. Получить AC от @analyst + техрешение от @architect
2. Создать ветку `feature/...` (или `fix/...`, `chore/...`)
3. **Сначала написать тесты** на acceptance criteria
4. Убедиться что тесты красные (fail) — если зелёные сразу, тест бессмысленный
5. Написать код, пока тесты не станут зелёные
6. Рефакторинг при необходимости
7. Запустить ВСЕ тесты — убедиться нет регрессий

**Минимум тестового покрытия:**
- Backend: каждый новый/изменённый endpoint, сервис, модель
- Frontend (UI-тесты): каждый новый/изменённый экран, компонент, user flow
- Edge cases: пустые данные, длинные строки, ошибки API, отсутствие данных

---

### Порядок шагов (технический)

1. Создать ветку `feature/...`
2. Написать тесты (RED)
3. Написать код (GREEN + REFACTOR)
4. Запустить тесты локально: `.venv/bin/python -m pytest tests/ -q --ignore=tests/ui -n auto`
5. Запустить UI-тесты: `.venv/bin/python -m pytest tests/ui/ -q`
6. **Codex Review:** `/codex:adversarial-review --base main` — исправить findings high/critical
7. Создать PR через `gh pr create`
8. Проверить: `gh pr view <N> --json mergeable,mergeStateStatus` → MERGEABLE
9. Дождаться: `gh pr checks <N>` → все зелёные
10. Смержить: `gh pr merge <N> --squash --auto` (или `--merge`)
11. `git checkout main && git pull origin main`
12. `git push origin main` → запускает деплой
13. Проверить GitHub Actions "Deploy" → сообщить пользователю о результате

**Software Factory checkpoints (обязательно для PRs с изменением карточек):**
1. **QA Agent:** `pytest tests/ -q` + проверить что все тесты зелёные
2. **UX Agent:** запустить `bot.agents.ux_reviewer.review_card_ux()` на изменённых карточках — score ≥ 0.7
3. **Aromatherapy Expert:** `bot.agents.aromatherapy_expert.verify_card_content(card, dry_run=True)` — проверка категоризации и source_type
4. **Image QA:** `tests/test_image_quality.py` — white stripe detection на все images в `assets/reference_images/`

**VPS скрипты запускать через `screen` (не `nohup`):**
```bash
ssh root@46.32.186.192 'screen -S oil-import -d -m bash -c "cd /opt/aroma && .venv/bin/python scripts/import_oil_pdfs.py 2>&1 | tee /tmp/oil_import.log"'
ssh root@46.32.186.192 'screen -S symptom-reseed -d -m bash -c "cd /opt/aroma && .venv/bin/python scripts/reseed_symptom_hierarchy.py 2>&1 | tee /tmp/reseed.log"'
# Проверить: ssh root@46.32.186.192 'screen -ls'
# Логи: ssh root@46.32.186.192 'cat /tmp/oil_import.log'
```

---

## Git-правила

- **ЗАПРЕЩЕНО коммитить напрямую в `main`** — только через Pull Request
- Все изменения в отдельной ветке (`git checkout -b feature/...`)
- После создания PR — обязательно проверить перед мержем:
  1. `gh pr view <N> --json mergeable,mergeStateStatus` → `"MERGEABLE"`, не `"CONFLICTING"`
  2. Если конфликт → `git rebase origin/main`, разрешить, тесты, force-push
  3. `gh pr checks <N>` → **ВСЕ зелёные** (и pytest, и miniapp-ui)
- **ЗАПРЕЩЕНО использовать `gh pr merge --admin`** для обхода красных тестов. Deploy зависит от прохождения ВСЕХ checks — если хоть один красный, Deploy не запустится. Если тесты падают — починить тесты, не обходить.
- **После мержа:** `git push origin main` — запускает автодеплой через GitHub Actions
- **Проверка деплоя:** Убедиться что GitHub Action "Deploy" прошёл успешно

---

## Тесты — обязательно перед каждым PR

Запускать оба набора:
```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/ui -n auto  # backend
.venv/bin/python -m pytest tests/ui/ -q                   # UI (Playwright)
```

Если UI-тесты не проходят — исправить ДО создания PR. Failing CI блокирует деплой.

### Правила написания UI-тестов (Playwright)

**ЗАПРЕЩЕНО** использовать `page.wait_for_timeout()` для ожидания рендера, навигации, данных или анимаций.
Единственные допустимые случаи для `wait_for_timeout()`: keyboard simulation delay, scroll momentum settle, visual snapshot stabilization.

**ОБЯЗАТЕЛЬНО** использовать хелперы из `tests/ui/helpers.py`:

| Хелпер | Когда использовать |
|--------|-------------------|
| `click_bottom_tab(page, "#btnTabXxx")` | Переключение нижних табов (ждёт `aria-pressed`) |
| `click_content_sub_tab(page, "Лейбл")` | Переключение контентных саб-табов (ждёт `.active`) |
| `click_draft_card(page, "Текст")` | Клик по карточке черновика (ждёт detail + контент) |
| `click_handbook_tab(page, "Название")` | Переключение табов справочника (ждёт `.reference-card`) |
| `click_section_chip(page, "Лейбл")` | Клик по секции-чипу (ждёт табы) |
| `nav_back_to_list(page)` | Возврат к списку (`goBackToList()` + ждёт карточки) |
| `click_create_tool(page, "Заголовок")` | Клик по инструменту создания (ждёт форму) |
| `wait_for_detail_panel(page)` | Ожидание контента в detail panel |
| `wait_visible(page, selector)` | Ожидание видимости элемента |
| `wait_hidden(page, selector)` | Ожидание скрытия элемента |
| `wait_for_app_ready(page)` | Ожидание `body.app-ready` |

**Принцип:** вместо "подождать N мс" → "подождать пока элемент появится/исчезнет". Это устраняет race conditions и flaky tests.

**Для новых элементов:** если кнопки/контент загружаются асинхронно, ВСЕГДА добавить `locator.wait_for(state="visible")` перед assert. Не полагаться на то, что предыдущий wait гарантирует рендер дочерних элементов.

---

## Чеклист после каждого изменения

| # | Пункт | Когда обязательно |
|---|-------|-------------------|
| 1 | ✅/❌ Тесты запущены и все зелёные | всегда |
| 2 | ✅/❌ Новые тесты добавлены | если изменилась логика/функция |
| 3 | ✅/❌ **Codex adversarial-review пройден** | **всегда перед PR** |
| 4 | ✅/❌ README.md обновлён | если добавлена новая команда или фича |
| 5 | ✅/❌ HELP_TEXT / WELCOME_TEXT обновлены | если добавлена новая команда |
| 6 | ✅/❌ n8n workflow обновлён и задеплоен | если изменился промпт или логика флоу |
| 7 | ✅/❌ PR создан и CI зелёный | всегда |
| 8 | ✅/❌ PR смержен автоматически после зелёного CI | всегда |
| 9 | ✅/❌ `git push origin main` выполнен | после мержа |
| 10 | ✅/❌ Деплой проверен на VPS | после пуша в main |
| 11 | ✅/❌ Данные проверены на VPS после обогащения | после скриптов enrich/summarize/generate |
| 12 | ✅/❌ UI проверен во всех 6 цветовых темах | если изменился UI/CSS |

---

## Система тем (Color Themes)

Miniapp поддерживает 6 цветовых тем:
`terracotta` (по умолчанию), `racing-green`, `champagne`, `violet`, `teal`, `raspberry`.

**Как работает:**
- Тема хранится в `BrandSettingsModel.theme` (SQLite) и в `localStorage("aromara_theme")`
- Применяется через `data-theme="<name>"` на `<body>` — все CSS-компоненты используют CSS-переменные
- При загрузке: сначала восстанавливается из localStorage (мгновенно, без мигания),
  затем синхронизируется с сервером (`GET /api/preferences/theme`)
- API: `GET /api/preferences/theme`, `PATCH /api/preferences/theme` (в `miniapp/api/routers/misc.py`)
- Выбор темы — в Настройках → Система → Цветовая тема

**Правило разработки UI:**
После добавления любого нового UI-компонента или экрана — проверить читаемость
и контраст во **всех 6 темах**. Использовать только CSS-переменные (`--brand`, `--bg`,
`--surface`, `--text`, `--muted`, `--border` и т.д.), никаких хардкодных hex-цветов.

**Тестирование тем (обязательно при изменениях UI):**
- Визуально проверить компонент в каждой из 6 тем через `document.body.dataset.theme = "X"`
- Минимальный контраст текста: WCAG AA (4.5:1 для обычного текста, 3:1 для крупного)
- Особое внимание: тема `champagne` — самая светлая из тёмных, `raspberry`/`teal` — нетипичные акценты

---

## Codex Review (обязательно перед каждым PR)

Проект использует OpenAI Codex (`@openai/codex`) как **второе мнение** для code review. Codex запускается через Claude Code plugin — `/codex:adversarial-review`.

**Принцип:** Codex должен быть **максимально придирчивым**. Его задача — найти причины НЕ мержить. Findings с severity high/critical блокируют мерж.

### Базовый review (каждый PR)
```
/codex:adversarial-review --base main
```
Codex проверяет: auth bypass, data loss, race conditions, idempotency, error handling, state management.

### Content Factory review (при изменении агентов/промптов)
При изменениях в `bot/agents/`, `bot/agents/prompts/`, `bot/services/miniapp_references/` — adversarial-review с расширенным focus-промптом (prompt injection, quality bypass, brand drift, retry/fallback, medical safety, cross-reference). Полный focus-промпт + состав агентов (~47) и промпт-файлов — в **[`docs/CONTENT-FACTORY.md`](docs/CONTENT-FACTORY.md)** (читать по необходимости, не грузится автоматически).

### Роль Codex (единая линия со всеми проектами)
- **Codex — primary reviewer/verifier.** `/codex:adversarial-review` обязателен на гейте перед PR (см. выше). Это основной режим использования Codex в проекте.
- **`codex:rescue` — только для разблокировки**, когда Claude-pipeline застрял (3+ итерации без прогресса) или нужна независимая диагностика/верификация сложного решения. НЕ рутинный fix-механизм: обычные фиксы делает разработчик (@backend/@frontend), не Codex.
- Мелкие правки (typo, README) — можно пропустить review (но пункт в чеклисте остаётся).

---

## Верификация данных на VPS

**После запуска любого скрипта обогащения** (`enrich_name_en.py`, `summarize_aroma_fields.py`, `generate_description_short.py` и др.) — **ОБЯЗАТЕЛЬНО проверить что данные реально сохранились** в БД. Запустить на VPS простой SELECT на обновлённое поле и убедиться что значение не `None`.

**Правило для JSON-столбцов:** Все JSON-столбцы в `db/models.py` используют `MutableDict.as_mutable(JSON)` / `MutableList.as_mutable(JSON)` для корректного отслеживания мутаций. **При добавлении новых моделей с JSON-столбцами — всегда использовать `MutableDict`/`MutableList`.** Без этого `model.payload = new_dict` не помечает объект как dirty и `session.commit()` молча ничего не сохраняет.

---

## Icon Policy

Проект использует **Phosphor Icons** (НЕ Lucide — миграция выполнена; Lucide не загружается, `data-lucide` даёт пустые/сломанные иконки).

- **NEVER use raw inline SVG strings** for icons in miniapp code.
- **Always use Phosphor Icons** via `<i class="ph ph-{name}">` — напрямую или через helper'ы `icon(name, size)` / `uiIcon(name)` в `miniapp/static/app.js`.
- Семантические алиасы — в `PHOSPHOR_MAP` (`app.js`, напр. "note" → "pencil-line", "reel" → "video-camera"). Проверять там перед выбором имени.
- **NEVER use `data-lucide`** attributes или любые ссылки на Lucide.
- **Prefer Phosphor over emoji** for UI elements (buttons, tabs, badges). Emoji OK only for category/sentiment indicators in text content.
- Before choosing an icon name, verify it exists at: https://phosphoricons.com/

---

## Обработчики событий в HTML-артефактах

- **НИКОГДА** не используй inline-атрибуты `onclick`/`onchange`/`onsubmit`/`oninput` и т.д.:
  - ❌ `<button onclick="exportToCanva()">`
  - ❌ `<div onchange="handleChange(event)">`
- **ВСЕГДА** вешай обработчики через `addEventListener` после DOMContentLoaded:
  - ✅ `document.getElementById('btn').addEventListener('click', exportToCanva)`
  - ✅ `document.querySelector('.select').addEventListener('change', handleChange)`
- **Причина:** inline `onclick` ищет функцию в `window`. Функции внутри `<script type="module">`, IIFE или замыканий — в `window` не попадают.
- Если HTML генерируется динамически (`innerHTML`), используй **делегирование событий**:
  ```js
  container.addEventListener('click', (e) => {
    if (e.target.matches('.export-btn')) exportToCanva(e.target.dataset.id);
  });
  ```

---

## Архитектура и База Данных

**Хранение данных:**
- Вместо JSON используется **SQLite** через **SQLAlchemy (Async)**.
- База данных: `data/aroma.db` (исключена из git).
- Модели: `db/models.py`.
- Сессии: `db/session.py` (использовать `AsyncSessionLocal`).

**Миграции (Alembic):**
- Все изменения схемы БД делаются через миграции.
- Создать миграцию: `.venv/bin/alembic revision --autogenerate -m "описание"`
- Применить миграции: `.venv/bin/alembic upgrade head`

**Важное правило для Drafts и Plans:**
- Все функции в `bot/services/drafts_store.py` и `bot/services/plans_store.py` являются **асинхронными**.
- `Drafts` и `Plans` хранятся в SQLite как основной source of truth, а не в JSON-файлах.
- Всегда вызывать store-функции через `await`.
- JSON-файлы в `data/` и `scripts/` допустимы только как seed/import-артефакты для справочника и одноразовых утилит.
- Нельзя добавлять новые runtime-paths для `Drafts`/`Plans` через JSON без отдельного архитектурного решения.
- Coverage/alignment PR и product/behavior PR лучше держать раздельно; если scope изменился, PR должен быть переименован или разделён.
- `miniapp/static/app.js` должен оставаться orchestration-слоем, а общие helper-куски выносятся в `miniapp/static/js/*`.

**Тесты:**
- Тесты находятся в `tests/` и запускаются командой: `.venv/bin/pytest`
- Проект использует `pytest-asyncio`. Настройки в `pytest.ini`.
- UI-тесты используют **Playwright**. Запуск: `.venv/bin/pytest tests/ui/`
- Перед запуском UI-тестов нужно установить браузеры: `playwright install chromium`

---

## Проект

Telegram-бот для мониторинга трендов ароматерапии / ольфактотерапии / гонг-медитации / звукового целительства.

- Рабочая директория: `/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aroma/`
- Виртуальное окружение: `.venv/`
- Запуск бота: `.venv/bin/python main.py`
- Лог бота: `/tmp/aroma_bot.log`

---

## n8n визуализация пайплайна

- URL: http://localhost:5678
- Workflow ID: `uVGs2O7RguKjLWSW`
- Файл: `aroma_bot_pipeline.n8n.json`
- Запуск n8n: `docker start n8n`

**После изменения любого промпта или логики флоу — обновить n8n:**
```bash
curl -s -X PUT http://localhost:5678/api/v1/workflows/uVGs2O7RguKjLWSW \
  -H "Content-Type: application/json" \
  -H "X-N8N-API-KEY: <API_KEY>" \
  -d @"/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aroma/aroma_bot_pipeline.n8n.json"
```
*(API ключ берётся из настроек n8n UI → Settings → API Keys)*

---

## Деплой на VPS

Бот работает на VPS `46.32.186.192` как systemd-сервисы `aroma-bot` и `aroma-miniapp`.

**Автоматический деплой (GitHub Actions):**
Деплой происходит автоматически при пуше в ветку `main` после прохождения тестов.
1. Смержить PR в `main`
2. Выполнить `git push origin main`
3. Следить за статусом в [GitHub Actions](https://github.com/stress-ins/aroma-bot/actions)

**One-time data scripts (VPS):**
Deploy workflow автоматически запускает скрипты обогащения данных на VPS (cleanup, name_ru, descriptions).
Скрипты идемпотентные — запускаются один раз (маркер `.enrichment_done`).
Для повторного запуска: `ssh root@46.32.186.192 'rm /opt/aroma/.enrichment_done'` и передеплоить.

**Перезапуск вручную:**
```bash
ssh root@46.32.186.192 'systemctl restart aroma-bot aroma-miniapp'
```

**Логи:**
```bash
ssh root@46.32.186.192 'journalctl -u aroma-bot -n 50 --no-pager'
ssh root@46.32.186.192 'journalctl -u aroma-miniapp -n 50 --no-pager'
```

---

## n8n на VPS

Сервис: `n8n-aroma` (systemd, Docker-wrapper через `deploy/n8n.service`)
Первичная установка: `bash scripts/vps_n8n_setup.sh`
Доступ: `./n8n-tunnel.sh` → http://localhost:5678
Workflow JSON: `n8n/workflows/` — импортируются автоматически через `deploy.yml`

**GitHub Secrets (добавить обязательно):**
- `N8N_API_KEY` — для импорта workflow через deploy.yml
- `N8N_WEBHOOK_SECRET` — X-Webhook-Secret для POST /api/trends/trigger и /api/mentions/ingest

**Workflows:**
- `01_trends_schedule.json` — daily 06:00 UTC → POST /api/trends/trigger
- `02_telegram_mentions.json` — Telegram webhook → ingest mentions
- `03_threads_instagram_polling.json` — poll Threads/Instagram every 3 min
- `04_mention_notifications.json` — notify admin on new mention
- `05_token_refresh.json` — daily token expiry check + refresh

После установки: активировать все 5 workflow в n8n UI (по умолчанию `active: false`).
