from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import io

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents import ContentDraft, format_content_message, generate_strategist_step, generate_writer_step
from bot.agents.planner import generate_plan_sync
from bot.agents.reels_agent import generate_reels_director_sync, generate_reels_scenario_sync
from bot.handlers.threads import _format_trends
from bot.services.drafts_store import save_draft, update_draft
from bot.services.gemini_images import generate_gemini_image_sync
from bot.services.mini_app import append_mini_app_button
from bot.services.plans_store import save_plan
from bot.services.plans_store import get_plan
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class PlanEntry:
    day_label: str
    platform: str
    format_label: str
    goal: str
    topic: str
    angle: str


def _parse_plan_entries(raw: str) -> list[PlanEntry]:
    entries: list[PlanEntry] = []
    blocks = [block.strip() for block in raw.split("📅 ") if block.strip()]

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        day_label = lines[0]
        data = {
            "platform": "",
            "format": "",
            "goal": "",
            "topic": "",
            "angle": "",
        }
        for line in lines[1:]:
            if line.startswith("Платформа:"):
                data["platform"] = line.split(":", 1)[1].strip()
            elif line.startswith("Формат:"):
                data["format"] = line.split(":", 1)[1].strip()
            elif line.startswith("Цель:"):
                data["goal"] = line.split(":", 1)[1].strip()
            elif line.startswith("Тема:"):
                data["topic"] = line.split(":", 1)[1].strip()
            elif line.startswith("Угол:"):
                data["angle"] = line.split(":", 1)[1].strip()

        if data["topic"]:
            entries.append(
                PlanEntry(
                    day_label=day_label,
                    platform=data["platform"],
                    format_label=data["format"],
                    goal=data["goal"],
                    topic=data["topic"],
                    angle=data["angle"],
                )
            )
    return entries


def _plan_actions_keyboard(entries: list[PlanEntry]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"{idx + 1}", callback_data=f"pl:pick:{idx}")
        for idx in range(len(entries))
    ]
    return InlineKeyboardMarkup([buttons])


def _content_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Другой вариант", callback_data="pl:review:regen"),
            InlineKeyboardButton("✏️ Свой текст", callback_data="pl:review:manual"),
        ],
        [
            InlineKeyboardButton("✅ Согласовать", callback_data="pl:review:approve"),
        ],
    ])


def _reels_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Новая раскадровка", callback_data="pl:review:storyboard"),
            InlineKeyboardButton("✏️ Свой сценарий", callback_data="pl:review:manual"),
        ],
        [
            InlineKeyboardButton("✅ Согласовать", callback_data="pl:review:approve"),
        ],
    ])


def _normalize_content_format(entry: PlanEntry) -> str:
    platform = entry.platform.lower()
    format_label = entry.format_label.lower()

    if "reels" in platform or "рилс" in format_label or "reels" in format_label:
        return "reels"
    if "карус" in format_label or "carousel" in format_label:
        return "carousel"
    if "threads" in platform:
        return "threads"
    if "instagram" in platform:
        return "instagram"
    if "telegram" in platform:
        return "telegram"
    return "instagram"


def _normalize_goal(goal_label: str) -> str:
    value = goal_label.lower()
    if "прод" in value:
        return "sales"
    if "вовл" in value:
        return "engagement"
    if "эксперт" in value:
        return "authority"
    return "trust"


def _reels_result_text(topic: str, scenario: str, storyboard_lines: list[str], images_ready: int) -> str:
    storyboard_text = "\n".join(storyboard_lines) if storyboard_lines else "🎥 Раскадровка не сформировалась."
    return (
        f"🎬 Reels из плана: {topic}\n\n{scenario}\n\n{storyboard_text}\n\n"
        f"🖼 Gemini-кадры: {images_ready}/4"
    )


