"""Drafts: list, detail, search, content review."""
from __future__ import annotations

import json

from .helpers import WCAG_AA_MIN, contrast_ratio, parse_rgb


def test_filter_panel_layout_no_overflow(page):
    """Filter selects stay within viewport and labels stack vertically."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.locator("#filtersToggleBtn").click()
    page.wait_for_timeout(100)

    metrics = page.evaluate(
        """
        () => {
            const vw = window.innerWidth;
            const body = document.getElementById('filtersBody');
            if (!body) return { error: 'filtersBody not found' };
            const bodyRect = body.getBoundingClientRect();
            const labels = [...body.querySelectorAll('label')];
            const results = labels.map(l => {
                const rect = l.getBoundingClientRect();
                const sel = l.querySelector('select, input');
                const selRect = sel ? sel.getBoundingClientRect() : null;
                return {
                    text: l.textContent.trim().slice(0, 20),
                    right: Math.round(rect.right),
                    labelTop: Math.round(rect.top),
                    selectTop: selRect ? Math.round(selRect.top) : null,
                };
            });
            const count = document.getElementById('draftCount');
            const countRect = count ? count.getBoundingClientRect() : null;
            return {
                vw,
                bodyRight: Math.round(bodyRect.right),
                labels: results,
                countRight: countRect ? Math.round(countRect.right) : null,
                countClipped: countRect ? countRect.right > vw : null,
            };
        }
        """
    )

    assert "error" not in metrics, metrics.get("error")
    vw = metrics["vw"]

    # Filter body should not overflow viewport
    assert metrics["bodyRight"] <= vw + 2, (
        f"Filter body overflows viewport: right={metrics['bodyRight']}px > vw={vw}px"
    )

    # Each label's select should be below the label text (column layout)
    for lbl in metrics["labels"]:
        if lbl["selectTop"] is not None:
            assert lbl["selectTop"] >= lbl["labelTop"], (
                f"Filter '{lbl['text']}': select not below label text"
            )

    # Draft count should not be clipped
    if metrics["countClipped"] is not None:
        assert not metrics["countClipped"], "Draft count is clipped by viewport"


def test_draft_search_empty_state_offers_guidance(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    # Expand collapsed filters to access the search field
    page.locator("#filtersToggleBtn").click()
    page.wait_for_timeout(100)
    page.locator("#queryFilter").fill("совсем-нет-такой-темы")
    # Search has a 300ms debounce — wait for API round-trip too
    page.locator("#emptyState .guided-state").wait_for(state="visible", timeout=3000)

    assert page.get_by_text("Ничего не найдено").is_visible()
    assert page.get_by_role("button", name="Открыть создание").is_visible()


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
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(100)

    page.locator("#contentCaptionField").fill("Обновленный текст для Threads.")
    page.locator("#contentEditorNotesField").fill("Сделать подачу мягче.")
    page.get_by_role("button", name="Сохранить версию").click()
    page.wait_for_timeout(100)

    assert page.locator("#contentEditorNotesField").input_value() == "Сделать подачу мягче."
    assert page.get_by_text("Откликнулось").count() >= 1

    page.get_by_role("button", name="Уточнить через AI").click()
    page.wait_for_timeout(100)
    assert page.locator("#contentCaptionField").input_value() == "Отполированный текст для Threads."

    page.get_by_role("button", name="Не дало результата").click()
    page.wait_for_timeout(100)
    assert page.get_by_text("Не дало результата").count() >= 1


def test_content_review_detail_highlights_editor_focus_and_summary(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(100)

    metrics = page.evaluate(
        """
        () => {
          const hero = document.querySelector('.detail-hero');
          const metaChips = document.querySelectorAll('.meta-chip').length;
          const caption = (document.querySelector('#contentCaptionField')?.value || '').trim();
          const captionRect = document.querySelector('#contentCaptionField')?.getBoundingClientRect();
          const notesRect = document.querySelector('#contentEditorNotesField')?.getBoundingClientRect();
          return {
            hasHero: Boolean(hero),
            metaChips,
            captionLength: caption.length,
            captionHeight: captionRect ? Math.round(captionRect.height) : 0,
            notesHeight: notesRect ? Math.round(notesRect.height) : 0,
          };
        }
        """
    )

    assert metrics["hasHero"] is True
    assert metrics["metaChips"] >= 1
    assert metrics["captionLength"] >= 20
    assert metrics["captionHeight"] > metrics["notesHeight"]


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
    page.wait_for_timeout(100)
    page.get_by_role("heading", name="Карусель").click()
    page.locator("textarea[name='topic']").fill("Тестовая карусель")
    page.get_by_role("button", name="Собрать карусель").click()
    page.wait_for_timeout(100)

    assert page.locator(".detail-title").inner_text().strip() == "Тестовая карусель"
    assert page.locator(".slide").count() == 2
    assert page.locator("#btnTabInspiration").get_attribute("class")


def test_themed_draft_detail_renders(themed_page):
    """Draft detail view renders with readable text in both themes."""
    themed_page.locator("#btnTabInspiration").click()
    themed_page.wait_for_timeout(100)
    themed_page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    themed_page.wait_for_timeout(100)

    title = themed_page.locator(".detail-title").inner_text().strip()
    assert "Как мягко выйти" in title

    text_color = themed_page.evaluate(
        "() => getComputedStyle(document.querySelector('.detail-title')).color"
    )
    bg_color = themed_page.evaluate(
        "() => getComputedStyle(document.querySelector('#detailPanel')).backgroundColor"
    )
    fg = parse_rgb(text_color)
    bg = parse_rgb(bg_color)
    if fg and bg:
        ratio = contrast_ratio(fg, bg)
        assert ratio >= WCAG_AA_MIN, (
            f"Detail title unreadable: contrast {ratio:.2f} < {WCAG_AA_MIN} "
            f"(color={text_color}, bg={bg_color})"
        )
