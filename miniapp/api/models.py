from __future__ import annotations

from pydantic import BaseModel, Field


class DraftStatusPayload(BaseModel):
    status: str


class DraftFeedbackPayload(BaseModel):
    feedback: str


class DraftContentPayload(BaseModel):
    topic: str = Field(default="")
    angle: str = Field(default="")
    hook: str = Field(default="")
    caption: str = Field(default="")
    cta: str = Field(default="")
    hashtags: str = Field(default="")
    visual_prompt: str = Field(default="")
    editor_notes: str = Field(default="")
    threads_posts: list[dict] | None = Field(default=None)


class DraftMovePayload(BaseModel):
    target_team_id: str


class KeywordPayload(BaseModel):
    topic_idx: int
    field: str
    word: str


class ReelsFrameNotePayload(BaseModel):
    note: str = Field(default="")


class ReelsFramePromptPayload(BaseModel):
    prompt: str = Field(default="")


class ReelsScenarioPayload(BaseModel):
    scenario: str = Field(default="")
    concept: str = Field(default="")
    revision_note: str = Field(default="")


class ReelsFrameFieldsPayload(BaseModel):
    scene: str = Field(default="")
    angle: str = Field(default="")
    timecode: str = Field(default="")


class BlendContext(BaseModel):
    title: str = Field(default="")
    brief: str = Field(default="")
    oils: list[dict] = Field(default_factory=list)
    total_drops: int = Field(default=0)
    profile: dict = Field(default_factory=dict)
    expert_note: str = Field(default="")
    application_guide: str = Field(default="")
    tags: list[str] = Field(default_factory=list)


class DailyOilContext(BaseModel):
    oil_name: str = Field(default="")
    oil_slug: str = Field(default="")
    reason: str = Field(default="")
    fact: str = Field(default="")
    daily_practice: str = Field(default="")
    date: str = Field(default="")


class CreateContentPayload(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="")
    format_key: str = Field(default="")
    practice_focus: str = Field(default="aroma")
    blend_context: BlendContext | None = Field(default=None)
    daily_oil_context: DailyOilContext | None = Field(default=None)


class CreateReelsPayload(BaseModel):
    topic: str = Field(default="")


class CreateReelsV2Payload(BaseModel):
    topic: str = Field(default="")
    goal: str = Field(default="trust")
    emotion: str = Field(default="calm")
    lightweight: bool = Field(default=False)
    practice_focus: str = Field(default="aroma")
    blend_context: BlendContext | None = Field(default=None)
    daily_oil_context: DailyOilContext | None = Field(default=None)


class ReelsFramePatchPayload(BaseModel):
    frame_id: str = Field(default="")
    overlay_text: str | None = Field(default=None)
    image_prompt: str | None = Field(default=None)


class ReelsApprovePayload(BaseModel):
    shooting_deadline_days: int = Field(default=3)


class ReelsFeedbackPayload(BaseModel):
    platform: str = Field(default="")
    rating: int = Field(default=0)
    reaction_types: list[str] = Field(default_factory=list)


class ReelsRegenFramePayload(BaseModel):
    frame_id: str = Field(default="")
    prompt: str | None = Field(default=None)


class CreateYouTubePayload(BaseModel):
    topic: str = Field(default="")
    subformat: str = Field(default="talking_head")  # talking_head | listicle | podcast
    goal: str = Field(default="trust")
    emotion: str = Field(default="calm")
    duration_target: int = Field(default=10)  # minutes
    practice_focus: str = Field(default="aroma")
    item_count: int = Field(default=7)  # for listicle
    question_count: int = Field(default=6)  # for podcast
    guest_description: str = Field(default="")  # for podcast


class YouTubeThumbnailPayload(BaseModel):
    mode: str = Field(default="prompt")  # prompt | photo_based | upload
    revision_note: str = Field(default="")


class YouTubeMetadataPayload(BaseModel):
    """Trigger metadata generation after montage."""
    pass


class CreateCarouselPayload(BaseModel):
    topic: str = Field(default="")
    practice_focus: str = Field(default="aroma")
    blend_context: BlendContext | None = Field(default=None)
    daily_oil_context: DailyOilContext | None = Field(default=None)
    layout_style: str = Field(default="overlay")  # "overlay" | "editorial"


class CarouselSlideRegeneratePayload(BaseModel):
    note: str | None = Field(default=None)


class CarouselSlideTextPayload(BaseModel):
    text: str = Field(default="")