async def open_plan_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: str) -> None:
    record = await get_plan(plan_id)
    if not record:
        await update.effective_message.reply_text("❌ План с таким ID не найден.")
        return

    entries = _parse_plan_entries(record.raw_text)
    kwargs = {"parse_mode": "Markdown"}
    if entries:
        kwargs["reply_markup"] = append_mini_app_button(
            _plan_actions_keyboard(entries),
            label="🧭 Открыть Plan в Mini App",
            tab="plans",
        )
    else:
        kwargs["reply_markup"] = append_mini_app_button(
            None,
            label="🧭 Открыть Plan в Mini App",
            tab="plans",
        )

    context.user_data["plan_entries"] = [
        {
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "topic": entry.topic,
            "angle": entry.angle,
        }
        for entry in entries
    ]
    context.user_data["plan_id"] = record.plan_id
    await update.effective_message.reply_text(
        f"📅 *Контент-план на неделю:*\n\n{record.raw_text}\n\n🗂 Plan ID: `{record.plan_id}`",
        **kwargs,
    )


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /plan нужен ANTHROPIC_API_KEY.")
        return

    from cache.store import cache
    from analytics.aggregator import collect_all

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды для плана...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    status = await update.message.reply_text("📅 Составляю контент-план на неделю...")

    trends_text = _format_trends(results)

    loop = asyncio.get_event_loop()
    plan = await loop.run_in_executor(_executor, generate_plan_sync, trends_text)

    if not plan:
        await status.edit_text("❌ Не удалось составить план. Попробуй позже.")
        return

    entries = _parse_plan_entries(plan)
    context.user_data["plan_entries"] = [
        {
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "topic": entry.topic,
            "angle": entry.angle,
        }
        for entry in entries
    ]
    plan_record = await save_plan(
        plan,
        entries=[
            {
                "day_label": entry.day_label,
                "platform": entry.platform,
                "format_label": entry.format_label,
                "goal": entry.goal,
                "topic": entry.topic,
                "angle": entry.angle,
            }
            for entry in entries
        ],
    )
    context.user_data["plan_id"] = plan_record.plan_id

    kwargs = {"parse_mode": "Markdown"}
    if entries:
        kwargs["reply_markup"] = _plan_actions_keyboard(entries)
    await status.edit_text(
        f"📅 *Контент-план на неделю:*\n\n{plan}\n\n🗂 Plan ID: `{plan_record.plan_id}`\n\nВыбери номер пункта ниже, и я сразу превращу его в материал.",
        **kwargs,
    )


async def cb_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "pl:review:approve":
        review = context.user_data.get("plan_review", {})
        draft_id = str(review.get("draft_id", ""))
        if not review or not draft_id:
            await query.message.reply_text("❌ Черновик из плана не найден. Сгенерируй его заново.")
            return
        update_draft(draft_id, status="approved")
        await query.message.reply_text(
            f"✅ Черновик из плана согласован.\n🗂 Draft ID: {draft_id}\n"
            f"Позже оцени результат через /drafts {draft_id}",
            reply_markup=append_mini_app_button(
                None,
                label="🧭 Открыть Draft в Mini App",
                draft_id=draft_id,
                tab="reels" if str(review.get("mode", "")) == "reels" else "drafts",
            ),
        )
        return

    if data == "pl:review:manual":
        review = context.user_data.get("plan_review", {})
        if not review:
            await query.message.reply_text("❌ Черновик из плана не найден. Сгенерируй его заново.")
            return
        mode = str(review.get("mode", "content"))
        context.user_data["plan_awaiting_manual_edit"] = mode
        await query.message.reply_text(
            "✏️ Пришли новую версию одним сообщением.\n"
            + ("Для Reels пришли сценарий целиком." if mode == "reels" else "Я заменю основной текст.")
        )
        return

    if data == "pl:review:regen":
        review = context.user_data.get("plan_review", {})
        if not review or str(review.get("mode", "")) != "content":
            await query.message.reply_text("❌ Контент-черновик не найден. Сгенерируй его заново.")
            return
        entry = PlanEntry(**review["entry"])
        await _generate_content_from_plan(query.message, context, entry, str(review.get("format_key", "instagram")))
        return

    if data == "pl:review:storyboard":
        review = context.user_data.get("plan_review", {})
        if not review or str(review.get("mode", "")) != "reels":
            await query.message.reply_text("❌ Reels-черновик не найден. Сгенерируй его заново.")
            return
        entry = PlanEntry(**review["entry"])
        scenario = str(review.get("scenario", ""))
        if not scenario:
            await query.message.reply_text("❌ Сценарий не найден. Сгенерируй Reels заново.")
            return
        await _generate_reels_from_plan(
            query.message,
            context,
            entry,
            scenario_override=scenario,
            existing_draft_id=str(review.get("draft_id", "")),
        )
        return

    if not data.startswith("pl:pick:"):
        return

    raw_entries = context.user_data.get("plan_entries", [])
    idx = int(data.split(":")[2])
    if idx >= len(raw_entries):
        await query.message.reply_text("❌ План устарел. Запусти /plan заново.")
        return

    entry = PlanEntry(**raw_entries[idx])
    target = _normalize_content_format(entry)

    if target == "reels":
        await _generate_reels_from_plan(query.message, context, entry)
        return
    if target == "carousel":
        from bot.handlers.carousel import _run_carousel

        status = await query.message.reply_text(
            f"📅 {entry.day_label}\n🎠 {entry.topic}\n\n⏳ Запускаю полный carousel-flow из плана..."
        )
        await _run_carousel(query.message, context, entry.topic, status)
        return

    await _generate_content_from_plan(query.message, context, entry, target)


