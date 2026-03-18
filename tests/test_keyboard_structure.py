"""Keyboard structure validation tests.

Verifies that all InlineKeyboard builders in the project produce valid keyboards:
- callback_data is not empty
- callback_data values are unique within a keyboard
- button text is not empty
- no more than 8 buttons per row (Telegram limit)
- total buttons are reasonable (< 100)
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Keyboard builders that take no arguments
# ---------------------------------------------------------------------------

NO_ARG_KEYBOARDS = [
    ("content._goals_keyboard", "bot.handlers.content", "_goals_keyboard"),
    ("content._formats_keyboard", "bot.handlers.content", "_formats_keyboard"),
    ("content._draft_keyboard", "bot.handlers.content", "_draft_keyboard"),
    ("content._source_keyboard", "bot.handlers.content", "_source_keyboard"),
    ("carousel._source_keyboard", "bot.handlers.carousel", "_source_keyboard"),
    ("carousel._action_buttons_no_images", "bot.handlers.carousel", "_action_buttons_no_images"),
    ("carousel._canva_buttons", "bot.handlers.carousel", "_canva_buttons"),
    ("reels._review_keyboard", "bot.handlers.reels", "_review_keyboard"),
    ("adapter._platforms_keyboard", "bot.handlers.adapter", "_platforms_keyboard"),
    ("keywords._main_kb", "bot.handlers.keywords", "_main_kb"),
    ("threads_manager.publish_threads_keyboard", "bot.handlers.threads_manager", "publish_threads_keyboard"),
]


def _import_keyboard_func(module_path: str, func_name: str):
    """Dynamically import a keyboard builder function."""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


def _validate_keyboard(kb) -> list[str]:
    """Return list of issues found in the keyboard, empty if valid."""
    issues = []
    all_datas = []
    total_buttons = 0

    for row_idx, row in enumerate(kb.inline_keyboard):
        if len(row) > 8:
            issues.append(f"Row {row_idx}: {len(row)} buttons (max 8)")

        for btn in row:
            total_buttons += 1

            # Button text must not be empty
            if not btn.text or not btn.text.strip():
                issues.append(f"Row {row_idx}: empty button text")

            # Must have either callback_data or url
            if btn.callback_data:
                if not btn.callback_data.strip():
                    issues.append(f"Row {row_idx}: empty callback_data")
                all_datas.append(btn.callback_data)
            elif btn.url:
                pass  # URL buttons are OK without callback_data
            elif btn.web_app:
                pass  # WebApp buttons OK
            else:
                issues.append(f"Row {row_idx}: button '{btn.text}' has no callback_data or url")

    # Check uniqueness of callback_data
    seen = set()
    for d in all_datas:
        if d in seen:
            issues.append(f"Duplicate callback_data: {d}")
        seen.add(d)

    if total_buttons >= 100:
        issues.append(f"Too many buttons: {total_buttons}")

    return issues


# ---------------------------------------------------------------------------
# Parametrized test for no-arg keyboards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,module_path,func_name",
    NO_ARG_KEYBOARDS,
    ids=[k[0] for k in NO_ARG_KEYBOARDS],
)
def test_keyboard_structure_no_args(label, module_path, func_name):
    func = _import_keyboard_func(module_path, func_name)
    kb = func()
    issues = _validate_keyboard(kb)
    assert not issues, f"Keyboard {label} has issues:\n" + "\n".join(issues)


# ---------------------------------------------------------------------------
# Keyboards that take topics list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,module_path,func_name",
    [
        ("content._topics_keyboard", "bot.handlers.content", "_topics_keyboard"),
        ("carousel._topics_keyboard", "bot.handlers.carousel", "_topics_keyboard"),
        ("reels._topics_keyboard", "bot.handlers.reels", "_topics_keyboard"),
        ("threads._topics_keyboard", "bot.handlers.threads", "_topics_keyboard"),
    ],
    ids=["content", "carousel", "reels", "threads"],
)
def test_topics_keyboard_structure(label, module_path, func_name):
    func = _import_keyboard_func(module_path, func_name)
    topics = [f"Topic {i}" for i in range(10)]
    kb = func(topics)
    issues = _validate_keyboard(kb)
    assert not issues, f"Keyboard {label} has issues:\n" + "\n".join(issues)


# ---------------------------------------------------------------------------
# Keyboards with integer arguments
# ---------------------------------------------------------------------------

def test_carousel_text_review_keyboard():
    from bot.handlers.carousel import _text_review_keyboard
    kb = _text_review_keyboard(6)
    issues = _validate_keyboard(kb)
    assert not issues, f"Issues:\n" + "\n".join(issues)


def test_carousel_review_keyboard():
    from bot.handlers.carousel import _review_keyboard
    kb = _review_keyboard(6, has_failed=False)
    issues = _validate_keyboard(kb)
    assert not issues

    kb_with_failed = _review_keyboard(6, has_failed=True)
    issues = _validate_keyboard(kb_with_failed)
    assert not issues


def test_carousel_slide_actions_keyboard():
    from bot.handlers.carousel import _slide_actions_keyboard
    for idx in range(6):
        kb = _slide_actions_keyboard(idx)
        issues = _validate_keyboard(kb)
        assert not issues, f"Slide {idx} issues:\n" + "\n".join(issues)


def test_carousel_pptx_button():
    from bot.handlers.carousel import _pptx_from_my_images_button
    kb = _pptx_from_my_images_button(3)
    issues = _validate_keyboard(kb)
    assert not issues


def test_threads_manager_suggestions_keyboard():
    from bot.handlers.threads_manager import _suggestions_keyboard
    kb = _suggestions_keyboard(5)
    issues = _validate_keyboard(kb)
    assert not issues


def test_threads_manager_reply_actions_keyboard():
    from bot.handlers.threads_manager import _reply_actions_keyboard
    for idx in range(3):
        kb = _reply_actions_keyboard(idx)
        issues = _validate_keyboard(kb)
        assert not issues, f"Reply {idx} issues:\n" + "\n".join(issues)


def test_keywords_topics_kb():
    from bot.handlers.keywords import _topics_kb
    kb = _topics_kb("add")
    issues = _validate_keyboard(kb)
    assert not issues


def test_keywords_fields_kb():
    from bot.handlers.keywords import _fields_kb
    kb = _fields_kb(0)
    issues = _validate_keyboard(kb)
    assert not issues


def test_drafts_feedback_keyboard():
    from bot.handlers.drafts import _feedback_keyboard
    kb = _feedback_keyboard("test-draft-id", "")
    issues = _validate_keyboard(kb)
    assert not issues


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_topics_keyboard():
    """Topics keyboard with 0 topics should still be valid."""
    from bot.handlers.content import _topics_keyboard
    kb = _topics_keyboard([])
    issues = _validate_keyboard(kb)
    assert not issues


def test_single_topic_keyboard():
    """Topics keyboard with 1 topic."""
    from bot.handlers.content import _topics_keyboard
    kb = _topics_keyboard(["Single topic"])
    issues = _validate_keyboard(kb)
    assert not issues
    # Should have 1 topic button + refresh button
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(all_buttons) == 2
