from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents.reels_agent import (
    StoryboardFrame,
    generate_reels_director_sync,
    generate_reels_scenario_sync,
    generate_reels_topics_sync,
)
from bot.handlers.threads import _format_trends
from bot.services.drafts_store import save_draft, update_draft
from bot.services.gemini_images import generate_gemini_image_sync
from bot.services.mini_app import append_mini_app_button
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_img_executor = ThreadPoolExecutor(max_workers=4)


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"rl:pick:{i}") for i in range(len(topics))]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="rl:refresh")])
    return InlineKeyboardMarkup(buttons)


def _topics_text(topics: list[str]) -> str:
    items = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return f"🎬 *Темы для Reels:*\n\n{items}\n\nНажми номер — получишь детальный сценарий:"


def _review_keyboard() -> InlineKeyboardMarkup:
    frame_buttons = [
        InlineKeyboardButton(str(idx + 1), callback_data=f"rl:frame:open:{idx}")
        for idx in range(4)
    ]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Новая раскадровка", callback_data="rl:review:storyboard"),
            InlineKeyboardButton("✏️ Свой сценарий", callback_data="rl:review:manual"),
        ],
        frame_buttons,
        [
            InlineKeyboardButton("✅ Согласовать", callback_data="rl:review:approve"),
        ],
    ])


def _storyboard_text(frames: list[StoryboardFrame]) -> str:
    if not frames:
        return "🎥 Раскадровка не сформировалась."

    parts = ["🎥 Раскадровка:"]
    for idx, frame in enumerate(frames, 1):
        parts.append(
            f"\n{idx}. {frame.timecode}\n"
            f"Сцена: {frame.scene}\n"
            f"Ракурс: {frame.angle}"
        )
    return "\n".join(parts)


def _reels_result_text(topic: str, scenario: str, frames: list[StoryboardFrame], images_ready: int) -> str:
    image_note = (
        f"\n\n🖼 Gemini-кадры: {images_ready}/4"
        if settings.image_api_key
        else "\n\n🖼 Gemini-кадры пропущены: не настроен GEMINI_API_KEY/NANA_BANANA_API_KEY."
    )
    return f"🎬 Reels: {topic}\n\n{scenario}\n\n{_storyboard_text(frames)}{image_note}"


def _gemini_reels_frame(prompt: str) -> bytes | None:
    return generate_gemini_image_sync(prompt, log_context="Gemini reels image")


def _apply_note_to_prompt(prompt: str, note: str) -> str:
    cleaned = note.strip()
    if not cleaned:
        return prompt
    return f"{prompt.rstrip('. ')}. Additional direction: {cleaned}."


async def _generate_storyboard_images(
    status_message,
    topic: str,
    frames: list[StoryboardFrame],
) -> list[bytes | None]:
    if not settings.image_api_key or not frames:
        return []

    loop = asyncio.get_event_loop()
    images: list[bytes | None] = [None] * len(frames[:4])
    processed: set[int] = set()
    done_count = 0
    total = len(images)

    async def gen_one(i: int, frame: StoryboardFrame) -> None:
        nonlocal done_count
        image = await loop.run_in_executor(_img_executor, _gemini_reels_frame, frame.gemini_prompt)
        images[i] = image
        processed.add(i)
        done_count += 1
        icons = "".join(
            ("✅" if images[idx] else "❌") if idx in processed else "⏳"
            for idx in range(total)
        )
        try:
            await status_message.edit_text(
                f"🎬 Тема: {topic}\n\n🖼 Кадры: {icons} {done_count}/{total}"
            )
        except Exception:
            pass

    await asyncio.gather(*[
        gen_one(i, frame)
        for i, frame in enumerate(frames[:4])
    ])
    return images


async def _load_topics(context: ContextTypes.DEFAULT_TYPE, results: list) -> list[str]:
    trends_text = _format_trends(results)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, generate_reels_topics_sync, trends_text)


async def cmd_reels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /reels нужен ANTHROPIC_API_KEY.")
        return

    from cache.store import cache
    from analytics.aggregator import collect_all

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    status = await update.message.reply_text("🎬 Генерирую темы для Reels...")
    topics = await _load_topics(context, results)

    if not topics:
        await status.edit_text("❌ Не удалось сгенерировать темы. Попробуй позже.")
        return

    context.user_data["rl_topics"] = topics
    context.user_data.pop("rl_review", None)
    context.user_data.pop("rl_awaiting_manual_edit", None)
    await status.edit_text(
        _topics_text(topics),
        parse_mode="Markdown",
        reply_markup=_topics_keyboard(topics),
    )


