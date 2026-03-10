from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from bot.agents.content import BRAND_CONTEXT
from bot.services.threads_api import ThreadsCandidate
from config import settings


@dataclass
class ReplySuggestion:
    candidate_index: int
    reason: str
    draft_reply: str


def _extract_json(raw: str) -> list[dict]:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []


def suggest_replies_sync(candidates: list[ThreadsCandidate]) -> list[ReplySuggestion]:
    if not candidates:
        return []

    numbered = []
    for idx, item in enumerate(candidates):
        numbered.append(
            f"[{idx}] source={item.source}; author={item.author}; text={item.text}; "
            f"root={item.root_text or '-'}; permalink={item.permalink}"
        )

    prompt = f"""\
{BRAND_CONTEXT}

Ты — community manager и редактор для Threads.
Нужно решить, на какие входящие сообщения в Threads сейчас стоит ответить от имени автора.

Правила:
- Выбирай только те сообщения, где ответ реально может усилить доверие, вовлечение или мягко вести к диалогу.
- Не предлагай отвечать на спам, слишком пустые реакции, агрессию без смысла.
- Ответ должен быть коротким, естественным, человеческим, без ИИ-стиля.
- Не обещай лечение и не давай медицинских рекомендаций.
- Если автор пишет о стрессе, перегрузе, сне, телесном состоянии — можно отвечать теплее и конкретнее.
- Верни максимум 5 лучших вариантов.

Кандидаты:
{chr(10).join(numbered)}

Верни строго JSON-массив объектов вида:
[
  {{
    "candidate_index": 0,
    "reason": "почему стоит ответить",
    "draft_reply": "готовый ответ"
  }}
]
"""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    payload = _extract_json(raw)

    suggestions: list[ReplySuggestion] = []
    for item in payload:
        try:
            suggestions.append(
                ReplySuggestion(
                    candidate_index=int(item["candidate_index"]),
                    reason=str(item["reason"]).strip(),
                    draft_reply=str(item["draft_reply"]).strip(),
                )
            )
        except Exception:
            continue
    return suggestions[:5]
