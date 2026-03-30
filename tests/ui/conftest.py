"""Shared Playwright fixtures for UI tests.

Key design decisions:
- ONE Chromium browser per session (not per test) to avoid launch overhead.
- Each test gets a fresh browser context + page (function scope) for isolation.
- miniapp_server is session-scoped: starts uvicorn once, shared by all tests.
- DB schema created from SQLAlchemy models (stays in sync with db/models.py).
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from base64 import b64decode
from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from tests.ui.forbidden_zones import (
    INTERACTIVE_SELECTORS,
    get_forbidden_zones,
    overlaps,
)

_PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zk6cAAAAASUVORK5CYII="
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Mini App test server did not start in time")


@pytest.fixture(scope="session")
def miniapp_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("miniapp-ui")
    db_file = root / "test_aroma.db"
    assets_dir = root / "reels_assets"

    # Create all tables from SQLAlchemy models (stays in sync with db/models.py)
    from sqlalchemy import create_engine
    from db.models import Base
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    engine.dispose()

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    draft_id = "reels001"
    asset_file = assets_dir / draft_id / "frame_1.png"
    asset_file.parent.mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(_PNG_1X1)

    reels_payload = {
        "concept": "Вечернее переключение через ароматический ритуал",
        "scenario": "Короткий сценарий рилса про вечернее переключение.",
        "caption": "Попробуй простой ритуал сегодня вечером.",
        "images_ready": 1,
        "frames": [
            {
                "id": "f1",
                "frame_id": "f1",
                "timecode": "0-3 сек",
                "overlay_text": "Попробуй сегодня",
                "image_prompt": "warm evening desk, close-up hands closing laptop",
                "image_status": "ready",
                "image_url": f"/generated/reels_assets/{draft_id}/frame_1.png",
            }
        ],
    }
    threads_payload = {
        "angle": "Через телесный переключатель, а не силу воли.",
        "hook": "Иногда телу нужен не совет, а сигнал безопасности.",
        "caption": "Короткий текст для Threads про переключение после работы.",
        "cta": "Если откликается, напиши мне.",
        "visual_prompt": "warm calm evening ritual, soft light, cozy interior",
    }
    carousel_payload = {
        "slides": [
            "Стресс часто начинается с перегрузки ощущений.",
            "Запах и звук помогают мягко вернуть фокус.",
        ],
        "img_prompts": [
            "calm sensory ritual, soft amber light, minimalist editorial photo",
            "wellness still life, aroma bottle, warm shadows, premium composition",
        ],
        "slide_images": [
            {
                "url": "/generated/carousel_assets/carousel001/slide_1.png",
                "filename": "slide_1.png",
                "generated_at": "2026-03-11T18:00:00+00:00",
            },
            None,
        ],
        "slide_image_versions": [
            [
                {
                    "url": "/generated/carousel_assets/carousel001/slide_1.png",
                    "filename": "slide_1.png",
                    "generated_at": "2026-03-11T18:00:00+00:00",
                    "prompt": "prompt 1",
                }
            ],
            [],
        ],
        "img_prompt_notes": ["", ""],
        "cta": "Напиши, если хочешь такую карусель под свой проект.",
    }

    now = "2026-03-11T18:00:00+00:00"
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        (draft_id, "reels_v2", "Вечерний ароматический ритуал", "/miniapp", "draft", "", json.dumps(reels_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        ("threads001", "threads", "Как мягко выйти из рабочего напряжения", "/content", "in_review", "worked", json.dumps(threads_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        ("carousel001", "carousel", "Сенсорная карусель для вечернего ритуала", "/miniapp", "draft", "", json.dumps(carousel_payload), now),
    )
    threads_series_payload = {
        "series_summary": "Опорная мысль серии про восстановление.",
        "goal": "trust",
        "emotion": "calm",
        "posts": [
            {"slot": 1, "text": "Утренний пост серии.", "status": "draft"},
            {"slot": 2, "text": "Дневной пост серии.", "status": "draft"},
        ],
    }
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        ("threads_series001", "threads_series", "Восстановление энергии и ресурса", "/miniapp", "draft", "", json.dumps(threads_series_payload), now),
    )
    for slug, name, category, source_type in [
        ("lavender", "Лаванда", "aroma", "herb"),
        ("grounding", "Grounding", "blend", "blend"),
        ("stress", "Стресс", "symptom", "symptom"),
        ("limbic-system", "Лимбическая система", "concept", "theory"),
        ("box-breathing", "Квадратное дыхание", "practice", "practice"),
        ("gong", "Гонг", "sound", "instrument"),
    ]:
        cursor.execute(
            "INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, category, source_type, json.dumps([]), json.dumps({}), now, now),
        )
    symptom_rows = [
        ("headache", "Головная боль", "НЕРВНАЯ СИСТЕМА", [], []),
        ("anxiety", "Тревожность", "НЕРВНАЯ СИСТЕМА", ["lavender"], ["grounding"]),
        ("indigestion", "Несварение желудка", "ПИЩЕВАРЕНИЕ", [], []),
        ("insomnia", "Бессонница", "СОН И ОТДЫХ", [], []),
        ("fatigue", "Усталость и истощение", "ЭНЕРГИЯ", [], []),
        ("hypertension", "Гипертония", "СЕРДЕЧНО-СОСУДИСТАЯ", [], []),
        ("depression", "Депрессия", "ПСИХОЭМОЦИОНАЛЬНОЕ", [], []),
        ("allergy", "Аллергия", "ИММУНИТЕТ И КОЖА", [], []),
    ]
    for slug, name, cat_group, oil_slugs, blend_slugs in symptom_rows:
        payload = {"category_group": cat_group, "parent_group": cat_group}
        if oil_slugs:
            payload["recommended_oil_slugs"] = oil_slugs
        if blend_slugs:
            payload["recommended_blend_slugs"] = blend_slugs
        cursor.execute(
            "INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, "symptom", "symptom", json.dumps([]), json.dumps(payload), now, now),
        )
    cursor.execute(
        "INSERT INTO mentions (mention_id, platform, external_id, type, author_username, author_name, content, url, context_post, received_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("mention001", "threads", "ext001", "mention", "aroma_user", "Aroma User", "Подскажите, какое масло лучше для вечернего расслабления?", "https://threads.net/t/123", "", now, "pending"),
    )
    # Mention with a published reply — for testing published state UI
    cursor.execute(
        "INSERT INTO mentions (mention_id, platform, external_id, type, author_username, author_name, content, url, context_post, received_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("mention002", "instagram", "ext002", "mention", "wellness_fan", "Wellness Fan", "Спасибо за рекомендацию лаванды!", "https://instagram.com/p/456", "", now, "replied"),
    )
    cursor.execute(
        "INSERT INTO mention_replies (reply_id, mention_id, tone, content, selected, generated_at, published_at, publish_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("reply001", "mention002", "warm", "Рады, что помогли! Лаванда — отличный выбор для вечернего расслабления.", 1, now, now, ""),
    )
    # Inbox conversations + messages for testing Входящие tab
    cursor.execute(
        "INSERT INTO conversations (conversation_id, platform, participant_id, participant_username, participant_name, last_message_preview, last_message_at, status, unread_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("conv001", "instagram", "ext_user_001", "wellness_dm", "Wellness DM User", "Подскажите, как использовать масло лаванды?", now, "active", 1, now),
    )
    cursor.execute(
        "INSERT INTO direct_messages (message_id, conversation_id, sender_type, content, sent_at, external_id) VALUES (?, ?, ?, ?, ?, ?)",
        ("dm001", "conv001", "user", "Подскажите, как использовать масло лаванды?", now, "ext_dm_001"),
    )
    cursor.execute(
        "INSERT INTO plans (plan_id, raw_text, entries, status, created_at) VALUES (?, ?, ?, 'draft', ?)",
        (
            "20260311180000",
            "## Контент-план\n- Понедельник: Threads\n- Среда: Reels",
            json.dumps(
                [
                    {
                        "day_label": "Понедельник",
                        "platform": "Threads",
                        "format_label": "пост",
                        "goal": "Доверие",
                        "topic": "Почему вечерний ритуал помогает нервной системе",
                        "angle": "Через простые телесные сигналы.",
                    }
                ],
                ensure_ascii=False,
            ),
            now,
        ),
    )
    # Archive (past publications) seed data
    cursor.execute(
        "INSERT INTO past_publications (pub_id, platform, kind, external_url, external_id, topic, caption, hashtags, published_at, likes, comments, shares, saves, views, score_engagement, score_brand_fit, score_craft, score_goal_hit, content_pillar, funnel_stage, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("pub001", "threads", "text", "https://threads.net/t/test1", "ext_pub001", "Утренний ритуал пробуждения", "Попробуйте начать утро с аромата лаванды.", "[]", now, 142, 23, 8, 5, 1240, 4, 3, 5, 4, "Образование", "awareness", "Хороший хук", now, now),
    )
    cursor.execute(
        "INSERT INTO past_publications (pub_id, platform, kind, external_url, external_id, topic, caption, hashtags, published_at, likes, comments, shares, saves, views, content_pillar, funnel_stage, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("pub002", "instagram", "carousel", "https://instagram.com/p/test2", "ext_pub002", "5 масел для сна", "Карусель про масла для крепкого сна.", "[]", now, 89, 15, 3, 12, 800, "Рецепты", "consideration", "", now, now),
    )
    conn.commit()
    conn.close()

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "REPORT_TARGET_CHAT_ID": "test-chat",
            "AROMA_DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
            "AROMA_REELS_ASSETS_DIR": str(assets_dir),
            "MINIAPP_AROMA_ALLOWED_USER_IDS": "12345",
            "AROMA_BYPASS_AUTH": "1",
            "AROMA_ENV": "test",
            "AROMA_RATE_LIMIT_DISABLED": "1",
        }
    )

    server_log = root / "server.log"
    server_log_fh = server_log.open("w")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "miniapp_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=server_log_fh,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_ready(base_url)
        yield base_url
    except Exception:
        server_log_fh.flush()
        print(f"\n=== SERVER LOG ===\n{server_log.read_text()}\n=== END ===", flush=True)
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Override the root conftest's async DB fixture — UI tests use their own miniapp_server."""
    yield


