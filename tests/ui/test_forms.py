"""Forms: create, settings, keywords."""
from __future__ import annotations

import json

from .helpers import click_bottom_tab, click_draft_card


def test_create_tab_uses_guided_empty_state_before_tool_selection(desktop_page):
    # "Создать" tab removed from strip; navigate via URL param
    base = desktop_page.url.split("?")[0]
    desktop_page.goto(f"{base}?tab=create", wait_until="domcontentloaded")
    desktop_page.wait_for_selector("body.app-ready", timeout=10000)
    desktop_page.locator(".guided-state").wait_for(state="visible", timeout=5000)

    assert desktop_page.locator(".guided-state").is_visible()
    assert desktop_page.get_by_text("Выберите формат для старта").is_visible()
    assert desktop_page.get_by_text("быстрые сценарии для контента, рилса, плана недели и карусели").is_visible()


def test_create_tool_selection_isolates_form(page):
    click_bottom_tab(page, "#btnTabCreate")

    page.get_by_role("heading", name="Карусель").click()
    page.get_by_role("heading", name="Создать карусель").wait_for(state="visible", timeout=5000)

    assert page.get_by_role("heading", name="Создать карусель").is_visible()
    assert page.get_by_role("heading", name="Создать контент").count() == 0

    if page.locator(".back-button").is_visible():
        page.locator(".back-button").click()
        page.locator(".create-card").first.wait_for(state="visible", timeout=5000)
        assert page.locator("#topbarTitle").evaluate("(el) => el.textContent.trim()") == "Инструменты"
        assert page.locator(".create-card").count() >= 2


def test_settings_and_keywords_use_guided_detail_copy(desktop_page):
    desktop_page.evaluate("window.openSettingsSection('status')")
    desktop_page.get_by_role("heading", name="Источники данных").wait_for(state="visible", timeout=5000)
    assert desktop_page.get_by_role("heading", name="Источники данных").is_visible()

    desktop_page.evaluate("window.openSettingsSection('brand')")
    desktop_page.get_by_role("heading", name="Бренд и ключи").wait_for(state="visible", timeout=5000)
    assert desktop_page.get_by_role("heading", name="Бренд и ключи").is_visible()


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
    page.wait_for_timeout(500)  # settings section render
    page.evaluate("window.openKeywordTopic(0)")
    page.locator(".keyword-fields").wait_for(state="visible", timeout=5000)

    kw_section = page.locator(".keyword-fields")
    kw_section.locator(".keyword-form input").first.fill("пауза")
    kw_section.get_by_role("button", name="Добавить").first.click()
    page.wait_for_timeout(500)  # wait for notice
    assert page.get_by_text("Ключ добавлен").is_visible()
    assert page.get_by_text("пауза").count() >= 1

    chips_before_delete = kw_section.locator(".keyword-chip").count()
    page.evaluate(
        """
        () => {
          window.Telegram = window.Telegram || {};
          window.Telegram.WebApp = window.Telegram.WebApp || {};
          window.Telegram.WebApp.showConfirm = (_message, callback) => callback(true);
        }
        """
    )
    kw_section.locator(".keyword-chip button").first.click()
    page.wait_for_timeout(500)  # keyword chip removal animation
    assert kw_section.locator(".keyword-chip").count() == chips_before_delete - 1


def test_create_and_detail_forms_show_helper_microcopy(page):
    click_bottom_tab(page, "#btnTabCreate")
    page.get_by_text("Пост для соцсетей").click()
    page.get_by_text("Сформулируйте тему как готовую мысль").wait_for(state="visible", timeout=5000)

    assert page.get_by_text("Сформулируйте тему как готовую мысль").is_visible()
    assert page.get_by_role("button", name="Собрать черновик").is_visible()

    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Как мягко выйти из рабочего напряжения")

    assert page.get_by_text("Сохраняйте версию после смыслового прохода").is_visible()
    assert page.get_by_role("button", name="Согласовать").is_visible()


def test_themed_create_tab_renders(themed_page):
    """Create tab tool selection renders in both themes."""
    click_bottom_tab(themed_page, "#btnTabCreate")
    themed_page.get_by_role("heading", name="Карусель").wait_for(state="visible", timeout=5000)
    assert themed_page.get_by_role("heading", name="Карусель").is_visible()
    assert themed_page.get_by_role("heading", name="Пост для соцсетей").is_visible()