async def cb_reels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "rl:refresh":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Нет данных. Запусти /reels заново.")
            return
        await query.message.edit_text("🎬 Обновляю темы...")
        topics = await _load_topics(context, results)
        if not topics:
            await query.message.edit_text("❌ Не удалось обновить темы.")
            return
        context.user_data["rl_topics"] = topics
        await query.message.edit_text(
            _topics_text(topics),
            parse_mode="Markdown",
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data == "rl:review:manual":
        review = context.user_data.get("rl_review")
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        context.user_data["rl_awaiting_manual_edit"] = True
        await query.message.reply_text(
            "✏️ Пришли новый сценарий целиком одним сообщением.\n"
            "Потом я оставлю кнопки на согласование и пересборку раскадровки."
        )
        return

    if data.startswith("rl:frame:open:"):
        review = context.user_data.get("rl_review")
        idx = int(data.split(":")[3])
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        storyboard = review.get("storyboard", [])
        images = review.get("images", [])
        if idx >= len(storyboard):
            await query.message.reply_text("❌ Кадр не найден.")
            return
        frame = storyboard[idx]
        text = (
            f"🎞 Кадр {idx + 1}\n"
            f"Таймкод: {frame.get('timecode', '')}\n"
            f"Сцена: {frame.get('scene', '')}\n"
            f"Ракурс: {frame.get('angle', '')}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🖼 Перегенерировать", callback_data=f"rl:frame:regen:{idx}"),
                InlineKeyboardButton("✏️ Замечание", callback_data=f"rl:frame:note:{idx}"),
            ],
            [InlineKeyboardButton("↩️ К review", callback_data="rl:review:back")],
        ])
        if idx < len(images) and images[idx]:
            photo = io.BytesIO(images[idx])
            photo.name = f"reels_frame_{idx + 1}.png"
            await query.message.reply_photo(photo=photo, caption=text, reply_markup=keyboard)
        else:
            await query.message.reply_text(text + "\n\nкартинка ещё не сгенерирована", reply_markup=keyboard)
        return

    if data.startswith("rl:frame:regen:"):
        review = context.user_data.get("rl_review")
        idx = int(data.split(":")[3])
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        await _regen_reels_frame(query.message, context, idx)
        return

    if data.startswith("rl:frame:note:"):
        review = context.user_data.get("rl_review")
        idx = int(data.split(":")[3])
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        context.user_data["rl_awaiting_image_note"] = idx
        await query.message.reply_text(
            f"✏️ Пришли замечание для кадра {idx + 1}.\n"
            "Например: темнее, меньше предметов, ближе камера, без рук."
        )
        return

    if data == "rl:review:back":
        review = context.user_data.get("rl_review")
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        frames = [
            StoryboardFrame(
                timecode=str(frame.get("timecode", "")),
                scene=str(frame.get("scene", "")),
                angle=str(frame.get("angle", "")),
                gemini_prompt=str(frame.get("gemini_prompt", "")),
            )
            for frame in review.get("storyboard", [])
        ]
        images = [img for img in review.get("images", []) if img]
        draft_id = review.get("draft_id", "")
        await query.message.reply_text(
            f"{_reels_result_text(str(review.get('topic', '')), str(review.get('scenario', '')), frames, len(images))}\n\n🗂 Draft ID: {draft_id}",
            reply_markup=_review_keyboard(),
        )
        return

    if data == "rl:review:approve":
        review = context.user_data.get("rl_review")
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        draft_id = review.get("draft_id", "")
        if draft_id:
            update_draft(draft_id, status="approved")
        await query.message.reply_text(
            f"✅ Reels-черновик согласован.\n🗂 Draft ID: {draft_id}\n"
            f"Позже оцени результат через /drafts {draft_id}",
            reply_markup=append_mini_app_button(
                None,
                label="🧭 Открыть Reels в Mini App",
                draft_id=str(draft_id),
                tab="reels",
            ),
        )
        return

    if data == "rl:review:storyboard":
        review = context.user_data.get("rl_review")
        if not review:
            await query.message.reply_text("❌ Черновик Reels не найден. Сгенерируй заново.")
            return
        topic = review.get("topic", "")
        scenario = review.get("scenario", "")
        if not topic or not scenario:
            await query.message.reply_text("❌ Контекст потерян. Сгенерируй заново.")
            return
        status = await query.message.reply_text("🎥 Пересобираю раскадровку...")
        await _build_reels_review(status, query.message, context, topic, scenario, existing_draft_id=review.get("draft_id", ""))
        return

    if data.startswith("rl:pick:"):
        idx = int(data.split(":")[2])
        topics: list[str] = context.user_data.get("rl_topics", [])
        if not topics or idx >= len(topics):
            await query.message.reply_text("❌ Темы устарели — запусти /reels заново.")
            return

        topic = topics[idx]
        status = await query.message.reply_text(f"🎬 Тема: {topic}\n\n⏳ Пишу сценарий...")
        loop = asyncio.get_event_loop()
        scenario = await loop.run_in_executor(_executor, generate_reels_scenario_sync, topic)
        await _build_reels_review(status, query.message, context, topic, scenario)


