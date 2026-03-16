# Aroma Trends Bot — инструкции для Claude

---

## Режимы работы

Проект использует два режима. Выбирай нужный по контексту задачи.

---

### Режим 1 — Software Factory (разработка фич)

Применяется когда: план согласован, задача описана через acceptance criteria + UX-вариант.

**Человек участвует ТОЛЬКО в двух точках:**
1. Утверждение UX-варианта (если выбор из нескольких дизайнов)
2. Утверждение критериев приёмки (что считать "готово")

**Всё остальное — полностью автономно:**
- Написать план → **не ждать подтверждения**, сразу реализовывать
- Создать ветку → написать код → запустить тесты → создать PR
- Дождаться зелёного CI → **смержить PR самостоятельно**
- После мержа: `git push origin main` → проверить деплой

**Пользователь НЕ проверяет и НЕ апрувит PR.** PR мержится автоматически после зелёного CI.

**Порядок шагов в Software Factory:**
1. Создать ветку `feature/...`
2. Реализовать фичу
3. Запустить тесты локально: `.venv/bin/python -m pytest tests/ -q --ignore=tests/ui`
4. Создать PR через `gh pr create`
5. Проверить: `gh pr view <N> --json mergeable,mergeStateStatus` → MERGEABLE
6. Дождаться: `gh pr checks <N>` → все зелёные
7. Смержить: `gh pr merge <N> --squash --auto` (или `--merge`)
8. `git checkout main && git pull origin main`
9. `git push origin main` → запускает деплой
10. Проверить GitHub Actions "Deploy" → сообщить пользователю о результате

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

### Режим 2 — Обычная разработка (парное программирование)

Применяется когда: разовая задача, эксперимент, правка бага без плана.

**Порядок:**
1. Написать план — дождаться явного подтверждения пользователя
2. Реализовать
3. Создать PR
4. Дождаться зелёного CI
5. **Показать PR пользователю и ждать его одобрения** перед мержем
6. После одобрения: смержить → `git push origin main` → проверить деплой

---

## Git-правила (оба режима)

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
.venv/bin/python -m pytest tests/ -q --ignore=tests/ui   # backend
.venv/bin/python -m pytest tests/ui/ -q                   # UI (Playwright)
```

Если UI-тесты не проходят — исправить ДО создания PR. Failing CI блокирует деплой.

---

## Чеклист после каждого изменения

| # | Пункт | Когда обязательно |
|---|-------|-------------------|
| 1 | ✅/❌ Тесты запущены и все зелёные | всегда |
| 2 | ✅/❌ Новые тесты добавлены | если изменилась логика/функция |
| 3 | ✅/❌ README.md обновлён | если добавлена новая команда или фича |
| 4 | ✅/❌ HELP_TEXT / WELCOME_TEXT обновлены | если добавлена новая команда |
| 5 | ✅/❌ n8n workflow обновлён и задеплоен | если изменился промпт или логика флоу |
| 6 | ✅/❌ PR создан и CI зелёный | всегда |
| 7 | ✅/❌ PR смержен (SF: авто; Regular: после апрува) | всегда |
| 8 | ✅/❌ `git push origin main` выполнен | после мержа |
| 9 | ✅/❌ Деплой проверен на VPS | после пуша в main |
| 10 | ✅/❌ Данные проверены на VPS после обогащения | после скриптов enrich/summarize/generate |

---

## Верификация данных на VPS

**После запуска любого скрипта обогащения** (`enrich_name_en.py`, `summarize_aroma_fields.py`, `generate_description_short.py` и др.) — **ОБЯЗАТЕЛЬНО проверить что данные реально сохранились** в БД. Запустить на VPS простой SELECT на обновлённое поле и убедиться что значение не `None`.

**Правило для JSON-столбцов:** Все JSON-столбцы в `db/models.py` используют `MutableDict.as_mutable(JSON)` / `MutableList.as_mutable(JSON)` для корректного отслеживания мутаций. **При добавлении новых моделей с JSON-столбцами — всегда использовать `MutableDict`/`MutableList`.** Без этого `model.payload = new_dict` не помечает объект как dirty и `session.commit()` молча ничего не сохраняет.

---

## Icon Policy

- **NEVER use raw inline SVG strings** for icons in miniapp code.
- **Always use Lucide Icons** via `icon(name, size)` helper → `<i data-lucide="...">`.
- After any dynamic DOM render that injects icons, call `if (window.lucide) lucide.createIcons()`.
- The MutationObserver on `#app` (falls back to `document.body`) handles most cases automatically.
- **Prefer Lucide over emoji** for UI elements (buttons, tabs, badges). Emoji OK only for category/sentiment indicators in text content.
- Before choosing an icon name, verify it exists at: https://lucide.dev/icons/

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
