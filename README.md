# 🌿 Aroma Trends Bot

Телеграм-бот для мониторинга трендов в ароматерапии, ольфактотерапии, медитации гонг и звуковом целительстве. Собирает данные из 10+ источников, формирует два отчёта (🇷🇺 и 🇬🇧), генерирует темы постов для Threads и карусели с картинками через AI.

---

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/trends` | Полный дайджест прямо сейчас (🇷🇺 + 🇬🇧) |
| `/threads` | Темы постов для Threads на основе трендов + пост + картинка |
| `/carousel` | Карусель из 5 слайдов на основе трендов + картинки |
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

### /trends — двойной отчёт
Отправляет два отчёта: сначала 🇷🇺, потом 🇬🇧. В конце — кнопка **🖼 Обложки YouTube**: нажатие присылает превью топ-видео медиагруппой.

### /threads — контент для Threads
1. Анализирует текущие тренды через Claude
2. Генерирует 10 актуальных тем с хуками
3. Вы выбираете тему → Claude пишет готовый пост (≤450 символов)
4. Gemini (Nano Banana 2) рисует картинку под тему
5. Бот присылает фото + текст — копируете и публикуете вручную

Кнопка **🔄 Обновить темы** — новый набор тем по тем же трендам.

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

# Расписание
DAILY_DIGEST_TIME=09:00
TIMEZONE=Europe/Moscow
```

### 3. Запуск

```bash
source .venv/bin/activate
python main.py
```

Фоновый запуск:
```bash
nohup python main.py > /tmp/aroma_bot.log 2>&1 &
```

Логи: `tail -f /tmp/aroma_bot.log`

---

## Файловая структура

```
aroma/
├── main.py
├── config.py
├── .env
├── analytics/
│   ├── aggregator.py         # параллельный запуск всех коллекторов
│   ├── google_trends.py      # EN + RU
│   ├── youtube.py            # EN + RU, AI-выжимки через Claude
│   ├── instagram.py          # EN + RU (instagrapi)
│   ├── tiktok.py             # EN + RU (TikTokApi + Playwright)
│   ├── wordstat.py           # Яндекс Wordstat API (объёмы + динамика)
│   ├── vk.py
│   ├── reddit.py
│   ├── twitter.py
│   ├── telegram_channels.py
│   └── ai_recommendations.py # Claude haiku
├── bot/
│   ├── application.py
│   └── handlers/
│       ├── commands.py       # /trends (+ кнопка обложек YouTube)
│       ├── keywords.py       # /keywords
│       └── threads.py        # /threads (темы + пост + картинка)
├── keywords/
│   ├── registry.py
│   ├── store.py
│   └── custom.json
├── formatters/
│   ├── report.py             # RU_SOURCE_KEYS / EN_SOURCE_KEYS
│   └── sections.py
├── scheduler/
│   └── jobs.py
└── cache/
    └── store.py              # TTL-кеш 1 час, ключи: digest, results
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
