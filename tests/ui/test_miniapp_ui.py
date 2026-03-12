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
from datetime import datetime, timezone
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
    plans_file = root / "plans.json"
    assets_dir = root / "reels_assets"

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
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
        """
    )
    cursor.execute(
        """
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
        """
    )

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
                "scene": "Руки закрывают ноутбук",
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
        "img_prompt_notes": ["", ""],
        "cta": "Напиши, если хочешь такую карусель под свой проект.",
    }

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (draft_id, "reels", "Вечерний ароматический ритуал", "/miniapp", "draft", "", json.dumps(reels_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("threads001", "threads", "Как мягко выйти из рабочего напряжения", "/content", "in_review", "worked", json.dumps(threads_payload), now),
    )
    cursor.execute(
        "INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("carousel001", "carousel", "Сенсорная карусель для вечернего ритуала", "/miniapp", "draft", "", json.dumps(carousel_payload), now),
    )
    cursor.execute(
        "INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("lavender", "Лаванда", "aroma", "herb", json.dumps([]), json.dumps({}), now, now),
    )
    conn.commit()
    conn.close()

    plans_file.write_text(
        json.dumps(
            [
                {
                    "plan_id": "20260311180000",
                    "created_at": "2026-03-11T18:00:00+00:00",
                    "raw_text": "Понедельник: Threads, Среда: Reels",
                    "entries": [
                        {
                            "day_label": "Понедельник",
                            "platform": "Threads",
                            "format_label": "пост",
                            "goal": "Доверие",
                            "topic": "Почему вечерний ритуал помогает нервной системе",
                            "angle": "Через простые телесные сигналы.",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "REPORT_TARGET_CHAT_ID": "test-chat",
            "AROMA_DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
            "AROMA_PLANS_FILE": str(plans_file),
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


@pytest.fixture()
def page(miniapp_server: str):
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error as exc:
            pytest.skip(f"Playwright browser is not available: {exc}")
        context = browser.new_context(
            viewport={"width": 430, "height": 932},
            is_mobile=True,
            extra_http_headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"},
        )
        page = context.new_page()
        page.goto(miniapp_server, wait_until="networkidle")
        yield page
        context.close()
        browser.close()


def test_mobile_tabs_and_drafts_render_in_russian(page):
    tabs = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Создать" in tabs
    assert "Черновики" in tabs

    page.get_by_role("button", name="Справочник").click()
    page.wait_for_timeout(300)

    tabs_handbook = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert tabs_handbook == ["Ароматы", "Практики", "Звуки"]

    page.get_by_role("button", name="Контент").click()
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")

    page.locator(".draft-card").first.wait_for(state="visible")
    assert page.locator(".draft-card").count() >= 2
    assert not page.locator("#emptyState").is_visible()


def test_reels_tab_opens_storyboard_without_empty_state(page):
    page.get_by_role("button", name="Рилсы").click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".reels-card").count() == 1
    page.locator(".reels-card").click()
    page.wait_for_timeout(300)

    assert not page.locator("#emptyState").is_visible()
    assert page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"
    
    # Open the prompt details to make the copy button visible
    page.get_by_text("Показать промпт").first.click()
    page.wait_for_timeout(150)
    assert page.get_by_role("button", name="Скопировать промпт кадра").is_visible()
    assert page.locator(".frame-image").count() == 1


def test_mobile_layout_has_no_overlapping_controls(page):
    for tab_name in ["Черновики", "Рилсы", "Создать"]:
        page.get_by_role("button", name=tab_name).click()
        page.wait_for_timeout(300)

        overlaps = page.evaluate(
            """
            () => {
              const controls = [...document.querySelectorAll('button, select, input, textarea')]
                .filter((node) => {
                  const style = getComputedStyle(node);
                  const rect = node.getBoundingClientRect();
                  return !node.hidden && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                })
                .map((node) => ({
                  text: (node.innerText || node.value || node.textContent || '').trim().slice(0, 40),
                  x: node.getBoundingClientRect().x,
                  y: node.getBoundingClientRect().y,
                  w: node.getBoundingClientRect().width,
                  h: node.getBoundingClientRect().height,
                }));
              const bad = [];
              for (let i = 0; i < controls.length; i++) {
                for (let j = i + 1; j < controls.length; j++) {
                  const a = controls[i];
                  const b = controls[j];
                  const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
                  const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
                  const area = ix * iy;
                  if (area > 150) {
                    bad.push({ a: a.text, b: b.text, area });
                  }
                }
              }
              return bad;
            }
            """
        )
        assert overlaps == []


def test_mobile_detail_actions_do_not_overlap(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    page.locator(".draft-card").first.wait_for(state="visible")
    page.locator(".draft-card").first.click()
    page.wait_for_timeout(300)

    overlaps = page.evaluate(
        """
        () => {
          const root = document.querySelector('#draftDetail');
          const controls = [...root.querySelectorAll('button, select, input, textarea')]
            .filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return !node.hidden && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            })
            .map((node) => ({
              text: (node.innerText || node.value || node.textContent || '').trim().slice(0, 50),
              x: node.getBoundingClientRect().x,
              y: node.getBoundingClientRect().y,
              w: node.getBoundingClientRect().width,
              h: node.getBoundingClientRect().height,
            }));
          const bad = [];
          for (let i = 0; i < controls.length; i++) {
            for (let j = i + 1; j < controls.length; j++) {
              const a = controls[i];
              const b = controls[j];
              const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
              const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
              if ((ix * iy) > 100) bad.push({ a: a.text, b: b.text, area: ix * iy });
            }
          }
          return bad;
        }
        """
    )
    assert overlaps == []


def test_carousel_detail_shows_prompt_copy_buttons(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.wait_for(state="visible")
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(300)

    assert page.get_by_role("button", name="Скопировать промпт слайда").count() >= 1
    assert page.get_by_role("button", name="Сохранить текст слайда").count() >= 1
    assert page.locator(".slide").count() >= 2


def test_create_tool_selection_isolates_form(page):
    page.get_by_role("button", name="Создать").click()
    page.wait_for_timeout(300)

    page.get_by_role("heading", name="Карусель").click()
    page.wait_for_timeout(300)

    assert page.get_by_role("heading", name="Создать карусель").is_visible()
    assert page.get_by_role("heading", name="Создать контент").count() == 0

    if page.locator(".back-button").is_visible():
        page.locator(".back-button").click()
        page.wait_for_timeout(300)
        assert page.get_by_text("Инструменты").is_visible()
        assert page.get_by_text("Пост для соцсетей").is_visible()
