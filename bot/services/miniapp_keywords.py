from __future__ import annotations

from keywords.registry import TOPICS, apply_custom
from keywords.store import FIELD_LABELS, add_word, remove_word


def serialize_topics() -> list[dict[str, object]]:
    return [
        {
            "topic_idx": idx,
            "name": topic.name,
            "fields": {
                "kw_ru": list(topic.keywords_ru),
                "kw_en": list(topic.keywords_en),
                "tag_ru": list(topic.hashtags_ru),
                "tag_en": list(topic.hashtags_en),
            },
        }
        for idx, topic in enumerate(TOPICS)
    ]


def field_labels() -> dict[str, str]:
    return dict(FIELD_LABELS)


def add_keyword(topic_idx: int, field: str, word: str) -> None:
    add_word(topic_idx, field, word)
    apply_custom()


def delete_keyword(topic_idx: int, field: str, word: str) -> None:
    remove_word(topic_idx, field, word)
    apply_custom()