class CarouselSlideNotePayload(BaseModel):
    note: str = Field(default="")


class CarouselCaptionPayload(BaseModel):
    caption: str = Field(default="")


class CarouselPreviewPayload(BaseModel):
    slide_index: int | None = Field(default=None, description="Generate preview for specific slide (None = all)")


class PlanGeneratePayload(BaseModel):
    entry_index: int


class ThreadsSeriesCreateRequest(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="trust")
    emotion: str = Field(default="")
    practice_focus: str = Field(default="aroma")
    blend_context: BlendContext | None = Field(default=None)
    daily_oil_context: DailyOilContext | None = Field(default=None)


class ThreadsSlotPatchRequest(BaseModel):
    slot: str = Field(default="")
    text: str | None = Field(default=None)
    scheduled_time: str | None = Field(default=None)


class ThreadsSlotRegenRequest(BaseModel):
    slot: str = Field(default="")
    note: str | None = Field(default=None)


class ScheduleSeriesRequest(BaseModel):
    draft_id: str = Field(..., min_length=1)
    date: str = Field(..., min_length=1)
    slots: list[str] = Field(default_factory=lambda: ["morning", "day", "evening"])


class ContentSeriesCreateRequest(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="trust")
    format_key: str = Field(default="instagram")
    post_count: int = Field(default=5, ge=3, le=7)
    template_key: str = Field(default="custom")
    blend_context: BlendContext | None = Field(default=None)


class SeriesPostPatchRequest(BaseModel):
    caption: str | None = Field(default=None)
    cta: str | None = Field(default=None)
    visual_prompt: str | None = Field(default=None)
    hashtags: str | None = Field(default=None)
    scheduled_at: str | None = Field(default=None)


class SeriesRegenPostRequest(BaseModel):
    note: str | None = Field(default=None)


class ReelsPublishPayload(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    date: str = Field(default="")
    time: str = Field(default="")
    youtube_title: str = Field(default="")
    youtube_privacy: str = Field(default="public")


class ReelsRetryPlatformPayload(BaseModel):
    platform: str = Field(default="")


class CleanVideoPayload(BaseModel):
    min_pause_duration: float = Field(default=0.4, ge=0.1, le=2.0)
    silence_threshold_db: float = Field(default=-35.0, ge=-60.0, le=-10.0)
    use_whisper: bool = Field(default=True)


class AromaCardPayload(BaseModel):
    description: str = Field(default="")
    questions: str = Field(default="")
    nps_effect: str = Field(default="")
    therapeutic_properties: str = Field(default="")
    psychological_properties: str = Field(default="")
    history: str = Field(default="")
    volatility: str = Field(default="")
    botanical_family: str = Field(default="")
    origin_countries: str = Field(default="")
    extraction_method: str = Field(default="")
    key: str = Field(default="")
    resource_values: dict[str, str] = Field(default_factory=dict)


# ── Mentions ────────────────────────────────────────────────────────────────

class MentionIngestPayload(BaseModel):
    platform: str = Field(default="telegram")
    external_id: str = Field(default="")
    type: str = Field(default="mention")
    author_username: str = Field(default="")
    author_name: str = Field(default="")
    content: str = Field(default="")
    url: str = Field(default="")
    context_post: str = Field(default="")


class MentionReplySelectPayload(BaseModel):
    reply_id: str


class MentionReplyResponse(BaseModel):
    reply_id: str
    mention_id: str
    tone: str
    content: str
    generated_at: str
    selected: bool
    published_at: str | None
    publish_error: str


class MentionDetailResponse(BaseModel):
    mention_id: str
    platform: str
    external_id: str
    type: str
    author_username: str
    author_name: str
    content: str
    url: str
    context_post: str
    received_at: str
    status: str
    replies: list[MentionReplyResponse] = Field(default_factory=list)


class MentionListResponse(BaseModel):
    items: list[MentionDetailResponse]
    total: int


# ── Platform tokens ──────────────────────────────────────────────────────────

class TokenUpdatePayload(BaseModel):
    access_token: str
    expires_at: str | None = Field(default=None)


class TokenStatusResponse(BaseModel):
    platform: str
    has_token: bool
    expires_at: str | None
    updated_at: str | None


# ── Thread Monitor ──────────────────────────────────────────────────────────

class SuggestTopicsRequest(BaseModel):
    goal_key: str = Field(default="trust")
    format_key: str = Field(default="instagram")


class ThreadActionRequest(BaseModel):
    action: str = Field(default="")
