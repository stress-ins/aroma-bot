"""Daily Oil of the Day — contextual selection, caching, and notification service."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from functools import partial

import httpx
from sqlalchemy import select

from db.models import AromaCardModel, DailyOilModel, UserProfile
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 30


def _strip_markdown_json(text: str) -> str:
    """Remove ```json ... ``` wrapper if present."""
    s = text.strip()
    if s.startswith("```"):
        # Remove opening ``` line
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        # Remove closing ```
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
_MAX_CANDIDATES = 10

# ---------------------------------------------------------------------------
# Season / keyword mappings for pre-filtering
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]

_MONTH_NAMES_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

_SEASON_TAGS: dict[str, list[str]] = {
    "весна": ["тонизирующ", "очища", "бодр", "освежа", "детокс", "обновлен"],
    "лето": ["освежа", "охлажда", "лёгк", "цитрус", "антисептич"],
    "осень": ["укрепля", "иммунитет", "согрева", "защит", "адаптоген"],
    "зима": ["согрева", "иммунитет", "противовирус", "тепл", "защит", "антисептич"],
}

_WEEKEND_TAGS = ["расслабл", "успокаива", "восстановлен", "релакс", "медитац", "сон"]
_WEEKDAY_TAGS = ["концентрац", "бодр", "тонизир", "фокус", "энерги", "стимул"]
_COLD_TAGS = ["согрева", "тепл", "иммунитет"]
_HOT_TAGS = ["освежа", "охлажда", "лёгк"]
_HIGH_KP_TAGS = ["успокаива", "нервн", "стресс", "расслабл", "адаптоген"]


def _get_season(month: int) -> str:
    if month in (3, 4, 5):
        return "весна"
    if month in (6, 7, 8):
        return "лето"
    if month in (9, 10, 11):
        return "осень"
    return "зима"


# ---------------------------------------------------------------------------
# External data fetchers (graceful fallback)
# ---------------------------------------------------------------------------


async def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Fetch current weather from Open-Meteo (free, no key)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
    )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        current = data.get("current", {})
        wcode = current.get("weather_code", 0)
        condition = _weather_code_to_text(wcode)
        return {
            "temp_c": current.get("temperature_2m"),
            "condition": condition,
            "humidity": current.get("relative_humidity_2m"),
        }
    except Exception as exc:
        logger.debug("Weather fetch failed: %s", exc)
        return None


def _weather_code_to_text(code: int) -> str:
    if code == 0:
        return "ясно"
    if code in (1, 2, 3):
        return "облачно"
    if code in (45, 48):
        return "туман"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67):
        return "дождь"
    if code in (71, 73, 75, 77, 85, 86):
        return "снег"
    if code in (80, 81, 82):
        return "ливень"
    if code in (95, 96, 99):
        return "гроза"
    return "переменно"


async def _fetch_kp_index() -> dict | None:
    """Fetch planetary Kp-index from NOAA (free, no key)."""
    url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        # data is list of lists: [timestamp, kp_value, ...]
        # Skip header row, take latest forecast
        if len(data) > 1:
            latest = data[-1]
            kp = float(latest[1])
            if kp >= 7:
                level = "высокая"
            elif kp >= 5:
                level = "повышенная"
            elif kp >= 3:
                level = "умеренная"
            else:
                level = "низкая"
            return {"kp_index": round(kp, 1), "level": level}
    except Exception as exc:
        logger.debug("Kp-index fetch failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Day context builder
# ---------------------------------------------------------------------------


async def _build_day_context(target_date: str) -> dict:
    """Build contextual information about the day."""
    from bot.services.brand_settings_store import get_brand_settings

    dt = datetime.strptime(target_date, "%Y-%m-%d")
    month = dt.month
    weekday_idx = dt.weekday()  # 0=Monday
    season = _get_season(month)

    # Get city from brand settings
    city_name = "Москва"
    city_lat = 55.7558
    city_lon = 37.6173
    try:
        settings = await get_brand_settings()
        city_name = getattr(settings, "city_name", "Москва") or "Москва"
        city_lat = getattr(settings, "city_lat", 55.7558) or 55.7558
        city_lon = getattr(settings, "city_lon", 37.6173) or 37.6173
    except Exception:
        logger.warning("_build_day_context: get_brand_settings failed", exc_info=True)
        pass

    ctx: dict = {
        "date": target_date,
        "weekday": _WEEKDAY_NAMES_RU[weekday_idx],
        "is_weekend": weekday_idx >= 5,
        "season": season,
        "month_name": _MONTH_NAMES_RU[month],
        "city": city_name,
    }

    # Fetch weather and Kp in parallel
    weather = await _fetch_weather(city_lat, city_lon)
    if weather:
        ctx["weather"] = weather

    solar = await _fetch_kp_index()
    if solar:
        ctx["solar_activity"] = solar

    return ctx


# ---------------------------------------------------------------------------
# Candidate scoring / pre-filtering
# ---------------------------------------------------------------------------


def _score_candidate(card: AromaCardModel, ctx: dict) -> float:
    """Score a candidate card based on day context. Higher = more relevant."""
    payload = card.payload or {}
    props_text = " ".join([
        " ".join(payload.get("therapeutic_properties", [])),
        " ".join(payload.get("psychological_properties", [])),
        payload.get("description_short", ""),
    ]).lower()

    if not props_text.strip():
        return 0.0

    score = 0.0
    season = ctx.get("season", "")

    # Season relevance
    for tag in _SEASON_TAGS.get(season, []):
        if tag in props_text:
            score += 2.0

    # Weekend vs weekday
    if ctx.get("is_weekend"):
        for tag in _WEEKEND_TAGS:
            if tag in props_text:
                score += 1.5
    else:
        for tag in _WEEKDAY_TAGS:
            if tag in props_text:
                score += 1.5

    # Weather-based
    weather = ctx.get("weather")
    if weather and weather.get("temp_c") is not None:
        temp = weather["temp_c"]
        if temp < 5:
            for tag in _COLD_TAGS:
                if tag in props_text:
                    score += 1.0
        elif temp > 25:
            for tag in _HOT_TAGS:
                if tag in props_text:
                    score += 1.0

    # High solar activity → calming oils
    solar = ctx.get("solar_activity")
    if solar and solar.get("kp_index", 0) >= 5:
        for tag in _HIGH_KP_TAGS:
            if tag in props_text:
                score += 1.5

    return score


def _prefilter_candidates(
    candidates: list[AromaCardModel], ctx: dict, max_count: int = _MAX_CANDIDATES
) -> list[AromaCardModel]:
    """Score and return top candidates by contextual relevance."""
    scored = [(card, _score_candidate(card, ctx)) for card in candidates]
    # Sort by score descending, with random tiebreaker
    scored.sort(key=lambda x: (x[1], random.random()), reverse=True)

    # If all scores are 0 (no payload data), return random sample
    if scored and scored[0][1] == 0:
        return random.sample(candidates, min(max_count, len(candidates)))

    return [card for card, _ in scored[:max_count]]


# ---------------------------------------------------------------------------
# Smart oil selection via Claude
# ---------------------------------------------------------------------------


def _pick_oil_via_claude(
    candidates: list[AromaCardModel], ctx: dict
) -> tuple[AromaCardModel, str]:
    """Ask Claude Haiku to pick the best oil from candidates. Returns (card, reason)."""
    from bot.services.claude_client import HAIKU, call_claude

    # Build candidate descriptions
    lines = []
    for i, c in enumerate(candidates, 1):
        payload = c.payload or {}
        props = payload.get("therapeutic_properties", [])[:3]
        psych = payload.get("psychological_properties", [])[:3]
        desc_parts = []
        if props:
            desc_parts.append(", ".join(props))
        if psych:
            desc_parts.append(", ".join(psych))
        desc = " — " + "; ".join(desc_parts) if desc_parts else ""
        lines.append(f"{i}. {c.slug} | {c.name}{desc}")

    # Build context description
    ctx_lines = []
    ctx_lines.append(f"Дата: {ctx['weekday']}, {ctx['date']} ({ctx['season']})")
    weather = ctx.get("weather")
    if weather:
        parts = []
        if weather.get("temp_c") is not None:
            parts.append(f"{weather['temp_c']:+.0f}°C")
        if weather.get("condition"):
            parts.append(weather["condition"])
        if weather.get("humidity") is not None:
            parts.append(f"влажность {weather['humidity']}%")
        ctx_lines.append(f"Погода в {ctx.get('city', 'Москва')}: {', '.join(parts)}")
    solar = ctx.get("solar_activity")
    if solar:
        ctx_lines.append(
            f"Солнечная активность: Kp={solar['kp_index']}, {solar['level']}"
        )

    prompt = (
        "Ты — эксперт по ароматерапии. Выбери ОДНО масло из списка, "
        "наиболее подходящее для сегодняшнего дня.\n\n"
        f"Контекст дня:\n" + "\n".join(f"- {l}" for l in ctx_lines) + "\n\n"
        f"Кандидаты:\n" + "\n".join(lines) + "\n\n"
        'Ответ строго JSON: {"slug": "...", "reason": "...почему сегодня (1 предложение)"}\n'
        "Без markdown, только JSON."
    )

    try:
        raw = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            model=HAIKU,
            context="daily_oil_pick",
        )
        data = json.loads(_strip_markdown_json(raw))
        slug = data.get("slug", "")
        reason = data.get("reason", "")
        for c in candidates:
            if c.slug == slug:
                return c, reason
        # Slug not found in candidates — use first candidate
        logger.warning("Claude picked unknown slug '%s', falling back", slug)
    except Exception as exc:
        logger.warning("Claude oil pick failed: %s", exc)

    return random.choice(candidates), ""


# ---------------------------------------------------------------------------
# Fact & practice generation (with context)
# ---------------------------------------------------------------------------


def _generate_fact_and_practice(oil_name: str, ctx: dict | None = None) -> tuple[str, str]:
    """Call Claude Haiku to get a fun fact and daily practice for the oil."""
    from bot.services.claude_client import HAIKU, call_claude

    ctx_hint = ""
    if ctx:
        parts = [f"{ctx.get('weekday', '')}, {ctx.get('season', '')}"]
        weather = ctx.get("weather")
        if weather:
            if weather.get("temp_c") is not None:
                parts.append(f"{weather['temp_c']:+.0f}°C")
            if weather.get("condition"):
                parts.append(weather["condition"])
        solar = ctx.get("solar_activity")
        if solar:
            parts.append(f"солнечная активность {solar['level']}")
        ctx_hint = (
            f"\nКонтекст: {', '.join(parts)}.\n"
            "Учти при формулировке практики — утренняя для рабочего дня "
            "или вечерняя для выходного; сезонность если уместно.\n"
        )

    prompt = (
        f'Ты — эксперт по ароматерапии. Для эфирного масла "{oil_name}" дай:\n'
        "1. Интересный факт (1-2 предложения)\n"
        "2. Простую практику на день с этим маслом (2-3 предложения)\n"
        f"{ctx_hint}\n"
        "Правила для daily_practice:\n"
        "- Не упоминай «аромалампу» — используй «диффузор»\n"
        "- Вместо «нюхать из флакона» — «капните 1-2 капли на ладонь, разотрите и вдыхайте с ладоней»\n"
        "- Ванна: «предварительно накапайте масло на морскую соль или добавьте в жирные сливки, затем растворите в воде»\n\n"
        'Ответ строго в JSON: {{"fact": "...", "daily_practice": "..."}}\n'
        "Без markdown, только JSON."
    )

    try:
        raw = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            model=HAIKU,
            context="daily_oil",
        )
        data = json.loads(_strip_markdown_json(raw))
        return data.get("fact", ""), data.get("daily_practice", "")
    except Exception as exc:
        logger.warning("Claude daily-oil generation failed: %s", exc)
        return "", ""


# ---------------------------------------------------------------------------
# Main selection flow
# ---------------------------------------------------------------------------


async def select_daily_oil(target_date: str) -> DailyOilModel:
    """Pick the most contextually relevant oil, generate fact+practice via Claude Haiku.

    If a row for *target_date* already exists it is returned unchanged.
    """
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == target_date)
            )
        ).scalar_one_or_none()
        if existing:
            if not existing.reason and not existing.fact and not existing.daily_practice:
                # Content generation failed on initial run — retry
                loop = asyncio.get_running_loop()
                fact, practice = await loop.run_in_executor(
                    None, partial(_generate_fact_and_practice, existing.name, existing.context)
                )
                if fact or practice:
                    from bot.services.humanizer import humanize, humanize_llm  # noqa: PLC0415

                    existing.fact = humanize_llm(humanize(fact), "daily_oil") if fact else fact
                    existing.daily_practice = (
                        humanize_llm(humanize(practice), "daily_oil") if practice else practice
                    )
                    await session.commit()
                    await session.refresh(existing)
            return existing

        # Build day context (weather, Kp, season, etc.)
        ctx = await _build_day_context(target_date)

        # Recently used slugs (last 30 days)
        cutoff = (
            datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%d")
        recent_rows = (
            await session.execute(
                select(DailyOilModel.slug).where(DailyOilModel.date >= cutoff)
            )
        ).scalars().all()
        recent_slugs = set(recent_rows)

        # All aroma cards
        all_aromas = (
            await session.execute(
                select(AromaCardModel).where(AromaCardModel.category == "aroma")
            )
        ).scalars().all()

        candidates = [a for a in all_aromas if a.slug not in recent_slugs]
        if not candidates:
            candidates = list(all_aromas)
        if not candidates:
            raise RuntimeError("No aroma cards in the database")

        # Pre-filter to top N by context relevance
        top_candidates = _prefilter_candidates(candidates, ctx)

        # Let Claude pick the best one (sync → run in thread to avoid blocking event loop)
        loop = asyncio.get_running_loop()
        chosen, reason = await loop.run_in_executor(
            None, partial(_pick_oil_via_claude, top_candidates, ctx)
        )

        # Generate fact and daily practice with context
        fact, practice = await loop.run_in_executor(
            None, partial(_generate_fact_and_practice, chosen.name, ctx)
        )

        # Humanize all generated text: remove AI artifacts, em-dashes, markdown
        from bot.services.humanizer import humanize, humanize_llm  # noqa: PLC0415

        fact = humanize_llm(humanize(fact), "daily_oil") if fact else fact
        practice = humanize_llm(humanize(practice), "daily_oil") if practice else practice
        reason = humanize(reason) if reason else reason

        row = DailyOilModel(
            date=target_date,
            slug=chosen.slug,
            name=chosen.name,
            fact=fact,
            daily_practice=practice,
            reason=reason,
            context=ctx,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def get_daily_oil(target_date: str | None = None) -> dict | None:
    """Return today's daily oil card as a dict, creating it lazily if needed."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == target_date)
            )
        ).scalar_one_or_none()
        if not row:
            try:
                oil = await select_daily_oil(target_date)
                return {
                    "date": oil.date,
                    "slug": oil.slug,
                    "name": oil.name,
                    "fact": oil.fact,
                    "daily_practice": oil.daily_practice,
                    "reason": oil.reason,
                    "context": oil.context,
                    "sent_at": oil.sent_at.isoformat() if oil.sent_at else None,
                }
            except Exception:
                return None
        return {
            "date": row.date,
            "slug": row.slug,
            "name": row.name,
            "fact": row.fact,
            "daily_practice": row.daily_practice,
            "reason": row.reason,
            "context": row.context,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        }


