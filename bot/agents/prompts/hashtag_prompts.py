"""Prompt templates for the Hashtag Recommender agent."""

from __future__ import annotations


def extract_themes_prompt(text: str, platform: str) -> str:
    return f"""\
Проанализируй текст поста для {platform} и извлеки 3-5 ключевых тем.

Текст:
{text[:1500]}

Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{{"themes": ["тема1_рус|theme1_eng", "тема2_рус|theme2_eng"]}}

Примеры: ароматерапия|aromatherapy, эфирные масла|essential oils, лаванда|lavender, сон|sleep, стресс|stress.
Не выдумывай темы, которых нет в тексте. Верни ТОЛЬКО валидный JSON."""
