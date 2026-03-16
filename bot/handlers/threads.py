from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.gemini_images import generate_gemini_image_sync
from bot.handlers.threads_manager import publish_threads_keyboard, threads_api_enabled

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

_PROMPT_TOPICS = """\
Ты — стратег по росту в Threads. Ниша: ароматерапия. \
Цель: привлечь клиентов на корпоративные мероприятия и индивидуальные практики.

На основе трендов ниже предложи 10 тем для постов. \
Каждая = один цепляющий хук в стиле дерзкого маркетолога. \
Без банальностей. Без воды. Спорные, провокационные, те что хочется переслать.

Формат — строго пронумерованный список без пояснений:
1. [хук]
...
10. [хук]
"""

_PROMPT_POST = """\
Ты — копирайтер для Threads. Ниша: ароматерапия (корпоративные мероприятия + индивидуальные практики).
Сделай 3 поста для Threads на сегодня по теме: {topic}

Требования:
- Дай три блока в порядке: УТРО, ДЕНЬ, ВЕЧЕР
- Каждый пост = одна идея
- Каждый пост = 5-12 коротких строк
- Каждый пост = 40-120 слов
- Живой разговорный стиль, легко читать в мобильной ленте
- Утро: наблюдение, мысль или инсайт
- День: микро-экспертный пост
- Вечер: вопрос аудитории
- Иногда можно закончить вопросом
- Без хэштегов
- Без научных лекций, длинных объяснений и сложных терминов

Верни только текст поста — ничего больше.
"""

_PROMPT_IMAGE = """\
Based on this post topic: {topic}

Generate a short English image prompt (max 25 words) for Midjourney/Nana Banana.
Brand visual style: terracotta + beige + sage palette, dried herbs, incense smoke, stones, candles, hands, wood, fabric, soft natural light, minimal lifestyle atmosphere.
Forbidden: stock photo look, plastic, white background, harsh light.
End with: --ar 4:5 --style atmospheric

Return only the image prompt, nothing else.
"""


def _fix_dashes(text: str) -> str:
    """Replace em/en dashes with plain hyphen to avoid GPT-like style."""
    return text.replace("\u2014", "-").replace("\u2013", "-")


def _format_trends(results: list) -> str:
    parts = []
    for r in results:
        if not r.items or r.source_key in ("ai_recommendations",):
            continue
        top = r.items[:3]
        lines = [f"  • {i.title[:80]} {i.score}".strip() for i in top]
        parts.append(f"{r.source_name}:\n" + "\n".join(lines))
    return "\n\n".join(parts[:12])


def _claude_topics(trends_text: str) -> list[str]:
    from bot.services.claude_client import call_claude

    raw = call_claude(
        messages=[{"role": "user", "content": f"Тренды:\n{trends_text}"}],
        max_tokens=800,
        system=_PROMPT_TOPICS,
        context="threads topics",
    )
    topics: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            topics.append(line.split(". ", 1)[1].strip())
    return topics[:10]


def _claude_post_and_prompt(topic: str) -> tuple[str, str]:
    from bot.agents.content import _generate_strategist_sync
    from bot.agents.creative_team import edit_post_sync
    from bot.services.claude_client import call_claude

    # Strategist step: find angle and hook before writing
    angle, hook = _generate_strategist_sync(topic, goal_key="engagement", format_key="threads")
    strategist_context = ""
    if angle:
        strategist_context = (
            f"\n\nСтратегический угол: {angle}"
            f"\nПервая строка (хук): {hook}"
            f"\nИспользуй этот угол и хук в посте.\n"
        )

    raw_post = call_claude(
        messages=[{"role": "user", "content": _PROMPT_POST.format(topic=topic) + strategist_context}],
        max_tokens=900,
        context="threads post",
    )
    post_text = edit_post_sync(raw_post, topic, platform="threads")

    image_prompt = call_claude(
        messages=[{"role": "user", "content": _PROMPT_IMAGE.format(topic=topic)}],
        max_tokens=60,
        context="threads img prompt",
    )

    return post_text, image_prompt


def _gemini_image(prompt: str) -> bytes | None:
    return generate_gemini_image_sync(prompt, log_context="Gemini image")


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"tt:g:{i}") for i in range(len(topics))]
    # Split into rows of 5
    buttons = [row[i:i+5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="tt:topics")])
    return InlineKeyboardMarkup(buttons)


def _topics_text(topics: list[str], header: str) -> str:
    items = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
    return f"{header}\n\n{items}\n\nНажми номер темы — напишу пост и нарисую картинку:"


async def cmd_threads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    context.user_data["tt_topics"] = topics
    await msg.edit_text(
        _topics_text(topics, "📱 Темы для Threads на основе сегодняшних трендов:"),
        reply_markup=_topics_keyboard(topics),
    )


async def cb_threads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache
    from analytics.aggregator import collect_all

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tt:topics":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Нет данных. Сначала запроси /trends или /threads.")
            return
        await query.message.edit_text("🧠 Обновляю темы...")
        loop = asyncio.get_event_loop()
        trends_text = _format_trends(results)
        topics = await loop.run_in_executor(_executor, _claude_topics, trends_text)
        context.user_data["tt_topics"] = topics
        await query.message.edit_text(
            _topics_text(topics, "📱 Темы для Threads (обновлено):"),
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data.startswith("tt:g:"):
        idx = int(data.split(":")[2])
        topics: list[str] = context.user_data.get("tt_topics", [])
        if not topics or idx >= len(topics):
            await query.message.reply_text("❌ Темы устарели — запроси /threads снова.")
            return

        topic = topics[idx]
        status = await query.message.reply_text(
            f"✍️ Тема: {topic}\n\n⏳ Генерирую пост и картинку...",
        )

        loop = asyncio.get_event_loop()
        post_text, image_prompt = await loop.run_in_executor(
            _executor, _claude_post_and_prompt, topic
        )
        post_text = _fix_dashes(post_text)
        image_bytes = await loop.run_in_executor(_executor, _gemini_image, image_prompt)

        await status.delete()

        if image_bytes:
            await query.message.reply_photo(
                photo=image_bytes,
                caption=post_text,
            )
            if threads_api_enabled():
                context.user_data["threads_publish_text"] = post_text
                await query.message.reply_text(
                    "Если текст готов, можешь отправить его прямо в Threads:",
                    reply_markup=publish_threads_keyboard(),
                )
        else:
            context.user_data["tt_img_prompt"] = image_prompt
            if threads_api_enabled():
                context.user_data["threads_publish_text"] = post_text
            prompt_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("🖼 Промпт для картинки", callback_data="tt:prompt"),
            ]])
            await query.message.reply_text(post_text, reply_markup=prompt_btn)
            if threads_api_enabled():
                await query.message.reply_text(
                    "Если текст готов, можешь отправить его прямо в Threads:",
                    reply_markup=publish_threads_keyboard(),
                )

    if data == "tt:prompt":
        prompt = context.user_data.get("tt_img_prompt", "")
        if prompt:
            import html as _html
            await query.message.reply_text(
                f"🍌 Промпт для Nana Banana (1080×1350, --ar 4:5):\n\n"
                f"<pre>{_html.escape(prompt)}</pre>",
                parse_mode="HTML",
            )
        else:
            await query.message.reply_text("❌ Промпт не найден. Сгенерируй пост заново.")


def build_threads_handler():
    from telegram.ext import Application
    return [
        CommandHandler("threads", cmd_threads),
        CallbackQueryHandler(cb_threads, pattern="^tt:"),
    ]
