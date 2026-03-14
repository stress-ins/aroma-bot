# Backlog — Aroma Trends Bot
> Обновлено: 2026-03-14
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

- [ ] **[MED] Картинки симптомов не передают смысл** — для "Астма" показан букет трав, а должна быть иллюстрация понятия (лёгкие, бронхи, человек). Нужно: промпт для генерации изображений симптомов изменить с "herbs/botanicals" на "medical illustration of [symptom name]" / "conceptual visual of [name]". Файл: `scripts/generate_missing_images.py` или `bot/services/image_generation.py`. Аналогично для смесей: изображение должно отражать назначение смеси (красота, стресс, иммунитет), а не показывать абстрактные травы.

- [ ] **[MED] Промпты генерации изображений по category** — разделить промпт по категории: aroma=botanical illustration, symptom=medical/conceptual, blend=purpose illustration (beauty, mood, immunity), practice=meditative scene. Это позволит каждой карточке иметь осмысленное изображение, а не шаблонные травы.

- [x] **Smoke-тесты после деплоя** — ✅ Создано `tests/smoke/test_smoke.py` + healthz check в deploy.yml.

- [ ] **29 aroma карточек без description** — после запуска enrich_passport_fields.py проверить что все aromas имеют description. Запустить fill_missing_descriptions.py --category aroma если нужно.

- [x] **Playwright UI тесты нестабильны** — ✅ Уже решено: session-scoped fixture автоматически запускает сервер.

- [x] **KB-004: проверить запрещённый паттерн truncation** — ✅ Проверено: единственный `slice(0,180)` в hero summary — это UX-подзаголовок, полный текст ниже.

- [ ] **Изображения для blends** — у смесей placeholder SVG, Gemini-генерация реализована для масел. Проверить покрытие и запустить generate_missing_images.py --category blend если нужно.

---

## 🟢 LOW

- [ ] **README обновить** — добавить секцию про справочник (handbook), команды /start, описание Mini App. Сейчас README описывает только тренд-бота.

- [ ] **Чистка requirements.txt** — проверить TikTokApi+Playwright, instagrapi — используются ли активно или отключены через is_source_enabled().

- [ ] **Оптимизация reference images** — ветка `codex/optimize-reference-images` существует, но не смержена. Проверить что там.

- [ ] **n8n workflow синхронизация** — `aroma_bot_pipeline.n8n.json` может быть устаревшим если менялись промпты. Сверить с текущим кодом.

---

## ❓ UNGROOMED

- [ ] **Threads OAuth** — ветки `codex/bot-oauth-connect-flow`, `codex/instagram-facebook-login` существуют. Что это — реализованный функционал или незавершённый эксперимент?

- [ ] **handbook lesson 6 PDF** — ветка `codex/handbook-lesson-6-pdf` не смержена. Что за контент, нужен ли?

- [ ] **miniapp-accessibility-pass** — ветка `codex/miniapp-accessibility-pass` существует. Приоритет a11y для Mini App?

