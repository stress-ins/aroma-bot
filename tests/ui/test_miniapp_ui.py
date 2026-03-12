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


@pytest.fixture()
def desktop_page(miniapp_server: str):
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error as exc:
            pytest.skip(f"Playwright browser is not available: {exc}")
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            is_mobile=False,
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
    assert tabs_handbook == ["🌿Ароматы", "🫁Практики", "🔔Звуки"]

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


def test_overview_lists_use_consistent_card_meta(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(250)
    assert page.locator(".draft-card .overview-card-date").first.inner_text().strip()

    page.get_by_role("button", name="Планы").click()
    page.wait_for_timeout(250)
    assert page.locator(".plan-card .draft-kind").first.is_visible()
    assert page.locator(".plan-card .overview-card-date").first.is_visible()

    page.get_by_role("button", name="Рилсы").click()
    page.wait_for_timeout(250)
    assert page.locator(".reels-card .draft-meta .tag").count() >= 2

def test_keyboard_can_open_cards_and_create_tools(desktop_page):
    desktop_page.get_by_role("button", name="Черновики").click()
    desktop_page.wait_for_timeout(250)
    desktop_page.locator(".draft-card").first.focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.wait_for_timeout(300)
    assert desktop_page.locator(".detail-title").is_visible()

    desktop_page.get_by_role("button", name="Создать").click()
    desktop_page.wait_for_timeout(250)
    desktop_page.locator(".create-card[data-tool='content']").focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.wait_for_timeout(250)
    assert desktop_page.locator("[data-create-content]").is_visible()

def test_keyboard_can_open_cards_and_create_tools(desktop_page):
    desktop_page.get_by_role("button", name="Черновики").click()
    desktop_page.wait_for_timeout(250)
    desktop_page.locator(".draft-card").first.focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.wait_for_timeout(300)
    assert desktop_page.locator(".detail-title").is_visible()

    desktop_page.get_by_role("button", name="Создать").click()
    desktop_page.wait_for_timeout(250)
    desktop_page.locator(".create-card[data-tool='content']").focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.wait_for_timeout(250)
    assert desktop_page.locator("[data-create-content]").is_visible()


def test_create_tab_uses_guided_empty_state_before_tool_selection(desktop_page):
    desktop_page.get_by_role("button", name="Создать").click()
    desktop_page.wait_for_timeout(250)

    assert desktop_page.locator(".create-card").count() == 4
    assert desktop_page.locator(".guided-state").is_visible()
    assert desktop_page.get_by_text("Выберите формат для старта").is_visible()


def test_draft_search_empty_state_offers_guidance(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(250)
    page.locator("#queryFilter").fill("совсем-нет-такой-темы")
    page.wait_for_timeout(450)

    assert page.locator("#emptyState .guided-state").is_visible()
    assert page.get_by_text("Ничего не найдено.").is_visible()


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


def test_mobile_primary_controls_have_comfortable_hit_targets(page):
    metrics = page.evaluate(
        """
        () => {
          const selectors = ['.mode-button', '.tab-button', '.icon-corner-button', '.secondary-button', '.primary-button', '.back-button.visible'];
          return selectors.flatMap((selector) =>
            [...document.querySelectorAll(selector)]
              .filter((node) => {
                const style = getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              })
              .map((node) => ({
                selector,
                text: (node.textContent || '').trim().slice(0, 40),
                width: Math.round(node.getBoundingClientRect().width),
                height: Math.round(node.getBoundingClientRect().height),
              }))
          );
        }
        """
    )
    bad = [item for item in metrics if item["height"] < 44]
    assert bad == []


def test_desktop_layout_keeps_split_panels_and_comfortable_controls(desktop_page):
    desktop_page.get_by_role("button", name="Черновики").click()
    desktop_page.wait_for_timeout(200)
    layout = desktop_page.evaluate(
        """
        () => {
          const listPanel = document.querySelector('#listPanel');
          const detailPanel = document.querySelector('#detailPanel');
          const tabs = [...document.querySelectorAll('.tab-button')].map((node) => {
            const rect = node.getBoundingClientRect();
            return { text: (node.textContent || '').trim(), height: Math.round(rect.height) };
          });
          const actions = [...document.querySelectorAll('.secondary-button, .primary-button')]
            .filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            })
            .map((node) => ({ text: (node.textContent || '').trim().slice(0, 40), height: Math.round(node.getBoundingClientRect().height) }));
          return {
            listWidth: Math.round(listPanel.getBoundingClientRect().width),
            detailWidth: Math.round(detailPanel.getBoundingClientRect().width),
            tabs,
            actions,
          };
        }
        """
    )
    assert layout["listWidth"] >= 300
    assert layout["detailWidth"] >= 500
    assert all(item["height"] >= 40 for item in layout["tabs"])
    assert all(item["height"] >= 40 for item in layout["actions"])


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
    assert page.get_by_text("Сохранить подпись").count() >= 1
    assert page.get_by_text("Версии").count() >= 1
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


def test_create_carousel_routes_into_draft_detail(page):
    created = {
        "draft_id": "newcar01",
        "kind": "carousel",
        "topic": "Тестовая карусель",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-12T02:00:00+00:00",
        "preview": "Первый слайд / Второй слайд",
        "slides_count": 2,
        "storyboard_count": 0,
        "payload": {
            "slides": ["Первый слайд", "Второй слайд"],
            "img_prompts": ["prompt 1", "prompt 2"],
            "slide_images": [],
            "img_prompt_notes": ["", ""],
            "images_ready": 0,
        },
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/generate/carousel"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(created, ensure_ascii=False))
            return
        if "/api/drafts?" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [
                            {
                                "draft_id": created["draft_id"],
                                "kind": "carousel",
                                "topic": created["topic"],
                                "source": created["source"],
                                "created_at": created["created_at"],
                                "status": created["status"],
                                "feedback": "",
                                "preview": created["preview"],
                                "slides_count": 2,
                                "storyboard_count": 0,
                                "images_ready": 0,
                                "generation_pending": True,
                            }
                        ],
                        "total": 1,
                    },
                    ensure_ascii=False,
                ),
            )
            return
        if url.endswith(f"/api/drafts/{created['draft_id']}"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(created, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    page.get_by_role("button", name="Создать").click()
    page.wait_for_timeout(200)
    page.get_by_role("heading", name="Карусель").click()
    page.locator("textarea[name='topic']").fill("Тестовая карусель")
    page.get_by_role("button", name="Сгенерировать карусель").click()
    page.wait_for_timeout(500)

    assert page.locator(".detail-title").inner_text().strip() == "Тестовая карусель"
    assert page.locator(".slide").count() == 2
    assert page.get_by_role("button", name="Черновики").get_attribute("class")


def test_plan_detail_allows_creating_and_opening_linked_draft(page):
    updated_plan = {
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
        "related_drafts": [
            {
                "draft_id": "planth01",
                "kind": "threads",
                "topic": "Почему вечерний ритуал помогает нервной системе",
                "status": "draft",
            }
        ],
    }
    created_draft = {
        "draft_id": "planth01",
        "kind": "threads",
        "topic": "Почему вечерний ритуал помогает нервной системе",
        "source": "/plan",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-12T02:00:00+00:00",
        "preview": "Иногда телу нужен сигнал безопасности.",
        "slides_count": 0,
        "storyboard_count": 0,
        "payload": {
            "angle": "Через простые телесные сигналы.",
            "hook": "Иногда телу нужен сигнал безопасности.",
            "caption": "Текст для Threads.",
            "cta": "Напиши, если хочешь разбор.",
            "visual_prompt": "warm evening ritual",
        },
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/plans/20260311180000/generate"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"kind": "draft", "draft": created_draft}, ensure_ascii=False),
            )
            return
        if url.endswith("/api/plans?limit=20"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"items": [updated_plan], "total": 1}, ensure_ascii=False),
            )
            return
        if url.endswith("/api/plans/20260311180000"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(updated_plan, ensure_ascii=False))
            return
        if "/api/drafts?" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [
                            {
                                "draft_id": created_draft["draft_id"],
                                "kind": created_draft["kind"],
                                "topic": created_draft["topic"],
                                "source": created_draft["source"],
                                "created_at": created_draft["created_at"],
                                "status": created_draft["status"],
                                "feedback": "",
                                "preview": created_draft["preview"],
                                "slides_count": 0,
                                "storyboard_count": 0,
                                "images_ready": 0,
                                "generation_pending": False,
                            }
                        ],
                        "total": 1,
                    },
                    ensure_ascii=False,
                ),
            )
            return
        if url.endswith("/api/drafts/planth01"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(created_draft, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    page.get_by_role("button", name="Планы").click()
    page.wait_for_timeout(300)

    page.locator(".plan-card").first.click()
    page.wait_for_timeout(300)

    assert page.get_by_role("button", name="Создать Тредс").is_visible()
    page.get_by_role("button", name="Создать Тредс").click()
    page.wait_for_timeout(500)

    assert page.get_by_role("button", name="Открыть Тредс").is_visible()
    page.get_by_role("button", name="Открыть Тредс").click()
    page.wait_for_timeout(500)

    assert page.locator(".detail-title").inner_text().strip() == "Почему вечерний ритуал помогает нервной системе"
    assert page.get_by_role("button", name="Черновики").get_attribute("class")


def test_content_review_detail_supports_save_polish_and_feedback(page):
    updated_draft = {
        "draft_id": "threads001",
        "kind": "threads",
        "topic": "Как мягко выйти из рабочего напряжения",
        "source": "/content",
        "status": "draft",
        "feedback": "worked",
        "created_at": "2026-03-12T02:00:00+00:00",
        "preview": "Иногда телу нужен не совет, а сигнал безопасности.",
        "slides_count": 0,
        "storyboard_count": 0,
        "payload": {
            "angle": "Через телесный переключатель, а не силу воли.",
            "hook": "Иногда телу нужен не совет, а сигнал безопасности.",
            "caption": "Обновленный текст для Threads.",
            "cta": "Если откликается, напиши мне.",
            "hashtags": "#ritual",
            "visual_prompt": "warm calm evening ritual, soft light, cozy interior",
            "editor_notes": "Сделать подачу мягче.",
        },
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/drafts/threads001/content"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(updated_draft, ensure_ascii=False))
            return
        if url.endswith("/api/drafts/threads001/content/polish"):
            polished = dict(updated_draft)
            polished["payload"] = dict(updated_draft["payload"])
            polished["payload"]["caption"] = "Отполированный текст для Threads."
            polished["preview"] = "Отполированный текст для Threads."
            route.fulfill(status=200, content_type="application/json", body=json.dumps(polished, ensure_ascii=False))
            return
        if url.endswith("/api/drafts/threads001/feedback"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(updated_draft, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)

    page.locator("#contentCaptionField").fill("Обновленный текст для Threads.")
    page.locator("#contentEditorNotesField").fill("Сделать подачу мягче.")
    page.get_by_role("button", name="Сохранить правки").click()
    page.wait_for_timeout(350)

    assert page.locator("#contentEditorNotesField").input_value() == "Сделать подачу мягче."
    assert page.get_by_text("Сработало").count() >= 1

    page.get_by_role("button", name="AI polish").click()
    page.wait_for_timeout(350)
    assert page.locator("#contentCaptionField").input_value() == "Отполированный текст для Threads."

    page.get_by_role("button", name="Не сработало").click()
    page.wait_for_timeout(350)
    assert page.get_by_text("Не сработало").count() >= 1


def test_content_review_detail_highlights_editor_focus_and_summary(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)

    metrics = page.evaluate(
        """
        () => {
          const hero = document.querySelector('.detail-hero');
          const facts = document.querySelectorAll('.detail-fact').length;
          const summary = (document.querySelector('.detail-summary')?.textContent || '').trim();
          const captionRect = document.querySelector('#contentCaptionField')?.getBoundingClientRect();
          const notesRect = document.querySelector('#contentEditorNotesField')?.getBoundingClientRect();
          return {
            hasHero: Boolean(hero),
            facts,
            summaryLength: summary.length,
            captionHeight: captionRect ? Math.round(captionRect.height) : 0,
            notesHeight: notesRect ? Math.round(notesRect.height) : 0,
          };
        }
        """
    )

    assert metrics["hasHero"] is True
    assert metrics["facts"] >= 4
    assert metrics["summaryLength"] >= 20
    assert metrics["captionHeight"] > metrics["notesHeight"]


def test_keywords_detail_supports_add_and_remove(page):
    updated_keywords = {
        "items": [
            {
                "topic_idx": 0,
                "name": "Расслабление",
                "fields": {
                    "kw_ru": ["расслабление", "пауза"],
                    "kw_en": ["relaxation"],
                    "tag_ru": ["#ритуал"],
                    "tag_en": [],
                },
            }
        ],
        "field_labels": {
            "kw_ru": "Ключи RU",
            "kw_en": "Ключи EN",
            "tag_ru": "Теги RU",
            "tag_en": "Теги EN",
        },
    }

    removed_keywords = {
        "items": [
            {
                "topic_idx": 0,
                "name": "Расслабление",
                "fields": {
                    "kw_ru": ["пауза"],
                    "kw_en": ["relaxation"],
                    "tag_ru": ["#ритуал"],
                    "tag_en": [],
                },
            }
        ],
        "field_labels": updated_keywords["field_labels"],
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/keywords/add"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(updated_keywords, ensure_ascii=False))
            return
        if url.endswith("/api/keywords/remove"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(removed_keywords, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    page.get_by_role("button", name="Ключи").click()
    page.wait_for_timeout(300)
    page.locator(".keyword-topic").first.click()
    page.wait_for_timeout(300)

    page.locator(".keyword-form input").first.fill("пауза")
    page.get_by_role("button", name="Добавить").first.click()
    page.wait_for_timeout(350)
    assert page.locator("#uiNotice").is_visible()
    assert page.get_by_text("Ключ добавлен").is_visible()
    assert page.get_by_text("пауза").count() >= 1

    chips_before_delete = page.locator(".keyword-chip").count()
    page.evaluate(
        """
        () => {
          window.Telegram = window.Telegram || {};
          window.Telegram.WebApp = window.Telegram.WebApp || {};
          window.Telegram.WebApp.showConfirm = (_message, callback) => callback(true);
        }
        """
    )
    page.locator(".keyword-chip button").first.click()
    page.wait_for_timeout(350)
    assert page.locator(".keyword-chip").count() == chips_before_delete - 1


def test_tap_outside_textarea_dismisses_keyboard_focus(page):
    page.get_by_role("button", name="Создать").click()
    page.wait_for_timeout(200)
    page.get_by_role("heading", name="Пост для соцсетей").click()
    page.wait_for_timeout(300)
    page.locator("textarea[name='topic']").wait_for(state="visible")
    page.locator("textarea[name='topic']").focus()
    assert page.evaluate("document.activeElement && document.activeElement.tagName") == "TEXTAREA"

    page.locator("#detailPanel").click(position={"x": 20, "y": 20})
    page.wait_for_timeout(150)

    assert page.evaluate("document.activeElement && document.activeElement.tagName") != "TEXTAREA"


def test_focusing_lower_review_field_keeps_it_in_view(page):
    page.get_by_role("button", name="Черновики").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)

    page.evaluate("window.scrollTo(0, 0)")
    page.locator("#contentEditorNotesField").focus()
    page.wait_for_timeout(350)

    metrics = page.evaluate(
        """
        () => {
          const field = document.getElementById('contentEditorNotesField');
          if (!field) return null;
          const rect = field.getBoundingClientRect();
          const viewportHeight = window.visualViewport?.height || window.innerHeight;
          return {
            top: Math.round(rect.top),
            bottom: Math.round(rect.bottom),
            viewportHeight: Math.round(viewportHeight),
          };
        }
        """
    )

    assert metrics is not None
    assert metrics["top"] >= 0
    assert metrics["bottom"] <= metrics["viewportHeight"]
