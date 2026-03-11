from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import sqlite3
from base64 import b64decode
from pathlib import Path
from datetime import datetime, timezone

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
    plans_file = root / "plans.json"
    assets_dir = root / "reels_assets"
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY,
            draft_id VARCHAR(32) UNIQUE,
            kind VARCHAR(64),
            topic VARCHAR(255),
            source VARCHAR(64),
            status VARCHAR(32),
            feedback VARCHAR(255),
            payload JSON,
            created_at DATETIME
        )
    """)
    cursor.execute("""
        CREATE TABLE aroma_cards (
            id INTEGER PRIMARY KEY,
            category VARCHAR(32) DEFAULT 'aroma',
            slug VARCHAR(64) UNIQUE,
            name VARCHAR(255),
            source_type VARCHAR(32),
            aliases JSON,
            payload JSON,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    
    draft_id = "reels001"
    now = datetime.now(timezone.utc).isoformat()
    
    reels_payload = {"scenario": "Test", "storyboard": [{"scene": "Scene 1"}]}
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (draft_id, "reels", "Reels Topic", "/miniapp", "draft", "", json.dumps(reels_payload), now)
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("draft001", "threads", "Draft Topic", "/content", "draft", "", "{}", now)
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("inbox001", "instagram", "Inbox Topic", "/content", "in_review", "", "{}", now)
    )
    
    cursor.execute(
        "INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("lavender", "Лаванда", "aroma", "herb", "[]", "{}", now, now)
    )
    
    conn.commit()
    conn.close()

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "AROMA_DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
        "MINIAPP_AROMA_ALLOWED_USER_IDS": "12345",
        "AROMA_BYPASS_AUTH": "1"
    })

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "miniapp_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
    )
    try:
        _wait_until_ready(base_url)
        yield base_url
    finally:
        process.terminate()
        process.wait()


@pytest.fixture()
def page(miniapp_server: str):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        # Mocking initData for auth
        context = browser.new_context(
            viewport={"width": 430, "height": 932}, 
            is_mobile=True,
            extra_http_headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"}
        )
        page = context.new_page()
        page.goto(miniapp_server, wait_until="networkidle")
        yield page
        context.close()
        browser.close()


def test_each_tab_has_unique_content(page):
    # 1. 'Создать' Tab
    page.get_by_role("button", name="Создать").click()
    page.wait_for_timeout(300)
    assert page.get_by_text("Инструменты").is_visible()
    assert page.get_by_text("Пост для соцсетей").is_visible()
    # Check that it doesn't show drafts list
    assert page.locator(".draft-card").count() == 0

    # 2. 'Согласование' Tab
    page.get_by_role("button", name="Согласование").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    assert page.get_by_role("heading", name="Согласование").is_visible()
    page.wait_for_timeout(300)
    assert page.get_by_text("Пост для соцсетей").count() == 0

    # 3. 'Черновики' Tab
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    assert page.get_by_role("heading", name="Черновики", exact=True).is_visible()
    page.wait_for_timeout(300)
    assert page.get_by_text("Пост для соцсетей").count() == 0

    # 4. 'Рилсы' Tab
    page.get_by_role("button", name="Рилсы").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    assert page.get_by_role("heading", name="Рилсы", exact=True).is_visible()
    page.locator(".reels-card").first.wait_for(state="visible")
    assert page.get_by_text("Reels Topic").is_visible()

    # 5. 'Справочник' -> 'Масла' Tab
    page.get_by_role("button", name="Справочник").click()
    page.wait_for_timeout(300)
    assert page.get_by_role("heading", name="Масла").is_visible()
    assert page.get_by_text("Лаванда").is_visible()
    # Check that it doesn't show tools from 'Create'
    assert page.get_by_text("Пост для соцсетей").count() == 0


def test_create_tool_selection_isolates_form(page):
    page.get_by_role("button", name="Создать").click()
    page.wait_for_timeout(300)
    
    # Select 'Карусель' heading card
    page.get_by_role("heading", name="Карусель").click()
    page.wait_for_timeout(300)
    
    # Form for carousel should be visible
    assert page.get_by_role("heading", name="Создать карусель").is_visible()
    # Form for content should NOT be visible
    assert page.get_by_role("heading", name="Создать контент").count() == 0
    
    # Back button should show the list again
    if page.locator(".back-button").is_visible():
        page.locator(".back-button").click()
        page.wait_for_timeout(300)
        assert page.get_by_text("Инструменты").is_visible()
        assert page.get_by_text("Пост для соцсетей").is_visible()
