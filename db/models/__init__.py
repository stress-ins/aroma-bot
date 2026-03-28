"""db.models — backward-compatible re-exports of all ORM models.

Import any model directly::

    from db.models import DraftModel, Base
"""

from db.models.base import Base

from db.models.teams import TeamModel, TeamMemberModel, TeamInviteModel

from db.models.content import DraftModel, DraftRevisionModel, PlanModel, RepurposeGroupModel

from db.models.references import AromaCardModel, BlendModel, SavedBlendModel, DailyOilModel

from db.models.social import (
    MentionModel,
    MentionReplyModel,
    PlatformTokenModel,
    TrackedThreadModel,
    SocialTrendPostModel,
    HashtagQuotaModel,
    ConversationModel,
    DirectMessageModel,
)

from db.models.analytics import (
    PostMetricsModel,
    ApiCostLog,
    TrendSignal,
    TrendCardModel,
    CollectorHealth,
    LlmCacheModel,
    UsageLog,
    DigestCache,
    AnalyticsEvent,
)

from db.models.media import VideoTaskModel, KieTaskModel

from db.models.publishing import PublishLogModel, PastPublicationModel

from db.models.users import UserProfile, Subscription, PromoCode

from db.models.settings import BrandSettingsModel, TodoModel

__all__ = [
    "Base",
    # teams
    "TeamModel",
    "TeamMemberModel",
    "TeamInviteModel",
    # content
    "DraftModel",
    "DraftRevisionModel",
    "PlanModel",
    "RepurposeGroupModel",
    # references
    "AromaCardModel",
    "BlendModel",
    "SavedBlendModel",
    "DailyOilModel",
    # social
    "MentionModel",
    "MentionReplyModel",
    "PlatformTokenModel",
    "TrackedThreadModel",
    "SocialTrendPostModel",
    "HashtagQuotaModel",
    "ConversationModel",
    "DirectMessageModel",
    # analytics
    "PostMetricsModel",
    "ApiCostLog",
    "TrendSignal",
    "TrendCardModel",
    "CollectorHealth",
    "LlmCacheModel",
    "UsageLog",
    "DigestCache",
    # media
    "VideoTaskModel",
    "KieTaskModel",
    # publishing
    "PublishLogModel",
    "PastPublicationModel",
    # users
    "UserProfile",
    "Subscription",
    "PromoCode",
    # settings
    "BrandSettingsModel",
    "TodoModel",
]