async def get_subscribed_user_ids() -> list[int]:
    """Return telegram_ids of users with daily_oil_subscribed=True."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(UserProfile.telegram_id).where(
                    UserProfile.daily_oil_subscribed == True  # noqa: E712
                )
            )
        ).scalars().all()
        return list(rows)


async def send_daily_oil_notifications(app) -> None:
    """Send daily oil message to each subscribed user."""
    oil = await get_daily_oil()
    if not oil:
        logger.warning("No daily oil to send")
        return

    user_ids = await get_subscribed_user_ids()
    if not user_ids:
        logger.info("No subscribers for daily oil")
        return

    reason_line = ""
    if oil.get("reason"):
        reason_line = f"\n\U0001f4a1 <b>Почему сегодня:</b> {oil['reason']}\n"

    text = (
        f"\U0001f33f <b>Масло дня — {oil['name']}</b>\n"
        f"{reason_line}\n"
        f"{oil['fact']}\n\n"
        f"\U0001f9d8 <b>Практика дня:</b>\n{oil['daily_practice']}"
    )

    sent = 0
    for uid in user_ids:
        try:
            await app.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except Exception as exc:
            logger.debug("Failed to send daily oil to %s: %s", uid, exc)

    # Mark as sent
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == oil["date"])
            )
        ).scalar_one_or_none()
        if row:
            row.sent_at = now
            await session.commit()

    logger.info("Daily oil sent to %d/%d subscribers", sent, len(user_ids))


async def toggle_subscription(telegram_id: int) -> bool:
    """Toggle daily_oil_subscribed flag. Returns new value."""
    async with AsyncSessionLocal() as session:
        user = await session.get(UserProfile, telegram_id)
        if not user:
            return True  # no profile yet — default is subscribed
        user.daily_oil_subscribed = not user.daily_oil_subscribed
        await session.commit()
        return user.daily_oil_subscribed
