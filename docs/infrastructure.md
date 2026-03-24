# Infrastructure Runbook

> Единый источник правды для воспроизведения сервера с нуля.
> Обновлять при каждом изменении инфраструктуры.

---

## 1. Сервер

| Параметр | Значение |
|----------|----------|
| IP | `46.32.186.192` |
| OS | Ubuntu 24.04 LTS |
| CPU | 2 vCPU |
| RAM | 4 GB |
| Swap | 2 GB |
| Disk | 80 GB SSD (`/dev/sda2`) |
| Python | 3.12 (system) |
| Node.js | 22.x (для Remotion) |
| FFmpeg | 6.1 (system) |
| Nginx | 1.24 (system) |
| Certbot | 2.9 (Let's Encrypt) |

### Важные ограничения текущего железа

- FFmpeg при обработке видео потребляет до **2 GB RAM** — при 4 GB это критично.
- `aroma-miniapp.service` ограничен `MemoryMax=2500M` + `OOMPolicy=continue` чтобы OOM-killer не ронял gunicorn.
- При апгрейде до 8+ GB RAM можно увеличить `MemoryMax` и добавить `--workers 3-4` в gunicorn.

---

## 2. Домены и SSL

| Домен | Назначение | Backend |
|-------|------------|---------|
| `aromara.ru` | Публичный сайт (Next.js) | `127.0.0.1:3005` |
| `app.aromara.ru` | Mini App (Telegram WebApp) | `127.0.0.1:8091` |
| `oauth.aromara.ru` | Threads OAuth callback | `127.0.0.1:8090` |

SSL-сертификаты: Let's Encrypt, автопродление через certbot.

Конфиги nginx:
- `/etc/nginx/sites-enabled/aromara.ru`
- `/etc/nginx/sites-enabled/app.aromara.ru` (= `deploy/nginx-miniapp.conf`)
- `/etc/nginx/sites-enabled/oauth.aromara.ru`

---

## 3. Systemd-сервисы

| Сервис | Описание | Порт | Файл |
|--------|----------|------|------|
| `aroma-bot` | Telegram-бот (python-telegram-bot) | — | `deploy/` (не в репо, см. ниже) |
| `aroma-miniapp` | Mini App API (Gunicorn + Uvicorn) | 8091 | `deploy/aroma-miniapp.service` |
| `threads-oauth` | Threads OAuth callback (Uvicorn) | 8090 | `deploy/threads-oauth.service` |
| `aroma-monitor` | Monitor bot (проверка здоровья) | — | `deploy/aroma-monitor.service` |
| `n8n-aroma` | n8n workflows (Docker) | 5678 | `deploy/n8n.service` |
| `aromara-site` | Публичный сайт (Next.js) | 3005 | отдельный репо |

### aroma-bot.service (не в репо, только на VPS)

```ini
[Unit]
Description=Aroma Trends Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aroma
ExecStart=/opt/aroma/.venv/bin/python main.py
Restart=always
OnFailure=aroma-bot-crash.service
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Критичные параметры aroma-miniapp

```ini
MemoryMax=2500M        # Ограничение RAM (FFmpeg ест до 2GB)
MemorySwapMax=512M     # Лимит свопа
OOMPolicy=continue     # Gunicorn выживает если FFmpeg убит OOM
--workers 2            # 2 воркера для 4GB RAM
--graceful-timeout 30  # Zero-downtime reload через HUP
```

---

## 4. Деплой-пайплайн

```
git push → GitHub Actions (test.yml)
  ├── pytest (backend)
  └── playwright (miniapp-ui)
        ↓ (success + main branch)
GitHub Actions (deploy.yml)
  ├── scp systemd/nginx configs
  ├── git push --force vps HEAD:main
  │     ↓ triggers post-receive hook
  │     ├── pip install -r requirements.txt
  │     ├── alembic upgrade head
  │     ├── python scripts/patch_aroma_cards.py
  │     ├── systemctl restart aroma-bot
  │     ├── systemctl reload aroma-miniapp (zero-downtime)
  │     └── wait for /readyz (max 30s)
  ├── npm ci + remotion browser ensure
  ├── cleanup scripts (duplicates, blends)
  ├── patch_oil_questions.py (idempotent)
  ├── fill_complementary_oils_from_pdf.py
  ├── AI enrichment scripts (idempotent, skip if filled)
  └── n8n workflow import via API
```

### Bare git repo

- Path: `/opt/aroma.git` (bare)
- Work tree: `/opt/aroma` (checkout)
- Hook: `/opt/aroma.git/hooks/post-receive` (= `deploy/post-receive`)

### Zero-downtime reload

Miniapp использует `systemctl reload` → `kill -HUP` → gunicorn спавнит новые воркеры, старые дообслуживают запросы. Проверка через `/readyz` endpoint.

---

## 5. База данных

| Параметр | Значение |
|----------|----------|
| Engine | SQLite (async, aiosqlite) |
| Файл | `/opt/aroma/data/aroma.db` |
| ORM | SQLAlchemy 2.x (AsyncSession) |
| Миграции | Alembic |
| Бэкап | **НЕ НАСТРОЕН** — при миграции скопировать `data/aroma.db` |

### Что хранится в БД (не в файлах)

- Drafts, Plans — runtime source of truth
- AromaCards (74 масла), Blends, Symptoms — справочник
- Subscriptions, Teams, BrandSettings
- PostMetrics, PublishLogs, Mentions
- VideoTasks — очередь обработки видео

### Что хранится в seed-файлах (не в БД)

- `data/reference_cards_seed.json` — 43 масла (seed для первичного заполнения)
- `data/oil_questions_patch.json` — 74 масла с вопросами (patch)
- `data/base_blends.json`, `data/pdf_*.json` — импорт из PDF

---

## 6. Мониторинг

| Механизм | Описание |
|----------|----------|
| `aroma-monitor.service` | Python-бот, проверяет здоровье aroma-bot |
| `scripts/server_monitor.sh` | Cron каждые 10 мин: disk, RAM, swap, сервисы |
| `aroma-bot-crash.service` | OnFailure handler — уведомление при падении бота |
| Monitor bot token | `MONITOR_TG_BOT_TOKEN` — отдельный бот для алертов |
| Monitor chat | `62912125` (admin) |

---

## 7. Внешние зависимости

| Сервис | Назначение | Env-переменная |
|--------|------------|----------------|
| Anthropic Claude | AI-генерация контента | `ANTHROPIC_API_KEY` |
| Telegram Bot API | Бот + Mini App | `TELEGRAM_BOT_TOKEN` |
| Meta Graph API | Публикация в Instagram/Threads | `INSTAGRAM_*`, `THREADS_*` |
| YouTube Data API | Публикация видео | `YOUTUBE_*` |
| Kie.ai | AI-генерация изображений | `KIE_API_KEY` |
| Replicate | AI-генерация изображений | `REPLICATE_API_TOKEN` |
| n8n | Workflow automation | `N8N_API_KEY`, `N8N_WEBHOOK_SECRET` |

---

## 8. Чеклист миграции на новый сервер

### Подготовка

- [ ] Новый сервер: Ubuntu 24.04, Python 3.12+, Node.js 22+
- [ ] Установить: `apt install nginx certbot python3-certbot-nginx ffmpeg`
- [ ] Настроить swap: `fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile`

### DNS

- [ ] Обновить A-записи для `aromara.ru`, `app.aromara.ru`, `oauth.aromara.ru`
- [ ] Дождаться пропагации (TTL)

### SSL

- [ ] `certbot --nginx -d aromara.ru -d app.aromara.ru -d oauth.aromara.ru`

### Код и данные

- [ ] Создать bare repo: `git init --bare /opt/aroma.git`
- [ ] Скопировать post-receive hook: `cp deploy/post-receive /opt/aroma.git/hooks/ && chmod +x`
- [ ] Создать venv: `python3 -m venv /opt/aroma/.venv`
- [ ] **Скопировать `.env`** с текущего сервера (секреты!)
- [ ] **Скопировать `data/aroma.db`** (база данных!)
- [ ] `git push` для деплоя кода

### Systemd

- [ ] Скопировать все `.service` файлы из `deploy/` в `/etc/systemd/system/`
- [ ] Скопировать `aroma-bot.service` (он не в репо — см. секцию 3)
- [ ] `systemctl daemon-reload`
- [ ] `systemctl enable aroma-bot aroma-miniapp threads-oauth aroma-monitor`
- [ ] `systemctl start aroma-bot aroma-miniapp threads-oauth aroma-monitor`

### Nginx

- [ ] Скопировать конфиги из `deploy/nginx-miniapp.conf` + VPS-only конфиги
- [ ] `nginx -t && systemctl reload nginx`

### n8n (опционально)

- [ ] `bash scripts/vps_n8n_setup.sh`
- [ ] Активировать 5 workflows в n8n UI

### Cron

- [ ] `crontab -e` → `*/10 * * * * /opt/aroma/scripts/server_monitor.sh`

### Remotion

- [ ] `cd /opt/aroma/remotion && npm ci && npx remotion browser ensure`

### Верификация

- [ ] `curl -sf https://app.aromara.ru/readyz` → OK
- [ ] `systemctl status aroma-bot aroma-miniapp` → active
- [ ] Отправить тестовое сообщение боту
- [ ] Проверить Mini App в Telegram

### При апгрейде RAM (8+ GB)

- [ ] `MemoryMax=5000M` в `aroma-miniapp.service`
- [ ] `--workers 3` или `--workers 4` в gunicorn
- [ ] `systemctl daemon-reload && systemctl reload aroma-miniapp`

---

## 9. Аварийные процедуры

### Miniapp 502

```bash
ssh root@46.32.186.192
journalctl -u aroma-miniapp -n 50 --no-pager  # проверить логи
systemctl restart aroma-miniapp                 # перезапуск
curl -sf http://127.0.0.1:8091/readyz           # проверка
```

### Бот не отвечает

```bash
journalctl -u aroma-bot -n 50 --no-pager
systemctl restart aroma-bot
```

### OOM-kill

```bash
dmesg -T | grep -i oom | tail -5               # кто был убит
free -h                                         # текущая память
# Если FFmpeg — это штатно, сервис перезапустится сам
```

### Диск заполнен

```bash
du -sh /opt/aroma/data/* | sort -h | tail -10   # крупные файлы
du -sh /opt/aroma/cache/* | sort -h | tail -10   # кеш
# Очистить кеш и temp-файлы:
rm -rf /opt/aroma/cache/images/* /tmp/aroma-*
```