async def _build_reels_review(
    status_message,
    reply_target,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
    scenario: str,
    *,
    existing_draft_id: str = "",
) -> None:
    loop = asyncio.get_event_loop()
    await status_message.edit_text(f"🎬 Тема: {topic}\n\n🎥 Готовлю раскадровку...")
    frames = await loop.run_in_executor(_executor, generate_reels_director_sync, topic, scenario)

    images_raw = await _generate_storyboard_images(status_message, topic, frames)
    images: list[bytes] = [image for image in images_raw if image]

    payload = {
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
        updated = update_draft(existing_draft_id, topic=topic, status="draft", payload=payload)
        draft_id = updated.draft_id if updated else existing_draft_id
    else:
        saved = save_draft(kind="reels", topic=topic, source="/reels", payload=payload)
        draft_id = saved.draft_id

    context.user_data["rl_review"] = {
        "draft_id": draft_id,
        "topic": topic,
        "scenario": scenario,
        "storyboard": payload["storyboard"],
        "images": images_raw,
    }
    context.user_data["rl_awaiting_manual_edit"] = False
    context.user_data["rl_awaiting_image_note"] = None

    await status_message.edit_text(
        f"{_reels_result_text(topic, scenario, frames, len(images))}\n\n🗂 Draft ID: {draft_id}",
        reply_markup=append_mini_app_button(
            _review_keyboard(),
            label="🧭 Открыть Reels в Mini App",
            draft_id=str(draft_id),
            tab="reels",
        ),
    )

    if images:
        media: list[InputMediaPhoto] = []
        for frame_idx, image in enumerate(images, 1):
            photo = io.BytesIO(image)
            photo.name = f"reels_storyboard_{frame_idx}.png"
            caption = f"Reels storyboard: {topic}" if frame_idx == 1 else None
            media.append(InputMediaPhoto(media=photo, caption=caption))
        await reply_target.reply_media_group(media)


async def msg_reels_manual_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    image_note_idx = context.user_data.get("rl_awaiting_image_note")
    if image_note_idx is not None:
        context.user_data["rl_awaiting_image_note"] = None
        note = (update.message.text or "").strip()
        if not note:
            return
        await _regen_reels_frame(update.message, context, int(image_note_idx), note=note)
        return

    if not context.user_data.get("rl_awaiting_manual_edit"):
        return

    review = context.user_data.get("rl_review")
    text = (update.message.text or "").strip()
    if not review:
        context.user_data["rl_awaiting_manual_edit"] = False
        await update.message.reply_text("❌ Контекст редактирования потерян. Сгенерируй Reels заново.")
        return
    if len(text) < 20:
        await update.message.reply_text("❌ Сценарий слишком короткий. Пришли полную версию.")
        return

    context.user_data["rl_awaiting_manual_edit"] = False
    status = await update.message.reply_text("✏️ Сохраняю сценарий и пересобираю раскадровку...")
    await _build_reels_review(
        status,
        update.message,
        context,
        str(review.get("topic", "")),
        text,
        existing_draft_id=str(review.get("draft_id", "")),
    )


async def _regen_reels_frame(message, context: ContextTypes.DEFAULT_TYPE, idx: int, *, note: str = "") -> None:
    review = context.user_data.get("rl_review")
    if not review:
        await message.reply_text("❌ Черновик Reels не найден.")
        return
    storyboard = review.get("storyboard", [])
    images = list(review.get("images", []))
    if idx >= len(storyboard):
        await message.reply_text("❌ Кадр не найден.")
        return
    if not settings.image_api_key:
        await message.reply_text("❌ Для генерации кадра нужен GEMINI_API_KEY/NANA_BANANA_API_KEY.")
        return

    frame = dict(storyboard[idx])
    prompt = str(frame.get("gemini_prompt", ""))
    if note:
        prompt = _apply_note_to_prompt(prompt, note)
        frame["gemini_prompt"] = prompt
        storyboard[idx] = frame

    status = await message.reply_text(f"🖼 Перегенерирую кадр {idx + 1}...")
    loop = asyncio.get_event_loop()
    image = await loop.run_in_executor(_img_executor, _gemini_reels_frame, prompt)
    await status.delete()
    if not image:
        await message.reply_text("⚠️ Gemini не сгенерировал кадр. Попробуй ещё раз.")
        return

    while len(images) <= idx:
        images.append(None)
    images[idx] = image
    review["storyboard"] = storyboard
    review["images"] = images
    context.user_data["rl_review"] = review

    draft_id = str(review.get("draft_id", ""))
    if draft_id:
        payload = {
            "scenario": str(review.get("scenario", "")),
            "storyboard": storyboard,
            "images_ready": sum(1 for item in images if item),
        }
        update_draft(draft_id, payload=payload, status="draft")

    photo = io.BytesIO(image)
    photo.name = f"reels_frame_{idx + 1}.png"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Перегенерировать", callback_data=f"rl:frame:regen:{idx}"),
            InlineKeyboardButton("✏️ Замечание", callback_data=f"rl:frame:note:{idx}"),
        ],
        [InlineKeyboardButton("↩️ К review", callback_data="rl:review:back")],
    ])
    frame_text = (
        f"🎞 Кадр {idx + 1}\n"
        f"Таймкод: {frame.get('timecode', '')}\n"
        f"Сцена: {frame.get('scene', '')}\n"
        f"Ракурс: {frame.get('angle', '')}"
    )
    await message.reply_photo(photo=photo, caption=frame_text, reply_markup=keyboard)


def build_reels_handler():
    return [
        CommandHandler("reels", cmd_reels),
        CallbackQueryHandler(cb_reels, pattern="^rl:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_reels_manual_edit),
    ]
