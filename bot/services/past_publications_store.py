from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select, delete

from db.models import PastPublicationModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_SENTINEL = object()


@dataclass
class PastPublicationRecord:
    pub_id: str
    team_id: str | None
    created_by: int | None
    draft_id: str | None
    platform: str
    kind: str
    external_url: str
    external_id: str
    topic: str
    caption: str
    hashtags: list[str]
    published_at: str | None
    likes: int
    comments: int
    shares: int
    saves: int
    views: int
    score_engagement: int | None
    score_brand_fit: int | None
    score_craft: int | None
    score_goal_hit: int | None
    content_pillar: str
    funnel_stage: str
    notes: str
    created_at: str
    updated_at: str

    @property
    def avg_score(self) -> float | None:
        scores = [s for s in (self.score_engagement, self.score_brand_fit, self.score_craft, self.score_goal_hit) if s is not None]
        return round(sum(scores) / len(scores), 1) if scores else None

    @classmethod
    def from_model(cls, m: PastPublicationModel) -> PastPublicationRecord:
        def _dt(v: datetime | None) -> str | None:
            if v is None:
                return None
            return v.isoformat() if isinstance(v, datetime) else str(v)

        return cls(
            pub_id=m.pub_id,
            team_id=m.team_id,
            created_by=m.created_by,
            draft_id=m.draft_id,
            platform=m.platform,
            kind=m.kind,
            external_url=m.external_url or "",
            external_id=m.external_id or "",
            topic=m.topic or "",
            caption=m.caption or "",
            hashtags=list(m.hashtags) if m.hashtags else [],
            published_at=_dt(m.published_at),
            likes=m.likes or 0,
            comments=m.comments or 0,
            shares=m.shares or 0,
            saves=m.saves or 0,
            views=m.views or 0,
            score_engagement=m.score_engagement,
            score_brand_fit=m.score_brand_fit,
            score_craft=m.score_craft,
            score_goal_hit=m.score_goal_hit,
            content_pillar=m.content_pillar or "",
            funnel_stage=m.funnel_stage or "",
            notes=m.notes or "",
            created_at=_dt(m.created_at) or "",
            updated_at=_dt(m.updated_at) or "",
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["avg_score"] = self.avg_score
        return d


async def create_publication(
    *,
    platform: str,
    team_id: str | None = None,
    created_by: int | None = None,
    draft_id: str | None = None,
    kind: str = "text",
    external_url: str = "",
    external_id: str = "",
    topic: str = "",
    caption: str = "",
    hashtags: list[str] | None = None,
    published_at: datetime | None = None,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    saves: int = 0,
    views: int = 0,
    score_engagement: int | None = None,
    score_brand_fit: int | None = None,
    score_craft: int | None = None,
    score_goal_hit: int | None = None,
    content_pillar: str = "",
    funnel_stage: str = "",
    notes: str = "",
) -> PastPublicationRecord:
    pub_id = uuid4().hex[:12]
    async with AsyncSessionLocal() as session:
        model = PastPublicationModel(
            pub_id=pub_id,
            team_id=team_id,
            created_by=created_by,
            draft_id=draft_id,
            platform=platform,
            kind=kind,
            external_url=external_url,
            external_id=external_id,
            topic=topic.strip(),
            caption=caption.strip(),
            hashtags=list(hashtags) if hashtags else [],
            published_at=published_at,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            views=views,
            score_engagement=score_engagement,
            score_brand_fit=score_brand_fit,
            score_craft=score_craft,
            score_goal_hit=score_goal_hit,
            content_pillar=content_pillar,
            funnel_stage=funnel_stage,
            notes=notes,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return PastPublicationRecord.from_model(model)


async def update_publication(pub_id: str, **kwargs: Any) -> PastPublicationRecord | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PastPublicationModel).filter(PastPublicationModel.pub_id == pub_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None

        allowed = {
            "platform", "kind", "external_url", "external_id", "topic", "caption",
            "hashtags", "published_at", "likes", "comments", "shares", "saves", "views",
            "score_engagement", "score_brand_fit", "score_craft", "score_goal_hit",
            "content_pillar", "funnel_stage", "notes", "draft_id",
        }
        for key, value in kwargs.items():
            if key in allowed and value is not _SENTINEL:
                if key == "hashtags" and value is not None:
                    value = list(value)
                setattr(model, key, value)

        await session.commit()
        await session.refresh(model)
        return PastPublicationRecord.from_model(model)


async def delete_publication(pub_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(PastPublicationModel).where(PastPublicationModel.pub_id == pub_id)
        )
        await session.commit()
        return result.rowcount > 0


async def get_publication(pub_id: str) -> PastPublicationRecord | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PastPublicationModel).filter(PastPublicationModel.pub_id == pub_id)
        )
        model = result.scalar_one_or_none()
        return PastPublicationRecord.from_model(model) if model else None