async def _generate_content_from_plan(message, context: ContextTypes.DEFAULT_TYPE, entry: PlanEntry, format_key: str) -> None:
    goal_key = _normalize_goal(entry.goal)
    status = await message.reply_text(
        f"📅 {entry.day_label}\n"
        f"🧩 {entry.platform} / {entry.format_label}\n"
        f"📌 {entry.topic}\n\n"
        "🧠 Генерирую материал по пункту плана..."
    )
    try:
        angle, hook = await generate_strategist_step(entry.topic, goal_key, format_key)
        draft = await generate_writer_step(entry.topic, goal_key, format_key, angle or entry.angle, hook)
    except Exception:
        logger.exception("Plan content generation failed")
        await status.edit_text("❌ Не удалось сгенерировать материал по этому пункту плана.")
        return

    saved = save_draft(
        kind=format_key,
        topic=entry.topic,
        source="/plan",
        payload={
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "angle": draft.angle,
            "hook": draft.hook,
            "caption": draft.caption,
            "cta": draft.cta,
            "hashtags": draft.hashtags,
            "visual_prompt": draft.visual_prompt,
            "slides": draft.slides,
        },
    )
    context.user_data["plan_review"] = {
        "mode": "content",
        "draft_id": saved.draft_id,
        "format_key": format_key,
        "entry": {
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "topic": entry.topic,
            "angle": entry.angle,
        },
        "payload": {
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "angle": draft.angle,
            "hook": draft.hook,
            "caption": draft.caption,
            "cta": draft.cta,
            "hashtags": draft.hashtags,
            "visual_prompt": draft.visual_prompt,
            "slides": draft.slides,
        },
    }
    context.user_data["plan_awaiting_manual_edit"] = None
    await status.edit_text(
        f"{format_content_message(draft, entry.topic, goal_key, format_key)}\n\n🗂 Draft ID: {saved.draft_id}",
        reply_markup=append_mini_app_button(
            _content_review_keyboard(),
            label="🧭 Открыть Draft в Mini App",
            draft_id=saved.draft_id,
            tab="drafts",
        ),
    )


