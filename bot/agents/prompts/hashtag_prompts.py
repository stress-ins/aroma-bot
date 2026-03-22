"""Prompt templates for the Hashtag Recommender agent."""

from __future__ import annotations


def extract_themes_prompt(text: str, platform: str) -> str:
    return f"""\
Проанализируй текст поста для {platform} и извлеки 3-5 ключевых тем.

Текст:
{text[:1500]}

Верни строго в формате (список тем на русском и английском):
THEME: [тема на русском] | [theme in English]
THEME: ...

Примеры тем: ароматерапия, эфирные масла, лаванда, сон, стресс, медитация, гонг, wellness, selfcare, нервная система.
Не выдумывай темы, которых нет в тексте."""
