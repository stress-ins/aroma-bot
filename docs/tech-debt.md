# Техдолг

Технические проблемы, хаки, временные решения и устаревшие подходы.

**Severity:**
- **high** — ломает/блокирует, нужно исправить ASAP
- **medium** — мешает, но обходится; планируем исправление
- **low** — косметика, улучшит кодовую базу когда руки дойдут

**Формат:** `- [ ] [high/medium/low] Описание — где, почему, что будет если не исправить (дата)`

---

## Архитектура

- [ ] [high] SQLite в проде — не масштабируется, нет конкурентной записи; Phase 3 — PostgreSQL (2026-03-25)

## Производительность

- [ ] [medium] pytrends deprecated (2020) — ненадёжный парсинг Google Trends, заменить на SerpAPI/DataForSEO (2026-03-25)

## Безопасность

- [ ] [high] Нет rate limiting на FastAPI endpoints — злоупотребление генерационными endpoints, top priority (2026-03-25)
- [ ] [high] Pin all unversioned packages — anthropic, instagrapi, TikTokApi, edge-tts, faiss-cpu; supply chain risk (2026-03-25)

## Код

- [ ] [medium] 58 скриптов в scripts/ без тестов — могут ломаться незаметно (2026-03-25)
- [ ] [medium] instaloader unmaintained — может перестать работать в любой момент (2026-03-25)

## Тесты

- [ ] [medium] Software Factory pipeline не инструментализирован — агенты существуют но не вызываются как этапы CI (2026-03-30)

## Инфраструктура / CI / Deploy

- [ ] [medium] n8n workflow import с `|| true` — ошибки импорта проглатываются молча (2026-03-25)
- [ ] [medium] Нет rollback strategy в deploy.yml — если деплой ломает прод, откат ручной (2026-03-25)
- [ ] [low] Нет cascade delete rules в DB models — при удалении parent остаются orphans (2026-03-25)

---

*Последний пересмотр: 2026-03-30*