async def _generate_reels_from_plan(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    entry: PlanEntry,
    *,
    scenario_override: str = "",
    existing_draft_id: str = "",
) -> None:
    status = await message.reply_text(
        f"📅 {entry.day_label}\n"
        f"🎬 {entry.topic}\n\n"
        "⏳ Собираю Reels по пункту плана..."
    )
    loop = asyncio.get_event_loop()
    try:
        scenario = scenario_override or await loop.run_in_executor(_executor, generate_reels_scenario_sync, entry.topic)
        frames = await loop.run_in_executor(_executor, generate_reels_director_sync, entry.topic, scenario)
    except Exception:
        logger.exception("Plan reels generation failed")
        await status.edit_text("❌ Не удалось собрать Reels по этому пункту плана.")
        return

    images: list[bytes] = []
    for frame in frames[:4]:
        image = await loop.run_in_executor(
            _executor,
            lambda prompt=frame.gemini_prompt: generate_gemini_image_sync(
                prompt,
                aspect_ratio="9:16",
                log_context="Gemini plan reels",
            ),
        )
        if image:
            images.append(image)

    payload = {
        "day_label": entry.day_label,
        "platform": entry.platform,
        "format_label": entry.format_label,
        "goal": entry.goal,
        "scenario": scenario,
        "storyboard": [
            {
                "timecode": frame.timecode,
                "scene": frame.scene,
                "angle": frame.angle,
                "gemini_prompt": frame.gemini_prompt,
            }
            for frame in frames
        ],
        "images_ready": len(images),
    }
    if existing_draft_id:
        updated = update_draft(existing_draft_id, topic=entry.topic, status="draft", payload=payload)
        draft_id = updated.draft_id if updated else existing_draft_id
    else:
        saved = save_draft(kind="reels", topic=entry.topic, source="/plan", payload=payload)
        draft_id = saved.draft_id

    storyboard_lines = [
        f"{idx + 1}. {frame.timecode}\nСцена: {frame.scene}\nРакурс: {frame.angle}"
        for idx, frame in enumerate(frames)
    ]
    context.user_data["plan_review"] = {
        "mode": "reels",
        "draft_id": draft_id,
        "entry": {
            "day_label": entry.day_label,
            "platform": entry.platform,
            "format_label": entry.format_label,
            "goal": entry.goal,
            "topic": entry.topic,
            "angle": entry.angle,
        },
        "scenario": scenario,
        "payload": payload,
    }
    context.user_data["plan_awaiting_manual_edit"] = None
    await status.edit_text(
        f"{_reels_result_text(entry.topic, scenario, storyboard_lines, len(images))}\n\n🗂 Draft ID: {draft_id}",
        reply_markup=append_mini_app_button(
            _reels_review_keyboard(),
            label="🧭 Открыть Reels в Mini App",
            draft_id=draft_id,
            tab="reels",
        ),
    )

    if images:
        media: list[InputMediaPhoto] = []
        for frame_idx, image in enumerate(images, 1):
            photo = io.BytesIO(image)
            photo.name = f"plan_reels_{frame_idx}.png"
            media.append(InputMediaPhoto(media=photo, caption=entry.topic if frame_idx == 1 else None))
        await message.reply_media_group(media)


async def msg_plan_manual_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = context.user_data.get("plan_awaiting_manual_edit")
    if not mode:
        return

    review = context.user_data.get("plan_review", {})
    draft_id = str(review.get("draft_id", ""))
    text = (update.message.text or "").strip()
    if not review or not draft_id:
        context.user_data["plan_awaiting_manual_edit"] = None
        await update.message.reply_text("❌ Контекст редактирования потерян. Сгенерируй материал из /plan заново.")
        return
    if len(text) < 5:
        await update.message.reply_text("❌ Текст слишком короткий. Пришли полную версию.")
        return

    entry = PlanEntry(**review["entry"])
    context.user_data["plan_awaiting_manual_edit"] = None

    if mode == "reels":
        await _generate_reels_from_plan(
            update.message,
            context,
            entry,
            scenario_override=text,
            existing_draft_id=draft_id,
        )
        return

    payload = dict(review.get("payload", {}))
    payload["caption"] = text
    update_draft(draft_id, status="draft", payload=payload)
    context.user_data["plan_review"] = {
        **review,
        "payload": payload,
    }

    draft = ContentDraft(
        angle=str(payload.get("angle", "")),
        hook=str(payload.get("hook", "")),
        caption=str(payload.get("caption", "")),
        cta=str(payload.get("cta", "")),
        hashtags=str(payload.get("hashtags", "")),
        visual_prompt=str(payload.get("visual_prompt", "")),
        slides=list(payload.get("slides", [])),
    )
    await update.message.reply_text(
        f"{format_content_message(draft, entry.topic, _normalize_goal(entry.goal), str(review.get('format_key', 'instagram')))}\n\n🗂 Draft ID: {draft_id}",
        reply_markup=append_mini_app_button(
            _content_review_keyboard(),
            label="🧭 Открыть Draft в Mini App",
            draft_id=draft_id,
            tab="drafts",
        ),
    )


def build_plan_handler():
    return [
        CommandHandler("plan", cmd_plan),
        CallbackQueryHandler(cb_plan, pattern="^pl:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_plan_manual_edit),
    ]
