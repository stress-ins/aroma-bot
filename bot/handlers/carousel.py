from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import settings
from bot.handlers.threads import _format_trends, _claude_topics, _fix_dashes, _topics_text

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

_PROMPT_CAROUSEL = """\
Ты — дизайнер карусели для Threads/Instagram. Ниша: ароматерапия (корпоративные мероприятия + индивидуальные практики).
Создай карусель из 5 слайдов по теме: {topic}

Требования:
- Слайд 1: цепляющий хук, до 60 символов
- Слайды 2-4: один тезис + 1-2 предложения, всего до 120 символов на слайд
- Слайд 5: призыв к действию, до 80 символов
- Живой язык, от первого лица, без клише и длинных тире
- Дай базовый промпт для фото (английский, 15-25 слов) в стиле Nana Banana: палитра терракота + беж + шалфей, природные элементы (травы, благовония, камни, свечи), мягкий свет, атмосферно. Заканчивай: --ar 4:5 --style atmospheric

Формат — строго:
SLIDE1: [текст]
SLIDE2: [текст]
SLIDE3: [текст]
SLIDE4: [текст]
SLIDE5: [текст]
IMG_PROMPT: [базовый промпт]
"""


def _claude_carousel(topic: str) -> tuple[list[str], str]:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        messages=[{"role": "user", "content": _PROMPT_CAROUSEL.format(topic=topic)}],
    )
    text = resp.content[0].text.strip()
    slides: list[str] = []
    img_prompt = ""
    for line in text.splitlines():
        line = line.strip()
        for i in range(1, 6):
            if line.startswith(f"SLIDE{i}:"):
                slides.append(_fix_dashes(line.split(":", 1)[1].strip()))
        if line.startswith("IMG_PROMPT:"):
            img_prompt = line.split(":", 1)[1].strip()
    return slides, img_prompt


def _gemini_slide(prompt: str) -> bytes | None:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data
    except Exception as exc:
        logger.warning("Gemini carousel error: %s", str(exc)[:120])
    return None


def _make_slide_prompts_with_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (картинка с текстом):\n"]
    for i, slide in enumerate(slides, 1):
        lines.append(f"Слайд {i}: {base}, text overlay: \"{slide}\", minimal clean design")
    return "\n".join(lines)


def _make_slide_prompts_no_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (чистый фон, без текста):\n"]
    for i, slide in enumerate(slides, 1):
        lines.append(f"Слайд {i} ({slide[:60]}): {base}, visual theme: {slide[:60]}, clean minimal background, negative space for text, no typography")
    return "\n".join(lines)


def _format_for_canva(slides: list[str]) -> str:
    SLIDE_LABELS = ["Слайд 1 — Хук", "Слайд 2", "Слайд 3", "Слайд 4", "Слайд 5 — CTA"]
    parts = ["📋 Тексты для Canva:\n"]
    for i, slide in enumerate(slides):
        label = SLIDE_LABELS[i] if i < len(SLIDE_LABELS) else f"Слайд {i + 1}"
        parts.append(f"━━━ {label} ━━━\n{slide}")
    parts.append("\n💡 Используй как фон изображения из Nana Banana (без текста), добавляй текст в Canva из Brand Kit.")
    return "\n\n".join(parts)


def _carousel_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"ca:g:{i}") for i in range(len(topics))]
    buttons = [row[i:i+5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="ca:topics")])
    return InlineKeyboardMarkup(buttons)


def _action_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍌 Nana Banana (с текстом)", callback_data="ca:prompt:text"),
            InlineKeyboardButton("🍌 Nana Banana (без текста)", callback_data="ca:prompt:notxt"),
        ],
        [InlineKeyboardButton("📋 Тексты для Canva", callback_data="ca:prompt:canva")],
    ])


