# Aroma Trends Bot — инструкции для Claude

## Рабочий процесс

**Всегда использовать план перед реализацией:**
1. Перед любым изменением кода написать план: что меняется, в каких файлах, почему
2. Дождаться явного подтверждения от пользователя
3. После подтверждения — выполнить всё самостоятельно, без вопросов на каждый шаг
4. В конце пройти по чеклисту и показать результат пользователю

Не спрашивать подтверждения на отдельные шаги внутри утверждённого плана.

**Git-workflow — обязательные правила:**
- Все изменения делаются в отдельной ветке (`git checkout -b feature/...`)
- **ЗАПРЕЩЕНО коммитить напрямую в `main`** — только через Pull Request
- После завершения работы: создать PR через `gh pr create`, дождаться явного одобрения от пользователя, только потом мержить
- **После создания PR — обязательно проверить:**
  1. `gh pr view <N> --json mergeable,mergeStateStatus` — должно быть `"mergeable":"MERGEABLE"`, не `"CONFLICTING"`
  2. Если конфликт — сделать `git rebase origin/main`, разрешить конфликты, запустить тесты, force-push
  3. GitHub Actions (CI) — убедиться что тесты запустились и прошли: `gh pr checks <N>`
  4. Только после зелёных проверок и отсутствия конфликтов — показывать PR пользователю
- **После мержа PR:** ОБЯЗАТЕЛЬНО сделать `git push origin main`, чтобы запустить автоматический деплой через GitHub Actions
- **Проверка деплоя:** Убедиться, что GitHub Action "Deploy" завершился успешно и изменения доехали до VPS

## Чеклист после каждого изменения

В конце каждой задачи **обязательно** пройти по этому списку и показать пользователю статус каждого пункта:

| # | Пункт | Когда обязательно |
|---|-------|-------------------|
| 1 | ✅/❌ Тесты запущены и все зелёные | всегда |
| 2 | ✅/❌ Новые тесты добавлены | если изменилась логика/функция |
| 3 | ✅/❌ README.md обновлён | если добавлена новая команда или фича |
| 4 | ✅/❌ HELP_TEXT / WELCOME_TEXT обновлены | если добавлена новая команда |
| 5 | ✅/❌ n8n workflow обновлён и задеплоен | если изменился промпт или логика флоу |
| 6 | ✅/❌ PR создан и одобрен пользователем | всегда |
| 7 | ✅/❌ Сделан `git push origin main` | после мержа в main |
| 8 | ✅/❌ Деплой проверен на VPS | после пуша в main |

Показывать таблицу в конце каждого ответа с выполненными задачами.

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
- Coverage/alignment PR и product/behavior PR лучше держать раздельно; если scope изменился, PR должен быть переименован или разделен.
- `miniapp/static/app.js` должен оставаться orchestration-слоем, а общие helper-куски выносятся в `miniapp/static/js/*`.

**Тесты:**
- Тесты находятся в `tests/` и запускаются командой: `.venv/bin/pytest`
- Проект использует `pytest-asyncio`. Настройки в `pytest.ini`.
- UI-тесты используют **Playwright**. Запуск: `.venv/bin/pytest tests/ui/`
- Перед запуском UI-тестов нужно установить браузеры: `playwright install chromium`

## Проект

Telegram-бот для мониторинга трендов ароматерапии / ольфактотерапии / гонг-медитации / звукового целительства.

- Рабочая директория: `/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aroma/`
- Виртуальное окружение: `.venv/`
- Запуск бота: `.venv/bin/python main.py`
- Лог бота: `/tmp/aroma_bot.log`

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

## Деплой на VPS

Бот работает на VPS `46.32.186.192` как systemd-сервисы `aroma-bot` и `aroma-miniapp`.

**Автоматический деплой (GitHub Actions):**
Деплой происходит автоматически при пуше в ветку `main` после прохождения тестов.
1. Смержить PR в `main` (локально или через UI)
2. Выполнить `git push origin main`
3. Следить за статусом в [GitHub Actions](https://github.com/stress-ins/aroma-bot/actions)

**Перезапуск вручную:**
```bash
ssh root@46.32.186.192 'systemctl restart aroma-bot aroma-miniapp'
```

**Логи:**
```bash
ssh root@46.32.186.192 'journalctl -u aroma-bot -n 50 --no-pager'
ssh root@46.32.186.192 'journalctl -u aroma-miniapp -n 50 --no-pager'
```
