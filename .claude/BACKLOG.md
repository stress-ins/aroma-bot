# Backlog — Aroma Trends Bot
> Обновлено: 2026-03-19
> Правила: добавляй баги сразу | при закрытии — переноси в DONE.md с датой

---

## 🔴 CRITICAL
*(нет блокирующих багов)*

---

## 🟠 HIGH

*(нет высокоприоритетных задач)*

---

## 🟡 MED

- [x] **[HIGH] Категории симптомов не кликабельны** — ✅ Исправлено в PR #134.

- [x] **[MED] Картинки симптомов не передают смысл** — ✅ Реализован image prompt router с category-aware промптами (PR #290): aroma→botanical, symptom→medical/conceptual, blend→purpose, practice→meditative scene.

- [x] **[MED] Промпты генерации изображений по category** — ✅ Закрыто вместе с предыдущей задачей. `bot/agents/image_prompt_router.py` + `scripts/generate_missing_images.py` поддерживают все 4 категории.

- [x] **Smoke-тесты после деплоя** — ✅ Создано `tests/smoke/test_smoke.py` + healthz check в deploy.yml.

- [x] **29 aroma карточек без description** — ✅ Заполнено. Осталась 1 из 76 карточек (ранее было 29). Скрипты `enrich_passport_fields.py` и `fill_missing_descriptions.py` работают.

- [x] **Playwright UI тесты нестабильны** — ✅ Уже решено: session-scoped fixture автоматически запускает сервер.

- [x] **KB-004: проверить запрещённый паттерн truncation** — ✅ Проверено: единственный `slice(0,180)` в hero summary — это UX-подзаголовок, полный текст ниже.

---

## 🟢 LOW

- [x] **README обновить** — ✅ README уже полный: секции про Mini App, справочник (5 табов), архитектуру, команды, деплой.

- [x] **Чистка requirements.txt** — ✅ Проверено: TikTokApi (analytics/tiktok.py), instagrapi (analytics/instagram.py), Playwright (UI-тесты) — все используются активно.

- [x] **Оптимизация reference images** — ✅ Смержено в main (PR от 2026-03-12, commit 9e543a6). 50+ изображений оптимизированы.

- [x] **n8n workflow синхронизация** — ✅ Workflows актуальны (обновлены 2026-03-16), деплоятся автоматически через deploy.yml.

---

## ❓ UNGROOMED

- [x] **Threads OAuth** — ✅ Реализовано: `bot/handlers/social_connect.py` + `bot/services/social_oauth.py` (Threads + Instagram OAuth). Ветка `codex/bot-oauth-connect-flow` устарела.

- [x] **handbook lesson 6 PDF** — ✅ Все изменения уже в main (6 карточек, CSS theory styles, archetype type, тесты). 3 handbook-ветки удалены (2026-03-19).

- [x] **miniapp-accessibility-pass** — ✅ Все изменения (interactive-card focus, keyboard activation, ARIA attrs) уже в main. Ветка удалена.

- [ ] **Изображения для blends** — перенесено из MED. BlendModel таблица пустая (0 записей). Зависит от seed данных master-blends. `generate_missing_images.py --category blend` готов к использованию.

---

## 🧹 Чистка проекта (2026-03-17)

- [x] **Удалено 272 стейл-ветки** (281 → 9 remote branches). Осталось: main + 3 с open PR + 3 pending decision + 2 vps.
- [x] **Удалено 282 локальные ветки** (290 → 8).
- [x] **Почищено 25 stale worktrees** из /tmp.
