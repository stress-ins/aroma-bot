"""Background generation tasks for blend construction."""
from __future__ import annotations

import asyncio

from bot.services.miniapp_references import build_reference_context


async def generate_blend_construct(body, telegram_id: int | None = None) -> dict:
    """Generate a blend via 3 parallel agents: expert + doctor + compatibility checker."""
    from bot.agents.aromatherapy_expert import construct_blend_sync
    from bot.agents.compatibility_checker import get_incompatible_oils_sync
    from bot.agents.medical_reviewer import review_blend_sync
    from bot.services.llm_cache import get_cached, make_cache_key, set_cached
    from bot.services.miniapp_references import list_reference_cards

    # Check cache
    effects_str = ",".join(sorted(body.effects)) if body.effects else ""
    custom_str = ",".join(sorted(body.custom_oils)) if body.custom_oils else ""
    cache_key = make_cache_key(
        "blend",
        brief=body.brief.lower().strip(),
        effects=effects_str,
        speed=body.speed,
        application=body.application,
        contraindications=body.contraindications.strip().lower(),
        custom_oils=custom_str,
    )
    cached = await get_cached(cache_key)
    if cached:
        return cached

    reference_context = await build_reference_context(
        categories=("aroma",), max_items_per_category=20, max_total_chars=3000
    )

    loop = asyncio.get_running_loop()

    expert_task = loop.run_in_executor(
        None,
        construct_blend_sync,
        body.brief,
        body.effects,
        body.speed,
        body.application,
        body.contraindications,
        reference_context,
        body.custom_oils or None,
    )
    doctor_task = loop.run_in_executor(
        None,
        review_blend_sync,
        body.brief,
        body.effects,
        body.contraindications,
        reference_context,
    )
    incompat_task = loop.run_in_executor(
        None,
        get_incompatible_oils_sync,
        body.effects,
        body.brief,
    )

    from fastapi import HTTPException

    try:
        expert_result, doctor_result, incompat_result = await asyncio.wait_for(
            asyncio.gather(expert_task, doctor_task, incompat_task),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="blend_generation_timeout")

    # Match oils to DB entries
    oils = expert_result.get("oils", [])
    aromas = await list_reference_cards("aroma")
    aroma_map = {}
    for a in aromas:
        name = (a.get("name") or "").lower()
        name_en = (a.get("name_en") or "").lower()
        aroma_map[name] = a
        if name_en:
            aroma_map[name_en] = a

    oils_with_db = []
    for oil in oils:
        name_ru = oil.get("name_ru", "")
        name_en = oil.get("name_en", "")
        match = aroma_map.get(name_ru.lower()) or aroma_map.get(name_en.lower())
        oils_with_db.append({
            **oil,
            "db_id": match.get("id") if match else None,
            "in_db": match is not None,
        })

    result = {
        "title": expert_result.get("title", "Смесь"),
        "oils": oils_with_db,
        "total_drops": sum(o.get("drops", 0) for o in oils_with_db),
        "profile": expert_result.get("profile", {}),
        "expert_note": expert_result.get("explanation", ""),
        "doctor_note": doctor_result.get("summary", ""),
        "safety_status": doctor_result.get("status", "safe"),
        "restrictions": doctor_result.get("restrictions", []),
        "incompatible_oils": incompat_result if isinstance(incompat_result, list) else [],
        "application_guide": expert_result.get("application", ""),
        "tags": expert_result.get("tags", []),
    }

    # Store in cache (7 days, per-user)
    await set_cached(cache_key, "blend", result, ttl_hours=168, telegram_id=telegram_id)

    return result
