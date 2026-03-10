from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import settings
from bot.handlers.threads import _format_trends, _claude_topics, _fix_dashes, _topics_text

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# ── PPTX layout constants ──────────────────────────────────────────────────
_SLIDE_EMU = 1080 * 9525          # 1080 px → EMU (square 1:1)
_SLIDE_LABELS = ["Слайд 1 — Хук", "Слайд 2", "Слайд 3", "Слайд 4", "Слайд 5 — CTA"]

# ── Prompts ────────────────────────────────────────────────────────────────
_PROMPT_CAROUSEL = """\
Ты — дизайнер карусели для Instagram. Ниша: регуляция нервной системы через сенсорные практики \
(ароматерапия, медитации, гонг).
Создай карусель из 5 слайдов по теме: {topic}

Требования:
- Слайд 1: цепляющий хук, до 60 символов
- Слайды 2-4: один тезис + 1-2 предложения, всего до 120 символов на слайд
- Слайд 5: призыв к действию, до 80 символов
- Живой язык, от первого лица, без клише и длинных тире
- Дай базовый промпт для фото (английский, 15-25 слов) в стиле Nana Banana: \
палитра терракота + беж + шалфей, природные элементы (травы, благовония, камни, свечи), \
мягкий свет, атмосферно, square 1:1 composition. Заканчивай: --ar 1:1 --style atmospheric

Формат — строго:
SLIDE1: [текст]
SLIDE2: [текст]
SLIDE3: [текст]
SLIDE4: [текст]
SLIDE5: [текст]
IMG_PROMPT: [базовый промпт]
"""


# ── Claude helpers ─────────────────────────────────────────────────────────

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


# ── Gemini image generation ────────────────────────────────────────────────

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


# ── PPTX builder ───────────────────────────────────────────────────────────

def _build_pptx(slides: list[str], images: list[bytes | None] | None = None) -> bytes:
    from pptx import Presentation
    from pptx.util import Emu, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    BEIGE = RGBColor(0xF2, 0xE8, 0xD9)
    DARK  = RGBColor(0x3D, 0x2B, 0x1F)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    prs = Presentation()
    prs.slide_width  = Emu(_SLIDE_EMU)
    prs.slide_height = Emu(_SLIDE_EMU)
    blank = prs.slide_layouts[6]

    for i, text in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        img_bytes = (images[i] if images and i < len(images) else None)
        has_img = bool(img_bytes)

        if has_img:
            slide.shapes.add_picture(
                io.BytesIO(img_bytes), Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU)
            )
            text_color = WHITE
        else:
            bg = slide.shapes.add_shape(1, Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU))
            bg.fill.solid()
            bg.fill.fore_color.rgb = BEIGE
            bg.line.color.rgb = BEIGE
            text_color = DARK

        # Text box at bottom 40%
        margin = Emu(60000)
        box_top  = Emu(int(_SLIDE_EMU * 0.60))
        box_h    = Emu(int(_SLIDE_EMU * 0.40))
        txBox = slide.shapes.add_textbox(
            margin, box_top, Emu(_SLIDE_EMU) - margin * 2, box_h
        )
        txBox.fill.background()

        tf = txBox.text_frame
        tf.word_wrap = True

        label = _SLIDE_LABELS[i] if i < len(_SLIDE_LABELS) else f"Слайд {i + 1}"
        p_lbl = tf.paragraphs[0]
        p_lbl.alignment = PP_ALIGN.CENTER
        r_lbl = p_lbl.add_run()
        r_lbl.text = label
        r_lbl.font.size = Pt(14)
        r_lbl.font.color.rgb = text_color

        p_txt = tf.add_paragraph()
        p_txt.space_before = Pt(8)
        p_txt.alignment = PP_ALIGN.CENTER
        r_txt = p_txt.add_run()
        r_txt.text = text
        r_txt.font.size = Pt(24)
        r_txt.font.bold = True
        r_txt.font.color.rgb = text_color

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


# ── Prompt text helpers ────────────────────────────────────────────────────

def _make_slide_prompts_with_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (картинка с текстом):\n"]
    for i, slide in enumerate(slides, 1):
        lines.append(f"Слайд {i}: {base}, text overlay: \"{slide}\", minimal clean design")
    return "\n".join(lines)


