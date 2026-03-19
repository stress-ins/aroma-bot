# SKILL: Screenshot Gallery

## Назначение
Генерирует скриншоты всех экранов miniapp, проверяет все клики на моках,
сравнивает с эталоном (регрессия) и собирает HTML-галерею для ревью.
Всё складывается в одну папку — открыл index.html и смотришь.

## Вызов
```
claude "запусти скилл gallery"
claude "запусти скилл gallery --baseline"   # перезаписать эталон
claude "запусти скилл gallery --update"     # только текущие скриншоты (без baseline)
```

## Output
```
docs/screenshots/gallery/
  index.html          ← открыть в браузере для ревью
  registry.json       ← карта экранов
  clicks.json         ← результаты кликов
  diff_report.json    ← регрессия
  current/            ← свежие скриншоты
  baseline/           ← эталонные (не перезаписываются без --baseline)
  diff/               ← diff-изображения (если есть расхождения)
```

---

## ШАГ 0 — Подготовка

Прочитай CLAUDE.md проекта если есть.

Определи режим запуска:
- Если папка `docs/screenshots/gallery/baseline/` **пуста или не существует** → режим BASELINE (создаём эталон)
- Если передан флаг `--baseline` → режим BASELINE (перезаписываем эталон)
- Иначе → режим UPDATE (только current + diff)

Установи зависимости если не установлены:
```bash
pip install playwright pillow --break-system-packages --quiet
python -m playwright install chromium --quiet
```

Создай папки:
```bash
mkdir -p docs/screenshots/gallery/current
mkdir -p docs/screenshots/gallery/baseline
mkdir -p docs/screenshots/gallery/diff
```

---

## ШАГ 1 — Карта экранов (registry.json)

Найди все роуты miniapp. Ищи в:
- `miniapp/static/js/*.js` — router, navigate, pushState, hash
- `miniapp/static/*.html` — data-page, data-route атрибуты
- `miniapp/api/routers/*.py` — FastAPI роуты (для понимания структуры)

