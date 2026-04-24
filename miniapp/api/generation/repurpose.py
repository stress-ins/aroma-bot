"""Background orchestration for the Repurpose Engine."""

from __future__ import annotations

import asyncio
import logging
import uuid

from bot.services.drafts_store import get_draft, save_draft, update_draft

from ._common import set_generation_state

logger = logging.getLogger(__name__)


async def complete_repurpose_generation(
    group_id: str,
    source_draft_id: str,
    target_formats: list[str],
    team_id: str | None = None,
    created_by: int | None = None,
) -> None:
    """Orchestrate repurpose: extract ideas → generate drafts in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    from db.models import RepurposeGroupModel
    from db.session import AsyncSessionLocal

    try:
        # 1. Get source draft
        source = await get_draft(source_draft_id)
        if not source:
            raise RuntimeError(f"Source draft {source_draft_id} not found")

        payload = source.payload or {}
        source_text = payload.get("caption", "") or payload.get("text", "")
        if not source_text:
            # Try threads_posts or series_posts
            for key in ("threads_posts", "series_posts"):
                posts = payload.get(key, [])
                texts = [p.get("text", "") or p.get("caption", "") for p in posts]
                source_text = " ".join(t for t in texts if t)
                if source_text:
                    break

        if not source_text:
            raise RuntimeError("Source draft has no text content")

        # 2. Extract core ideas
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=1)

        from bot.agents.repurpose_agent import extract_core_ideas_sync
        core = await loop.run_in_executor(executor, extract_core_ideas_sync, source_text, source.topic)

        # Update group with core ideas
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group:
                group.core_message = core["core_message"]
                group.key_points = core["key_points"]
                group.status = "generating"
                await session.commit()

        # 3. Create stub drafts for each format and launch generation
        enriched_topic = f"{source.topic}\n\nCore: {core['core_message']}"
        target_draft_entries = []

        # Inherit mood fields from source draft when present, else use the same
        # defaults as direct /api/generate/carousel so downstream regen + analytics
        # see consistent values.
        inherited_goal = payload.get("goal_key", "trust") or "trust"
        inherited_emotion = payload.get("emotion", "calm") or "calm"

        for fmt in target_formats:
            if fmt == source.kind:
                continue  # Skip same format as source

            stub_payload = {
                "generation_pending": True,
                "generation_stage": "content",
                "generation_message": f"Адаптирую в {fmt}...",
                "repurpose_group_id": group_id,
                "repurpose_source_draft_id": source_draft_id,
                "goal_key": inherited_goal,
                "format_key": fmt if fmt not in ("reels_v2",) else "instagram",
            }
            if fmt == "carousel":
                # Carousel-specific: persist mood fields so regen + analytics see them.
                stub_payload["emotion"] = inherited_emotion

            draft = await save_draft(
                kind=fmt,
                topic=source.topic,
                source="repurpose",
                payload=stub_payload,
                team_id=team_id,
                created_by=created_by,
            )
            target_draft_entries.append({
                "draft_id": draft.draft_id,
                "format": fmt,
                "status": "generating",
            })

        # Update group with target drafts
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group:
                group.target_drafts = target_draft_entries
                await session.commit()

        # 4. Launch generation tasks in parallel
        from miniapp.api.generation import (
            complete_carousel_generation,
            complete_content_generation,
            complete_reels_v2_generation,
            complete_series_generation,
            complete_threads_series_generation,
        )

        tasks = []
        for entry in target_draft_entries:
            fmt = entry["format"]
            did = entry["draft_id"]
            goal = inherited_goal

            if fmt == "carousel":
                tasks.append(complete_carousel_generation(
                    did, enriched_topic, None,
                    goal_key=goal, emotion=inherited_emotion,
                ))
            elif fmt == "reels_v2":
                tasks.append(complete_reels_v2_generation(did, enriched_topic, goal, "calm", None))
            elif fmt == "threads_series":
                tasks.append(complete_threads_series_generation(did, enriched_topic, goal, "", None, team_id))
            elif fmt == "content_series":
                tasks.append(complete_series_generation(did, enriched_topic, goal, "instagram", 5, "custom"))
            elif fmt in ("instagram", "telegram"):
                tasks.append(complete_content_generation(did, enriched_topic, goal, fmt, None))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 5. Update group status
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group:
                # Check each draft status
                updated_entries = []
                for entry in target_draft_entries:
                    d = await get_draft(entry["draft_id"])
                    p = d.payload if d else {}
                    status = "ready" if not p.get("generation_pending") and not p.get("generation_error") else "error"
                    updated_entries.append({**entry, "status": status})
                group.target_drafts = updated_entries
                group.status = "review"
                await session.commit()

    except Exception as exc:
        logger.error("Repurpose generation failed for group %s: %s", group_id, exc, exc_info=True)
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group:
                group.status = "error"
                await session.commit()
