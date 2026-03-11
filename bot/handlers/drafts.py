from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.agents import ContentDraft, format_content_message
from bot.agents.reels_agent import StoryboardFrame
from bot.handlers.content import _draft_keyboard
from bot.handlers.reels import _review_keyboard, _reels_result_text
from bot.services.drafts_store import get_draft, list_recent_drafts


def _drafts_text(limit: int = 10) -> str:
    drafts = list_recent_drafts(limit=limit)
    if not drafts:
        return (
            "🗂 Черновиков пока нет.\n\n"
            "Сгенерируй что-нибудь через /content или /reels — я сохраню это в историю."
        )

    lines = ["🗂 Последние черновики:\n"]
    for idx, draft in enumerate(drafts, 1):
        lines.append(
            f"{idx}. [{draft.kind}] {draft.topic}\n"
            f"ID: {draft.draft_id} · Источник: {draft.source} · Статус: {draft.status}"
        )
    lines.append("\nОткрыть: /drafts <ID>")
    return "\n\n".join(lines)


async def cmd_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        await _open_draft(update, context, context.args[0].strip())
        return
    await update.message.reply_text(_drafts_text())


async def _open_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    draft = get_draft(draft_id)
    if not draft:
        await update.message.reply_text("❌ Черновик с таким ID не найден.")
        return

    if draft.kind == "reels":
        storyboard = [
            StoryboardFrame(
                timecode=str(item.get("timecode", "")),
                scene=str(item.get("scene", "")),
                angle=str(item.get("angle", "")),
                gemini_prompt=str(item.get("gemini_prompt", "")),
            )
            for item in draft.payload.get("storyboard", [])
        ]
        context.user_data["rl_review"] = {
            "draft_id": draft.draft_id,
            "topic": draft.topic,
            "scenario": str(draft.payload.get("scenario", "")),
            "storyboard": draft.payload.get("storyboard", []),
            "images": [],
        }
        await update.message.reply_text(
            f"{_reels_result_text(draft.topic, str(draft.payload.get('scenario', '')), storyboard, int(draft.payload.get('images_ready', 0)))}\n\n🗂 Draft ID: {draft.draft_id}\nСтатус: {draft.status}",
            reply_markup=_review_keyboard(),
        )
        return

    if draft.kind in {"threads", "instagram", "telegram"}:
        format_key = str(draft.payload.get("format_key", draft.kind))
        goal_key = str(draft.payload.get("goal_key", "trust"))
        content_draft = ContentDraft(
            angle=str(draft.payload.get("angle", "")),
            hook=str(draft.payload.get("hook", "")),
            caption=str(draft.payload.get("caption", "")),
            cta=str(draft.payload.get("cta", "")),
            hashtags=str(draft.payload.get("hashtags", "")),
            visual_prompt=str(draft.payload.get("visual_prompt", "")),
            slides=list(draft.payload.get("slides", [])),
        )
        context.user_data["content_last_draft_id"] = draft.draft_id
        context.user_data["content_last_topic"] = draft.topic
        context.user_data["content_last_goal"] = goal_key
        context.user_data["content_last_format"] = format_key
        context.user_data["content_review_draft"] = dict(draft.payload)
        await update.message.reply_text(
            f"{format_content_message(content_draft, draft.topic, goal_key, format_key)}\n\n🗂 Draft ID: {draft.draft_id}\nСтатус: {draft.status}",
            reply_markup=_draft_keyboard(),
        )
        return

    await update.message.reply_text(
        f"🗂 Draft ID: {draft.draft_id}\nТип: {draft.kind}\nТема: {draft.topic}\nСтатус: {draft.status}"
    )


def build_drafts_handler():
    return [
        CommandHandler("drafts", cmd_drafts),
    ]