def _make_slide_prompts_no_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (чистый фон, без текста):\n"]
    for i, slide in enumerate(slides, 1):
        lines.append(
            f"Слайд {i} ({slide[:60]}): {base}, visual theme: {slide[:60]}, "
            "clean minimal background, negative space for text, no typography"
        )
    return "\n".join(lines)


def _format_for_canva(slides: list[str]) -> str:
    parts = ["📋 Тексты для Canva:\n"]
    for i, slide in enumerate(slides):
        label = _SLIDE_LABELS[i] if i < len(_SLIDE_LABELS) else f"Слайд {i + 1}"
        parts.append(f"━━━ {label} ━━━\n{slide}")
    parts.append(
        "\n💡 Используй как фон изображения из Nana Banana (без текста), "
        "добавляй текст в Canva из Brand Kit."
    )
    return "\n\n".join(parts)


# ── Keyboards ──────────────────────────────────────────────────────────────

def _carousel_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"ca:g:{i}") for i in range(len(topics))]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="ca:topics")])
    return InlineKeyboardMarkup(buttons)


def _action_buttons_no_images() -> InlineKeyboardMarkup:
    """Buttons when Gemini failed — offer prompts + PPTX text-only."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍌 Nana Banana (без текста)", callback_data="ca:prompt:notxt"),
            InlineKeyboardButton("🍌 Nana Banana (с текстом)",  callback_data="ca:prompt:text"),
        ],
        [
            InlineKeyboardButton("📄 PPTX (только тексты)", callback_data="ca:pptx:noimg"),
            InlineKeyboardButton("📋 Тексты для Canva",     callback_data="ca:prompt:canva"),
        ],
    ])


def _pptx_from_my_images_button(count: int) -> InlineKeyboardMarkup:
    """Button to build PPTX from user-sent images."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"📄 Собрать PPTX ({count}/5 картинок)",
            callback_data="ca:pptx:userimages",
        )
    ]])


