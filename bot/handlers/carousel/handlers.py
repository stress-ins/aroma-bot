"""Telegram command, callback, and message handlers for the carousel flow."""
from __future__ import annotations

import asyncio
import html as _html
import io
import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import sys

from config import settings
from bot.handlers.threads import _format_trends
import bot.handlers.carousel.generation as _gen
import bot.handlers.carousel.pptx as _pptx_mod
import bot.handlers.carousel.keyboards as _kb
import bot.handlers.carousel.formatters as _fmt


def _pkg():
    """Return the parent package module (for test monkeypatch compatibility)."""
    return sys.modules["bot.handlers.carousel"]

logger = logging.getLogger(__name__)


# ── Slide-level display ─────────────────────────────────────────────────────

async def _show_slide_for_edit(
    target,
    idx: int,
    slides: list[str],
    images: list[bytes | None],
) -> None:
    """Send a single slide (image + text) with edit action buttons."""
    label = _gen.get_slide_label(idx, len(slides))
    text = slides[idx]
    img = images[idx] if idx < len(images) else None
    caption = f"<b>{_html.escape(label)}</b>\n\n{_html.escape(text)}"

    if img:
        await target.reply_photo(
            photo=img,
            caption=caption,
            parse_mode="HTML",
            reply_markup=_kb._slide_actions_keyboard(idx),
        )
    else:
        await target.reply_text(
            caption + "\n\n<i>картинка не сгенерирована</i>",
            parse_mode="HTML",
            reply_markup=_kb._slide_actions_keyboard(idx),
        )


# ── Parallel image generation ────────────────────────────────────────────────

