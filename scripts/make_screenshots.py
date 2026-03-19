#!/usr/bin/env python3
"""
Screenshot gallery generator for Aromara MiniApp.

Uses the same test-server approach as tests/ui/conftest.py:
- Starts uvicorn with a fresh SQLite test DB
- Seeds realistic data (drafts, plans, handbook, team, mentions)
- Takes screenshots for every screen in registry.json
- Tests clicks and records results

Usage:
    python scripts/make_screenshots.py                  # current screenshots
    python scripts/make_screenshots.py --baseline       # overwrite baseline
    python scripts/make_screenshots.py --screen=drafts  # single screen
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from base64 import b64decode
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "docs" / "screenshots" / "gallery"
CURRENT = GALLERY / "current"
BASELINE = GALLERY / "baseline"
DIFF_DIR = GALLERY / "diff"
REGISTRY = GALLERY / "registry.json"
VIEWPORT = {"width": 393, "height": 852}
TIMEOUT = 20000

# 1x1 transparent PNG for image stubs
_PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zk6cAAAAASUVORK5CYII="
)

def _telegram_stub(dark=False):
    """Build Telegram WebApp JS stub with theme and safe area insets."""
    scheme = "dark" if dark else "light"
    return (
        "window.Telegram={WebApp:{initData:'',initDataUnsafe:{user:{id:12345,username:'test'}},"
        "ready:function(){},expand:function(){},close:function(){},"
        "MainButton:{show:function(){},hide:function(){},setText:function(){},onClick:function(){}},"
        "BackButton:{show:function(){},hide:function(){},onClick:function(){}},"
        f"themeParams:{{}},colorScheme:'{scheme}',"
        "contentSafeAreaInset:{top:0,bottom:0,left:0,right:0},"
        "safeAreaInset:{top:0,bottom:0,left:0,right:0},"
        "viewportHeight:852,viewportStableHeight:852,"
        "platform:'ios',isExpanded:true,"
        "isVersionAtLeast:function(){return true},"
        "setHeaderColor:function(){},setBackgroundColor:function(){},setBottomBarColor:function(){},"
        "onEvent:function(){},offEvent:function(){},sendData:function(){},openLink:function(){},"
        "enableClosingConfirmation:function(){},disableVerticalSwipes:function(){},"
        "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},selectionChanged:function(){}}}};"
    )


_SAFE_AREA_OVERLAY_CSS = """
body::before {
  content: ''; position: fixed; top: 0; left: 0; right: 0;
  height: 0px; background: rgba(255,0,0,0.12); z-index: 99999;
  pointer-events: none;
}
body::after {
  content: ''; position: fixed; bottom: 0; left: 0; right: 0;
  height: 0px; background: rgba(255,0,0,0.12); z-index: 99999;
  pointer-events: none;
}
"""

# Forbidden zone Y boundaries (viewport coordinates)
ZONE_TOP_BOTTOM = 55       # TG header bottom edge (TG_HEADER_HEIGHT)
ZONE_BOTTOM_TOP = 852 - 34  # Home indicator top edge (viewport_h - HOME_INDICATOR_H = 818)

# Timings (ms)
DOM_RENDER = 100
API_ROUNDTRIP = 500


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Test server did not start in time")


def _seed_database(db_path: Path, assets_dir: Path, *, ignore_conflicts: bool = False) -> None:
    """Seed test database with realistic data (mirrors conftest.py)."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    INSERT = "INSERT OR IGNORE" if ignore_conflicts else "INSERT"
    _now = datetime.now(timezone.utc)
    _ts = lambda delta: (_now - delta).isoformat()
    now = _ts(timedelta(0))

    # Reels draft with asset
    draft_id = "reels001"
    asset_file = assets_dir / draft_id / "frame_1.png"
    asset_file.parent.mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(_PNG_1X1)

    reels_payload = {
        "scenario": "Короткий сценарий рилса про вечернее переключение.",
        "images_ready": 1,
        "storyboard": [{
            "timecode": "0-3 сек",
            "scene": "**Текст на экране:** Попробуй сегодня\n\n## Сцена\nРуки закрывают ноутбук",
            "angle": "Крупный план",
            "gemini_prompt": "warm evening desk, close-up hands closing laptop",
            "current_asset": {
                "url": f"/generated/reels_assets/{draft_id}/frame_1.png",
                "filename": "frame_1.png",
                "generated_at": _ts(timedelta(hours=1)),
            },
        }],
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
            "calm sensory ritual, soft amber light",
            "wellness still life, aroma bottle, warm shadows",
        ],
        "slide_images": [
            {"url": "/generated/carousel_assets/carousel001/slide_1.png", "filename": "slide_1.png", "generated_at": _ts(timedelta(hours=3))},
            None,
        ],
        "slide_image_versions": [[{"url": "/generated/carousel_assets/carousel001/slide_1.png", "filename": "slide_1.png", "generated_at": _ts(timedelta(hours=3)), "prompt": "prompt 1"}], []],
        "img_prompt_notes": ["", ""],
        "cta": "Напиши, если хочешь такую карусель под свой проект.",
    }
    threads_series_payload = {
        "series_summary": "Опорная мысль серии про восстановление.",
        "goal": "trust",
        "emotion": "calm",
        "posts": [
            {"slot": 1, "text": "Утренний пост серии.", "status": "draft"},
            {"slot": 2, "text": "Дневной пост серии.", "status": "draft"},
        ],
    }

    # Drafts — main set
    drafts = [
        ("reels001", "reels", "Вечерний ароматический ритуал", "/miniapp", "draft", "", reels_payload, _ts(timedelta(minutes=23))),
        ("threads001", "threads", "Как мягко выйти из рабочего напряжения", "/content", "in_review", "worked", threads_payload, _ts(timedelta(hours=2))),
        ("carousel001", "carousel", "Сенсорная карусель для вечернего ритуала", "/miniapp", "draft", "", carousel_payload, _ts(timedelta(hours=5))),
        ("threads_series001", "threads_series", "Восстановление энергии и ресурса", "/miniapp", "draft", "", threads_series_payload, _ts(timedelta(days=1))),
    ]
    for did, kind, topic, src, status, fb, payload, ts in drafts:
        c.execute(
            INSERT + " INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
            (did, kind, topic, src, status, fb, json.dumps(payload), ts),
        )

    # Scheduled draft
    scheduled_payload = {
        "angle": "Через утренний ритуал пробуждения.",
        "hook": "Три минуты утром меняют весь день.",
        "caption": "Утренний ритуал: масло мяты + дыхание.",
        "cta": "Попробуй завтра утром.",
        "visual_prompt": "morning ritual, mint oil, fresh start, soft sunlight",
    }
    c.execute(
        INSERT + " INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at, scheduled_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?, ?)",
        ("scheduled001", "threads", "Утренний ритуал пробуждения", "/miniapp", "scheduled", "", json.dumps(scheduled_payload), _ts(timedelta(days=2)), (_now + timedelta(days=3)).isoformat()),
    )

    # Published draft
    published_payload = {
        "angle": "Через вечернюю медитацию.",
        "hook": "Вечер — лучшее время для практики.",
        "caption": "Вечерняя медитация с лавандой.",
        "cta": "Расскажи, как прошёл вечер.",
        "visual_prompt": "evening meditation, lavender, candles, calm atmosphere",
    }
    c.execute(
        INSERT + " INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at, published_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[\"threads\"]', '{}', '', '', ?, ?)",
        ("published001", "threads", "Вечерняя медитация с лавандой", "/content", "published", "approved", json.dumps(published_payload), _ts(timedelta(days=3)), _ts(timedelta(days=1, hours=4))),
    )

    # Extra drafts for scroll testing
    extra_drafts = [
        ("threads002", "threads", "Как звуковые ванны помогают при мигрени", "draft", _ts(timedelta(hours=4))),
        ("threads003", "threads", "5 ароматов для продуктивного утра", "draft", _ts(timedelta(hours=8))),
        ("carousel002", "carousel", "Гид по эфирным маслам для новичков", "draft", _ts(timedelta(days=1, hours=2))),
        ("reels002", "reels", "Как правильно дышать с аромамаслом", "draft", _ts(timedelta(days=1, hours=6))),
        ("threads004", "threads", "Почему лаванда — не единственный релаксант", "in_review", _ts(timedelta(days=2))),
        ("carousel003", "carousel", "Масла для каждого времени года", "draft", _ts(timedelta(days=2, hours=3))),
        ("threads005", "threads", "Гонг-медитация: что говорит наука", "draft", _ts(timedelta(days=3))),
        ("reels003", "reels", "3 масла, которые должны быть в каждом доме", "in_review", _ts(timedelta(days=3, hours=5))),
    ]
    for did, kind, topic, status, ts in extra_drafts:
        simple_payload = {
            "angle": "Через личный опыт и исследования.",
            "hook": f"Тема: {topic}",
            "caption": f"Текст поста на тему «{topic}».",
            "cta": "Напиши, если хочешь узнать больше.",
        }
        c.execute(
            INSERT + " INTO drafts (draft_id, kind, topic, source, status, feedback, payload, publish_platforms, external_ids, revision_notes, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '{}', '', '', ?)",
            (did, kind, topic, "/miniapp", status, "", json.dumps(simple_payload), ts),
        )

    # Publish log
    c.execute(
        INSERT + " INTO publish_log (draft_id, platform, action, status, external_id, error_message, attempt_num, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("published001", "threads", "publish", "success", "ext-001", "", 1, _ts(timedelta(days=1, hours=4))),
    )

    # Handbook cards — enriched payloads
    lavender_payload = {
        "name_en": "Lavender",
        "name_ru": "Лаванда",
        "latin_name": "Lavandula angustifolia",
        "description": "Одно из самых универсальных эфирных масел. Лаванда обладает выраженным седативным, противовоспалительным и антисептическим действием.",
        "description_short": "Универсальное масло для сна, расслабления и снятия тревоги.",
        "therapeutic_properties": "Седативное, анксиолитическое, противовоспалительное, антисептическое, обезболивающее",
        "aroma_profile": "Цветочный, свежий, с травяными нотами",
        "volatility": "Средняя (нота сердца)",
        "recommended_for": "Бессонница, тревожность, головная боль, ожоги, раздражения кожи",
        "contraindications": "Индивидуальная непереносимость. С осторожностью в 1 триместре беременности.",
        "applications": "Диффузор: 3-5 капель. Массаж: 2% в базовом масле. Ванна: 5-7 капель с эмульгатором.",
    }
    grounding_payload = {
        "name_en": "Evening Relax",
        "ingredient_names_ru": "Лаванда, Бергамот, Ладан",
        "ingredient_names": "Lavender, Bergamot, Frankincense",
        "ingredient_slugs": "lavender,bergamot,frankincense",
        "ingredient_drops": "3,2,1",
        "therapeutic_properties": "Снижает тревожность, готовит ко сну",
        "applications": "Диффузор: 3-4 капли. Массаж: 2% в базовом масле.",
        "precautions": "Беременность 1 триместр — проконсультируйтесь с врачом",
    }
    stress_payload = {
        "category_group": "НЕРВНАЯ СИСТЕМА",
        "parent_group": "НЕРВНАЯ СИСТЕМА",
        "description": "Хроническое напряжение, вызванное длительным воздействием стрессоров. Проявляется в теле, эмоциях и когнитивных функциях.",
        "recommended_oil_names": "Лаванда, Бергамот, Ромашка, Иланг-иланг",
        "recommended_oil_slugs": "lavender,bergamot,chamomile,ylang-ylang",
        "applications": "Ингаляция: 2-3 капли на салфетку. Диффузор: 4-5 капель. Массаж воротниковой зоны: 2% в базовом масле.",
    }
    limbic_payload = {
        "description": "Лимбическая система — совокупность структур головного мозга, участвующих в регуляции эмоций, памяти и обоняния. Ароматические молекулы напрямую воздействуют на миндалевидное тело и гиппокамп.",
        "complementary_oil_names": "Лаванда, Розмарин, Мята",
        "questions": "Как запахи влияют на эмоции?,Почему ароматерапия работает быстро?,Связь обоняния и памяти",
        "resource_values": "Научные исследования в Journal of Neuroscience, PubMed",
    }
    breathing_payload = {
        "description": "Техника дыхания, при которой вдох, задержка, выдох и задержка выполняются на равные промежутки времени (обычно 4 секунды). Активирует парасимпатическую нервную систему.",
        "complementary_oil_names": "Мята, Эвкалипт, Лаванда",
        "course_notes": "Начните с 3 циклов, постепенно увеличивая до 10. Выполняйте 2-3 раза в день.",
    }
    gong_payload = {
        "description": "Гонг — один из древнейших инструментов звукового целительства. Вибрации гонга воздействуют на все тело, помогая войти в глубокое медитативное состояние.",
        "volatility": "20-60 минут (сессия)",
        "audio_url": "/static/audio/gong_sample.mp3",
        "duration_seconds": 180,
        "frequency_range": "80-800 Hz",
        "therapeutic_properties": "Глубокая релаксация, снятие мышечного напряжения, медитативное состояние",
        "applications": "Звуковая ванна: 30-60 минут. Медитация: 15-20 минут. Перед сном: 10 минут.",
    }

    cards = [
        ("lavender", "Лаванда", "aroma", "herb", lavender_payload),
        ("grounding", "Вечерний релакс / Evening Relax", "blend", "blend", grounding_payload),
        ("stress", "Стресс", "symptom", "symptom", stress_payload),
        ("limbic-system", "Лимбическая система", "concept", "theory", limbic_payload),
        ("box-breathing", "Квадратное дыхание", "practice", "practice", breathing_payload),
        ("gong", "Гонг", "sound", "instrument", gong_payload),
    ]
    for slug, name, category, source_type, payload in cards:
        c.execute(
            INSERT + " INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, category, source_type, json.dumps([]), json.dumps(payload), _ts(timedelta(days=7)), _ts(timedelta(hours=12))),
        )

    # Extra blend cards
    extra_blends = [
        ("clear-mind", "Ясный ум / Clear Mind", {
            "name_en": "Clear Mind",
            "ingredient_names_ru": "Розмарин, Мята, Лимон",
            "ingredient_names": "Rosemary, Peppermint, Lemon",
            "ingredient_slugs": "rosemary,peppermint,lemon",
            "ingredient_drops": "2,2,2",
            "therapeutic_properties": "Улучшает концентрацию, пробуждает",
            "applications": "Диффузор: 4-5 капель утром.",
        }),
        ("morning-energy", "Утренняя энергия / Morning Energy", {
            "name_en": "Morning Energy",
            "ingredient_names_ru": "Апельсин, Грейпфрут, Имбирь",
            "ingredient_names": "Orange, Grapefruit, Ginger",
            "ingredient_slugs": "orange,grapefruit,ginger",
            "ingredient_drops": "3,2,1",
            "therapeutic_properties": "Тонизирует, поднимает настроение",
            "applications": "Диффузор: 5 капель. Аромакулон: 1-2 капли.",
        }),
        ("immunity", "Иммунитет / Immunity Shield", {
            "name_en": "Immunity Shield",
            "ingredient_names_ru": "Чайное дерево, Эвкалипт, Лимон",
            "ingredient_names": "Tea Tree, Eucalyptus, Lemon",
            "ingredient_slugs": "tea-tree,eucalyptus,lemon",
            "ingredient_drops": "2,2,2",
            "therapeutic_properties": "Антисептическое, иммуностимулирующее",
            "applications": "Диффузор: 4-6 капель. Ингаляция: 2-3 капли.",
            "precautions": "Не наносить неразбавленным на кожу.",
        }),
    ]
    for slug, name, payload in extra_blends:
        c.execute(
            INSERT + " INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, "blend", "blend", json.dumps([]), json.dumps(payload), _ts(timedelta(days=5)), _ts(timedelta(days=1))),
        )

    # Symptom cards with category groups
    symptoms = [
        ("headache", "Головная боль", "НЕРВНАЯ СИСТЕМА", {
            "category_group": "НЕРВНАЯ СИСТЕМА", "parent_group": "НЕРВНАЯ СИСТЕМА",
            "description": "Боль в области головы различной интенсивности и локализации.",
            "recommended_oil_names": "Мята, Лаванда, Эвкалипт",
            "recommended_oil_slugs": "peppermint,lavender,eucalyptus",
            "applications": "Нанести 1 каплю мяты на виски. Ингаляция: 2-3 капли лаванды.",
        }),
        ("anxiety", "Тревожность", "НЕРВНАЯ СИСТЕМА", {
            "category_group": "НЕРВНАЯ СИСТЕМА", "parent_group": "НЕРВНАЯ СИСТЕМА",
            "description": "Состояние повышенного беспокойства и напряжения без видимой причины.",
            "recommended_oil_names": "Лаванда, Бергамот, Иланг-иланг",
            "recommended_oil_slugs": "lavender,bergamot,ylang-ylang",
            "applications": "Диффузор: 3-4 капли. Ванна: 5 капель с солью.",
        }),
        ("insomnia", "Бессонница", "СОН И ОТДЫХ", {
            "category_group": "СОН И ОТДЫХ", "parent_group": "СОН И ОТДЫХ",
            "description": "Нарушение засыпания или поддержания сна.",
            "recommended_oil_names": "Лаванда, Ромашка, Ветивер",
            "recommended_oil_slugs": "lavender,chamomile,vetiver",
            "applications": "Подушка: 2 капли лаванды. Диффузор за 30 минут до сна.",
        }),
        ("fatigue", "Усталость и истощение", "ЭНЕРГИЯ", {
            "category_group": "ЭНЕРГИЯ", "parent_group": "ЭНЕРГИЯ",
            "description": "Физическое и эмоциональное истощение, снижение работоспособности.",
            "recommended_oil_names": "Розмарин, Мята, Апельсин",
            "recommended_oil_slugs": "rosemary,peppermint,orange",
            "applications": "Ингаляция: 2 капли розмарина. Диффузор: 4 капли цитрусовой смеси.",
        }),
    ]
    for slug, name, _cat_group, payload in symptoms:
        c.execute(
            INSERT + " INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, name, "symptom", "symptom", json.dumps([]), json.dumps(payload), _ts(timedelta(days=7)), _ts(timedelta(hours=12))),
        )

    # Plan
    c.execute(
        INSERT + " INTO plans (plan_id, raw_text, entries, status, created_at) VALUES (?, ?, ?, 'draft', ?)",
        ("20260311180000", "## Контент-план\n- Понедельник: Threads\n- Среда: Reels",
         json.dumps([{
             "day_label": "Понедельник", "platform": "Threads",
             "format_label": "пост", "goal": "Доверие",
             "topic": "Почему вечерний ритуал помогает нервной системе",
             "angle": "Через простые телесные сигналы.",
         }], ensure_ascii=False), _ts(timedelta(days=2))),
    )

    # Team
    c.execute(
        INSERT + " INTO teams (team_id, name, slug, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("team-test-01", "Aromara Studio", "aromara-studio", 12345, _ts(timedelta(days=14)), _ts(timedelta(days=1))),
    )
    c.execute(
        INSERT + " INTO team_members (team_id, telegram_id, username, role, joined_at) VALUES (?, ?, ?, ?, ?)",
        ("team-test-01", 12345, "test", "owner", _ts(timedelta(days=14))),
    )

    # Mention
    c.execute(
        INSERT + " INTO mentions (mention_id, team_id, platform, external_id, type, author_username, author_name, content, url, context_post, status, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("mention-001", "team-test-01", "threads", "ext-m-001", "mention", "aroma_fan", "Анна",
         "Попробовала вашу смесь — невероятный эффект!", "https://threads.net/p/123", "", "pending", _ts(timedelta(hours=6))),
    )

    # Saved blend
    c.execute(
        INSERT + " INTO saved_blends (saved_id, telegram_id, team_id, title, brief, tags, oils, total_drops, profile, expert_note, application_guide, safety_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("blend-saved-001", 12345, "team-test-01", "Вечерний релакс", "Смесь для расслабления перед сном",
         json.dumps(["релакс", "сон"]),
         json.dumps([{"name": "Лаванда", "drops": 3}, {"name": "Ромашка", "drops": 2}]),
         5, json.dumps({"goal": "relaxation"}),
         "Идеальна для вечернего ритуала.", "Нанести на запястья за 30 минут до сна.", "safe", _ts(timedelta(days=4))),
    )

    conn.commit()
    conn.close()


