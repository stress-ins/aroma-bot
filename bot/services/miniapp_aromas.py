from __future__ import annotations

from bot.services.miniapp_references import (
    get_reference_card,
    list_reference_cards,
    update_reference_card,
)


async def list_aromas() -> list[dict[str, str]]:
    return await list_reference_cards("aroma")


async def get_aroma_card(slug_or_name: str) -> dict[str, object] | None:
    return await get_reference_card("aroma", slug_or_name)


async def update_aroma_card(slug: str, payload: dict[str, object]) -> dict[str, object] | None:
    return await update_reference_card("aroma", slug, payload)