def _canva_buttons() -> InlineKeyboardMarkup:
    """Shown after successful Gemini images — quick access to Canva texts."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Тексты для Canva", callback_data="ca:prompt:canva"),
    ]])


# ── Handlers ───────────────────────────────────────────────────────────────

async def cmd_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache
    from analytics.aggregator import collect_all

    context.user_data["ca_awaiting_images"] = False
    context.user_data["ca_user_image_ids"] = []

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды для генерации тем...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    msg = await update.message.reply_text("🧠 Анализирую тренды, генерирую темы...")
    loop = asyncio.get_event_loop()
    topics = await loop.run_in_executor(_executor, _claude_topics, _format_trends(results))

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

    # ── Refresh topics ───────────────────────────────────────────────────
    if data == "ca:topics":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Нет данных. Сначала запроси /trends или /carousel.")
            return
        await query.message.edit_text("🧠 Обновляю темы...")
        loop = asyncio.get_event_loop()
        topics = await loop.run_in_executor(
            _executor, _claude_topics, _format_trends(results)
        )
        context.user_data["ca_topics"] = topics
        await query.message.edit_text(
            _topics_text(topics, "🎠 Темы для карусели (обновлено):"),
            reply_markup=_carousel_keyboard(topics),
        )
        return

    # ── Generate carousel for selected topic ─────────────────────────────
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

        context.user_data["ca_slides"]     = slides
        context.user_data["ca_img_prompt"] = img_prompt
        context.user_data["ca_awaiting_images"] = False
        context.user_data["ca_user_image_ids"]  = []

        # Generate images (no text overlay — text goes in PPTX/Canva)
        images: list[bytes | None] = []
        for slide in slides:
            slide_prompt = (
                f"{img_prompt}, visual theme inspired by: {slide[:50]}, "
                "clean minimal background, no text, no typography, square 1:1 composition"
            )
            img = await loop.run_in_executor(_executor, _gemini_slide, slide_prompt)
            images.append(img)

        await status.delete()

        # Send slide texts
        slides_text = "\n\n".join(f"Слайд {i+1}:\n{s}" for i, s in enumerate(slides))
        await query.message.reply_text(f"📝 Тексты слайдов:\n\n{slides_text}")

        all_ok = all(images)
        context.user_data["ca_gemini_images"] = images

        if all_ok:
            # Build and send PPTX with embedded images
            pptx_bytes = await loop.run_in_executor(_executor, _build_pptx, slides, images)
            await query.message.reply_document(
                document=io.BytesIO(pptx_bytes),
                filename="carousel.pptx",
                caption=(
                    "📄 PPTX готов — фоны уже вставлены.\n"
                    "Загрузи в Canva и настрой шрифт / цвета из Brand Kit."
                ),
            )
            # Also send Canva texts for convenience
            await query.message.reply_text(
                "Нужны тексты отдельно?",
                reply_markup=_canva_buttons(),
            )
        else:
            # Some images failed
            generated = sum(1 for img in images if img)
            # Show what was generated as preview
            media = [
                InputMediaPhoto(media=img, caption=f"Слайд {i+1}: {slides[i]}")
                for i, img in enumerate(images) if img
            ]
            if media:
                await query.message.reply_media_group(media)

            await query.message.reply_text(
                f"⚠️ Сгенерировано {generated}/5 картинок.\n"
                "Сгенерируй остальные в Nana Banana и пришли сюда — соберу PPTX.\n"
                "Или скачай PPTX с текстами и добавь картинки сам в Canva:",
                reply_markup=_action_buttons_no_images(),
            )
            context.user_data["ca_awaiting_images"] = True
        return

    # ── Prompt buttons ───────────────────────────────────────────────────
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
        context.user_data["ca_awaiting_images"] = True
        await query.message.reply_text(
            "📸 Сгенерировал в Nana Banana? Пришли картинки сюда (по одной или все сразу) — "
            "я соберу PPTX с ними."
        )
        return

    if data == "ca:prompt:canva":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(_format_for_canva(slides))
        return

    # ── PPTX: text only (no images) ──────────────────────────────────────
    if data == "ca:pptx:noimg":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        loop = asyncio.get_event_loop()
        pptx_bytes = await loop.run_in_executor(_executor, _build_pptx, slides, None)
        await query.message.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel_texts.pptx",
            caption=(
                "📄 PPTX с текстами (без фонов).\n"
                "В Canva замени фон каждого слайда на картинку из Nana Banana."
            ),
        )
        return

    # ── PPTX: from user-sent images ───────────────────────────────────────
    if data == "ca:pptx:userimages":
        slides = context.user_data.get("ca_slides", [])
        image_ids: list[str] = context.user_data.get("ca_user_image_ids", [])
        if not slides or not image_ids:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return

        status = await query.message.reply_text(
            f"⏳ Скачиваю {len(image_ids)} картинок и собираю PPTX..."
        )

        images: list[bytes | None] = []
        for file_id in image_ids[:5]:
            try:
                tg_file = await context.bot.get_file(file_id)
                buf = await tg_file.download_as_bytearray()
                images.append(bytes(buf))
            except Exception as exc:
                logger.warning("Failed to download user image: %s", exc)
                images.append(None)

        loop = asyncio.get_event_loop()
        pptx_bytes = await loop.run_in_executor(_executor, _build_pptx, slides, images)
        await status.delete()
        await query.message.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel_with_images.pptx",
            caption=(
                "📄 PPTX с твоими картинками готов.\n"
                "Загрузи в Canva и настрой шрифты / цвета из Brand Kit."
            ),
        )
        context.user_data["ca_awaiting_images"] = False
        return


async def msg_carousel_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect user-sent photos when awaiting images for PPTX."""
    if not context.user_data.get("ca_awaiting_images"):
        return

    photo = update.message.photo[-1]  # best quality
    ids: list[str] = context.user_data.setdefault("ca_user_image_ids", [])

    if len(ids) >= 5:
        await update.message.reply_text("✅ Уже 5 картинок — нажми кнопку для сборки PPTX.")
        return

    ids.append(photo.file_id)
    count = len(ids)

    if count < 5:
        await update.message.reply_text(
            f"✅ Получено {count}/5. Пришли ещё или собирай PPTX сейчас:",
            reply_markup=_pptx_from_my_images_button(count),
        )
    else:
        await update.message.reply_text(
            "✅ Все 5 картинок получены! Собираю PPTX:",
            reply_markup=_pptx_from_my_images_button(count),
        )


def build_carousel_handler():
    return [
        CommandHandler("carousel", cmd_carousel),
        CallbackQueryHandler(cb_carousel, pattern="^ca:"),
        MessageHandler(filters.PHOTO, msg_carousel_photo),
    ]