@pytest.fixture(scope="session")
def _playwright():
    """Session-scoped Playwright instance."""
    pw = sync_playwright().start()
    yield pw
    pw.stop()


@pytest.fixture(scope="session")
def browser(_playwright):
    """Single Chromium browser for the entire test session."""
    try:
        b = _playwright.chromium.launch()
    except Error as exc:
        pytest.skip(f"Playwright browser is not available: {exc}")
    yield b
    b.close()


_TELEGRAM_JS_STUB = (
    "window.Telegram={WebApp:{initData:'',initDataUnsafe:{user:{id:12345,username:'test'}},"
    "ready:function(){},expand:function(){},close:function(){},"
    "MainButton:{show:function(){},hide:function(){},setText:function(){},onClick:function(){}},"
    "BackButton:{show:function(){},hide:function(){},onClick:function(){}},"
    "themeParams:{},colorScheme:'light',isExpanded:true,"
    "contentSafeAreaInset:{top:0,bottom:0,left:0,right:0},"
    "safeAreaInset:{top:0,bottom:0,left:0,right:0},"
    "setHeaderColor:function(){},setBackgroundColor:function(){},"
    "onEvent:function(){},offEvent:function(){},sendData:function(){},openLink:function(){},"
    "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},selectionChanged:function(){}}}};"
)


