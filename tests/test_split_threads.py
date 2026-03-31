"""Tests for split_threads_posts, _extract_why_it_works, and _strip_format_labels."""
from bot.agents.content import (
    split_threads_posts, _extract_why_it_works, _strip_format_labels, _THREADS_MAX_WORDS,
    SERIES_TEMPLATES, _detect_template_from_caption, pick_series_template,
    build_dynamic_slots,
)


def test_extract_why_it_works_present():
    text = "Some post text here.\nParagraph two.\nПОЧЕМУ ЭТО СРАБОТАЕТ: Because it hooks."
    cleaned, why = _extract_why_it_works(text)
    assert why == "Because it hooks."
    assert "ПОЧЕМУ ЭТО СРАБОТАЕТ" not in cleaned
    assert cleaned == "Some post text here.\nParagraph two."


def test_extract_why_it_works_missing():
    text = "Some post text here."
    cleaned, why = _extract_why_it_works(text)
    assert why == ""
    assert cleaned == text


def test_extract_why_it_works_lowercase():
    text = "Post text.\nПочему это сработает: it's relatable"
    cleaned, why = _extract_why_it_works(text)
    assert why == "it's relatable"
    assert "Почему это сработает" not in cleaned


def test_split_threads_posts_with_annotations():
    caption = """УТРО
Post one morning text.
ПОЧЕМУ ЭТО СРАБОТАЕТ: Provokes discussion.

ДЕНЬ
Post two day text.
ПОЧЕМУ ЭТО СРАБОТАЕТ: Practical value.

ВЕЧЕР
Post three evening text.
ПОЧЕМУ ЭТО СРАБОТАЕТ: Emotional connection."""

    posts = split_threads_posts(caption)
    assert len(posts) == 3

    assert posts[0]["slot"] == "morning"
    assert posts[0]["text"] == "Post one morning text."
    assert posts[0]["why_it_works"] == "Provokes discussion."

    assert posts[1]["slot"] == "day"
    assert posts[1]["text"] == "Post two day text."
    assert posts[1]["why_it_works"] == "Practical value."

    assert posts[2]["slot"] == "evening"
    assert posts[2]["text"] == "Post three evening text."
    assert posts[2]["why_it_works"] == "Emotional connection."


def test_split_threads_posts_without_annotations():
    """Backward compatibility — old format without why_it_works."""
    caption = """УТРО
Morning text here.

ДЕНЬ
Day text here.

ВЕЧЕР
Evening text here."""

    posts = split_threads_posts(caption)
    assert len(posts) == 3
    assert posts[0]["why_it_works"] == ""
    assert posts[1]["why_it_works"] == ""
    assert posts[2]["why_it_works"] == ""
    assert posts[0]["text"] == "Morning text here."


def test_split_threads_default_times():
    caption = "УТРО\na\nДЕНЬ\nb\nВЕЧЕР\nc"
    posts = split_threads_posts(caption)
    assert posts[0]["default_time"] == "09:00"
    assert posts[1]["default_time"] == "13:00"
    assert posts[2]["default_time"] == "19:00"


def test_threads_max_words_limit_is_120():
    assert _THREADS_MAX_WORDS == 120


def test_strip_format_labels_hot_take():
    result = _strip_format_labels("(Hot Take)\n\nАроматерапия не лечит...")
    assert "(Hot Take)" not in result
    assert "Ароматерапия не лечит..." in result


def test_strip_format_labels_multiple():
    text = "(Thread) Some text (Список) more text"
    result = _strip_format_labels(text)
    assert "(Thread)" not in result
    assert "(Список)" not in result
    assert "Some text" in result


def test_strip_format_labels_preserves_normal_parens():
    text = "Ароматерапия (и звукотерапия) помогает"
    assert _strip_format_labels(text) == text


def test_split_threads_strips_format_labels():
    caption = """УТРО
(Hot Take)

Ароматерапия не лечит...
ПОЧЕМУ ЭТО СРАБОТАЕТ: Провоцирует дискуссию.

ДЕНЬ
(Список) Три масла на каждый день.

ВЕЧЕР
Вечерний пост."""
    posts = split_threads_posts(caption)
    assert "(Hot Take)" not in posts[0]["text"]
    assert "Ароматерапия не лечит..." in posts[0]["text"]
    assert "(Список)" not in posts[1]["text"]
    assert "Три масла на каждый день." in posts[1]["text"]


def test_platform_rules_have_hard_limit():
    from bot.agents.platform_rules import WRITER_PLATFORM_RULES
    for key in ("threads_series",):
        rules = WRITER_PLATFORM_RULES[key]
        assert "HARD LIMIT" in rules, f"Writer rules for {key} must have HARD LIMIT"
        assert "80" in rules


# ── Series template tests ─────────────────────────────────────────────────

def test_series_templates_have_required_keys():
    for key, tpl in SERIES_TEMPLATES.items():
        assert "name" in tpl, f"Template {key} missing 'name'"
        assert "slots" in tpl, f"Template {key} missing 'slots'"
        assert "default_times" in tpl, f"Template {key} missing 'default_times'"
        assert len(tpl["slots"]) >= 3, f"Template {key} must have at least 3 slots"
        for slot in tpl["slots"]:
            assert "slot" in slot
            assert "label" in slot
            assert "marker" in slot
            assert "icon" in slot
            assert "desc" in slot


def test_pick_series_template_returns_valid():
    tpl = pick_series_template()
    assert "name" in tpl
    assert "slots" in tpl
    assert len(tpl["slots"]) >= 3