async def find_by_external_id(platform: str, external_id: str) -> PastPublicationRecord | None:
    if not external_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PastPublicationModel).filter(
                PastPublicationModel.platform == platform,
                PastPublicationModel.external_id == external_id,
            )
        )
        model = result.scalar_one_or_none()
        return PastPublicationRecord.from_model(model) if model else None


async def list_publications(
    team_id: str | None = None,
    *,
    platform: str | None = None,
    rated_only: bool = False,
    unrated_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[PastPublicationRecord]:
    async with AsyncSessionLocal() as session:
        query = select(PastPublicationModel).order_by(PastPublicationModel.published_at.desc().nullslast())
        if team_id is not None:
            query = query.filter(
                or_(PastPublicationModel.team_id == team_id, PastPublicationModel.team_id.is_(None))
            )
        if platform:
            query = query.filter(PastPublicationModel.platform == platform)
        if rated_only:
            query = query.filter(PastPublicationModel.score_engagement.isnot(None))
        if unrated_only:
            query = query.filter(PastPublicationModel.score_engagement.is_(None))
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        return [PastPublicationRecord.from_model(m) for m in result.scalars().all()]


async def get_stats(team_id: str | None = None) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        base = select(PastPublicationModel)
        if team_id is not None:
            base = base.filter(
                or_(PastPublicationModel.team_id == team_id, PastPublicationModel.team_id.is_(None))
            )

        # Total count
        total_q = select(func.count()).select_from(base.subquery())
        total = (await session.execute(total_q)).scalar() or 0

        # Rated count
        rated_base = base.filter(PastPublicationModel.score_engagement.isnot(None))
        rated_q = select(func.count()).select_from(rated_base.subquery())
        rated = (await session.execute(rated_q)).scalar() or 0

        # Average scores
        avg_scores: dict[str, float | None] = {}
        for col_name in ("score_engagement", "score_brand_fit", "score_craft", "score_goal_hit"):
            col = getattr(PastPublicationModel, col_name)
            avg_q = select(func.avg(col)).select_from(base.subquery())
            val = (await session.execute(avg_q)).scalar()
            avg_scores[col_name] = round(float(val), 1) if val is not None else None

        all_avgs = [v for v in avg_scores.values() if v is not None]
        avg_score = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else None

        return {
            "total": total,
            "rated": rated,
            "avg_score": avg_score,
            "avg_scores": avg_scores,
        }


async def bulk_create(
    publications: list[dict[str, Any]],
    *,
    team_id: str | None = None,
    created_by: int | None = None,
) -> dict[str, int]:
    imported = 0
    skipped = 0
    for pub_data in publications:
        ext_id = pub_data.get("external_id", "")
        platform = pub_data.get("platform", "")
        if ext_id and platform:
            existing = await find_by_external_id(platform, ext_id)
            if existing:
                skipped += 1
                continue
        pub_data.setdefault("team_id", team_id)
        pub_data.setdefault("created_by", created_by)
        await create_publication(**pub_data)
        imported += 1
    return {"imported": imported, "skipped": skipped}
