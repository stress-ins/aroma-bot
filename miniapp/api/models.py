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


class ReelsFrameFieldsPayload(BaseModel):
    scene: str = Field(default="")
    angle: str = Field(default="")
    timecode: str = Field(default="")


class CreateContentPayload(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="")
    format_key: str = Field(default="")


class CreateReelsPayload(BaseModel):
    topic: str = Field(default="")


class CreateReelsV2Payload(BaseModel):
    topic: str = Field(default="")
    goal: str = Field(default="trust")
    emotion: str = Field(default="calm")


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


class CreateCarouselPayload(BaseModel):
    topic: str = Field(default="")


class CarouselSlideRegeneratePayload(BaseModel):
    note: str | None = Field(default=None)


class CarouselSlideTextPayload(BaseModel):
    text: str = Field(default="")


class CarouselSlideNotePayload(BaseModel):
    note: str = Field(default="")


class CarouselPreviewPayload(BaseModel):
    slide_index: int | None = Field(default=None, description="Generate preview for specific slide (None = all)")


class PlanGeneratePayload(BaseModel):
    entry_index: int


class ThreadsSeriesCreateRequest(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="trust")
    emotion: str = Field(default="")


class ThreadsSlotPatchRequest(BaseModel):
    slot: str = Field(default="")
    text: str | None = Field(default=None)
    scheduled_time: str | None = Field(default=None)


class ThreadsSlotRegenRequest(BaseModel):
    slot: str = Field(default="")
    note: str | None = Field(default=None)


class ScheduleSeriesRequest(BaseModel):
    draft_id: str = Field(default="")
    date: str = Field(default="")
    slots: list[str] = Field(default_factory=lambda: ["morning", "day", "evening"])


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
