from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from io import BytesIO
from base64 import b64decode
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import Error, sync_playwright


_PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zk6cAAAAASUVORK5CYII="
)
_SNAPSHOT_DIR = Path(__file__).with_name("snapshots")


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


def _prepare_visual_state(page) -> None:
    page.add_style_tag(
        content="""
        *,
        *::before,
        *::after {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
          scroll-behavior: auto !important;
        }
        """
    )
    page.wait_for_timeout(150)


def _assert_visual_snapshot(locator, snapshot_name: str, *, max_diff_ratio: float = 0.0025) -> None:
    expected_path = _SNAPSHOT_DIR / snapshot_name
    actual_bytes = locator.screenshot(animations="disabled")

    if os.getenv("UPDATE_VISUAL_BASELINE") == "1":
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_bytes(actual_bytes)
        return

    assert expected_path.exists(), f"Missing visual baseline: {expected_path}"

    expected = Image.open(expected_path).convert("RGBA")
    actual = Image.open(BytesIO(actual_bytes)).convert("RGBA")

    # Crop both to the smaller common area to tolerate minor cross-platform size differences
    w = min(actual.size[0], expected.size[0])
    h = min(actual.size[1], expected.size[1])
    expected = expected.crop((0, 0, w, h))
    actual = actual.crop((0, 0, w, h))

    expected_pixels = np.array(expected)
    actual_pixels = np.array(actual)
    diff_mask = np.any(np.abs(actual_pixels.astype(np.int16) - expected_pixels.astype(np.int16)) > 12, axis=2)
    diff_ratio = float(diff_mask.mean())
    assert diff_ratio <= max_diff_ratio, (
        f"Visual regression in {snapshot_name}: diff ratio {diff_ratio:.4%} exceeds {max_diff_ratio:.4%}"
    )


