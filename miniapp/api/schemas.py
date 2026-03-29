"""Pydantic response models for key API endpoints.

Provides type-safe response_model declarations that:
- Document the API contract
- Validate outgoing data
- Strip unexpected fields from responses
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Drafts ────────────────────────────────────────────────────────────────────


class DraftSummaryItem(BaseModel):
    """Compact draft representation for list views."""
    draft_id: str
    seq_id: int | None = None
    kind: str = ""
    topic: str = ""
    source: str = ""
    created_at: str | None = None
    status: str = ""
    feedback: str = ""
    preview: str = ""
    slides_count: int = 0
    storyboard_count: int = 0
    images_ready: int = 0
    generation_pending: bool = False
    generation_stage: str = ""
    generation_message: str = ""
    generation_error: str = ""
    created_by: int | None = None
    metrics_summary: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class DraftListResponse(BaseModel):
    """Response for GET /api/drafts."""
    items: list[DraftSummaryItem]
    total: int


class DraftDetailResponse(BaseModel):
    """Response for GET /api/drafts/{id} - full draft with payload."""
    draft_id: str
    seq_id: int | None = None
    kind: str = ""
    topic: str = ""
    source: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    status: str = ""
    feedback: str = ""
    preview: str = ""
    slides_count: int = 0
    storyboard_count: int = 0
    images_ready: int = 0
    generation_pending: bool = False
    generation_stage: str = ""
    generation_message: str = ""
    generation_error: str = ""
    has_avatar: bool = False
    created_by: int | None = None
    created_by_username: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# ── Trends Intelligence ──────────────────────────────────────────────────────


class TrendOpportunity(BaseModel):
    """Single trend opportunity with scoring."""
    keyword: str
    score: float
    velocity: float
    convergence: float
    lifecycle: str
    sentiment: str = "neutral"
    sources: list[str] = Field(default_factory=list)
    suggested_formats: list[str] = Field(default_factory=list)
    content_angle: str = ""


class TrendIntelligenceResponse(BaseModel):
    """Response for GET /api/trends/intelligence."""
    top_opportunities: list[TrendOpportunity] = Field(default_factory=list)
    emerging_signals: list[TrendOpportunity] = Field(default_factory=list)
    declining_topics: list[TrendOpportunity] = Field(default_factory=list)
    total_signals_analyzed: int = 0
    generated_at: str = ""


# ── Trend Cards ──────────────────────────────────────────────────────────────


class TrendCardItem(BaseModel):
    """Single trend card."""
    card_id: str
    keyword: str = ""
    title: str = ""
    strength: float = 0.0
    lifecycle: str = ""
    sentiment: str = ""
    summary: str = ""
    recommendation: str = ""
    suggested_formats: list[str] = Field(default_factory=list)
    velocity: float | None = None
    convergence: float | None = None
    source_signals: list[str] = Field(default_factory=list)
    created_at: str = ""


class TrendCardsResponse(BaseModel):
    """Response for GET /api/trends/cards."""
    cards: list[TrendCardItem]


# ── Archive ──────────────────────────────────────────────────────────────────


class ArchiveItem(BaseModel):
    """Single past publication."""
    pub_id: str
    team_id: str | None = None
    created_by: int | None = None
    draft_id: str | None = None
    platform: str = ""
    kind: str = "text"
    external_url: str = ""
    external_id: str = ""
    topic: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    published_at: str | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    views: int = 0
    score_engagement: int | None = None
    score_brand_fit: int | None = None
    score_craft: int | None = None
    score_goal_hit: int | None = None
    content_pillar: str = ""
    funnel_stage: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    avg_score: float | None = None

    model_config = {"extra": "allow"}


class ArchiveListResponse(BaseModel):
    """Response for GET /api/archive."""
    items: list[ArchiveItem]
    total: int