async def _run_image_generation(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    skip_existing: bool = False,
) -> None:
    """Generate slide images sequentially (Gemini has strict rate limits)."""
    slides      = context.user_data.get("ca_slides", [])
    img_prompts = context.user_data.get("ca_img_prompts", [])
    existing    = context.user_data.get("ca_gemini_images", [])
    n = len(slides)
    loop = asyncio.get_event_loop()

    # Start from existing images, extend to n slots
    images: list[bytes | None] = list(existing) + [None] * max(0, n - len(existing))

    # Which indices need generation
    indices = [
        i for i in range(n)
        if not (skip_existing and i < len(existing) and existing[i])
    ]

    if not indices:
        await msg.reply_text("✅ Все картинки уже готовы!")
        return

    processed: set[int] = set()
    # Pre-mark skipped slots as already processed
    for j in range(n):
        if j not in indices:
            processed.add(j)

    progress_msg = await msg.reply_text(
        f"🖼 Генерирую картинки: {'⏳' * n} 0/{len(indices)}"
    )
    done_count = 0

    async def gen_one(i: int) -> None:
        nonlocal done_count
        prompt = img_prompts[i] if i < len(img_prompts) else _gen._FALLBACK_IMG_PROMPT
        img = await loop.run_in_executor(_gen._img_executor, _gen._gemini_slide, prompt, i)
        images[i] = img
        processed.add(i)
        done_count += 1
        icons = "".join(
            ("✅" if images[j] else "❌") if j in processed else "⏳"
            for j in range(n)
        )
        try:
            await progress_msg.edit_text(
                f"🖼 Картинки: {icons} {done_count}/{len(indices)}"
            )
        except Exception:
            logger.warning("gen_one: progress_msg failed", exc_info=True)
            pass
    await asyncio.gather(*[gen_one(i) for i in indices])

    try:
        await progress_msg.delete()
    except Exception:
        logger.warning("gen_one: progress_msg failed", exc_info=True)
        pass

    context.user_data["ca_gemini_images"] = images
    generated  = sum(1 for img in images if img)
    has_failed = generated < n

    # ── QA phase ─────────────────────────────────────────────────────────
    qa_results: dict[int, tuple[bool, str]] = {}
    generated_indices = [i for i, img in enumerate(images) if img]
    last_note = context.user_data.get("ca_last_note", "")

    if generated_indices and settings.anthropic_api_key:
        # ── QA round 1 ───────────────────────────────────────────────────
        qa_icons = ["➖"] * n
        for i in generated_indices:
            qa_icons[i] = "⏳"
        qa_progress = await msg.reply_text(
            f"🔍 Проверяю: {''.join(qa_icons)} 0/{len(generated_indices)}"
        )
        qa_done = 0

        async def qa_one(i: int) -> None:
            nonlocal qa_done
            prompt_i = img_prompts[i] if i < len(img_prompts) else ""
            passed, reason = await loop.run_in_executor(
                _gen._executor, _gen._qa_image_sync, images[i], prompt_i, last_note, i
            )
            qa_results[i] = (passed, reason)
            qa_done += 1
            qa_icons[i] = "✅" if passed else "⚠️"
            try:
                await qa_progress.edit_text(
                    f"🔍 Проверяю: {''.join(qa_icons)} {qa_done}/{len(generated_indices)}"
                )
            except Exception:
                logger.warning("qa_one: qa_progress failed", exc_info=True)
                pass

        await asyncio.gather(*[qa_one(i) for i in generated_indices])

        # ── Auto-rerender failed QA images ───────────────────────────────
        failed_qa = [i for i, (passed, _) in qa_results.items() if not passed]
        if failed_qa:
            for i in failed_qa:
                _, reason = qa_results[i]
                fix_note = f"fix: {reason}" if reason and reason.upper() != "OK" else "avoid impossible elements"
                old_prompt = img_prompts[i] if i < len(img_prompts) else _gen._FALLBACK_IMG_PROMPT
                img_prompts[i] = _gen._apply_note_to_prompt(old_prompt, fix_note)
                qa_icons[i] = "🔄"

            try:
                await qa_progress.edit_text(
                    f"🔄 Перерендер: {''.join(qa_icons)} — исправляю {len(failed_qa)} сл."
                )
            except Exception:
                logger.warning("handlers: suppressed exception", exc_info=True)
                pass

            regen_done = 0

            async def regen_one(i: int) -> None:
                nonlocal regen_done
                img = await loop.run_in_executor(_gen._img_executor, _gen._gemini_slide, img_prompts[i], i)
                images[i] = img
                regen_done += 1
                qa_icons[i] = "⏳" if img else "❌"
                try:
                    await qa_progress.edit_text(
                        f"🔄 Перерендер: {''.join(qa_icons)} {regen_done}/{len(failed_qa)}"
                    )
                except Exception:
                    logger.warning("regen_one: qa_progress failed", exc_info=True)
                    pass

            await asyncio.gather(*[regen_one(i) for i in failed_qa])

            # ── QA round 2 ───────────────────────────────────────────────
            regenned = [i for i in failed_qa if images[i]]
            qa2_done = 0

            async def qa_two(i: int) -> None:
                nonlocal qa2_done
                prompt_i = img_prompts[i] if i < len(img_prompts) else ""
                passed, reason = await loop.run_in_executor(
                    _gen._executor, _gen._qa_image_sync, images[i], prompt_i, last_note, i
                )
                qa_results[i] = (passed, reason)
                qa2_done += 1
                qa_icons[i] = "✅" if passed else "⚠️"
                try:
                    await qa_progress.edit_text(
                        f"🔍 Повторная проверка: {''.join(qa_icons)} {qa2_done}/{len(regenned)}"
                    )
                except Exception:
                    logger.warning("qa_two: qa_progress failed", exc_info=True)
                    pass

            if regenned:
                await asyncio.gather(*[qa_two(i) for i in regenned])

            context.user_data["ca_img_prompts"] = img_prompts
            context.user_data["ca_gemini_images"] = images

        try:
            await qa_progress.delete()
        except Exception:
            logger.warning("qa_two: qa_progress failed", exc_info=True)
            pass

    # Send all images in order
    for i, img in enumerate(images):
        if img:
            label = _gen.get_slide_label(i, len(slides))
            caption = f"<b>{_html.escape(label)}</b>\n{_html.escape(slides[i])}"
            passed, reason = qa_results.get(i, (True, ""))
            if not passed and reason and reason.upper() != "OK":
                caption += f"\n\n⚠️ <i>{_html.escape(reason)}</i>"
            try:
                await msg.reply_photo(photo=img, caption=caption, parse_mode="HTML")
            except Exception:
                logger.warning("handlers: suppressed exception", exc_info=True)
                pass

    if not has_failed:
        pptx_bytes = await loop.run_in_executor(_gen._executor, _pptx_mod._build_pptx, slides, images)
        await msg.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel.pptx",
            caption=(
                "📄 PPTX готов — фоны уже вставлены.\n"
                "Загрузи в Canva и настрой шрифт / цвета из Brand Kit."
            ),
        )
    else:
        await msg.reply_text(
            f"⚠️ Сгенерировано {generated}/{n} картинок. "
            "Нажми «🔄 Повторить ❌» чтобы попробовать ещё раз."
        )

    await msg.reply_text(
        "✏️ Нажми номер слайда чтобы изменить:",
        reply_markup=_kb._review_keyboard(n, has_failed=has_failed),
    )


