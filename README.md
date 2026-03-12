# 🌿 Aroma Trends Bot

[![Tests](https://github.com/stress-ins/aroma-bot/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/stress-ins/aroma-bot/actions/workflows/test.yml)
[![Deploy](https://github.com/stress-ins/aroma-bot/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/stress-ins/aroma-bot/actions/workflows/deploy.yml)

Телеграм-бот для мониторинга трендов в ароматерапии, ольфактотерапии, медитации гонг и звуковом целительстве. Собирает данные из 10+ источников, формирует два отчёта (🇷🇺 и 🇬🇧), генерирует темы постов для Threads и карусели с картинками через AI.

## Репозитории и продакшен-роли

Этот репозиторий отвечает за Telegram-бот и Threads OAuth callback.

- локальный путь бота: `/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aroma`
- продакшен-путь бота на VPS: `/opt/aroma`
- systemd-сервис бота: `aroma-bot`
- Threads OAuth callback на VPS: `threads-oauth.service`
- Mini App на VPS: `aroma-miniapp.service`

Публичный сайт вынесен в отдельный репозиторий:

- локальный путь сайта: `/Users/p.kutsenko/Library/Mobile Documents/com~apple~CloudDocs/python/aromara-site`
- продакшен-путь сайта на VPS: `/opt/aromara-site`
- systemd-сервис сайта: `aromara-site`
- домен сайта: `https://aromara.ru`

Схема доменов на VPS:

- `https://aromara.ru` и `https://www.aromara.ru` → `nginx` → `127.0.0.1:3005` → `aromara-site`
- `https://oauth.aromara.ru` → `nginx` → `127.0.0.1:8090` → `threads-oauth.service`
- `https://app.aromara.ru` → `nginx` → `127.0.0.1:8091` → `aroma-miniapp.service`

## CI/CD

- `push` в `main` и `pull_request` запускают GitHub Actions workflow `Tests`
- `Tests` ставит зависимости и гоняет `pytest` для ключевых тестовых наборов
- после успешного `Tests` workflow `Deploy` автоматически пушит проверенный commit в VPS bare repo `/opt/aroma.git`
- post-receive hook на VPS обновляет `/opt/aroma` и перезапускает `aroma-bot`
- финальный шаг деплоя проверяет `systemctl is-active aroma-bot`

## Team Workflow

- все изменения делаем из feature-веток через pull request
- `main` используем только как merge-ветку после review и зелёных тестов
- UX-задачи заводим через GitHub issue template `UX Request`
- для Telegram Mini App первый продуктовый и UX-объём зафиксирован в [docs/telegram-mini-app-ux-brief.md](/Users/p.kutsenko/Library/Mobile%20Documents/com~apple~CloudDocs/python/aroma/docs/telegram-mini-app-ux-brief.md)

---

## Мониторинг

Для наблюдения за ботом и VPS работает отдельный **Monitor Bot** (`aroma-monitor.service`).

### Как это работает

- При **запуске** aroma-bot шлёт уведомление `✅ aroma-bot запущен` через второй бот.
- При **ошибке** в обработчике — шлёт тип ошибки + краткий трейсбек.
- При **полном краше** Python — systemd срабатывает `OnFailure=aroma-bot-crash.service`, который делает `curl` к Telegram API и шлёт `💥 aroma-bot упал!`.

Переменные окружения (`.env` на VPS):
```
MONITOR_BOT_TOKEN=<токен второго бота>
MONITOR_CHAT_ID=<твой chat_id>
```

### Команды Monitor Bot

| Команда | Описание |
|---------|----------|
| `/status` | Статус всех сервисов: `aroma-bot`, `aroma-miniapp`, `aromara-site`, `threads-oauth`, `nginx` |
| `/load` | Нагрузка на сервер: uptime, load avg, RAM, диск, swap |
| `/logs [N]` | Последние N строк логов aroma-bot (по умолчанию 30, макс 100) |
| `/errors` | Последние 5 строк с WARNING/ERROR из журнала aroma-bot |
| `/restart` | Перезапустить aroma-bot |

### Управление сервисом на VPS

```bash
# Статус
systemctl status aroma-monitor

# Перезапуск
systemctl restart aroma-monitor

# Логи
journalctl -u aroma-monitor -n 30
```

### Первичная установка monitor bot на VPS

```bash
cp /opt/aroma/deploy/aroma-monitor.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aroma-monitor
systemctl start aroma-monitor
```

---

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/trends` | Полный дайджест прямо сейчас (🇷🇺 + 🇬🇧) |
| `/content` | Агентный флоу: цель → формат → тренд или свой запрос → тема → готовый контент-пакет |
| `/threads` | Темы постов для Threads на основе трендов + пост + картинка |
| `/threads_account` | Проверка подключенного Threads-аккаунта |
| `/threads_inbox` | Анализ inbox Threads: бот предлагает, на что стоит ответить, и черновики ответов |
| `/carousel` | Карусель из 5 слайдов на основе трендов + картинки |
| `/app` | Открыть Mini App workspace |
| `/keywords` | Просмотр и редактирование ключевых слов |
| `/status` | Какие источники активны |
| `/help` | Список команд |

---

## Источники данных

### 🇷🇺 Русский отчёт

| Источник | Ключ | Что показывает |
|----------|------|----------------|
| 📈 Google Trends RU | нет | Тренды по русским ключевым словам |
| 📊 Яндекс Wordstat | `YANDEX_CLIENT_ID/SECRET` | Объёмы поиска + динамика (показов/мес, ▲▼%) |
| ▶️ YouTube RU | `YOUTUBE_API_KEY` | Топ видео по русскоязычным запросам + AI-выжимка |
| 📸 Instagram RU | `INSTAGRAM_USERNAME/PASSWORD` | Посты по русским хэштегам |
| 🎵 TikTok RU | `TIKTOK_MS_TOKEN` | Топ видео по русским хэштегам |
| 🔵 ВКонтакте | `VK_TOKEN` | Популярные посты из групп |
| 📱 Telegram-каналы | `TELEGRAM_API_ID/HASH` | Посты из выбранных каналов |
| 🤖 AI-рекомендации | `ANTHROPIC_API_KEY` | 3 идеи постов на основе всех трендов |

### 🇬🇧 Английский отчёт

| Источник | Ключ | Что показывает |
|----------|------|----------------|
| 📈 Google Trends EN | нет | Тренды по английским ключевым словам |
| ▶️ YouTube EN | `YOUTUBE_API_KEY` | Топ видео + AI-выжимка на русском |
| 💬 Reddit | `REDDIT_CLIENT_ID/SECRET` | Горячие посты из профильных сабреддитов |
| 📸 Instagram EN | `INSTAGRAM_USERNAME/PASSWORD` | Посты по английским хэштегам |
| 🎵 TikTok EN | `TIKTOK_MS_TOKEN` | Топ видео по английским хэштегам |
| 🐦 Twitter/X | `TWITTER_BEARER_TOKEN` | Твиты по хэштегам |

---

## Функции

### /content — агентный конвейер для соцсетей
1. Вы выбираете цель: продажа, вовлечение, доверие или экспертность
2. Вы выбираете формат: Threads, Instagram, Telegram или карусель
3. Выбираете источник идей:
   - актуальные тренды
   - свой текстовый запрос
4. Claude в роли набора агентов предлагает 10 тем
5. Вы выбираете тему
6. Бот возвращает готовый контент-пакет:
   - angle
   - hook
   - готовый текст или 5 слайдов
   - CTA
   - hashtags
   - visual prompt

Для формата `Карусель` бот дополнительно пытается сгенерировать изображения автоматически.
Если image API недоступен или не вернул картинки, бот показывает 2 кнопки:
- `🖼 С текстом` — промпты, где текст слайда встроен в изображение
- `🖼 Без текста` — промпты под чистый фон, чтобы потом доработать текст в Canva

Промпты формируются отдельно для каждого слайда и учитывают именно его текст.

Агентный контекст адаптирован под нишу: регуляция нервной системы через сенсорные практики, ароматерапию, медитации и гонг.

### /trends — двойной отчёт
Отправляет два отчёта: сначала 🇷🇺, потом 🇬🇧. В конце — кнопка **🖼 Обложки YouTube**: нажатие присылает превью топ-видео медиагруппой.

### /threads — контент для Threads
1. Анализирует текущие тренды через Claude
2. Генерирует 10 актуальных тем с хуками
3. Вы выбираете тему → Claude пишет готовый пост (≤450 символов)
4. Gemini (Nano Banana 2) рисует картинку под тему
5. Бот присылает фото + текст
6. Если настроен Threads API, бот показывает кнопку публикации в аккаунт Threads

Кнопка **🔄 Обновить темы** — новый набор тем по тем же трендам.

### /threads_account — проверка аккаунта
Показывает, какой Threads-аккаунт реально подключен через API, и сравнивает его с `THREADS_USERNAME`, если он задан.

### /threads_inbox — полуавтоматические ответы в Threads
1. Бот забирает mentions и свежие ответы под вашими последними тредами через официальный Threads API
2. Claude выбирает, на что действительно стоит ответить
3. Бот показывает кандидатов и готовые черновики ответов
4. Вы можете:
   - одобрить ответ
   - отредактировать текст
   - вернуться к списку
5. После approve бот публикует ответ в Threads

### /carousel — карусель для Threads/Instagram
1. Анализирует текущие тренды через Claude
2. Генерирует 10 актуальных тем с хуками
3. Вы выбираете тему → Claude пишет 5 слайдов (хук + 3 тезиса + CTA)
4. Gemini рисует картинку для каждого слайда
5. Бот присылает тексты слайдов + медиагруппу с картинками

Если картинки не сгенерировались автоматически — две кнопки:
- **🖼 Промпт с текстом** — промпты для Nano Banana, где текст слайда вписан в изображение
- **🖼 Промпт без текста** — те же промпты, но чистый фон (чтобы написать самому)

Кнопка **🔄 Обновить темы** — новый набор тем.

### /keywords — редактор ключевых слов
- **➕ Добавить** — тема → язык (RU/EN/хэштеги) → слово
- **❌ Удалить** — тема → нажать на слово

Изменения сохраняются в `keywords/custom.json` и применяются мгновенно.

### Автодайджест
Каждый день в `DAILY_DIGEST_TIME` (по умолчанию 09:00 МСК) бот автоматически отправляет оба отчёта в `REPORT_TARGET_CHAT_ID`.

---

## Установка и запуск

### 1. Зависимости

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install webkit chromium
```

### 2. Настройка `.env`

Минимум для запуска:
```
TELEGRAM_BOT_TOKEN=...
REPORT_TARGET_CHAT_ID=...
MINI_APP_URL=https://app.aromara.ru
```

Все опции:
```
# Обязательные
TELEGRAM_BOT_TOKEN=...
REPORT_TARGET_CHAT_ID=...

# YouTube
YOUTUBE_API_KEY=...

# Instagram (instagrapi — сессия кэшируется в .instagrapi_session.json)
INSTAGRAM_USERNAME=...
INSTAGRAM_PASSWORD=...
INSTAGRAM_APP_ID=...
INSTAGRAM_APP_SECRET=...
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_USER_ID=...

# ВКонтакте
VK_TOKEN=...

# Яндекс Wordstat
YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...

# TikTok (msToken из DevTools → Application → Cookies → tiktok.com, живёт несколько недель)
TIKTOK_MS_TOKEN=...

# AI (Claude — рекомендации постов и выжимки YouTube)
ANTHROPIC_API_KEY=...

# Gemini / Nano Banana (картинки для /threads)
GEMINI_API_KEY=...

# Threads API
THREADS_APP_ID=...
THREADS_APP_SECRET=...
THREADS_ACCESS_TOKEN=...
THREADS_USER_ID=...
THREADS_USERNAME=aleksandrakutsenko

# Расписание
DAILY_DIGEST_TIME=09:00
TIMEZONE=Europe/Moscow
```

### 3. Запуск

```bash
source .venv/bin/activate
# Применить миграции БД
alembic upgrade head
# Запустить бота
python main.py
```

### 4. Работа с БД (Alembic)

Если вы изменили модели в `db/models.py`, нужно создать и применить миграцию:
```bash
alembic revision --autogenerate -m "описание изменений"
alembic upgrade head
```

Фоновый запуск:
```bash
nohup python main.py > /tmp/aroma_bot.log 2>&1 &
```

Логи: `tail -f /tmp/aroma_bot.log`

### OAuth helper scripts

Собрать ссылку авторизации:
```bash
python scripts/threads_oauth.py authorize-url
python scripts/instagram_oauth.py authorize-url
```

Обменять `code` на long-lived token и обновить `.env`:
```bash
python scripts/threads_oauth.py exchange-code --code '...'
python scripts/instagram_oauth.py exchange-code --code '...'
```

### VPS

Продакшен-бот крутится на VPS как systemd-сервис `aroma-bot`.
Локальный запуск нужен для разработки и ручной проверки перед деплоем.

---

## Файловая структура

```
aroma/
├── main.py
├── config.py
├── .env
├── db/
│   ├── models.py             # SQLAlchemy модели (DraftModel)
│   └── session.py            # Настройка асинхронного engine и сессий
├── alembic/                  # Миграции базы данных
├── data/
│   └── aroma.db              # SQLite база данных (хранилище черновиков и планов)
├── analytics/
...
├── bot/
│   ├── services/
│   │   ├── drafts_store.py   # Асинхронный интерфейс к БД черновиков
│   │   └── reels_assets.py   # Управление медиа-файлами для Reels
```

---

## Решение проблем

**Instagram — `login_required`**
```bash
rm .instagrapi_session.json
# Войдите в аккаунт через приложение на телефоне
# Затем перезапустите бота — сессия пересоздастся
```

**TikTok — `EmptyResponseException`**
msToken истёк. Обновите:
1. Откройте [tiktok.com](https://www.tiktok.com) в Chrome
2. DevTools → Application → Cookies → `msToken`
3. Скопируйте значение → обновите `TIKTOK_MS_TOKEN` в `.env` → перезапустите бота

**Gemini картинки — `429 RESOURCE_EXHAUSTED`**
Квота исчерпана (free tier). Подождите несколько минут — бот отправит только текст поста без картинки.

**Бот не отвечает**
```bash
pgrep -af "main.py"       # найти процесс
tail -20 /tmp/aroma_bot.log
```

**Сбросить кеш дайджеста**
Перезапустить бота или подождать 1 час.