def _create_page(browser, miniapp_server, *, viewport, is_mobile, dark=False):
    """Create a fresh browser context + page. Returns (context, page)."""
    context = browser.new_context(
        viewport=viewport,
        device_scale_factor=3,
        is_mobile=is_mobile,
        color_scheme="dark" if dark else "light",
        extra_http_headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"},
    )
    page = context.new_page()
    page.on("console", lambda msg: print(f"\nBROWSER [{msg.type}]: {msg.text}"))
    page.on("pageerror", lambda err: print(f"\nBROWSER ERROR: {err}"))
    context.add_init_script(_TELEGRAM_JS_STUB)
    context.add_init_script("localStorage.setItem('aroma_onboarded', '1')")
    context.add_init_script("localStorage.setItem('aroma_walkthrough_done', '1')")
    if dark:
        context.add_init_script(
            "document.addEventListener('DOMContentLoaded',"
            " () => document.body.classList.add('tg-theme-dark'))"
        )
    page.goto(miniapp_server, wait_until="domcontentloaded", timeout=15000)
    try:
        page.wait_for_selector("body.app-ready", timeout=10000)
    except Error:
        page.evaluate("document.body.classList.add('app-ready')")
        page.wait_for_timeout(200)
    # Wait for bridge registration (module scripts are deferred)
    try:
        page.wait_for_function("typeof window.goBackToList === 'function'", timeout=5000)
    except Error:
        pass
    # Zero out Telegram content inset — in tests there is no TG chrome above
    page.evaluate("document.documentElement.style.setProperty('--tg-content-inset-top', '0px')")
    if dark:
        page.evaluate("document.body.classList.add('tg-theme-dark')")
        page.wait_for_timeout(50)
    return context, page