def test_split_myth_reality_template():
    caption = """МИФ
Эфирные масла лечат всё.
ПОЧЕМУ ЭТО СРАБОТАЕТ: Разрушает миф.

РЕАЛЬНОСТЬ
На самом деле масла поддерживают состояние.

ПРАКТИКА
Попробуй лаванду перед сном."""

    posts = split_threads_posts(caption)
    assert len(posts) == 3
    assert posts[0]["slot"] == "myth"
    assert posts[0]["label"] == "МИФ"
    assert "лечат" in posts[0]["text"]
    assert posts[1]["slot"] == "reality"
    assert posts[2]["slot"] == "practice"


def test_split_problem_solution_template():
    caption = """ПРОБЛЕМА
Ты не можешь уснуть уже третий день.

РАЗБОР
Кортизол остаётся высоким к вечеру.

ДЕЙСТВИЕ
Капни лаванду на подушку."""

    posts = split_threads_posts(caption)
    assert len(posts) == 3
    assert posts[0]["slot"] == "problem"
    assert posts[1]["slot"] == "analysis"
    assert posts[2]["slot"] == "action"


def test_split_story_arc_template():
    caption = """ЗАВЯЗКА
Клиентка пришла и сказала: я не верю в масла.

ПОВОРОТ
Через 20 минут она плакала, но не от грусти.

ВЫВОД
Иногда тело знает лучше головы."""

    posts = split_threads_posts(caption)
    assert len(posts) == 3
    assert posts[0]["slot"] == "setup"
    assert posts[1]["slot"] == "twist"
    assert posts[2]["slot"] == "takeaway"


def test_detect_template_from_caption_myth():
    caption = "МИФ\ntext\nРЕАЛЬНОСТЬ\ntext\nПРАКТИКА\ntext"
    tpl = _detect_template_from_caption(caption)
    assert tpl["name"] == "Миф / Реальность / Практика"


def test_detect_template_from_caption_default():
    caption = "УТРО\ntext\nДЕНЬ\ntext\nВЕЧЕР\ntext"
    tpl = _detect_template_from_caption(caption)
    assert tpl["name"] == "Утро / День / Вечер"


def test_detect_template_fallback_to_time_of_day():
    caption = "Some random text without markers"
    tpl = _detect_template_from_caption(caption)
    assert tpl["name"] == "Утро / День / Вечер"


def test_split_with_explicit_template():
    tpl = SERIES_TEMPLATES["myth_reality"]
    caption = """МИФ
Масла это ерунда.

РЕАЛЬНОСТЬ
Это инструмент.

ПРАКТИКА
Попробуй сам."""
    posts = split_threads_posts(caption, template=tpl)
    assert posts[0]["slot"] == "myth"
    assert posts[0]["icon"] == "x-circle"
    assert posts[1]["icon"] == "check-circle"
    assert posts[2]["icon"] == "hand"


# ── Dynamic slots tests ──────────────────────────────────────────────────

def test_build_dynamic_slots_3():
    tpl = SERIES_TEMPLATES["time_of_day"]
    slots, times = build_dynamic_slots(3, tpl)
    assert len(slots) == 3
    assert len(times) == 3
    assert slots[0]["slot"] == "morning"
    assert slots[1]["slot"] == "day"
    assert slots[2]["slot"] == "evening"


def test_build_dynamic_slots_5():
    tpl = SERIES_TEMPLATES["myth_reality"]
    slots, times = build_dynamic_slots(5, tpl)
    assert len(slots) == 5
    # First 3 slots come from template
    assert slots[0]["slot"] == "myth"
    assert slots[1]["slot"] == "reality"
    assert slots[2]["slot"] == "practice"
    # Extra slots are numbered
    assert slots[3]["slot"] == "post_4"
    assert slots[4]["slot"] == "post_5"
    assert slots[3]["label"] == "ПОСТ 4"
    assert "desc" in slots[3]
    # All have times
    for s in slots:
        assert s["slot"] in times


def test_build_dynamic_slots_8():
    tpl = SERIES_TEMPLATES["story_arc"]
    slots, times = build_dynamic_slots(8, tpl)
    assert len(slots) == 8
    assert slots[0]["slot"] == "setup"
    assert slots[7]["slot"] == "post_8"
    # Times spread across day
    first_time = times[slots[0]["slot"]]
    last_time = times[slots[-1]["slot"]]
    assert first_time < last_time


def test_build_dynamic_slots_times_spread():
    tpl = SERIES_TEMPLATES["time_of_day"]
    slots, times = build_dynamic_slots(6, tpl)
    time_values = sorted(times.values())
    assert time_values[0].startswith("09")
    # All times unique
    assert len(set(time_values)) == 6


def test_split_dynamic_posts():
    """Test that split_threads_posts works with dynamic N-post templates."""
    tpl = SERIES_TEMPLATES["myth_reality"]
    dyn_slots, dyn_times = build_dynamic_slots(5, tpl)
    dyn_template = {"name": tpl["name"], "slots": dyn_slots, "default_times": dyn_times}

    caption = """МИФ
Масла лечат.

РЕАЛЬНОСТЬ
Нет, поддерживают.

ПРАКТИКА
Лаванда перед сном.

ПОСТ 4
Ещё один факт.

ПОСТ 5
Финальный вывод."""

    posts = split_threads_posts(caption, template=dyn_template)
    assert len(posts) == 5
    assert posts[0]["slot"] == "myth"
    assert posts[3]["slot"] == "post_4"
    assert "факт" in posts[3]["text"]
    assert posts[4]["slot"] == "post_5"
