"""Tests for the aromara.ru article autopilot (bot.services.site_autopilot)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.services import site_autopilot as ap

NOW = datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc)  # Tuesday


def _topics():
    return [
        {"id": "t1", "cluster": "gong_private", "query": "гонг медитация москва",
         "angle": "a", "service": "gong-session-private", "slug": "gong-t1", "slug_en": "gong-t1-en"},
        {"id": "t2", "cluster": "sleep_stress", "query": "q2", "angle": "a",
         "service": "resource-aroma", "slug": "sleep-t2", "slug_en": "sleep-t2-en"},
    ]


def _words(n: int, word: str = "слово") -> str:
    return " ".join([word] * n)


def _article(ru_words=950, en_words=650):
    return {
        "ru": {"slug": "gong-t1", "date": "2026-10-06", "readMinutes": 6,
               "title": "Гонг-медитация в Москве: как проходит сессия",
               "excerpt": "Рассказываю, как проходит индивидуальная гонг-сессия: подготовка, звук, интеграция, и кому она подойдёт. Без обещаний.",
               "sections": [{"body": _words(ru_words)}]},
        "en": {"slug": "gong-t1-en", "date": "2026-10-06", "readMinutes": 4,
               "title": "Gong meditation in Moscow: what a session is like",
               "excerpt": "A walk through a private gong session: preparation, sound, integration, and who it suits. No promises, only what happens.",
               "sections": [{"body": _words(en_words, "word")}]},
        "meta": {"source": "autopilot", "topicId": "t1", "cluster": "gong_private",
                 "generatedAt": "2026-10-06T07:00:00+00:00"},
    }


# --- topic selection / state -------------------------------------------------

def test_pick_next_topic_first_pending():
    assert ap.pick_next_topic(_topics(), {"topics": {}}, now=NOW)["id"] == "t1"


def test_pick_next_topic_skips_done_topics():
    state = {"topics": {"t1": {"status": "published", "week": "2026-W30"}}}
    assert ap.pick_next_topic(_topics(), state, now=NOW)["id"] == "t2"


def test_pick_next_topic_idempotent_within_week():
    state = {"topics": {"t1": {"status": "published", "week": ap.iso_week(NOW)}}}
    assert ap.pick_next_topic(_topics(), state, now=NOW) is None


def test_failed_attempt_this_week_blocks_rerun_but_not_next_week():
    state = {"topics": {"t1": {"status": "failed", "week": ap.iso_week(NOW)}}}
    assert ap.pick_next_topic(_topics(), state, now=NOW) is None
    later = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
    # failed topics are not retried automatically: next pending is chosen
    assert ap.pick_next_topic(_topics(), state, now=later)["id"] == "t2"


def test_forced_topic_ignores_week_guard_but_not_published():
    state = {"topics": {"t1": {"status": "published", "week": ap.iso_week(NOW)}}}
    assert ap.pick_next_topic(_topics(), state, now=NOW, topic_id="t2")["id"] == "t2"
    assert ap.pick_next_topic(_topics(), state, now=NOW, topic_id="t1") is None


def test_state_roundtrip_atomic(tmp_path):
    p = tmp_path / "state.json"
    assert ap.load_state(p) == {"topics": {}}
    st = ap.load_state(p)
    ap.mark_topic(st, "t1", "published", now=NOW, slug="x")
    ap.save_state(st, p)
    assert not list(tmp_path.glob("*.tmp"))
    assert ap.load_state(p)["topics"]["t1"]["status"] == "published"


def test_backlog_file_is_valid():
    topics = ap.load_topics()
    assert len(topics) >= 40
    ids = [t["id"] for t in topics]
    slugs = [t["slug"] for t in topics] + [t["slug_en"] for t in topics]
    assert len(set(ids)) == len(ids)
    assert len(set(slugs)) == len(slugs)
    facts = ap.load_facts()
    assert not set(slugs) & set(facts["existing_slugs"])
    for t in topics:
        assert ap.SLUG_RE.match(t["slug"]) and ap.SLUG_RE.match(t["slug_en"])
        assert t["query"] and t["cluster"] and t["service"] in facts["services"]


# --- stoplist -----------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Это важно — очень",
    "Безусловно, это работает",
    "Таким образом, всё просто",
    "В заключение скажу",
    "Стоит отметить, что",
    "Погрузитесь в мир звука",
    "Гонг лечит бессонницу",
    "Метод исцеляет тело",
    "Мы гарантируем результат",
    "Это поможет поставить диагноз",
    "Раскройте потенциал команды",
])
def test_stoplist_ru_catches(text):
    assert ap.stoplist_violations(text, "ru")


def test_stoplist_ru_clean_text_passes():
    assert ap.stoplist_violations("Аромодиагностика: тестируем масла и смотрим на реакции.", "ru") == []


@pytest.mark.parametrize("text", [
    "This will cure insomnia", "It heals the body", "We guarantee results",
    "A wrong — dash", "In conclusion, it works",
])
def test_stoplist_en_catches(text):
    assert ap.stoplist_violations(text, "en")


@pytest.mark.parametrize("text", ["<b>bold</b>", "**жирный**", "# Заголовок", "- пункт списка", "[ссылка](http://x)"])
def test_stoplist_markup(text):
    assert ap.stoplist_violations(text, "ru")


def test_fact_check_flags_unknown_price():
    facts = ap.load_facts()
    assert ap.fact_violations("Сессия стоит 1 234 ₽ и всё.", facts)
    assert ap.fact_violations("Сессия стоит от 8 000 ₽.", facts) == []


# --- validator ----------------------------------------------------------------

def test_validate_ok():
    assert ap.validate_article(_article(), existing_slugs=set()) == []


def test_validate_lengths_and_slug():
    a = _article(ru_words=500, en_words=100)
    a["ru"]["title"] = "т" * 61
    a["ru"]["excerpt"] = "коротко"
    a["ru"]["slug"] = "Bad Slug"
    errs = " ".join(ap.validate_article(a, existing_slugs=set()))
    assert "title" in errs and "excerpt" in errs and "slug" in errs and "words" in errs


def test_validate_slug_must_be_unique():
    assert any("exists" in e for e in ap.validate_article(_article(), existing_slugs={"gong-t1"}))


def test_validate_rejects_em_dash_and_markup_in_body():
    a = _article()
    a["ru"]["sections"][0]["body"] += " тест — тест"
    a["en"]["sections"][0]["body"] += " <b>x</b>"
    errs = ap.validate_article(a, existing_slugs=set())
    assert len(errs) >= 2


# --- atomic write ---------------------------------------------------------------

def test_write_article_atomic(tmp_path):
    path = ap.write_article(_article(), tmp_path)
    assert path == tmp_path / "blog" / "gong-t1.json"
    assert json.loads(path.read_text())["ru"]["slug"] == "gong-t1"
    assert not list((tmp_path / "blog").glob("*.tmp"))


def test_write_article_failure_leaves_no_partial(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(ap.os, "replace", boom)
    with pytest.raises(OSError):
        ap.write_article(_article(), tmp_path)
    assert not list((tmp_path / "blog").glob("*"))


# --- draft parsing -----------------------------------------------------------------

def test_parse_draft():
    raw = "TITLE: Заголовок\nEXCERPT: Анонс\n\nВступление.\n\n@@ Раздел один\nТекст один.\n\nЕщё абзац.\n@@ Раздел два\nТекст два."
    d = ap.parse_draft(raw)
    assert d["title"] == "Заголовок" and d["excerpt"] == "Анонс"
    assert d["sections"][0] == {"body": "Вступление."}
    assert d["sections"][1]["heading"] == "Раздел один"
    assert d["sections"][1]["body"] == "Текст один.\n\nЕщё абзац."
    assert len(d["sections"]) == 3


def test_parse_draft_garbage_returns_none():
    assert ap.parse_draft("нет полей") is None


# --- pipeline with mocked LLM/HTTP ----------------------------------------------------

def _draft_text(words, lang="ru", dash=False):
    w = "слово" if lang == "ru" else "word"
    title = "Гонг в Москве: как проходит сессия" if lang == "ru" else "Gong in Moscow: how a session goes"
    excerpt = ("Рассказываю, как проходит индивидуальная гонг-сессия: подготовка, звук, интеграция, и кому она подойдёт. Без обещаний."
               if lang == "ru" else
               "A walk through a private gong session: preparation, sound, integration, and who it suits. No promises, only what happens.")
    body = " ".join([w] * words) + (" тест — тест" if dash else "")
    return f"TITLE: {title}\nEXCERPT: {excerpt}\n\n{body}\n\n@@ Раздел\n{body}"


class Env:
    def __init__(self, tmp_path, monkeypatch, *, ru_dash_always=False, verify_status=200, med_ok=True):
        self.calls = {"llm": [], "post": [], "get": [], "tg": [], "indexnow": []}
        self.ru_dash_always = ru_dash_always
        self.verify_status = verify_status
        self.med_ok = med_ok
        self.tmp = tmp_path
        monkeypatch.setenv("SITE_CONTENT_DIR", str(tmp_path / "content"))
        monkeypatch.setenv("REVALIDATE_SECRET", "s3cret")
        monkeypatch.setattr(ap, "STATE_PATH", tmp_path / "state.json")
        monkeypatch.setattr(ap, "load_topics", lambda *a, **k: _topics())
        monkeypatch.setattr(ap, "call_llm", self.llm)
        monkeypatch.setattr(ap, "medical_review", self.med)
        monkeypatch.setattr(ap, "guardian_signal", lambda text: {"passed": True, "score": 0.9})
        monkeypatch.setattr(ap, "http_post", self.post)
        monkeypatch.setattr(ap, "http_get_status", self.get)
        monkeypatch.setattr(ap, "send_group_message", lambda text: self.calls["tg"].append(text))
        monkeypatch.setattr(ap, "ping_indexnow", lambda urls: self.calls["indexnow"].append(urls))
        monkeypatch.setattr(ap, "_sleep", lambda s: None)

    def llm(self, *, system, user, max_tokens, context):
        self.calls["llm"].append(context)
        ru_title = "Гонг в Москве: как проходит сессия"
        ru_exc = ("Рассказываю, как проходит индивидуальная гонг-сессия: подготовка, звук, интеграция, и кому она подойдёт. Без обещаний.")
        en_exc = ("A walk through a private gong session: preparation, sound, integration, and who it suits. No promises, only what happens.")
        if context == "site_autopilot/plan_ru":
            return f"TITLE: {ru_title}\nEXCERPT: {ru_exc}\n" + "".join(f"@@ Раздел {i}\n" for i in range(1, 7))
        if context == "site_autopilot/section_ru":
            return _words(150) + (" тест — тест" if self.ru_dash_always else "")
        if context == "site_autopilot/rewrite_ru":
            return _words(150) + (" тест — тест" if self.ru_dash_always else "")
        if context == "site_autopilot/header_en":
            return f"TITLE: Gong in Moscow: how a session goes\nEXCERPT: {en_exc}"
        if context == "site_autopilot/headings_en":
            return "\n".join(f"Section {i}" for i in range(1, 7))
        return _words(110, "word")  # section_en / rewrite_en

    def med(self, text, cluster):
        return {"passed": self.med_ok, "issues": [] if self.med_ok else ["medical claim"]}

    def post(self, url, *, json_body, headers):
        self.calls["post"].append((url, json_body, headers))
        return 200

    def get(self, url):
        self.calls["get"].append(url)
        return self.verify_status


def test_pipeline_success(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "published"
    f = tmp_path / "content" / "blog" / "gong-t1.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert data["meta"]["source"] == "autopilot" and data["meta"]["topicId"] == "t1"
    url, body, headers = env.calls["post"][0]
    assert url.endswith("/api/revalidate") and body == {"slug": "gong-t1"}
    assert headers["x-revalidate-secret"] == "s3cret"
    assert env.calls["get"] == ["https://aromara.ru/blog/gong-t1"]
    assert env.calls["indexnow"] and env.calls["tg"]
    assert "https://aromara.ru/blog/gong-t1" in env.calls["tg"][0]
    assert ap.load_state(tmp_path / "state.json")["topics"]["t1"]["status"] == "published"


def test_pipeline_idempotent_second_run(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    ap.run_once(publish=True, now=NOW)
    n = len(env.calls["llm"])
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "skipped" and len(env.calls["llm"]) == n


def test_pipeline_rewrites_section_then_succeeds(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    state = {"first": True}
    orig = env.llm

    def llm(**kw):
        if kw["context"] == "site_autopilot/section_ru" and state["first"]:
            state["first"] = False
            env.calls["llm"].append(kw["context"])
            return _words(150) + " тест — тест"
        return orig(**kw)
    monkeypatch.setattr(ap, "call_llm", llm)
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "published"
    assert env.calls["llm"].count("site_autopilot/rewrite_ru") == 1


def test_pipeline_stoplist_failure_no_file(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, ru_dash_always=True)
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "failed"
    assert not (tmp_path / "content" / "blog").exists() or not list((tmp_path / "content" / "blog").glob("*"))
    assert env.calls["post"] == [] and env.calls["indexnow"] == []
    assert len(env.calls["tg"]) == 1 and "gong-t1" in env.calls["tg"][0]
    st = ap.load_state(tmp_path / "state.json")["topics"]["t1"]
    assert st["status"] == "failed" and st["reason"]
    # every section is rewritten at most twice, and the whole article retried at most twice
    assert env.calls["llm"].count("site_autopilot/rewrite_ru") <= 2 * 7 * 3
    assert env.calls["llm"].count("site_autopilot/plan_ru") == 3


def test_pipeline_medical_review_failure(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, med_ok=False)
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "failed"
    assert not (tmp_path / "content" / "blog" / "gong-t1.json").exists()


def test_pipeline_verify_404_rolls_back(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, verify_status=404)
    res = ap.run_once(publish=True, now=NOW)
    assert res["status"] == "failed"
    assert not (tmp_path / "content" / "blog" / "gong-t1.json").exists()
    assert env.calls["indexnow"] == []
    assert ap.load_state(tmp_path / "state.json")["topics"]["t1"]["status"] == "failed"
    assert env.calls["tg"]


def test_dry_run_has_no_side_effects(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    res = ap.run_once(publish=False, now=NOW, topic_id="t1")
    assert res["status"] == "dry-run" and res["article"]["ru"]["title"]
    assert not (tmp_path / "content").exists()
    assert env.calls["post"] == [] and env.calls["tg"] == []
    assert not (tmp_path / "state.json").exists()


# --- medical review parsing ----------------------------------------------------------

def test_medical_review_prose_is_parse_error(monkeypatch):
    import bot.services.claude_client as cc
    monkeypatch.setattr(cc, "call_claude", lambda **kw: "Всё хорошо, статья честная.")
    r = ap.medical_review("текст", "gong_private")
    assert r["passed"] is False and ap.PARSE_ERROR_ISSUE in r["issues"]


def test_medical_review_json_in_prose(monkeypatch):
    import bot.services.claude_client as cc
    monkeypatch.setattr(cc, "call_claude", lambda **kw: 'Вердикт: {"passed": true, "issues": []} Спасибо')
    assert ap.medical_review("текст", "aroma_diagnostics") == {"passed": True, "issues": []}


def test_env_falls_back_to_dotenv_file(tmp_path, monkeypatch):
    """aroma-bot has no systemd EnvironmentFile: values living only in .env must be visible."""
    from bot.services import site_autopilot as sa

    env = tmp_path / ".env"
    env.write_text("REVALIDATE_SECRET=from-file\nSITE_CONTENT_DIR=/x\n", encoding="utf-8")
    monkeypatch.delenv("REVALIDATE_SECRET", raising=False)
    monkeypatch.setattr(sa, "DOTENV_PATH", env)
    sa._dotenv_cache.clear()
    assert sa._env("REVALIDATE_SECRET") == "from-file"
    monkeypatch.setenv("REVALIDATE_SECRET", "from-env")
    assert sa._env("REVALIDATE_SECRET") == "from-env"
    assert sa._env("MISSING_KEY", "dflt") == "dflt"


def test_scheduler_flag_read_from_dotenv(tmp_path, monkeypatch):
    """The enable flag must also be visible when it lives only in .env."""
    import asyncio
    from bot.services import scheduler, site_autopilot as sa

    env = tmp_path / ".env"
    env.write_text("SITE_AUTOPILOT_ENABLED=1\n", encoding="utf-8")
    monkeypatch.delenv("SITE_AUTOPILOT_ENABLED", raising=False)
    monkeypatch.setattr(sa, "DOTENV_PATH", env)
    sa._dotenv_cache.clear()
    calls = []
    monkeypatch.setattr(sa, "run_once", lambda *a, **k: calls.append(1) or {"status": "skipped"})
    from datetime import datetime as _dt, timezone as _tz

    class _Tue(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 10, 6, 7, 0, tzinfo=_tz.utc)

    monkeypatch.setattr(scheduler, "datetime", _Tue)
    asyncio.run(scheduler._run_site_autopilot())
    assert calls, "autopilot did not run although .env enables it"
