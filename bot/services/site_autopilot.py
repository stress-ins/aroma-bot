"""Autopilot for aromara.ru blog articles.

Pipeline: topic -> RU draft -> checks (stoplist, facts, medical review,
contract validator; up to 2 rewrites) -> EN -> validation -> atomic file write
-> revalidate -> GET page == 200 -> IndexNow -> Telegram. Any failed check
means nothing is published, the topic is marked failed and the group is told.

The deterministic stoplist is the gate. Brand Guardian is an extra signal only.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from dotenv import dotenv_values

# aroma-bot.service has no EnvironmentFile; pydantic Settings reads .env only into
# declared fields, so autopilot keys are looked up here: process env first, then .env.
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_dotenv_cache: dict[str, str | None] = {}


def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    if not _dotenv_cache:
        _dotenv_cache.update(dotenv_values(DOTENV_PATH) if DOTENV_PATH.exists() else {})
        _dotenv_cache.setdefault("__loaded__", "1")
    return _dotenv_cache.get(key) or default

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
TOPICS_PATH = ROOT / "data" / "site_topics.json"
FACTS_PATH = ROOT / "data" / "site_facts.json"
STATE_PATH = ROOT / "data" / "site_autopilot_state.json"

DEFAULT_CONTENT_DIR = "/opt/aromara-content"
DEFAULT_REVALIDATE_URL = "https://aromara.ru/api/revalidate"
DEFAULT_SITE_URL = "https://aromara.ru"
DEFAULT_CHAT_ID = "-5057881804"  # группа «Арома практики»
INDEXNOW_KEY = "5b4453a5ba9543c9b3c2272c958fc566"
INDEXNOW_HOST = "aromara.ru"

SLUG_RE = re.compile(r"^[a-z0-9-]{3,80}$")
MAX_REWRITES = 2
RU_MIN_WORDS, EN_MIN_WORDS = 900, 600
TITLE_MAX = 60
EXCERPT_MIN, EXCERPT_MAX = 110, 160
MSK = ZoneInfo("Europe/Moscow")
PARSE_ERROR_ISSUE = "medical review: ответ не разобран (parse_error)"


# --------------------------------------------------------------------------
# Data, state, topic selection
# --------------------------------------------------------------------------

def load_topics(path: Path | None = None) -> list[dict]:
    return json.loads((path or TOPICS_PATH).read_text(encoding="utf-8"))


def load_facts(path: Path | None = None) -> dict:
    return json.loads((path or FACTS_PATH).read_text(encoding="utf-8"))


def iso_week(now: datetime) -> str:
    y, w, _ = now.astimezone(MSK).isocalendar()
    return f"{y}-W{w:02d}"


def load_state(path: Path | None = None) -> dict:
    p = path or STATE_PATH
    if not p.exists():
        return {"topics": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("topics", {})
        return data
    except (json.JSONDecodeError, OSError):
        logger.error("site_autopilot: corrupt state file %s", p)
        raise


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def save_state(state: dict, path: Path | None = None) -> None:
    _atomic_write(path or STATE_PATH, json.dumps(state, ensure_ascii=False, indent=1))


def mark_topic(state: dict, topic_id: str, status: str, *, now: datetime, **extra: Any) -> None:
    state.setdefault("topics", {})[topic_id] = {
        "status": status, "week": iso_week(now), "updatedAt": now.isoformat(), **extra,
    }


def pick_next_topic(topics: list[dict], state: dict, *, now: datetime,
                    topic_id: str | None = None) -> dict | None:
    done = state.get("topics", {})
    if topic_id:
        t = next((x for x in topics if x["id"] == topic_id), None)
        if t is None or done.get(topic_id, {}).get("status") == "published":
            return None
        return t
    week = iso_week(now)
    if any(v.get("week") == week and v.get("status") in ("published", "failed") for v in done.values()):
        return None  # one attempt per week
    return next((t for t in topics if t["id"] not in done), None)


# --------------------------------------------------------------------------
# Deterministic checks
# --------------------------------------------------------------------------

_RU_CLICHES = [
    r"безусловно", r"таким образом", r"в заключение", r"представляется", r"стоит отметить",
    r"следует подчеркнуть", r"важно отметить", r"уникальн\w+ опыт", r"погруз\w+ в мир",
    r"раскр\w+ потенциал",
]
_RU_MEDICAL = [
    r"\bлечит\w*", r"\bлечен\w*", r"\bлечить\b", r"вылеч\w*", r"излеч\w*", r"исцел\w*",
    r"диагноз\w*", r"гарантир\w*", r"\bгаранти[яию]\w*", r"избавит\w* от (болезн|депресс|бессонниц|тревог)\w*",
    r"заменя\w+ (врач|лекарств|терапи)\w*", r"вместо (врача|лекарств)\w*",
]
_EN_CLICHES = [
    r"in conclusion", r"it is important to note", r"it'?s worth noting", r"\bdelve\b",
    r"unlock (your|the) potential", r"unique experience", r"dive into the world",
]
_EN_MEDICAL = [
    r"\bcures?\b", r"\bcured\b", r"\bcuring\b", r"\bheals?\b", r"\bhealed\b", r"\bhealing\b",
    r"\bdiagnos(e|es|ed|is)\b", r"\bguarantee[sd]?\b", r"\btreats?\b", r"\btreatment\b",
]
_MARKUP = [
    (r"<[a-zA-Z/][^>]*>", "HTML-разметка"),
    (r"\*\*|__", "markdown-выделение"),
    (r"(?m)^\s*#{1,6}\s", "markdown-заголовок"),
    (r"(?m)^\s*[-*•]\s+\S", "маркированный список"),
    (r"`", "обратные кавычки"),
    (r"\[[^\]]+\]\([^)]+\)", "markdown-ссылка"),
]
_PRICE_RE = re.compile(r"(\d[\d\s  ]*)\s*(?:₽|руб|р\.)", re.I)


def stoplist_violations(text: str, lang: str = "ru") -> list[str]:
    out: list[str] = []
    if "—" in text:
        out.append("длинное тире (—)")
    cliches, medical = (_RU_CLICHES, _RU_MEDICAL) if lang == "ru" else (_EN_CLICHES, _EN_MEDICAL)
    low = text.lower()
    for pat in cliches:
        m = re.search(pat, low)
        if m:
            out.append(f"клише: «{m.group(0)}»")
    for pat in medical:
        m = re.search(pat, low)
        if m:
            out.append(f"медицинское обещание: «{m.group(0)}»")
    for pat, label in _MARKUP:
        if re.search(pat, text):
            out.append(label)
    return out


def fact_violations(text: str, facts: dict) -> list[str]:
    allowed = {int(x) for x in facts.get("allowed_prices_rub", [])}
    out = []
    for m in _PRICE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if digits and int(digits) not in allowed:
            out.append(f"цена вне блока фактов: {digits}")
    return out


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def post_text(post: dict) -> str:
    parts = [post.get("title", ""), post.get("excerpt", "")]
    for s in post.get("sections", []):
        parts.append(s.get("heading", "") or "")
        parts.append(s.get("body", "") or "")
    return "\n\n".join(p for p in parts if p)


def body_words(post: dict) -> int:
    return sum(word_count(s.get("body", "")) for s in post.get("sections", []))


def validate_post(post: dict, lang: str, existing_slugs: set[str]) -> list[str]:
    errs: list[str] = []
    slug = post.get("slug", "")
    if not SLUG_RE.match(slug):
        errs.append(f"{lang}: slug invalid: {slug!r}")
    elif slug in existing_slugs:
        errs.append(f"{lang}: slug already exists: {slug}")
    title, excerpt = post.get("title", ""), post.get("excerpt", "")
    if not title or len(title) > TITLE_MAX:
        errs.append(f"{lang}: title length {len(title)} (max {TITLE_MAX})")
    if not (EXCERPT_MIN <= len(excerpt) <= EXCERPT_MAX):
        errs.append(f"{lang}: excerpt length {len(excerpt)} (need {EXCERPT_MIN}-{EXCERPT_MAX})")
    n, need = body_words(post), (RU_MIN_WORDS if lang == "ru" else EN_MIN_WORDS)
    if n < need:
        errs.append(f"{lang}: words {n} (min {need})")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", post.get("date", "")):
        errs.append(f"{lang}: date invalid")
    if not isinstance(post.get("readMinutes"), int) or post["readMinutes"] < 1:
        errs.append(f"{lang}: readMinutes invalid")
    if not post.get("sections"):
        errs.append(f"{lang}: no sections")
    errs += [f"{lang}: {v}" for v in stoplist_violations(post_text(post), lang)]
    return errs


def validate_article(article: dict, *, existing_slugs: set[str]) -> list[str]:
    errs = validate_post(article["ru"], "ru", existing_slugs)
    errs += validate_post(article["en"], "en", existing_slugs)
    return errs


def existing_file_slugs(content_dir: Path) -> set[str]:
    d = content_dir / "blog"
    return {p.stem for p in d.glob("*.json")} if d.exists() else set()


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def write_article(article: dict, content_dir: Path) -> Path:
    path = content_dir / "blog" / f"{article['ru']['slug']}.json"
    _atomic_write(path, json.dumps(article, ensure_ascii=False, indent=2))
    return path


# --------------------------------------------------------------------------
# Draft format
# --------------------------------------------------------------------------

def parse_draft(raw: str) -> dict | None:
    """Parse TITLE:/EXCERPT: header and body; '@@ Heading' starts a section."""
    m_t = re.search(r"(?m)^TITLE:\s*(.+)$", raw)
    m_e = re.search(r"(?m)^EXCERPT:\s*(.+)$", raw)
    if not m_t or not m_e:
        return None
    body = raw[max(m_t.end(), m_e.end()):].strip("\n")
    sections: list[dict] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            s = {"body": text}
            if heading:
                s = {"heading": heading, **s}
            sections.append(s)

    for line in body.splitlines():
        if line.startswith("@@"):
            flush()
            heading, buf = line[2:].strip(), []
        else:
            buf.append(line)
    flush()
    if not sections:
        return None
    return {"title": m_t.group(1).strip(), "excerpt": m_e.group(1).strip(), "sections": sections}


# --------------------------------------------------------------------------
# External calls (module-level so tests can patch them)
# --------------------------------------------------------------------------

def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def call_llm(*, system: str, user: str, max_tokens: int, context: str) -> str:
    from bot.services.claude_client import SONNET, call_claude  # cost_stats logged inside

    return call_claude(
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens, system=system, model=SONNET, context=context,
    )


def medical_review(text: str, cluster: str) -> dict:
    """Medical + domain-expert review. Unparseable reply counts as failure."""
    from bot.agents.brand_guardian import extract_json
    from bot.services.claude_client import SONNET, call_claude

    expert = ("эксперта по звуковым практикам и гонг-медитации" if cluster.startswith("gong")
              else "эксперта по ароматерапии и эфирным маслам")
    instruction = (
        "Ты врач-рецензент и " + expert + ". Ниже статья для сайта аромапрактика. Найди: медицинские "
        "обещания (лечит, исцеляет, снимает диагноз), ложные физиологические утверждения, заявления "
        "о безопасности без оговорок, выдуманные факты о методах. passed=false ТОЛЬКО при прямом "
        "обещании лечения, исцеления, диагноза или гарантии результата, при явно ложном физиологическом "
        "факте или выдуманной услуге/цене. Описание субъективных ощущений («многие отмечают, что "
        "становится спокойнее», «у меня бывает так») допустимо и проблемой не является; стилистику "
        "и недостаток научных ссылок не считай."
    )
    answer = ("\n\nОтветь ОДНИМ JSON-объектом и больше ничем, без пояснений и без markdown, начни "
              "с символа {. Формат: {\"passed\": true, \"issues\": [\"краткое описание\"]}")
    for _ in range(2):
        raw = call_claude(
            messages=[{"role": "user", "content": instruction + "\n\nСТАТЬЯ:\n" + text[:12000] + answer}],
            max_tokens=700, system="", model=SONNET, context="site_autopilot/medical_review")
        obj = extract_json(raw)
        if obj is not None and "passed" in obj:
            return {"passed": bool(obj["passed"]), "issues": [str(i) for i in obj.get("issues", [])]}
    return {"passed": False, "issues": [PARSE_ERROR_ISSUE]}


def guardian_signal(text: str) -> dict:
    """Extra signal only: never blocks publishing."""
    try:
        from bot.agents.brand_guardian import audit_brand_sync

        r = audit_brand_sync(text[:6000], "default")
        return {"passed": bool(r.get("passed")), "score": r.get("score"),
                "violations": [v.get("type") for v in r.get("violations", [])][:5]}
    except Exception as exc:  # noqa: BLE001
        return {"passed": None, "error": str(exc)}


def http_post(url: str, *, json_body: dict, headers: dict) -> int:
    return httpx.post(url, json=json_body, headers=headers, timeout=20).status_code


def http_get_status(url: str) -> int:
    return httpx.get(url, timeout=15, follow_redirects=True).status_code


def send_group_message(text: str) -> None:
    from config import settings

    chat = _env("SITE_AUTOPILOT_CHAT_ID", DEFAULT_CHAT_ID)
    httpx.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
               json={"chat_id": chat, "text": text, "disable_web_page_preview": False},
               timeout=20).raise_for_status()


def ping_indexnow(urls: list[str]) -> None:
    httpx.post("https://api.indexnow.org/indexnow", json={
        "host": INDEXNOW_HOST, "key": INDEXNOW_KEY,
        "keyLocation": f"https://{INDEXNOW_HOST}/{INDEXNOW_KEY}.txt", "urlList": urls,
    }, timeout=20)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def _facts_block(facts: dict, service: str) -> str:
    svc = facts["services"].get(service, {})
    return json.dumps({
        "общие_правила": facts["general_rules"], "автор": facts["author"],
        "образование": facts["credentials"], "связанная_услуга": svc,
        "все_услуги_кратко": {k: f"{v['title']}: {v['meta']}, {v['price']}" for k, v in facts["services"].items()},
        "разрешённые_цены_руб": facts["allowed_prices_rub"],
    }, ensure_ascii=False, indent=1)


def _issues_text(issues: list[str]) -> str:
    return "\n".join(f"- {i}" for i in issues)


_HARD_RULES = (
    "ЖЁСТКИЕ ПРАВИЛА: никаких «—» (длинное тире), используй точку, двоеточие, точку с запятой; "
    "никаких клише (безусловно, таким образом, в заключение, представляется, стоит отметить, следует "
    "подчеркнуть, важно отметить, уникальный опыт, погрузиться в мир, раскрыть потенциал, путешествие, "
    "трансформация, гармония); никаких слов: лечит, исцеляет, диагноз, гарантирует (даже с отрицанием); "
    "не обещай медицинского эффекта, пиши про состояние и ощущения как субъективные («многие отмечают», «у меня бывает так», «может быть»), без утверждений о результате; не называй конкретные звуковые "
    "инструменты кроме гонга; цены, длительности, форматы и место бери только из блока фактов, ничего "
    "не выдумывай, не придумывай отзывы, клиентов, цифры и исследования; пиши от первого лица "
    "(«я», «у меня»), не «мы» и не «специалист»; без эзотерики и пафоса; чистый текст без markdown, "
    "HTML, списков, звёздочек и решёток."
)


def _ru_system(facts: dict, topic: dict) -> str:
    return (
        "Ты пишешь статью в блог aromara.ru от первого лица Александры Куценко (аромапрактик, "
        "гонг-медитация, корпоративные форматы). Тон: разговорный профессиональный, как специалист "
        "объясняет коллеге. Образцы голоса:\n- " + "\n- ".join(facts["voice_samples"]) + "\n\n"
        + _HARD_RULES + " Групповые гонг-медитации бывают иногда, по анонсу в Telegram @Aromara_ru.\n\n"
        "БЛОК ФАКТОВ (сверен " + facts["verified_at"] + "):\n" + _facts_block(facts, topic["service"])
    )


def _plan_user(topic: dict, facts: dict) -> str:
    return (
        _ru_system(facts, topic) + f"\n\nЗадача: спланировать статью. Тема: {topic['angle']}.\n"
        f"Целевой поисковый запрос: «{topic['query']}».\n"
        "Ответь строго в формате, ничего больше:\n"
        "TITLE: заголовок статьи (до 60 символов, содержит смысл запроса)\n"
        "EXCERPT: анонс 125-150 символов\n"
        "затем ровно 6 строк разделов, каждая вида «@@ Заголовок раздела» (без нумерации, "
        "последний раздел про связанную услугу " + topic["service"] + " и запись в Telegram @Aromara_ru)."
    )


def _section_user(topic: dict, facts: dict, plan: dict, heading: str | None, notes: str = "") -> str:
    outline = "\n".join(f"- {s['heading']}" for s in plan["sections"] if s.get("heading"))
    what = f"раздел «{heading}»" if heading else "вступление (без заголовка)"
    size = "230-280 слов" if heading else "130-170 слов"
    return (
        _ru_system(facts, topic) + f"\n\nСтатья: «{plan['title']}». Запрос: «{topic['query']}». "
        f"План разделов:\n{outline}\n\nНапиши только {what}: {size}, 3-4 абзаца, абзацы через пустую "
        "строку. Не повторяй заголовок, не пиши «Раздел», ничего кроме текста раздела."
        + (f"\n\n{notes}" if notes else "")
    )


def _clean_body(text: str) -> str:
    """Strip stray markdown a model adds around plain text (never touches meaning)."""
    t = (text or "").strip()
    t = re.sub(r"(?m)^\s*#{1,6}\s.*$\n?", "", t)  # headings the model repeated
    t = re.sub(r"\*\*|__|`", "", t)
    t = re.sub(r"(?m)^\s*[-*•]\s+", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _local_issues(body: str, lang: str, facts: dict) -> list[str]:
    out = stoplist_violations(body, lang)
    if lang == "ru":
        out += fact_violations(body, facts)
    return out


def _en_system() -> str:
    return (
        "You adapt a Russian blog article of aromara.ru (first person, Alexandra Kutsenko) into natural "
        "English, not a literal translation. Same facts, prices in rubles exactly as in the source, "
        "same conversational professional tone. HARD RULES: no em dash (use period, colon, semicolon); "
        "no clichés (in conclusion, it is important to note, delve, unlock the potential, unique "
        "experience, journey); never use the words cure, heal, healing, diagnose, guarantee, treat, "
        "treatment; no invented facts; plain text only, no markdown, HTML or lists. Keep all details "
        "and do not shorten."
    )


def _translate_headings(headings: list[str]) -> list[str]:
    if not headings:
        return []
    raw = call_llm(system=_en_system(), max_tokens=400, context="site_autopilot/headings_en",
                   user="Translate these section headings into natural English, one per line, same "
                        "order, no numbering, no markdown:\n" + "\n".join(headings))
    out = [re.sub(r"^[#\-*\d.\s]+", "", ln).strip() for ln in (raw or "").splitlines() if ln.strip()]
    return out if len(out) == len(headings) else headings


def _read_minutes(post: dict) -> int:
    return max(1, math.ceil(body_words(post) / 180))


def _header(raw: str) -> tuple[str, str] | None:
    m_t = re.search(r"(?m)^TITLE:\s*(.+)$", raw or "")
    m_e = re.search(r"(?m)^EXCERPT:\s*(.+)$", raw or "")
    return (m_t.group(1).strip(), m_e.group(1).strip()) if m_t and m_e else None


def _header_issues(plan: dict, lang: str) -> list[str]:
    out = []
    t, e = plan["title"], plan["excerpt"]
    if len(t) > TITLE_MAX:
        out.append(f"заголовок {len(t)} символов, нужно не больше {TITLE_MAX}")
    if not EXCERPT_MIN <= len(e) <= EXCERPT_MAX:
        out.append(f"анонс {len(e)} символов, нужно {EXCERPT_MIN}-{EXCERPT_MAX}")
    out += stoplist_violations(t + "\n" + e, lang)
    return out


def _jobs_ru(topic: dict, facts: dict, global_notes: str):
    raw = call_llm(system="", user=_plan_user(topic, facts), max_tokens=900, context="site_autopilot/plan_ru")
    hdr = _header(raw)
    heads = [h.strip() for h in re.findall(r"(?m)^@@\s*(.+)$", raw or "")][:7]
    if not hdr or len(heads) < 4:
        return None, "ru: план статьи не получен в нужном формате"
    plan = {"title": hdr[0], "excerpt": hdr[1], "sections": [{"heading": h} for h in heads]}
    jobs = [(h, _section_user(topic, facts, plan, h, global_notes)) for h in [None] + heads]
    return (plan, jobs, "site_autopilot/section_ru", _ru_system(facts, topic), None), None


def _jobs_en(source: dict, global_notes: str):
    raw = call_llm(
        system=_en_system(), max_tokens=400, context="site_autopilot/header_en",
        user="Translate and adapt. Reply in exactly two lines:\nTITLE: (max 60 characters)\n"
             "EXCERPT: (125-150 characters)\n\nTitle: " + source["title"] + "\nExcerpt: " + source["excerpt"])
    hdr = _header(raw)
    if not hdr:
        return None, "en: заголовок не получен в нужном формате"
    plan = {"title": hdr[0], "excerpt": hdr[1]}
    jobs = [(s.get("heading"),
             "Adapt this section into English. Output only the text of the section, paragraphs separated "
             "by a blank line.\n\n" + s["body"] + global_notes) for s in source["sections"]]
    heads_en = _translate_headings([s["heading"] for s in source["sections"] if s.get("heading")])
    return (plan, jobs, "site_autopilot/section_en", _en_system(), heads_en), None


def _generate_post(*, lang: str, topic: dict, facts: dict, base: dict, cluster: str,
                   existing: set[str], notes: list[str], source: dict | None = None
                   ) -> tuple[dict | None, list[str]]:
    """Section-by-section generation (the shared model is short-winded on long output).

    RU: plan call, then one call per section. EN: header + one call per RU section.
    Sections with stoplist/fact violations get up to MAX_REWRITES targeted rewrites; global
    issues (length, header, medical review) trigger a whole-article retry within the budget.
    """
    global_notes = ""
    issues: list[str] = []
    for full_attempt in range(MAX_REWRITES + 1):
        res, err = _jobs_ru(topic, facts, global_notes) if lang == "ru" else _jobs_en(source or {}, global_notes)
        if res is None:
            return None, [err or "нет плана"]
        plan, jobs, ctx, system, heads_en = res
        sys_arg = system if lang == "en" else ""
        sections: list[dict] = []
        hi = 0
        for heading, user in jobs:
            body = _clean_body(call_llm(system=sys_arg, user=user, max_tokens=1500, context=ctx))
            for _ in range(MAX_REWRITES):
                local = _local_issues(body, lang, facts)
                if not local:
                    break
                notes.append(f"{lang}: rewrite section {heading!r}: {len(local)} проблем")
                body = _clean_body(call_llm(
                    system=sys_arg, max_tokens=1500, context=f"site_autopilot/rewrite_{lang}",
                    user=user + "\n\nПРЕДЫДУЩИЙ ТЕКСТ:\n" + body + "\n\nИСПРАВЬ эти проблемы и верни "
                    "переписанный текст раздела целиком, только текст:\n" + _issues_text(local)))
            sec: dict = {"body": body}
            if heading:
                sec = {"heading": heads_en[hi] if heads_en else heading, **sec}
                hi += 1
            sections.append(sec)

        for _ in range(MAX_REWRITES):
            hdr_issues = _header_issues(plan, lang)
            if not hdr_issues:
                break
            notes.append(f"{lang}: header rewrite: {len(hdr_issues)} проблем")
            fixed = _header(call_llm(
                system=sys_arg, max_tokens=400, context=f"site_autopilot/header_fix_{lang}",
                user="Исправь заголовок и анонс статьи. Проблемы:\n" + _issues_text(hdr_issues)
                     + f"\n\nTITLE: {plan['title']}\nEXCERPT: {plan['excerpt']}\n\nВерни ровно две строки "
                     f"TITLE: и EXCERPT: (заголовок до {TITLE_MAX} символов, анонс {EXCERPT_MIN + 10}-{EXCERPT_MAX - 10} "
                     "символов, считай символы, без «—» и клише)."))
            if fixed:
                plan = {**plan, "title": fixed[0], "excerpt": fixed[1]}

        post = {**base, "title": plan["title"], "excerpt": plan["excerpt"], "sections": sections}
        post["readMinutes"] = _read_minutes(post)
        issues = validate_post(post, lang, existing)
        if lang == "ru":
            issues += [f"ru: {v}" for v in fact_violations(post_text(post), facts)]
            if not issues:
                review = medical_review(post_text(post), cluster)
                if not review["passed"]:
                    issues = [f"медицинский ревью: {i}" for i in review["issues"]] or ["медицинский ревью: не пройден"]
        if not issues:
            return post, []
        if PARSE_ERROR_ISSUE in " ".join(issues):
            return None, issues  # reviewer unavailable: regenerating the article will not help
        notes.append(f"{lang}: full retry {full_attempt + 1}: {len(issues)} проблем")
        global_notes = "\n\nУЧТИ замечания к прошлой версии:\n" + _issues_text(issues[:8])
    return None, issues


def build_article(topic: dict, facts: dict, content_dir: Path, now: datetime,
                  notes: list[str]) -> tuple[dict | None, list[str]]:
    existing = set(facts["existing_slugs"]) | existing_file_slugs(content_dir)
    date = now.astimezone(MSK).strftime("%Y-%m-%d")
    img = {"image": topic["image"]} if topic.get("image") else {}
    ru, issues = _generate_post(
        lang="ru", topic=topic, facts=facts, base={"slug": topic["slug"], "date": date, **img},
        cluster=topic["cluster"], existing=existing, notes=notes)
    if ru is None:
        return None, issues
    en, issues = _generate_post(
        lang="en", topic=topic, facts=facts, base={"slug": topic["slug_en"], "date": date, **img},
        cluster=topic["cluster"], existing=existing, notes=notes, source=ru)
    if en is None:
        return None, issues
    article = {"ru": ru, "en": en, "meta": {
        "source": "autopilot", "topicId": topic["id"], "cluster": topic["cluster"],
        "generatedAt": now.isoformat()}}
    errs = validate_article(article, existing_slugs=existing)
    return (article, []) if not errs else (None, errs)


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------

def _revalidate(slug: str) -> None:
    secret = _env("REVALIDATE_SECRET", "")
    if not secret:
        raise RuntimeError("REVALIDATE_SECRET не задан")
    url = _env("SITE_REVALIDATE_URL", DEFAULT_REVALIDATE_URL)
    last: Any = None
    for i in range(3):
        try:
            last = http_post(url, json_body={"slug": slug}, headers={"x-revalidate-secret": secret})
            if last == 200:
                return
        except httpx.HTTPError as exc:
            last = repr(exc)
        _sleep(3 * (i + 1))
    raise RuntimeError(f"revalidate не удался: {last}")


def _verify_page(url: str, attempts: int = 12, delay: float = 5.0) -> None:
    last: Any = None
    for _ in range(attempts):
        try:
            last = http_get_status(url)
            if last == 200:
                return
        except httpx.HTTPError as exc:
            last = repr(exc)
        _sleep(delay)
    raise RuntimeError(f"{url} отвечает {last}, ожидали 200")


def publish_article(article: dict, content_dir: Path) -> list[str]:
    """Write + revalidate + verify. Rolls back the file on failure. Returns public URLs."""
    site = _env("SITE_URL", DEFAULT_SITE_URL).rstrip("/")
    slug, slug_en = article["ru"]["slug"], article["en"]["slug"]
    path = write_article(article, content_dir)
    try:
        _revalidate(slug)
        _verify_page(f"{site}/blog/{slug}")
    except Exception:
        path.unlink(missing_ok=True)
        try:
            _revalidate(slug)  # drop the cached page/list entry
        except Exception:  # noqa: BLE001
            logger.warning("site_autopilot: rollback revalidate failed", exc_info=True)
        raise
    return [f"{site}/blog/{slug}", f"{site}/en/blog/{slug_en}", f"{site}/blog", f"{site}/en/blog"]


def _notify(text: str) -> None:
    try:
        send_group_message(text)
    except Exception:  # noqa: BLE001
        logger.error("site_autopilot: telegram notify failed", exc_info=True)


def run_once(*, publish: bool, now: datetime | None = None, topic_id: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    content_dir = Path(_env("SITE_CONTENT_DIR", DEFAULT_CONTENT_DIR))
    facts = load_facts()
    state = load_state()
    topic = pick_next_topic(load_topics(), state, now=now, topic_id=topic_id)
    if topic is None:
        return {"status": "skipped", "reason": "нет темы или на этой неделе уже была попытка"}

    notes: list[str] = []
    try:
        article, issues = build_article(topic, facts, content_dir, now, notes)
    except Exception as exc:  # noqa: BLE001
        logger.error("site_autopilot: generation error", exc_info=True)
        article, issues = None, [f"ошибка генерации: {exc!r}"]

    if article is None:
        reason = "; ".join(issues)[:900]
        if not publish:
            return {"status": "dry-run-failed", "topic": topic["id"], "issues": issues, "notes": notes}
        mark_topic(state, topic["id"], "failed", now=now, reason=reason)
        save_state(state)
        _notify(f"Автопилот сайта: статья «{topic['slug']}» не опубликована.\nПричина: {reason}")
        return {"status": "failed", "topic": topic["id"], "issues": issues}

    guardian = guardian_signal(post_text(article["ru"]))
    if not publish:
        return {"status": "dry-run", "topic": topic["id"], "article": article,
                "guardian": guardian, "notes": notes}

    try:
        urls = publish_article(article, content_dir)
    except Exception as exc:  # noqa: BLE001
        reason = f"публикация: {exc}"
        mark_topic(state, topic["id"], "failed", now=now, reason=reason)
        save_state(state)
        _notify(f"Автопилот сайта: статья «{topic['slug']}» не опубликована.\nПричина: {reason}")
        return {"status": "failed", "topic": topic["id"], "issues": [reason]}

    mark_topic(state, topic["id"], "published", now=now, slug=topic["slug"])
    save_state(state)
    try:
        ping_indexnow(urls)
    except Exception:  # noqa: BLE001
        logger.warning("site_autopilot: indexnow failed", exc_info=True)
    extra = "" if guardian.get("passed") in (True, None) else f"\nBrand Guardian (сигнал): {guardian}"
    _notify(f"Опубликована статья: {article['ru']['title']}\n{urls[0]}\nEN: {urls[1]}{extra}")
    return {"status": "published", "topic": topic["id"], "url": urls[0]}
