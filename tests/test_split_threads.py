"""Tests for split_threads_posts and _extract_why_it_works."""
from bot.agents.content import split_threads_posts, _extract_why_it_works, _THREADS_MAX_WORDS


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


def test_platform_rules_have_hard_limit():
    from bot.agents.platform_rules import WRITER_PLATFORM_RULES
    for key in ("threads_series",):
        rules = WRITER_PLATFORM_RULES[key]
        assert "HARD LIMIT" in rules, f"Writer rules for {key} must have HARD LIMIT"
        assert "80" in rules