@pytest.fixture()
def page(browser, miniapp_server):
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 393, "height": 852}, is_mobile=True,
    )
    yield pg
    context.close()


@pytest.fixture()
def dark_page(browser, miniapp_server):
    """Mobile page with dark theme (tg-theme-dark) applied from the start."""
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 393, "height": 852}, is_mobile=True, dark=True,
    )
    yield pg
    context.close()


@pytest.fixture(params=["light", "dark"], ids=["light", "dark"])
def themed_page(request, browser, miniapp_server):
    """Mobile page parametrized over light and dark themes."""
    dark = request.param == "dark"
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 393, "height": 852}, is_mobile=True, dark=dark,
    )
    yield pg
    context.close()


@pytest.fixture()
def ipad_page(browser, miniapp_server):
    """iPad Pro 11" viewport (834x1194) with touch enabled."""
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 834, "height": 1194}, is_mobile=True,
    )
    yield pg
    context.close()


@pytest.fixture()
def ipad_dark_page(browser, miniapp_server):
    """iPad Pro 11" viewport with dark theme."""
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 834, "height": 1194}, is_mobile=True, dark=True,
    )
    yield pg
    context.close()


@pytest.fixture()
def desktop_page(browser, miniapp_server):
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 1280, "height": 900}, is_mobile=False,
    )
    yield pg
    context.close()


# ---- Forbidden-zone fixtures ----


@pytest.fixture()
def forbidden_zones(page):
    """Return forbidden zones for the current page viewport."""
    vp = page.viewport_size
    return get_forbidden_zones(vp["width"], vp["height"])


def _check_interactive_elements_in_zones(page, zones: list) -> list[str]:
    """Check all interactive elements against forbidden zones. Returns list of violations."""
    violations: list[str] = []
    for selector in INTERACTIVE_SELECTORS:
        for el in page.locator(selector).all():
            try:
                box = el.bounding_box()
            except Error:
                continue
            if box is None or box["width"] == 0 or box["height"] == 0:
                continue
            # Skip invisible elements
            try:
                visible = el.evaluate(
                    "e => { const s = getComputedStyle(e); "
                    "return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'; }"
                )
                if not visible:
                    continue
            except Error:
                continue
            for zone in zones:
                if overlaps(box, zone):
                    try:
                        tag = el.evaluate("e => e.tagName.toLowerCase()")
                        text = (el.evaluate("e => (e.textContent || '').trim()") or "")[:40]
                        el_id = el.evaluate("e => e.id") or ""
                        el_cls = (el.evaluate("e => e.className") or "")[:60]
                    except Error:
                        tag, text, el_id, el_cls = "?", "?", "", ""
                    ident = f"<{tag}"
                    if el_id:
                        ident += f" id='{el_id}'"
                    if el_cls:
                        ident += f" class='{el_cls}'"
                    ident += f"> '{text}'"
                    violations.append(
                        f"{ident} overlaps zone '{zone.name}' "
                        f"(el: {box['x']:.0f},{box['y']:.0f} {box['width']:.0f}x{box['height']:.0f}  "
                        f"zone: {zone.x:.0f},{zone.y:.0f} {zone.width:.0f}x{zone.height:.0f})"
                    )
    return violations


@pytest.fixture(autouse=True)
def check_forbidden_zones(request):
    """After every UI test, verify no interactive element sits in a forbidden zone."""
    yield

    # Skip if marked
    if request.node.get_closest_marker("skip_zone_check"):
        return

    # Only run for tests that use a page fixture
    page = None
    for fixture_name in ("page", "dark_page", "themed_page", "ipad_page", "ipad_dark_page", "desktop_page"):
        if fixture_name in request.fixturenames:
            try:
                page = request.getfixturevalue(fixture_name)
            except Exception:
                return
            break

    if page is None:
        return

    # Skip if page/context already closed
    try:
        page.evaluate("1")
    except Error:
        return

    vp = page.viewport_size
    if vp is None:
        return

    zones = get_forbidden_zones(vp["width"], vp["height"])
    violations = _check_interactive_elements_in_zones(page, zones)

    if violations:
        msg = f"Forbidden zone violations ({len(violations)}):\n"
        msg += "\n".join(f"  - {v}" for v in violations)
        pytest.fail(msg)