def _start_server(db_path: Path, assets_dir: Path) -> tuple[str, subprocess.Popen]:
    """Start uvicorn test server, return (base_url, process)."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "TELEGRAM_BOT_TOKEN": "test-token",
        "REPORT_TARGET_CHAT_ID": "test-chat",
        "AROMA_DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "AROMA_REELS_ASSETS_DIR": str(assets_dir),
        "MINIAPP_AROMA_ALLOWED_USER_IDS": "12345",
        "AROMA_BYPASS_AUTH": "1",
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "miniapp_server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_until_ready(base_url)
    return base_url, process


def navigate_to_screen(page, base_url: str, screen: dict) -> bool:
    """Execute navigation steps from registry to reach a screen. Returns True on success."""
    for step in screen["steps"]:
        action = step["action"]

        if action == "goto":
            url = step["url"]
            try:
                if url.startswith("?"):
                    page.goto(f"{base_url}/{url}", wait_until="domcontentloaded", timeout=TIMEOUT)
                    try:
                        page.wait_for_selector("body.app-ready", timeout=10000)
                    except Exception:
                        page.evaluate("document.body.classList.add('app-ready')")
                        page.wait_for_timeout(200)
                elif url.startswith("/"):
                    page.goto(f"{base_url}{url}", wait_until="domcontentloaded", timeout=TIMEOUT)
                else:
                    page.goto(f"{base_url}/{url}", wait_until="domcontentloaded", timeout=TIMEOUT)
            except Exception:
                return False
            page.wait_for_timeout(API_ROUNDTRIP)

        elif action == "click":
            selector = step["selector"]
            try:
                page.locator(selector).first.wait_for(state="visible", timeout=5000)
                page.locator(selector).first.click()
            except Exception:
                return False
            wait_sel = step.get("wait")
            if wait_sel:
                try:
                    page.locator(wait_sel).first.wait_for(state="visible", timeout=5000)
                except Exception:
                    pass
            page.wait_for_timeout(DOM_RENDER)

        elif action == "evaluate":
            try:
                page.evaluate(step["js"])
            except Exception:
                return False
            page.wait_for_timeout(API_ROUNDTRIP)

        elif action == "wait":
            try:
                page.locator(step["selector"]).first.wait_for(state="visible", timeout=8000)
            except Exception:
                return False

        else:
            raise ValueError(f"Unknown navigation action: {action}")

    return True


def take_screenshot(page, path: Path, name: str) -> Path:
    """Take a viewport-only screenshot (full_page is never used)."""
    # Wait for spinners to disappear
    try:
        page.locator(".loading, .spinner, .panel-loader").first.wait_for(
            state="hidden", timeout=3000
        )
    except Exception:
        pass

    # Disable animations for clean screenshots
    page.add_style_tag(content="""
        *, *::before, *::after {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
        }
    """)
    page.wait_for_timeout(150)

    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)
    print(f"  \U0001f4f8 {name} -> {path.name}")
    return path


def make_diffs():
    """Compare current/ with baseline/ pixel-by-pixel."""
    try:
        from PIL import Image, ImageChops, ImageEnhance
    except ImportError:
        print("PIL not installed, skipping diff")
        return

    diffs = []
    for current in sorted(CURRENT.glob("*.png")):
        baseline = BASELINE / current.name
        if not baseline.exists():
            continue
        try:
            img_c = Image.open(current).convert("RGBA")
            img_b = Image.open(baseline).convert("RGBA")

            if img_c.size != img_b.size:
                img_b = img_b.resize(img_c.size, Image.LANCZOS)

            diff = ImageChops.difference(img_c, img_b)
            enhancer = ImageEnhance.Brightness(diff)
            diff_bright = enhancer.enhance(5.0)
            diff_bright.save(DIFF_DIR / f"{current.stem}_diff.png")

            pixels = list(diff.getdata())
            changed = sum(1 for px in pixels if any(c > 10 for c in px[:3]))
            total = len(pixels)
            pct = round(changed / total * 100, 2)

            diffs.append({
                "screen_id": current.stem,
                "diff_percent": pct,
                "diff_pixels": changed,
                "has_diff": pct > 0.5,
                "diff_image": f"diff/{current.stem}_diff.png",
            })
        except Exception as e:
            print(f"  diff error {current.name}: {e}")

    with open(GALLERY / "diff_report.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "diffs": diffs}, f, indent=2, ensure_ascii=False)

    regressions = [d for d in diffs if d["has_diff"]]
    print(f"\U0001f50d Regressions: {len(regressions)}/{len(diffs)} screens")
    for d in regressions:
        print(f"  \u26a0  {d['screen_id']}: {d['diff_percent']}% ({d['diff_pixels']} px)")


def _capture_scroll_snapshots(page, path_prefix: Path, sid: str, label: str, theme: str, viewport_height: int = 852, scroll_selector: str | None = None):
    """Capture multiple viewport-size snapshots by scrolling through the page.

    Args:
        scroll_selector: CSS selector for the scrollable container.
            None = body scroll (e.g. privacy page).
            '#detailPanel' = detail screens that scroll inside a panel.
    """
    import math
    if scroll_selector:
        total_height = page.evaluate(f"document.querySelector('{scroll_selector}')?.scrollHeight || 0")
    else:
        total_height = page.evaluate("document.body.scrollHeight")
    if total_height <= viewport_height:
        return  # Nothing extra to capture
    num_frames = math.ceil(total_height / viewport_height)
    frame_positions = [i * viewport_height for i in range(num_frames)]
    for i in range(num_frames):
        if scroll_selector:
            page.evaluate(f"document.querySelector('{scroll_selector}').scrollTop = {frame_positions[i]}")
        else:
            page.evaluate(f"window.scrollTo(0, {frame_positions[i]})")
        page.wait_for_timeout(150)
        take_screenshot(
            page, path_prefix / f"{sid}_scroll_{i}.png",
            f"[{theme}] {label} (scroll {i+1}/{num_frames})"
        )

    # --- Zone-boundary pass ---
    # Reset scroll
    if scroll_selector:
        page.evaluate(f"document.querySelector('{scroll_selector}').scrollTop = 0")
    else:
        page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(100)

    # Query interactive elements and compute zone-boundary scroll positions
    _interactive_sel = "button, a[href], input, select, [role='button'], [onclick], [data-action]"
    js_get_elements = f"""
    (() => {{
        const container = {f"document.querySelector('{scroll_selector}')" if scroll_selector else "null"};
        const scrollTop = container ? container.scrollTop : window.scrollY;
        const root = container || document.body;
        const els = root.querySelectorAll("{_interactive_sel}");
        const results = [];
        for (const el of els) {{
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const containerRect = container ? container.getBoundingClientRect() : {{ top: 0 }};
            const absTop = rect.top - containerRect.top + (container ? container.scrollTop : window.scrollY);
            const absBottom = rect.bottom - containerRect.top + (container ? container.scrollTop : window.scrollY);
            results.push({{ absTop, absBottom }});
        }}
        return results;
    }})()
    """
    try:
        elements = page.evaluate(js_get_elements)
    except Exception:
        elements = []

    # Calculate zone-boundary scroll positions
    zone_positions = set()
    for el in elements:
        # Scroll position where element top enters header zone
        pos_header = el["absTop"] - ZONE_TOP_BOTTOM
        if 0 <= pos_header <= total_height - viewport_height:
            zone_positions.add(pos_header)
        # Scroll position where element bottom enters home indicator zone
        pos_home = el["absBottom"] - ZONE_BOTTOM_TOP
        if 0 <= pos_home <= total_height - viewport_height:
            zone_positions.add(pos_home)

    # Deduplicate within 20px tolerance
    deduplicated = []
    for pos in sorted(zone_positions):
        if not deduplicated or abs(pos - deduplicated[-1]) > 20:
            deduplicated.append(pos)

    # Filter out positions already captured by frame loop (within 20px)
    filtered = []
    for pos in deduplicated:
        if not any(abs(pos - fp) <= 20 for fp in frame_positions):
            filtered.append(pos)

    # Cap at 20 zone captures
    filtered = filtered[:20]

    for idx, pos in enumerate(filtered):
        if scroll_selector:
            page.evaluate(f"document.querySelector('{scroll_selector}').scrollTop = {pos}")
        else:
            page.evaluate(f"window.scrollTo(0, {pos})")
        page.wait_for_timeout(150)
        take_screenshot(
            page, path_prefix / f"{sid}_zone_{idx}.png",
            f"[{theme}] {label} (zone {idx})"
        )

    # Scroll back to top
    if scroll_selector:
        page.evaluate(f"document.querySelector('{scroll_selector}').scrollTop = 0")
    else:
        page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(100)


FILTER_SCREENS = [
    {"base_url_param": "?tab=drafts", "sid": "drafts", "filters": [
        {"label": "scheduled", "js": "const el=document.getElementById('statusFilter');if(el){el.value='scheduled';el.dispatchEvent(new Event('change',{bubbles:true}))}"},
        {"label": "published", "js": "const el=document.getElementById('statusFilter');if(el){el.value='published';el.dispatchEvent(new Event('change',{bubbles:true}))}"},
    ]},
]


def _capture_filter_variants(page, base_url, *, dark=False):
    """Capture screenshots for filter/tab state variants."""
    prefix = "dark_" if dark else ""
    theme = "dark" if dark else "light"
    for fscreen in FILTER_SCREENS:
        for flt in fscreen["filters"]:
            sid = f"{fscreen['sid']}__filter_{flt['label']}"
            print(f"\n▶ [{theme}] Filter: {sid}")
            try:
                page.goto(f"{base_url}/{fscreen['base_url_param']}", wait_until="domcontentloaded", timeout=TIMEOUT)
                try:
                    page.wait_for_selector("body.app-ready", timeout=8000)
                except Exception:
                    page.evaluate("document.body.classList.add('app-ready')")
                    page.wait_for_timeout(200)
                if dark:
                    page.evaluate("document.body.classList.add('tg-theme-dark')")
                    page.wait_for_timeout(50)
                page.wait_for_timeout(API_ROUNDTRIP)
                try:
                    page.evaluate(flt["js"])
                except Exception:
                    pass
                page.wait_for_timeout(API_ROUNDTRIP)
                take_screenshot(page, CURRENT / f"{prefix}{sid}.png", f"[{theme}] {sid}")
            except Exception as e:
                print(f"  ✗ Filter {sid} failed: {e}")


def _create_context(browser, *, dark=False, safe_area_overlay=False):
    """Create a browser context with Telegram stub."""
    context = browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=3,
        is_mobile=True,
        color_scheme="dark" if dark else "light",
        extra_http_headers={
            "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"
        },
    )
    context.add_init_script(_telegram_stub(dark=dark))
    context.add_init_script("localStorage.setItem('aroma_onboarded', '1')")
    if dark:
        context.add_init_script(
            "document.addEventListener('DOMContentLoaded',"
            " () => document.body.classList.add('tg-theme-dark'))"
        )
    context._safe_area_overlay = safe_area_overlay
    return context


def _init_page(page, base_url, *, dark=False, safe_area_overlay=False):
    """Load the app and wait for ready state."""
    page.goto(base_url, wait_until="domcontentloaded", timeout=TIMEOUT)
    try:
        page.wait_for_selector("body.app-ready", timeout=8000)
    except Exception:
        page.evaluate("document.body.classList.add('app-ready')")
        page.wait_for_timeout(300)
    if dark:
        page.evaluate("document.body.classList.add('tg-theme-dark')")
        page.wait_for_timeout(50)
    if safe_area_overlay:
        page.add_style_tag(content=_SAFE_AREA_OVERLAY_CSS)


def _capture_screens(browser, base_url, screens, *, dark=False, click_results=None, safe_area_overlay=False):
    """Capture screenshots for all screens in light or dark mode."""
    theme = "dark" if dark else "light"
    prefix = "dark_" if dark else ""
    print(f"\n{'=' * 40}")
    print(f"  THEME: {theme.upper()}")
    print(f"{'=' * 40}")

    context = _create_context(browser, dark=dark, safe_area_overlay=safe_area_overlay)
    page = context.new_page()
    _init_page(page, base_url, dark=dark, safe_area_overlay=safe_area_overlay)

    def _fresh_page():
        """Create a fresh page in the context."""
        nonlocal page
        try:
            page.close()
        except Exception:
            pass
        page = context.new_page()
        _init_page(page, base_url, dark=dark, safe_area_overlay=safe_area_overlay)

    nav_failures = 0
    for screen in screens:
        sid = screen["id"]
        label = screen.get("label", sid)
        scrollable = screen.get("scrollable", False)
        print(f"\n\u25b6 [{theme}] {label} ({sid})")

        # Special case: onboarding
        if sid == "onboarding":
            ctx2 = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=3, is_mobile=True,
                color_scheme="dark" if dark else "light",
                extra_http_headers={
                    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D"
                },
            )
            ctx2.add_init_script(_telegram_stub(dark=dark))
            if dark:
                ctx2.add_init_script(
                    "document.addEventListener('DOMContentLoaded',"
                    " () => document.body.classList.add('tg-theme-dark'))"
                )
            pg2 = ctx2.new_page()
            pg2.goto(base_url, wait_until="domcontentloaded", timeout=TIMEOUT)
            pg2.wait_for_timeout(2000)
            if dark:
                pg2.evaluate("document.body.classList.add('tg-theme-dark')")
                pg2.wait_for_timeout(50)
            # Capture first slide
            take_screenshot(pg2, CURRENT / f"{prefix}{sid}.png", f"[{theme}] {label}")
            # Capture additional onboarding slides
            slide_idx = 1
            while True:
                try:
                    btn = pg2.locator(".onboarding-btn-next, .onboarding-next, button:has-text('Далее')")
                    if btn.count() == 0 or not btn.first.is_visible():
                        break
                    btn.first.click()
                    pg2.wait_for_timeout(500)
                    take_screenshot(
                        pg2, CURRENT / f"{prefix}{sid}_slide_{slide_idx}.png",
                        f"[{theme}] {label} (slide {slide_idx + 1})"
                    )
                    slide_idx += 1
                    if slide_idx > 10:  # safety limit
                        break
                except Exception:
                    break
            ctx2.close()
            _fresh_page()
            continue

        # Navigate to screen
        try:
            ok = navigate_to_screen(page, base_url, screen)
        except Exception:
            ok = False
        if not ok:
            print(f"  \u2717 Navigation failed for {sid}")
            try:
                take_screenshot(page, CURRENT / f"{prefix}{sid}__FAIL.png", f"[{theme}] {label} (FAIL)")
            except Exception:
                pass
            nav_failures += 1
            if nav_failures >= 2:
                print("  \u27f3 Refreshing page after consecutive failures")
                try:
                    _fresh_page()
                except Exception:
                    pass
                nav_failures = 0
            continue

        nav_failures = 0

        # Viewport screenshot (clean)
        try:
            take_screenshot(page, CURRENT / f"{prefix}{sid}.png", f"[{theme}] {label}")
        except Exception as e:
            print(f"  \u2717 Screenshot failed for {sid}: {e}")
            try:
                _fresh_page()
            except Exception:
                pass
            continue

        # Dual screenshot: overlay forbidden zones
        if safe_area_overlay:
            try:
                page.add_style_tag(content=_SAFE_AREA_OVERLAY_CSS)
                take_screenshot(page, CURRENT / f"{prefix}{sid}_zones.png", f"[{theme}] {label} (zones)")
            except Exception:
                pass

        # Scroll snapshots for scrollable screens
        if scrollable:
            # Detail screens scroll inside #detailPanel, not body
            is_detail = screen.get("group", "").endswith("-detail") or screen.get("group") == "modal"
            scroll_sel = "#detailPanel" if is_detail else None
            try:
                _capture_scroll_snapshots(page, CURRENT, f"{prefix}{sid}", label, theme, VIEWPORT["height"], scroll_selector=scroll_sel)
            except Exception as e:
                print(f"  ⚠ scroll capture failed for {sid}: {e}")

        # Test clicks (light theme only, no need to duplicate)
        if not dark and click_results is not None:
            for click in screen.get("clicks", []):
                selector = click["selector"]
                click_label = click.get("label", selector)
                try:
                    navigate_to_screen(page, base_url, screen)
                    page.wait_for_timeout(200)
                    el = page.locator(selector).first
                    el.wait_for(state="visible", timeout=3000)
                    el.click()
                    page.wait_for_timeout(500)

                    slug = selector.replace(".", "").replace("#", "").replace(" ", "_").replace(":", "").replace("'", "").replace("(", "").replace(")", "")[:30]
                    fname = f"{sid}_after_{slug}.png"
                    take_screenshot(page, CURRENT / fname, f"click: {click_label}")

                    click_results.append({
                        "screen_id": sid, "selector": selector, "label": click_label,
                        "status": "ok", "screenshot": fname,
                        "leads_to_route": page.url.replace(base_url, ""),
                    })
                except Exception as e:
                    print(f"  \u2717 click '{click_label}': {e}")
                    click_results.append({
                        "screen_id": sid, "selector": selector, "label": click_label,
                        "status": f"error: {str(e)[:120]}", "screenshot": None,
                        "leads_to_route": None,
                    })

    # Filter variant screenshots
    _capture_filter_variants(page, base_url, dark=dark)

    context.close()


def run():
    from playwright.sync_api import sync_playwright

    is_baseline = "--baseline" in sys.argv
    use_prod_data = "--prod-data" in sys.argv
    safe_area_overlay = "--no-safe-area-overlay" not in sys.argv  # enabled by default
    screen_filter = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--screen=")), None)

    # Load registry
    with open(REGISTRY, encoding="utf-8") as f:
        registry = json.load(f)

    screens = registry["screens"]
    if screen_filter:
        screens = [s for s in screens if s["id"] == screen_filter]
        if not screens:
            print(f"Screen '{screen_filter}' not found in registry")
            sys.exit(1)

    # Prepare directories
    CURRENT.mkdir(parents=True, exist_ok=True)
    BASELINE.mkdir(parents=True, exist_ok=True)
    DIFF_DIR.mkdir(parents=True, exist_ok=True)

    # Set up test DB and server
    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix="gallery-"))
    db_path = tmpdir / "test_aroma.db"
    assets_dir = tmpdir / "reels_assets"

    from sqlalchemy import create_engine
    sys.path.insert(0, str(ROOT))
    from db.models import Base

    if use_prod_data:
        prod_dump = ROOT / "data" / "aroma_prod_dump.db"
        if not prod_dump.exists():
            print(f"Prod dump not found: {prod_dump}")
            sys.exit(1)
        shutil.copy2(prod_dump, db_path)
        print(f"Using prod dump: {prod_dump}")
        # Ensure all tables exist (prod dump may lack newer tables)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()
        # Add synthetic data for navigation selectors (INSERT OR IGNORE)
        _seed_database(db_path, assets_dir, ignore_conflicts=True)
    else:
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()
        _seed_database(db_path, assets_dir)

    print("Starting test server...")
    base_url, server_proc = _start_server(db_path, assets_dir)
    print(f"Server ready at {base_url}")

    click_results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            # Light theme pass
            _capture_screens(browser, base_url, screens, dark=False, click_results=click_results, safe_area_overlay=safe_area_overlay)

            # Dark theme pass
            _capture_screens(browser, base_url, screens, dark=True, safe_area_overlay=safe_area_overlay)

            browser.close()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    # Save click results
    with open(GALLERY / "clicks.json", "w", encoding="utf-8") as f:
        json.dump(click_results, f, ensure_ascii=False, indent=2)

    ok_count = sum(1 for c in click_results if c["status"] == "ok")
    err_count = sum(1 for c in click_results if c["status"] != "ok")
    print(f"\nClicks: {ok_count} ok, {err_count} errors")

    # Baseline
    if is_baseline or not any(BASELINE.glob("*.png")):
        print("\nCopying current -> baseline")
        for f in CURRENT.glob("*.png"):
            shutil.copy2(f, BASELINE / f.name)

    # Pixel diff
    make_diffs()

    total_screenshots = len(list(CURRENT.glob("*.png")))
    total_baseline = len(list(BASELINE.glob("*.png")))
    total_diff = len(list(DIFF_DIR.glob("*.png")))
    light_count = len([f for f in CURRENT.glob("*.png") if not f.name.startswith("dark_")])
    dark_count = len([f for f in CURRENT.glob("*.png") if f.name.startswith("dark_")])
    full_count = len([f for f in CURRENT.glob("*_scroll_*.png")])
    zone_count = len([f for f in CURRENT.glob("*_zone_*.png")])
    regressions = 0
    try:
        with open(GALLERY / "diff_report.json") as f:
            diff_data = json.load(f)
            regressions = sum(1 for d in diff_data.get("diffs", []) if d.get("has_diff"))
    except Exception:
        pass

    print(f"""
\U0001f4ca Gallery ready
{'─' * 40}
Screens in registry:    {len(screens)}
Screenshots total:      {total_screenshots}
  Light theme:          {light_count}
  Dark theme:           {dark_count}
  Scroll snapshots:     {full_count}
  Zone captures:        {zone_count}
Baseline:               {total_baseline}
Clicks tested:          {ok_count} ok / {err_count} errors
Regressions:            {regressions} screens

\U0001f4c2 Open gallery:
  open docs/screenshots/gallery/index.html
{'─' * 40}""")


if __name__ == "__main__":
    run()
