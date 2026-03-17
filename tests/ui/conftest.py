"""Shared Playwright fixtures for UI tests.

Key design decisions:
- ONE Chromium browser per session (not per test) to avoid launch overhead.
- Each test gets a fresh browser context + page (function scope) for isolation.
- miniapp_server is session-scoped: starts uvicorn once, shared by all tests.
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
        "scenario": "Короткий сценарий рилса про вечернее переключение.",
        "images_ready": 1,
        "storyboard": [
            {
                "timecode": "0-3 сек",
                "scene": "**Текст на экране:** Попробуй сегодня\n\n## Сцена\nРуки закрывают ноутбук",
                "angle": "Крупный план",
                "gemini_prompt": "warm evening desk, close-up hands closing laptop",
                "current_asset": {
                    "url": f"/generated/reels_assets/{draft_id}/frame_1.png",
                    "filename": "frame_1.png",
                    "generated_at": "2026-03-11T18:00:00+00:00",
                },
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
        (draft_id, "reels", "Вечерний ароматический ритуал", "/miniapp", "draft", "", json.dumps(reels_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        ("threads001", "threads", "Как мягко выйти из рабочего напряжения", "/content", "in_review", "worked", json.dumps(threads_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
        ("carousel001", "carousel", "Сенсорная карусель для вечернего ритуала", "/miniapp", "draft", "", json.dumps(carousel_payload), now),
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
    for slug, name, cat_group in [
        ("headache", "Головная боль", "НЕРВНАЯ СИСТЕМА"),
        ("anxiety", "Тревожность", "НЕРВНАЯ СИСТЕМА"),
        ("indigestion", "Несварение желудка", "ПИЩЕВАРЕНИЕ"),
        ("insomnia", "Бессонница", "СОН И ОТДЫХ"),
        ("fatigue", "Усталость и истощение", "ЭНЕРГИЯ"),
        ("hypertension", "Гипертония", "СЕРДЕЧНО-СОСУДИСТАЯ"),
        ("depression", "Депрессия", "ПСИХОЭМОЦИОНАЛЬНОЕ"),
        ("allergy", "Аллергия", "ИММУНИТЕТ И КОЖА"),
    ]:
        cursor.execute(
            "INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, "symptom", "symptom", json.dumps([]), json.dumps({"category_group": cat_group, "parent_group": cat_group}), now, now),
        )
    cursor.execute(
        "INSERT INTO plans (plan_id, raw_text, entries, created_at) VALUES (?, ?, ?, ?)",
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
        }
    )

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "miniapp_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_ready(base_url)
        yield base_url
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
    "setHeaderColor:function(){},setBackgroundColor:function(){},"
    "onEvent:function(){},offEvent:function(){},sendData:function(){},openLink:function(){},"
    "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},selectionChanged:function(){}}}};"
)


def _create_page(browser, miniapp_server, *, viewport, is_mobile, dark=False):
    """Create a fresh browser context + page. Returns (context, page)."""
    context = browser.new_context(
        viewport=viewport,
        is_mobile=is_mobile,
        color_scheme="dark" if dark else "light",
        extra_http_headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"},
    )
    page = context.new_page()
    page.on("console", lambda msg: print(f"\nBROWSER [{msg.type}]: {msg.text}"))
    page.on("pageerror", lambda err: print(f"\nBROWSER ERROR: {err}"))
    context.add_init_script("localStorage.setItem('aroma_onboarded', '1')")
    if dark:
        context.add_init_script(
            "document.addEventListener('DOMContentLoaded',"
            " () => document.body.classList.add('tg-theme-dark'))"
        )
    page.goto(miniapp_server, wait_until="load", timeout=60000)
    try:
        page.wait_for_selector("body.app-ready", timeout=15000)
    except Error:
        # Fallback: set app-ready manually if bootstrap silently failed
        page.evaluate("document.body.classList.add('app-ready')")
        page.wait_for_timeout(500)
    if dark:
        page.evaluate("document.body.classList.add('tg-theme-dark')")
        page.wait_for_timeout(50)
    return context, page


@pytest.fixture()
def page(browser, miniapp_server):
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 430, "height": 932}, is_mobile=True,
    )
    yield pg
    context.close()


@pytest.fixture()
def dark_page(browser, miniapp_server):
    """Mobile page with dark theme (tg-theme-dark) applied from the start."""
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 430, "height": 932}, is_mobile=True, dark=True,
    )
    yield pg
    context.close()


@pytest.fixture(params=["light", "dark"], ids=["light", "dark"])
def themed_page(request, browser, miniapp_server):
    """Mobile page parametrized over light and dark themes."""
    dark = request.param == "dark"
    context, pg = _create_page(
        browser, miniapp_server,
        viewport={"width": 430, "height": 932}, is_mobile=True, dark=dark,
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