# ── Shared carousel generation helper ───────────────────────────────────────

async def _run_carousel(query_or_message, context: ContextTypes.DEFAULT_TYPE,
                        topic: str, status_msg) -> None:
    """Generate slide texts only. User then triggers image generation manually."""
    loop = asyncio.get_event_loop()

    await status_msg.edit_text(
        f"🎠 Тема: {topic}\n\n⏳ Генерирую черновик → прогоняю через редактора..."
    )

    slides, img_prompts, arc, angle, hook = await loop.run_in_executor(
        _gen._executor, _gen._generate_carousel_sync, topic
    )

    if not slides:
        target = query_or_message if hasattr(query_or_message, "reply_text") else query_or_message.message
        try:
            await status_msg.edit_text("❌ Не удалось сгенерировать карусель. Попробуй позже.")
        except Exception:
            await target.reply_text("❌ Не удалось сгенерировать карусель. Попробуй позже.")
        return

    context.user_data["ca_slides"]           = slides
    context.user_data["ca_img_prompts"]      = img_prompts
    context.user_data["ca_arc"]              = arc
    context.user_data["ca_topic"]            = topic
    context.user_data["ca_gemini_images"]    = []
    context.user_data["ca_awaiting_images"]  = False
    context.user_data["ca_user_image_ids"]   = []

    try:
        _kb._persist_carousel_draft(context, topic, slides, img_prompts, angle=angle, hook=hook)
    except Exception:
        logger.exception("carousel: failed to save draft for topic: %s", topic)

    target = query_or_message if hasattr(query_or_message, "reply_text") else query_or_message.message

    keyboard = _kb._text_review_keyboard(len(slides))

    lines = []
    for i, s in enumerate(slides):
        label = _gen.get_slide_label(i, len(slides))
        lines.append(f"<b>{_html.escape(label)}</b>\n{_html.escape(s)}")
    slides_body = "\n\n".join(lines)

    header = "📝 <b>Тексты слайдов готовы:</b>\n\n"
    footer = "\n\nНажми номер слайда чтобы изменить, или генерируй картинки:"
    full_text = header + slides_body + footer

    # Telegram HTML limit is ~4096 rendered chars; split into two messages if needed
    if len(full_text) <= 4096:
        try:
            await status_msg.edit_text(full_text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            try:
                await status_msg.delete()
            except Exception:
                logger.warning("handlers: suppressed exception", exc_info=True)
                pass
            await target.reply_text(full_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        # Send first half of slides, then second half + keyboard
        mid = len(slides) // 2
        part1 = header + "\n\n".join(lines[:mid])
        part2 = "\n\n".join(lines[mid:]) + footer
        try:
            await status_msg.edit_text(part1, parse_mode="HTML")
        except Exception:
            try:
                await status_msg.delete()
            except Exception:
                logger.warning("handlers: suppressed exception", exc_info=True)
                pass
            await target.reply_text(part1, parse_mode="HTML")
        await target.reply_text(part2, parse_mode="HTML", reply_markup=keyboard)


# ── Command handler ──────────────────────────────────────────────────────────

async def cmd_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /carousel нужен ANTHROPIC_API_KEY.")
        return

    context.user_data["ca_awaiting_images"]    = False
    context.user_data["ca_awaiting_topic"]     = False
    context.user_data["ca_awaiting_slide_edit"] = None
    context.user_data["ca_user_image_ids"]     = []

    await update.message.reply_text(
        "🎠 *Карусель для Instagram*\n\nВыбери, откуда взять тему:",
        parse_mode="Markdown",
        reply_markup=_kb._source_keyboard(),
    )


# ── Callback handler ─────────────────────────────────────────────────────────

async def cb_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache
    from analytics.aggregator import collect_all

    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Source: trends ────────────────────────────────────────────────────
    if data == "ca:source:trends":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Собираю тренды...")
            results = await collect_all()
            cache.set("results", results)

        await query.message.edit_text("🧠 Генерирую темы на основе трендов...")
        loop = asyncio.get_event_loop()
        topics = await loop.run_in_executor(
            _gen._executor, _pkg()._claude_topics_carousel, _format_trends(results)
        )

        if not topics:
            await query.message.edit_text("❌ Не удалось сгенерировать темы. Попробуй позже.")
            return

        context.user_data["ca_topics"] = topics
        items = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
        await query.message.edit_text(
            f"📈 Темы из трендов:\n\n{items}\n\nНажми номер — сгенерирую карусель:",
            reply_markup=_kb._topics_keyboard(topics),
        )
        return

    # ── Source: custom topic ──────────────────────────────────────────────
    if data == "ca:source:custom":
        context.user_data["ca_awaiting_topic"] = True
        await query.message.edit_text(
            "✏️ Напиши тему для карусели одним сообщением.\n\n"
            "Например:\n"
            "— как запах помогает выйти из тревожной петли\n"
            "— 5 минут утром: сенсорный ритуал для старта\n"
            "— почему корпоративный wellbeing не работает без тела"
        )
        return

    # ── Pick topic from list ──────────────────────────────────────────────
    if data.startswith("ca:g:"):
        idx = int(data.split(":")[2])
        topics: list[str] = context.user_data.get("ca_topics", [])
        if not topics or idx >= len(topics):
            await query.message.reply_text("❌ Темы устарели — запроси /carousel снова.")
            return

        topic = topics[idx]
        status = await query.message.reply_text("⏳ Начинаю...")
        try:
            await _run_carousel(query, context, topic, status)
        except Exception:
            logger.exception("_run_carousel failed")
            await query.message.reply_text("❌ Ошибка при генерации. Попробуй ещё раз.")
        return

    # ── Prompt buttons ────────────────────────────────────────────────────
    if data in ("ca:prompt:text", "ca:prompt:notxt"):
        slides     = context.user_data.get("ca_slides", [])
        img_prompts = context.user_data.get("ca_img_prompts", [])
        topic      = context.user_data.get("ca_topic", "")
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        if not img_prompts:
            gen_msg = await query.message.reply_text("⏳ Генерирую промпты для картинок...")
            loop = asyncio.get_event_loop()
            img_prompts = await loop.run_in_executor(
                _gen._executor, _gen._generate_slide_image_prompts_sync, slides, topic
            )
            context.user_data["ca_img_prompts"] = img_prompts
            await gen_msg.delete()
        if data == "ca:prompt:text":
            await query.message.reply_text(
                _fmt._make_slide_prompts_with_text(img_prompts, slides),
                parse_mode="HTML",
            )
        else:
            await query.message.reply_text(
                _fmt._make_slide_prompts_no_text(img_prompts, slides),
                parse_mode="HTML",
            )
            context.user_data["ca_awaiting_images"] = True
            await query.message.reply_text(
                "📸 Сгенерировал в Nana Banana? Пришли картинки сюда — я соберу PPTX."
            )
        return

    if data == "ca:prompt:canva":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(_fmt._format_for_canva(slides), parse_mode="HTML")
        return

    # ── Generate images (first time) ──────────────────────────────────────
    if data == "ca:gen:images":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await _run_image_generation(query.message, context, skip_existing=False)
        return

    # ── Regen ALL images with a note ─────────────────────────────────────
    if data == "ca:regen:all:imgnote":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        context.user_data["ca_awaiting_img_note"] = {"idx": None, "skip_existing": False}
        await query.message.reply_text(
            "✏️ Напиши замечание — применю ко всем картинкам.\n"
            "<i>Например: более тёмные тона, без рук, добавить свечи, минималистичнее</i>",
            parse_mode="HTML",
        )
        return

    # ── Retry failed images — ask for note first ──────────────────────────
    if data == "ca:regen:failed:note":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        context.user_data["ca_awaiting_img_note"] = {"idx": None, "skip_existing": True}
        await query.message.reply_text(
            "✏️ Напиши замечание к картинкам — что изменить, добавить или убрать.\n"
            "<i>Например: более тёмные тона, без рук, добавить свечи, минималистичнее</i>",
            parse_mode="HTML",
        )
        return

    # ── Retry failed images — no note (kept for backward compat) ─────────
    if data == "ca:regen:failed":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await _run_image_generation(query.message, context, skip_existing=True)
        return

    # ── Review screen ─────────────────────────────────────────────────────
    if data == "ca:review":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        images = context.user_data.get("ca_gemini_images", [])
        if images:
            has_failed = any(img is None for img in images[:len(slides)])
            await query.message.reply_text(
                "✏️ Нажми номер слайда чтобы изменить:",
                reply_markup=_kb._review_keyboard(len(slides), has_failed=has_failed),
            )
        else:
            await query.message.reply_text(
                "✏️ Нажми номер слайда чтобы изменить, или генерируй картинки:",
                reply_markup=_kb._text_review_keyboard(len(slides)),
            )
        return

    # ── Regenerate whole carousel with same topic ──────────────────────────
    if data == "ca:regen:all":
        topic = context.user_data.get("ca_topic", "")
        if not topic:
            await query.message.reply_text("❌ Тема не найдена. Запроси /carousel заново.")
            return
        status = await query.message.reply_text("🔄 Пересоздаю карусель...")
        try:
            await _run_carousel(query, context, topic, status)
        except Exception:
            logger.exception("_run_carousel (regen) failed")
            await query.message.reply_text("❌ Ошибка при генерации. Попробуй ещё раз.")
        return

    # ── Slide editor ──────────────────────────────────────────────────────
    if data.startswith("ca:edit:"):
        parts = data.split(":")
        idx = int(parts[2])
        action = parts[3] if len(parts) > 3 else ""
        slides = context.user_data.get("ca_slides", [])
        images = context.user_data.get("ca_gemini_images", [])
        topic  = context.user_data.get("ca_topic", "")
        img_prompts = context.user_data.get("ca_img_prompts", [])

        if not slides or idx >= len(slides):
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return

        # ── Show slide ────────────────────────────────────────────────────
        if not action:
            await _show_slide_for_edit(query.message, idx, slides, images)
            return

        # ── AI: regenerate text (+ image) ─────────────────────────────────
        if action == "ai":
            status = await query.message.reply_text(
                f"🔄 Генерирую новый текст для слайда {idx + 1}..."
            )
            loop = asyncio.get_event_loop()
            new_text = await loop.run_in_executor(
                _gen._executor, _gen._regen_slide_text_sync, topic, slides, idx
            )
            slides[idx] = new_text
            context.user_data["ca_slides"] = slides

            if img_prompts and idx < len(img_prompts):
                await status.edit_text(f"🖼 Обновляю картинку для слайда {idx + 1}...")
                new_img = await loop.run_in_executor(
                    _gen._img_executor, _gen._gemini_slide, img_prompts[idx]
                )
                if new_img:
                    while len(images) <= idx:
                        images.append(None)
                    images[idx] = new_img
                    context.user_data["ca_gemini_images"] = images

            await status.delete()
            await _show_slide_for_edit(query.message, idx, slides, images)
            return

        # ── Manual: wait for user text ────────────────────────────────────
        if action == "manual":
            context.user_data["ca_awaiting_slide_edit"] = idx
            label = _gen.get_slide_label(idx, len(slides))
            await query.message.reply_text(
                f"✏️ Введи новый текст для <b>{_html.escape(label)}</b>:\n"
                f"<i>Просто напиши следующим сообщением</i>",
                parse_mode="HTML",
            )
            return

        # ── Regenerate image only ─────────────────────────────────────────
        if action == "img":
            if not img_prompts or idx >= len(img_prompts):
                await query.message.reply_text("❌ Промт для картинки не найден.")
                return
            status = await query.message.reply_text(
                f"🖼 Генерирую новую картинку для слайда {idx + 1}..."
            )
            loop = asyncio.get_event_loop()
            new_img = await loop.run_in_executor(
                _gen._img_executor, _gen._gemini_slide, img_prompts[idx]
            )
            await status.delete()
            if new_img:
                while len(images) <= idx:
                    images.append(None)
                images[idx] = new_img
                context.user_data["ca_gemini_images"] = images
            else:
                await query.message.reply_text("⚠️ Gemini не сгенерировал картинку. Попробуй ещё раз.")
            await _show_slide_for_edit(query.message, idx, slides, images)
            return

        # ── Regenerate image with user note ──────────────────────────────
        if action == "imgnote":
            if not img_prompts or idx >= len(img_prompts):
                await query.message.reply_text("❌ Промт для картинки не найден.")
                return
            context.user_data["ca_awaiting_img_note"] = {"idx": idx, "skip_existing": False}
            label = _gen.get_slide_label(idx, len(slides))
            await query.message.reply_text(
                f"✏️ Замечание для картинки <b>{_html.escape(label)}</b>:\n"
                "<i>Что изменить, добавить или убрать?</i>\n"
                "<i>Например: темнее, без рук, добавить свечи, более абстрактно</i>",
                parse_mode="HTML",
            )
            return

    # ── Final PPTX from current state ─────────────────────────────────────
    if data == "ca:pptx:final":
        slides = context.user_data.get("ca_slides", [])
        images = context.user_data.get("ca_gemini_images", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        status = await query.message.reply_text("⏳ Собираю PPTX...")
        loop = asyncio.get_event_loop()
        pptx_bytes = await loop.run_in_executor(_gen._executor, _pptx_mod._build_pptx, slides, images or None)
        await status.delete()
        await query.message.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel_final.pptx",
            caption="📄 PPTX из текущей версии карусели.",
        )
        return

    # ── PPTX: text only ───────────────────────────────────────────────────
    if data == "ca:pptx:noimg":
        slides = context.user_data.get("ca_slides", [])
        if not slides:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        loop = asyncio.get_event_loop()
        pptx_bytes = await loop.run_in_executor(_gen._executor, _pptx_mod._build_pptx, slides, None)
        await query.message.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel_texts.pptx",
            caption="📄 PPTX с текстами (без фонов). Замени фон в Canva на картинки из Nana Banana.",
        )
        return

    # ── PPTX: from user images ────────────────────────────────────────────
    if data == "ca:pptx:userimages":
        slides    = context.user_data.get("ca_slides", [])
        image_ids = context.user_data.get("ca_user_image_ids", [])
        if not slides or not image_ids:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return

        status = await query.message.reply_text(
            f"⏳ Скачиваю {len(image_ids)} картинок и собираю PPTX..."
        )
        images: list[bytes | None] = []
        for file_id in image_ids[:len(slides)]:
            try:
                tg_file = await context.bot.get_file(file_id)
                buf = await tg_file.download_as_bytearray()
                images.append(bytes(buf))
            except Exception as exc:
                logger.warning("Failed to download user image: %s", exc)
                images.append(None)

        loop = asyncio.get_event_loop()
        pptx_bytes = await loop.run_in_executor(_gen._executor, _pptx_mod._build_pptx, slides, images)
        await status.delete()
        await query.message.reply_document(
            document=io.BytesIO(pptx_bytes),
            filename="carousel_with_images.pptx",
            caption="📄 PPTX с твоими картинками готов. Загрузи в Canva и настрой шрифты / цвета.",
        )
        context.user_data["ca_awaiting_images"] = False
        return


# ── Message handlers ──────────────────────────────────────────────────────────

async def msg_carousel_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input — either a new topic or manual slide edit."""
    text = (update.message.text or "").strip()

    # ── Image note received ────────────────────────────────────────────────
    img_note_state = context.user_data.get("ca_awaiting_img_note")
    if img_note_state is not None:
        if not text:
            return
        context.user_data["ca_awaiting_img_note"] = None
        context.user_data["ca_last_note"] = text
        slides     = context.user_data.get("ca_slides", [])
        img_prompts = list(context.user_data.get("ca_img_prompts", []))
        images     = context.user_data.get("ca_gemini_images", [])
        slide_idx_note  = img_note_state.get("idx")        # None = all failed
        skip_existing   = img_note_state.get("skip_existing", False)

        if not slides:
            await update.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return

        if slide_idx_note is None:
            # Apply note to all prompts (for retry-failed flow)
            img_prompts = [_gen._apply_note_to_prompt(p, text) for p in img_prompts]
        else:
            # Apply note to single slide prompt
            if slide_idx_note < len(img_prompts):
                img_prompts[slide_idx_note] = _gen._apply_note_to_prompt(
                    img_prompts[slide_idx_note], text
                )

        context.user_data["ca_img_prompts"] = img_prompts

        if slide_idx_note is None:
            await _run_image_generation(update.message, context, skip_existing=skip_existing)
        else:
            status = await update.message.reply_text(
                f"🖼 Генерирую картинку для слайда {slide_idx_note + 1} с замечанием..."
            )
            loop = asyncio.get_event_loop()
            new_img = await loop.run_in_executor(
                _gen._img_executor, _gen._gemini_slide, img_prompts[slide_idx_note]
            )
            await status.delete()
            if new_img:
                while len(images) <= slide_idx_note:
                    images.append(None)
                images[slide_idx_note] = new_img
                context.user_data["ca_gemini_images"] = images
            else:
                await update.message.reply_text("⚠️ Gemini не сгенерировал картинку. Попробуй ещё раз.")
            await _show_slide_for_edit(update.message, slide_idx_note, slides, images)
        return

    # ── Manual slide edit ──────────────────────────────────────────────────
    slide_idx = context.user_data.get("ca_awaiting_slide_edit")
    if slide_idx is not None:
        if not text:
            return
        slides = context.user_data.get("ca_slides", [])
        images = context.user_data.get("ca_gemini_images", [])
        img_prompts = context.user_data.get("ca_img_prompts", [])

        if not slides or slide_idx >= len(slides):
            await update.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            context.user_data["ca_awaiting_slide_edit"] = None
            return

        slides[slide_idx] = text
        context.user_data["ca_slides"] = slides
        context.user_data["ca_awaiting_slide_edit"] = None

        # Regenerate image for the edited slide
        if img_prompts and slide_idx < len(img_prompts):
            status = await update.message.reply_text("✅ Текст обновлён! 🖼 Генерирую картинку...")
            loop = asyncio.get_event_loop()
            new_img = await loop.run_in_executor(
                _gen._executor, _gen._gemini_slide, img_prompts[slide_idx]
            )
            await status.delete()
            if new_img:
                while len(images) <= slide_idx:
                    images.append(None)
                images[slide_idx] = new_img
                context.user_data["ca_gemini_images"] = images

        await _show_slide_for_edit(update.message, slide_idx, slides, images)
        return

    # ── New carousel topic ─────────────────────────────────────────────────
    if not context.user_data.get("ca_awaiting_topic"):
        return

    if len(text) < 5:
        await update.message.reply_text("❌ Тема слишком короткая. Опиши подробнее.")
        return

    context.user_data["ca_awaiting_topic"] = False
    status = await update.message.reply_text("⏳ Начинаю...")
    try:
        await _run_carousel(update.message, context, text, status)
    except Exception:
        logger.exception("_run_carousel (topic msg) failed")
        await update.message.reply_text("❌ Ошибка при генерации. Попробуй ещё раз.")


async def msg_carousel_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect user-sent photos for PPTX assembly."""
    if not context.user_data.get("ca_awaiting_images"):
        return

    photo = update.message.photo[-1]
    ids: list[str] = context.user_data.setdefault("ca_user_image_ids", [])
    slides = context.user_data.get("ca_slides", [])
    max_slides = len(slides) if slides else 10

    if len(ids) >= max_slides:
        await update.message.reply_text(
            f"✅ Уже {max_slides} картинок — нажми кнопку для сборки PPTX."
        )
        return

    ids.append(photo.file_id)
    count = len(ids)

    await update.message.reply_text(
        f"✅ Получено {count}/{max_slides}."
        + ("" if count < max_slides else " Все получены!") +
        " Пришли ещё или собирай PPTX:" if count < max_slides else " Собирай PPTX:",
        reply_markup=_kb._pptx_from_my_images_button(count),
    )


def build_carousel_handler():
    return [
        CommandHandler("carousel", cmd_carousel),
        CallbackQueryHandler(cb_carousel, pattern="^ca:"),
        MessageHandler(filters.PHOTO, msg_carousel_photo),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_carousel_topic),
    ]
