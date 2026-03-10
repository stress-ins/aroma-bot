# Aroma Trends Bot — инструкции для Claude

## Рабочий процесс

**Всегда использовать план перед реализацией:**
1. Перед любым изменением кода написать план: что меняется, в каких файлах, почему
2. Дождаться явного подтверждения от пользователя
3. После подтверждения — выполнить всё самостоятельно, без вопросов на каждый шаг
4. В конце пройти по чеклисту и показать результат пользователю

Не спрашивать подтверждения на отдельные шаги внутри утверждённого плана.

## Чеклист после каждого изменения

В конце каждой задачи **обязательно** пройти по этому списку и показать пользователю статус каждого пункта:

| # | Пункт | Когда обязательно |
|---|-------|-------------------|
| 1 | ✅/❌ Тесты запущены и все зелёные | всегда |
| 2 | ✅/❌ Новые тесты добавлены | если изменилась логика/функция |
| 3 | ✅/❌ README.md обновлён | если добавлена новая команда или фича |
| 4 | ✅/❌ HELP_TEXT / WELCOME_TEXT обновлены | если добавлена новая команда |
| 5 | ✅/❌ n8n workflow обновлён и задеплоен | если изменился промпт или логика флоу |
| 6 | ✅/❌ Бот перезапущен | всегда |

Показывать таблицу в конце каждого ответа с выполненными задачами.

**После любого изменения функциональности ОБЯЗАТЕЛЬНО обновить:**
- `README.md` — команды, описание фич, файловая структура
- `HELP_TEXT` и `WELCOME_TEXT` в `bot/handlers/commands.py` если добавлена новая команда

**Тесты:**
- Тесты находятся в `tests/` и запускаются командой: `.venv/bin/python -m pytest tests/ -v`
- После любого изменения логики: запустить тесты и убедиться что все проходят
- При добавлении новой функции: добавить тесты в соответствующий файл в `tests/`
  - `tests/test_formatters.py` — форматтеры, MarkdownV2, отчёты
  - `tests/test_utils.py` — утилиты, парсинг ответов Claude, вспомогательные функции

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

Бот работает на VPS `46.32.186.192` как systemd-сервис `aroma-bot`.

**Задеплоить изменения:**
```bash
cd "/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aroma"
git add -A && git commit -m "описание изменений"
git push vps main
```
После push хук автоматически: checkout → pip install → systemctl restart aroma-bot.

**Перезапуск вручную:**
```bash
ssh root@46.32.186.192 'systemctl restart aroma-bot'
```

**Логи:**
```bash
ssh root@46.32.186.192 'journalctl -u aroma-bot -n 50 --no-pager'
```