Для каждого экрана определи:
- `id` — slug (drafts_list, content_create, settings_promo)
- `name` — человекочитаемое название на русском
- `route` — URL (/#drafts, /drafts, /settings/promo)
- `states` — какие состояния есть: ["default", "empty", "error"]
- `requires_seed` — нужны ли тестовые данные
- `clicks` — все кнопки/ссылки/табы с которыми взаимодействует пользователь:
  ```json
  {"selector": ".btn-primary", "label": "Создать контент", "leads_to": "content_create"}
  ```

Сохрани в `docs/screenshots/gallery/registry.json`:
```json
{
  "generated_at": "<ISO datetime>",
  "app_name": "Aromara MiniApp",
  "viewport": {"width": 390, "height": 844},
  "screens": [ ... ]
}
```

---

## ШАГ 2 — Скриншоты и проверка кликов

Создай и запусти `scripts/make_screenshots.py`:

```python
#!/usr/bin/env python3
"""
Генератор скриншотов для gallery skill.
Запуск: python scripts/make_screenshots.py [--baseline] [--screen=id]
"""
import asyncio, json, sys, shutil
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

GALLERY   = Path("docs/screenshots/gallery")
CURRENT   = GALLERY / "current"
BASELINE  = GALLERY / "baseline"
DIFF_DIR  = GALLERY / "diff"
VIEWPORT  = {"width": 390, "height": 844}
TIMEOUT   = 8000

# Реалистичные seed-данные (русский текст про ароматерапию)
SEED_DATA = {
    "drafts": [
        {
            "id": 1,
            "title": "Лаванда для восстановления",
            "content": "После перегруженной недели тело просит тишины. Лаванда — не просто запах, это сигнал нервной системе: можно выдохнуть.",
            "platform": "instagram",
            "status": "draft",
            "created_at": "2026-03-18T20:00:00"
        },
        {
            "id": 2,
            "title": "Бергамот и утренний ритуал",
            "content": "Медитирует 40 минут, спит 5 часов, пьёт кофе вместо воды. Угадай, почему практики не сработали?",
            "platform": "threads",
            "status": "draft",
            "created_at": "2026-03-17T09:00:00"
        },
        {
            "id": 3,
            "title": "Эвкалипт: мифы и реальность",
            "content": "Для одних это запах, для других — звук, для третьих — молча погулять. Кому-то нужен телесный ритуал.",
            "platform": "instagram",
            "status": "scheduled",
            "created_at": "2026-03-16T15:30:00"
        }
    ],
    "aroma_cards": [
        {"slug": "lavender",   "name": "Лаванда",    "category": "floral",   "note": "верхняя"},
        {"slug": "bergamot",   "name": "Бергамот",   "category": "citrus",   "note": "верхняя"},
        {"slug": "eucalyptus", "name": "Эвкалипт",   "category": "herbal",   "note": "средняя"},
        {"slug": "frankincense","name": "Ладан",     "category": "resinous", "note": "базовая"},
        {"slug": "ylang",      "name": "Иланг-иланг","category": "floral",   "note": "средняя"},
    ]
}


async def seed(page, screen_id: str, empty: bool = False):
    """Загружает seed-данные через API или localStorage."""
    try:
        if empty:
            await page.request.post("/api/test/seed", data={"screen": screen_id, "empty": True})
        else:
            await page.request.post("/api/test/seed", data={
                "screen": screen_id,
                "data": json.dumps(SEED_DATA)
            })
    except Exception:
        # Если нет seed endpoint — пробуем через localStorage
        await page.evaluate(f"localStorage.setItem('seed_data', {json.dumps(json.dumps(SEED_DATA))})")


async def take(page, path: Path, name: str):
    """Делает скриншот после networkidle."""
    await page.wait_for_load_state("networkidle", timeout=TIMEOUT)
    # Ждём исчезновения спиннеров
    try:
        await page.locator(".loading, .spinner, [data-loading='true']").wait_for(
            state="hidden", timeout=2000
        )
    except Exception:
        pass
    await page.wait_for_timeout(300)  # CSS анимации
    await page.screenshot(path=str(path), full_page=False)
    print(f"  📸 {name} → {path.name}")
    return path


async def run():
    is_baseline = "--baseline" in sys.argv
    screen_filter = next((a.split("=")[1] for a in sys.argv if a.startswith("--screen=")), None)

    with open("docs/screenshots/gallery/registry.json") as f:
        registry = json.load(f)

    screens = registry["screens"]
    if screen_filter:
        screens = [s for s in screens if s["id"] == screen_filter]

    # Определяем BASE_URL
    base_url = "http://localhost:8000"  # подбери по проекту

    click_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport=VIEWPORT,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            # Мокируем Telegram WebApp
            extra_http_headers={"X-Test-Mode": "1"}
        )

        # Мокируем Telegram.WebApp
        await ctx.add_init_script("""
            window.Telegram = {
                WebApp: {
                    ready: () => {},
                    expand: () => {},
                    close: () => {},
                    initData: 'test_init_data',
                    initDataUnsafe: { user: { id: 12345, first_name: 'Test', language_code: 'ru' } },
                    colorScheme: 'dark',
                    themeParams: {},
                    BackButton: { show: ()=>{}, hide: ()=>{}, onClick: ()=>{}, offClick: ()=>{} },
                    MainButton: { show: ()=>{}, hide: ()=>{}, setText: ()=>{} },
                    HapticFeedback: { impactOccurred: ()=>{}, notificationOccurred: ()=>{} }
                }
            };
        """)

        page = await ctx.new_page()

        for screen in screens:
            sid   = screen["id"]
            route = screen["route"]
            print(f"\n▶ {screen['name']} ({route})")

            # ── Default state ──
            if screen.get("requires_seed"):
                await seed(page, sid)
            await page.goto(f"{base_url}{route}", timeout=TIMEOUT)
            await take(page, CURRENT / f"{sid}.png", "default")

            # ── Empty state ──
            if "empty" in screen.get("states", []):
                await seed(page, sid, empty=True)
                await page.goto(f"{base_url}{route}", timeout=TIMEOUT)
                await take(page, CURRENT / f"{sid}_empty.png", "empty")

            # ── Клики ──
            for click in screen.get("clicks", []):
                selector = click["selector"]
                label    = click.get("label", selector)
                try:
                    # Возвращаемся на экран с данными
                    if screen.get("requires_seed"):
                        await seed(page, sid)
                    await page.goto(f"{base_url}{route}", timeout=TIMEOUT)
                    await page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                    el = page.locator(selector).first
                    await el.wait_for(state="visible", timeout=3000)
                    await el.click()
                    await page.wait_for_timeout(600)

                    slug  = selector.replace(".", "").replace("#", "").replace(" ","_")[:30]
                    fname = f"{sid}_after_{slug}.png"
                    await take(page, CURRENT / fname, f"click: {label}")

                    click_results.append({
                        "screen_id":    sid,
                        "selector":     selector,
                        "label":        label,
                        "status":       "ok",
                        "screenshot":   fname,
                        "leads_to_route": page.url.replace(base_url, "")
                    })
                except Exception as e:
                    print(f"  ✗ клик '{label}': {e}")
                    click_results.append({
                        "screen_id": sid,
                        "selector":  selector,
                        "label":     label,
                        "status":    f"error: {str(e)[:120]}",
                        "screenshot": None,
                        "leads_to_route": None
                    })

        await browser.close()

    # Сохраняем результаты кликов
    with open(GALLERY / "clicks.json", "w", encoding="utf-8") as f:
        json.dump(click_results, f, ensure_ascii=False, indent=2)

    ok  = sum(1 for c in click_results if c["status"] == "ok")
    err = sum(1 for c in click_results if c["status"] != "ok")
    print(f"\n✅ Кликов: {ok} ok, {err} ошибок")

    # ── Baseline ──
    if is_baseline or not any(BASELINE.glob("*.png")):
        print("\n📌 Копирую current → baseline (эталон)")
        for f in CURRENT.glob("*.png"):
            shutil.copy2(f, BASELINE / f.name)

    # ── Pixel diff ──
    await make_diffs()

    print(f"\n🖼  Скриншотов: {len(list(CURRENT.glob('*.png')))}")


async def make_diffs():
    """Сравнивает current/ с baseline/ попиксельно через PIL."""
    try:
        from PIL import Image, ImageChops, ImageEnhance
        import struct
    except ImportError:
        print("PIL не установлен, пропускаем diff")
        return

    diffs = []
    for current in CURRENT.glob("*.png"):
        baseline = BASELINE / current.name
        if not baseline.exists():
            continue
        try:
            img_c = Image.open(current).convert("RGBA")
            img_b = Image.open(baseline).convert("RGBA")

            # Приводим к одному размеру
            if img_c.size != img_b.size:
                img_b = img_b.resize(img_c.size, Image.LANCZOS)

            diff = ImageChops.difference(img_c, img_b)
            # Усиливаем diff для видимости
            enhancer = ImageEnhance.Brightness(diff)
            diff_bright = enhancer.enhance(5.0)
            diff_bright.save(DIFF_DIR / f"{current.stem}_diff.png")

            # Считаем изменённые пиксели
            pixels = list(diff.getdata())
            changed = sum(1 for px in pixels if any(c > 10 for c in px[:3]))
            total   = len(pixels)
            pct     = round(changed / total * 100, 2)

            diffs.append({
                "screen_id":   current.stem,
                "diff_percent": pct,
                "diff_pixels":  changed,
                "has_diff":     pct > 0.5,
                "diff_image":   f"diff/{current.stem}_diff.png"
            })
        except Exception as e:
            print(f"  diff error {current.name}: {e}")

    with open(GALLERY / "diff_report.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "diffs": diffs}, f, indent=2)

    regressions = [d for d in diffs if d["has_diff"]]
    print(f"🔍 Регрессий: {len(regressions)}/{len(diffs)} экранов")
    for d in regressions:
        print(f"  ⚠  {d['screen_id']}: {d['diff_percent']}% ({d['diff_pixels']} px)")


if __name__ == "__main__":
    asyncio.run(run())
```

Запусти скрипт:
```bash
python scripts/make_screenshots.py
```

---

## ШАГ 3 — Скопировать галерею

Скопируй HTML-галерею в output:
```bash
cp .claude/skills/gallery/gallery.html docs/screenshots/gallery/index.html
```

---

## ШАГ 4 — Финальный отчёт

Выведи итог:
```
📊 Gallery готова
─────────────────────────────────────
Экранов в реестре:   N
Скриншотов создано:  N  (current/)
Эталонных:           N  (baseline/)
Diff-изображений:    N  (diff/)
Кликов протестировано: N ok / N ошибок
Регрессий:           N экранов

⚠ Ошибки кликов:
  [screen_id] selector → причина

⚠ Регрессии (>0.5%):
  [screen_id] — 2.3% пикселей

📂 Открой галерею:
  open docs/screenshots/gallery/index.html
─────────────────────────────────────
```

Если есть ошибки кликов — объясни возможную причину (элемент не найден,
роут требует авторизации, экран недоступен).

---

## ПРАВИЛА

- **Viewport всегда 390×844** — единый размер для всех скриншотов
- **`full_page=True` ЗАПРЕЩЁН** — даёт нечитаемые вытянутые изображения. Всегда `full_page=False`
- **Для длинных страниц — scroll-скриншоты:** используй `_capture_scroll_snapshots()` из `make_screenshots.py`. Каждый кадр = ровно viewport 390×844, прокрутка через `scrollTop`
- Мокируй Telegram.WebApp через `add_init_script` — не через реальный TG
- Seed-данные реалистичные: русский текст, реальные даты, ароматерапия
- Скриншот только после `networkidle` + исчезновения спиннеров
- baseline/ **не трогать** без явного флага `--baseline`
- Если роут требует авторизации — добавь тестовый заголовок `X-Test-User-Id: 12345`
- Если сервер не запущен — запусти его перед скриншотами:
  ```bash
  uvicorn miniapp.main:app --port 8000 &
  sleep 2
  ```
- Все файлы только в `docs/screenshots/gallery/` — не в `tests/`
