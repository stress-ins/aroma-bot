from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required
    telegram_bot_token: str
    report_target_chat_id: str

    # Phase 1
    youtube_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_password: str = ""

    # Russian sources
    vk_token: str = ""
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    tiktok_ms_token: str = ""
    gemini_api_key: str = ""
    nana_banana_api_key: str = ""  # Gemini key dedicated to image generation

    @property
    def image_api_key(self) -> str:
        """Key for image generation — prefers nana_banana_api_key, falls back to gemini_api_key."""
        return self.nana_banana_api_key or self.gemini_api_key

    # Phase 2
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    telegram_channels: str = ""  # comma-separated
    twitter_bearer_token: str = ""
    instagram_username: str = ""
    instagram_password: str = ""

    # Monitoring
    monitor_bot_token: str = ""   # second bot token for crash/error notifications
    monitor_chat_id: str = ""     # owner's chat_id

    # AI
    anthropic_api_key: str = ""

    # Threads API
    threads_access_token: str = ""
    threads_user_id: str = ""
    threads_username: str = ""
    mini_app_url: str = ""

    # Scheduler
    daily_digest_time: str = "09:00"
    timezone: str = "Europe/Moscow"

    # Cache
    cache_ttl: int = 3600

    def is_source_enabled(self, source: str) -> bool:
        checks = {
            "google_trends_en": True,
            "google_trends_ru": True,
            "youtube": bool(self.youtube_api_key or (self.google_client_id and self.google_client_secret and self.google_refresh_token)),
            "reddit": bool(self.reddit_client_id and self.reddit_client_secret),
            "telegram_channels": bool(self.telegram_api_id and self.telegram_api_hash and self.telegram_channels),  # type: ignore[truthy-bool]
            "twitter": bool(self.twitter_bearer_token),
            "instagram": bool(self.instagram_username and self.instagram_password),
            "youtube_ru": bool(self.youtube_api_key or (self.google_client_id and self.google_client_secret and self.google_refresh_token)),
            "instagram_ru": bool(self.instagram_username and self.instagram_password),
            "vk": bool(self.vk_token),
            "wordstat": bool(self.yandex_client_id and self.yandex_client_secret),
            "tiktok": bool(self.tiktok_ms_token),
            "tiktok_ru": bool(self.tiktok_ms_token),
            "threads": True,
            "ai_recommendations": bool(self.anthropic_api_key),
        }
        return checks.get(source, False)

    @property
    def is_threads_api_enabled(self) -> bool:
        return bool(self.threads_access_token and self.threads_user_id)

    @property
    def telegram_channels_list(self) -> list[str]:
        if not self.telegram_channels:
            return []
        return [ch.strip().lstrip("@") for ch in self.telegram_channels.split(",") if ch.strip()]

    @property
    def digest_hour(self) -> int:
        return int(self.daily_digest_time.split(":")[0])

    @property
    def digest_minute(self) -> int:
        return int(self.daily_digest_time.split(":")[1])


settings = Settings()