async def cmd_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache
    from analytics.aggregator import collect_all

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды для генерации тем...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    msg = await update.message.reply_text("🧠 Анализирую тренды, генерирую темы...")

    loop = asyncio.get_event_loop()
    trends_text = _format_trends(results)
    topics = await loop.run_in_executor(_executor, _claude_topics, trends_text)

    if not topics:
        await msg.edit_text("❌ Не удалось сгенерировать темы. Попробуй позже.")
        return

    context.user_data["ca_topics"] = topics
    await msg.edit_text(
        _topics_text(topics, "🎠 Темы для карусели на основе сегодняшних трендов:"),
        reply_markup=_carousel_keyboard(topics),
    )


async def cb_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "ca:topics":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Нет данных. Сначала запроси /trends или /carousel.")
            return
        await query.message.edit_text("🧠 Обновляю темы...")
        loop = asyncio.get_event_loop()
        trends_text = _format_trends(results)
        topics = await loop.run_in_executor(_executor, _claude_topics, trends_text)
        context.user_data["ca_topics"] = topics
        await query.message.edit_text(
            _topics_text(topics, "🎠 Темы для карусели (обновлено):"),
            reply_markup=_carousel_keyboard(topics),
        )
        return

    if data.startswith("ca:g:"):
        idx = int(data.split(":")[2])
        topics: list[str] = context.user_data.get("ca_topics", [])
        if not topics or idx >= len(topics):
            await query.message.reply_text("❌ Темы устарели — запроси /carousel снова.")
            return

        topic = topics[idx]
        status = await query.message.reply_text(
            f"🎠 Тема: {topic}\n\n⏳ Генерирую карусель и картинки..."
        )

        loop = asyncio.get_event_loop()
        slides, img_prompt = await loop.run_in_executor(_executor, _claude_carousel, topic)

        if not slides:
            await status.edit_text("❌ Не удалось сгенерировать карусель. Попробуй позже.")
            return

        # Try to generate images for each slide
        media: list[InputMediaPhoto] = []
        for i, slide in enumerate(slides):
            slide_prompt = f"{img_prompt}, text overlay: \"{slide[:60]}\", minimal clean design"
            img_bytes = await loop.run_in_executor(_executor, _gemini_slide, slide_prompt)
            if img_bytes:
                caption = f"Слайд {i+1}: {slide}"
                media.append(InputMediaPhoto(media=img_bytes, caption=caption))

        await status.delete()

        # Always store slides for action buttons
        context.user_data["ca_slides"] = slides
        context.user_data["ca_img_prompt"] = img_prompt

        # Always send slide texts
        slides_text = "\n\n".join(f"Слайд {i+1}:\n{s}" for i, s in enumerate(slides))
        await query.message.reply_text(f"📝 Тексты слайдов:\n\n{slides_text}")

        if media:
            for i in range(0, len(media), 10):
                await query.message.reply_media_group(media[i:i+10])
            await query.message.reply_text(
                "🎨 Хочешь использовать Nana Banana + Canva вместо автогенерации?",
                reply_markup=_action_buttons(),
            )
        else:
            await query.message.reply_text(
                "⚠️ Картинки не удалось сгенерировать автоматически.\n"
                "Сгенерируй фоны в Nana Banana и собери в Canva:",
                reply_markup=_action_buttons(),
            )
        return

    if data == "ca:prompt:text":
        slides = context.user_data.get("ca_slides", [])
        img_prompt = context.user_data.get("ca_img_prompt", "")
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(_make_slide_prompts_with_text(img_prompt, slides))
        return

    if data == "ca:prompt:notxt":
        slides = context.user_data.get("ca_slides", [])
        img_prompt = context.user_data.get("ca_img_prompt", "")
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(_make_slide_prompts_no_text(img_prompt, slides))
        return

    if data == "ca:prompt:canva":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(_format_for_canva(slides))


def build_carousel_handler():
    return [
        CommandHandler("carousel", cmd_carousel),
        CallbackQueryHandler(cb_carousel, pattern="^ca:"),
    ]