@pytest.fixture(scope="session")
def miniapp_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("miniapp-ui")
    db_file = root / "test_aroma.db"
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
    cursor.execute(
        """
        CREATE TABLE plans (
            id INTEGER PRIMARY KEY,
            plan_id VARCHAR(32) UNIQUE,
            raw_text TEXT,
            entries JSON,
            created_at DATETIME
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
        page.on("console", lambda msg: print(f"\nBROWSER [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"\nBROWSER ERROR: {err}"))
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
        page.on("console", lambda msg: print(f"\nBROWSER [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"\nBROWSER ERROR: {err}"))
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
    assert "🌿Ароматы" in tabs_handbook
    assert "🧭Теория" in tabs_handbook
    assert "🫁Практики" in tabs_handbook
    assert "🔔Звуки" in tabs_handbook

    page.locator("#modeContent").click()
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")

    page.locator(".draft-card").first.wait_for(state="visible")
    assert page.locator(".draft-card").count() >= 2
    assert not page.locator("#emptyState").is_visible()


def _open_reels_detail_from_drafts(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(300)


def test_reels_tab_opens_storyboard_without_empty_state(page):
    _open_reels_detail_from_drafts(page)

    assert not page.locator("#emptyState").is_visible()
    assert page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"
    
    # Open the editor details to make the copy button visible
    page.get_by_text("Открыть редактирование кадра").first.click()
    page.wait_for_timeout(150)
    assert page.get_by_role("button", name="Скопировать промпт кадра").is_visible()
    assert page.locator(".frame-image").count() == 1


def test_reels_detail_shows_production_overview_and_frame_status(page):
    _open_reels_detail_from_drafts(page)

    assert page.get_by_text("План рилса").is_visible()
    assert page.get_by_text("Shot 1").is_visible()
    assert page.get_by_text("Кадр готов").first.is_visible()
    assert page.get_by_text("Открыть редактирование кадра").first.is_visible()


def test_reels_detail_falls_back_to_payload_storyboard(page):
    def _fulfill_reel(route):
        if not route.request.url.endswith("/api/reels/reels001"):
            route.continue_()
            return
        payload = {
            "draft_id": "reels001",
            "kind": "reels",
            "topic": "Вечерний ароматический ритуал",
            "source": "/miniapp",
            "status": "draft",
            "feedback": "",
            "created_at": "2026-03-11T18:00:00+00:00",
            "preview": "Рилс с fallback-раскадровкой.",
            "images_ready": 1,
            "frame_count": 0,
            "frames": [],
            "payload": {
                "concept": "Вечернее переключение",
                "scenario": "Короткий сценарий",
                "storyboard": [
                    {
                        "timecode": "0-3 сек",
                        "scene": "**Текст на экране:** Попробуй сегодня",
                        "angle": "Крупный план",
                        "current_asset": {
                            "url": "/generated/reels_assets/reels001/frame_1.png",
                            "filename": "frame_1.png",
                        },
                    }
                ],
            },
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

    page.route("**/api/reels/reels001", _fulfill_reel)
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(200)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(250)

    assert page.locator(".storyboard-frame").count() == 1
    assert page.get_by_text("Попробуй сегодня").first.is_visible()


def test_drafts_reels_card_routes_into_storyboard_detail_with_mocked_api(page):
    reels_detail = {
        "draft_id": "reels001",
        "kind": "reels",
        "topic": "Вечерний ароматический ритуал",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-11T18:00:00+00:00",
        "preview": "Рилс с раскадровкой.",
        "images_ready": 1,
        "frame_count": 1,
        "frames": [
            {
                "timecode": "0-3 сек",
                "scene": "Камера идет по флакону и ладони",
                "angle": "Крупный план",
                "gemini_prompt": "close-up bottle and hand, warm evening light",
                "current_asset": {
                    "url": "/generated/reels_assets/reels001/frame_1.png",
                    "filename": "frame_1.png",
                },
            }
        ],
        "payload": {
            "concept": "Вечернее переключение",
            "scenario": "Короткий сценарий",
            "storyboard": [],
        },
    }

    def _draft_detail(route):
        if route.request.url.endswith("/api/drafts/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reels_detail, ensure_ascii=False))
            return
        route.continue_()

    def _reel_detail(route):
        if route.request.url.endswith("/api/reels/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reels_detail, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/api/drafts/reels001", _draft_detail)
    page.route("**/api/reels/reels001", _reel_detail)

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(200)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(300)

    assert page.locator(".storyboard-frame").count() == 1
    assert page.get_by_text("Камера идет по флакону и ладони").first.is_visible()
    assert not page.get_by_text("Превью").is_visible()


def test_overview_lists_use_consistent_card_meta(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    assert page.locator(".draft-card .overview-card-date").first.inner_text().strip()

    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(250)
    assert page.locator(".plan-card .draft-kind").first.is_visible()
    assert page.locator(".plan-card .overview-card-date").first.is_visible()

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(250)
    assert page.locator(".storyboard-frame").count() >= 1

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

    assert desktop_page.locator(".guided-state").is_visible()
    assert desktop_page.get_by_text("Выберите формат для старта").is_visible()
    assert desktop_page.get_by_text("быстрые сценарии для контента, рилса, плана недели и карусели").is_visible()


def test_draft_search_empty_state_offers_guidance(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    page.locator("#queryFilter").fill("совсем-нет-такой-темы")
    page.wait_for_timeout(450)

    assert page.locator("#emptyState .guided-state").is_visible()
    assert page.get_by_text("Ничего не найдено").is_visible()
    assert page.get_by_role("button", name="Открыть создание").is_visible()


def test_settings_and_keywords_use_guided_detail_copy(desktop_page):
    desktop_page.get_by_role("button", name="Статус").click()
    desktop_page.wait_for_timeout(250)
    assert desktop_page.get_by_text("Проверьте состояние источников").is_visible()

    desktop_page.get_by_role("button", name="Ключи").click()
    desktop_page.wait_for_timeout(250)
    assert desktop_page.get_by_text("Откройте тему для редактирования").is_visible()

def test_mobile_layout_has_no_overlapping_controls(page):
    for tab_name in ["Черновики", "Планы", "Создать"]:
        {"Черновики": page.locator("#btnTabDrafts"), "Планы": page.locator("#btnTabPlans"), "Создать": page.locator("#btnTabCreate")}[tab_name].click()
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
          const selectors = ['.mode-button', '.tab-button', '.icon-corner-button', '.secondary-button', '.primary-button', '.back-button.visible', '.bottom-tab-btn'];
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


def test_mobile_bottom_tab_bar_switches_primary_sections(page):
    bottom_nav = page.locator("#bottomTabBar")
    assert bottom_nav.is_visible()

    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(300)
    assert page.locator("#btnTabPlans").get_attribute("aria-pressed") == "true"
    assert page.locator(".plan-card").count() >= 1

    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)
    assert page.locator("#btnTabHandbook").get_attribute("aria-pressed") == "true"
    handbook_tabs = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "🌿Ароматы" in handbook_tabs
    assert "🫁Практики" in handbook_tabs
    assert "🔔Звуки" in handbook_tabs

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    assert page.locator("#btnTabDrafts").get_attribute("aria-pressed") == "true"
    assert page.locator(".draft-card").count() >= 2


def test_mobile_handbook_tab_remembers_last_section(page):
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(250)
    page.get_by_role("button", name="Практики").click()
    page.wait_for_timeout(250)

    active_before = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_before

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(250)

    active_after = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_after


def test_mobile_swipe_back_from_left_edge_works_over_interactive_controls(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(250)
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(300)

    page.evaluate(
        """
        () => {
          const button = document.querySelector('#draftDetail .prompt-actions .secondary-button');
          if (!button) throw new Error('detail action button not found');
          const makeEvent = (type, touches, changedTouches = touches) => {
            const event = new Event(type, { bubbles: true, cancelable: true });
            Object.defineProperty(event, 'touches', { value: touches });
            Object.defineProperty(event, 'changedTouches', { value: changedTouches });
            return event;
          };
          const start = [{ clientX: 12, clientY: 180 }];
          const move = [{ clientX: 120, clientY: 184 }];
          button.dispatchEvent(makeEvent('touchstart', start));
          button.dispatchEvent(makeEvent('touchmove', move));
          button.dispatchEvent(makeEvent('touchend', [], move));
        }
        """
    )
    page.wait_for_timeout(260)

    assert page.locator("#listPanel").evaluate("(node) => !node.classList.contains('hidden-mobile')")
    assert page.locator("#detailPanel").evaluate("(node) => node.classList.contains('hidden-mobile')")
    assert page.get_by_text("Сенсорная карусель для вечернего ритуала").first.is_visible()


def test_dark_theme_class_styles_bottom_tab_bar(page):
    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    theme_state = page.evaluate(
        """
        () => {
          const tabBar = document.querySelector('.bottom-tab-bar-inner');
          return {
            bodyDark: document.body.classList.contains('tg-theme-dark'),
            tabBarBackground: getComputedStyle(tabBar).backgroundColor,
            tabBarBorder: getComputedStyle(tabBar).borderColor,
          };
        }
        """
    )

    assert theme_state["bodyDark"] is True
    assert "37, 30, 24" in theme_state["tabBarBackground"]
    assert "255, 230, 200" in theme_state["tabBarBorder"]


def test_dark_theme_keeps_reels_storyboard_text_readable(page):
    _open_reels_detail_from_drafts(page)
    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    frame_style = page.evaluate(
        """
        () => {
          const card = document.querySelector('.storyboard-frame');
          const text = document.querySelector('.reels-frame-section-value');
          const section = card.closest('.section');
          const cardStyle = getComputedStyle(card);
          const textStyle = getComputedStyle(text);
          const sectionStyle = getComputedStyle(section);
          return {
            cardBackgroundImage: cardStyle.backgroundImage,
            sectionBackgroundImage: sectionStyle.backgroundImage,
            textColor: textStyle.color,
          };
        }
        """
    )

    assert "gradient" in frame_style["cardBackgroundImage"] or "gradient" in frame_style["sectionBackgroundImage"]
    # After dark-mode fix, text uses dark-theme --text (#f0e8df = 240,232,223) instead of old hardcoded light #2a1e16
    text_color = frame_style["textColor"]
    assert "240, 232, 223" in text_color or "42, 30, 22" not in text_color, (
        f"Expected dark-theme text color (light on dark), got: {text_color}"
    )


def test_reels_and_plans_render_markdown_in_detail_views(page):
    _open_reels_detail_from_drafts(page)

    frame_markup = page.locator(".reels-frame-section-value").first.evaluate(
        "(node) => ({ html: node.innerHTML, text: node.textContent })"
    )
    assert "<strong>" in frame_markup["html"]
    assert "<h4>" in frame_markup["html"]
    assert "**Текст на экране:**" not in frame_markup["text"]
    assert "## Сцена" not in frame_markup["text"]

    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(250)
    page.locator(".plan-card").first.click()
    page.wait_for_timeout(250)

    plan_markup = page.locator(".detail-preview.detail-markdown").first.evaluate(
        "(node) => ({ html: node.innerHTML, text: node.textContent })"
    )
    assert "<h4>Контент-план</h4>" in plan_markup["html"]
    assert "<li>Понедельник: Threads</li>" in plan_markup["html"]
    assert "## Контент-план" not in plan_markup["text"]


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
    page.locator("#btnTabDrafts").click()
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
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.evaluate("window.goBackToList()")
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.wait_for(state="visible")
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(300)

    assert page.get_by_role("button", name="Скопировать промпт слайда").count() >= 1
    assert page.get_by_text("Сохранить подпись").count() >= 1
    assert page.get_by_text("Версии").count() >= 1
    assert page.locator(".slide").count() >= 2
    assert page.locator(".prompt-actions.actions-grid-two").count() >= 1
    assert page.locator(".slide-version-actions.actions-grid-two").count() >= 1


def test_mobile_carousel_actions_use_two_columns(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(300)

    columns = page.locator(".prompt-actions.actions-grid-two").first.evaluate(
        "(node) => getComputedStyle(node).gridTemplateColumns"
    )
    assert columns.count(" ") >= 1


def test_reels_storyboard_regenerate_enters_pending_images_state(page):
    pending_reel = {
        "draft_id": "reels001",
        "kind": "reels",
        "topic": "Вечерний ароматический ритуал",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-11T18:00:00+00:00",
        "preview": "Короткий сценарий рилса про вечернее переключение.",
        "scenario": "Обновленный сценарий",
        "frame_count": 4,
        "images_ready": 0,
        "generation_pending": True,
        "generation_stage": "images",
        "generation_message": "Генерирую кадры для рилса.",
        "frames": [],
        "shot_list": [],
        "production_notes": {"required": [], "optional": []},
        "payload": {},
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/reels/reels001/storyboard/regenerate"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(pending_reel, ensure_ascii=False))
            return
        if url.endswith("/api/reels/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(pending_reel, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    _open_reels_detail_from_drafts(page)
    page.get_by_role("button", name="Пересобрать раскадровку").click()
    page.wait_for_timeout(450)

    assert page.get_by_text("Генерирую кадры для рилса.").count() >= 1
    assert page.get_by_text("0/4 кадров").count() >= 1


def test_create_tool_selection_isolates_form(page):
    page.locator("#btnTabCreate").click()
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
    page.locator("#btnTabCreate").click()
    page.wait_for_timeout(200)
    page.get_by_role("heading", name="Карусель").click()
    page.locator("textarea[name='topic']").fill("Тестовая карусель")
    page.get_by_role("button", name="Собрать карусель").click()
    page.wait_for_timeout(500)

    assert page.locator(".detail-title").inner_text().strip() == "Тестовая карусель"
    assert page.locator(".slide").count() == 2
    assert page.locator("#btnTabDrafts").get_attribute("class")


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
    page.locator("#btnTabPlans").click()
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
    assert page.locator("#btnTabDrafts").get_attribute("class")


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
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)

    page.locator("#contentCaptionField").fill("Обновленный текст для Threads.")
    page.locator("#contentEditorNotesField").fill("Сделать подачу мягче.")
    page.get_by_role("button", name="Сохранить версию").click()
    page.wait_for_timeout(350)

    assert page.locator("#contentEditorNotesField").input_value() == "Сделать подачу мягче."
    assert page.get_by_text("Откликнулось").count() >= 1

    page.get_by_role("button", name="Уточнить через AI").click()
    page.wait_for_timeout(350)
    assert page.locator("#contentCaptionField").input_value() == "Отполированный текст для Threads."

    page.get_by_role("button", name="Не дало результата").click()
    page.wait_for_timeout(350)
    assert page.get_by_text("Не дало результата").count() >= 1


def test_content_review_detail_highlights_editor_focus_and_summary(page):
    page.locator("#btnTabDrafts").click()
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


def test_create_and_detail_forms_show_helper_microcopy(page):
    page.locator("#btnTabCreate").click()
    page.wait_for_timeout(250)
    page.get_by_text("Пост для соцсетей").click()
    page.wait_for_timeout(250)

    assert page.get_by_text("Сформулируйте тему как готовую мысль").is_visible()
    assert page.get_by_role("button", name="Собрать черновик").is_visible()

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)

    assert page.get_by_text("Сохраняйте версию после смыслового прохода").is_visible()
    assert page.get_by_role("button", name="Согласовать").is_visible()


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
    page.evaluate("window.openSettingsSection('keywords')")
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
    page.locator("#btnTabCreate").click()
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
    page.locator("#btnTabDrafts").click()
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


def test_visual_mobile_drafts_list_baseline(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    _prepare_visual_state(page)
    _assert_visual_snapshot(page.locator(".shell"), "mobile-drafts-list.png")


def test_visual_mobile_draft_detail_baseline(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(300)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(300)
    _prepare_visual_state(page)
    _assert_visual_snapshot(page.locator("#detailPanel"), "mobile-draft-detail.png")


def test_visual_mobile_plan_detail_baseline(page):
    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(300)
    page.locator(".plan-card").first.click()
    page.wait_for_timeout(300)
    _prepare_visual_state(page)
    _assert_visual_snapshot(page.locator("#detailPanel"), "mobile-plan-detail.png")


def test_visual_mobile_reels_detail_baseline(page):
    _open_reels_detail_from_drafts(page)
    _prepare_visual_state(page)
    _assert_visual_snapshot(page.locator("#detailPanel"), "mobile-reels-detail.png")


def test_visual_desktop_split_view_baseline(desktop_page):
    desktop_page.get_by_role("button", name="Черновики").click()
    desktop_page.wait_for_timeout(300)
    desktop_page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    desktop_page.wait_for_timeout(300)
    _prepare_visual_state(desktop_page)
    _assert_visual_snapshot(desktop_page.locator(".shell"), "desktop-split-view.png")


def test_dark_theme_class_applies_without_js_errors(page):
    """Smoke test: adding body.tg-theme-dark triggers no JS exceptions and
    the dark CSS vars are applied so the shell background darkens."""
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(80)

    result = page.evaluate(
        """
        () => {
          const style = getComputedStyle(document.body);
          return {
            hasDarkClass: document.body.classList.contains('tg-theme-dark'),
            bgColor: style.backgroundColor,
          };
        }
        """
    )

    assert result["hasDarkClass"] is True, "body.tg-theme-dark class was not set"
    # --bg in dark mode is #1a1512 = rgb(26,21,18); just verify it's not bright white
    bg = result["bgColor"]
    # rgb values for a dark background have all channels < 100
    import re
    channels = [int(v) for v in re.findall(r"\d+", bg)[:3]]
    assert all(c < 100 for c in channels), (
        f"Expected dark background on body in tg-theme-dark, got: {bg}"
    )
    assert js_errors == [], f"JS errors when applying tg-theme-dark: {js_errors}"


def test_dark_theme_storyboard_and_section_accent_use_dark_backgrounds(page):
    """After CSS fix: .storyboard-frame and .section-accent must render with
    dark surface colors (not hardcoded near-white) when tg-theme-dark is active."""
    _open_reels_detail_from_drafts(page)

    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(80)

    styles = page.evaluate(
        """
        () => {
          const frame = document.querySelector('.storyboard-frame');
          const sectionAccent = document.querySelector('.section-accent');
          const frameStyle = frame ? getComputedStyle(frame) : null;
          const accentStyle = sectionAccent ? getComputedStyle(sectionAccent) : null;
          return {
            frameBg: frameStyle ? frameStyle.backgroundImage || frameStyle.backgroundColor : null,
            accentBg: accentStyle ? accentStyle.backgroundImage || accentStyle.backgroundColor : null,
          };
        }
        """
    )

    # storyboard-frame must have a gradient background (dark surface gradient)
    assert styles["frameBg"] is not None, ".storyboard-frame not found in reels detail"
    assert "gradient" in styles["frameBg"], (
        f".storyboard-frame should have gradient background in dark mode, got: {styles['frameBg']}"
    )

    # section-accent must not use the old near-white rgba(255,255,255,...) background
    if styles["accentBg"] is not None:
        assert "rgba(255, 255, 255" not in styles["accentBg"] and "rgba(255,255,255" not in styles["accentBg"], (
            f".section-accent should not have near-white background in dark mode, got: {styles['accentBg']}"
        )
