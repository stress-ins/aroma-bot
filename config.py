from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

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
    gemini_api_key: str = ""  # deprecated, kept for .env compat
    nana_banana_api_key: str = ""

    @property
    def image_api_key(self) -> str:
        """Key for NanoBanana image generation API."""
        return self.nana_banana_api_key

    # Phase 2
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    telegram_channels: str = ""  # comma-separated
    twitter_bearer_token: str = ""
    instagram_username: str = ""
    instagram_password: str = ""

    # Monitoring
    monitor_bot_token: str = Field(default="", alias="MONITOR_TG_BOT_TOKEN")  # second bot token
    monitor_chat_id: str = ""     # owner's chat_id

    # AI
    anthropic_api_key: str = ""

    # Threads API
    threads_app_id: str = ""
    threads_app_secret: str = ""
    threads_access_token: str = ""
    threads_user_id: str = ""
    threads_username: str = ""

    # Instagram Platform API
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    instagram_business_account_id: str = ""
    mini_app_url: str = ""
    carousel_forbidden_phrases: str = ""
    carousel_forbidden_visual_motifs: str = ""

    # Upload-Post (cross-platform publishing)
    upload_post_api_key: str = ""
    upload_post_user: str = ""

    # Scheduler
    daily_digest_time: str = "09:00"
    timezone: str = "Europe/Moscow"
    miniapp_aroma_allowed_user_ids: str = ""

    # Public assets
    public_assets_base_url: str = ""

    # n8n integration
    n8n_webhook_secret: str = ""
    admin_telegram_chat_id: str = ""

    # Admin
    admin_telegram_id: int = 247982221

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

    @property
    def assets_base_url(self) -> str:
        """Public base URL for generated assets. Falls back to mini_app_url."""
        base = (self.public_assets_base_url or self.mini_app_url or "").strip().rstrip("/")
        return base

    @property
    def miniapp_aroma_allowed_user_id_set(self) -> set[int]:
        fixed_ids = {247982221, 62912125}
        if not self.miniapp_aroma_allowed_user_ids:
            return fixed_ids
        parsed: set[int] = set()
        for raw_value in self.miniapp_aroma_allowed_user_ids.split(","):
            value = raw_value.strip()
            if not value:
                continue
            try:
                parsed.add(int(value))
            except ValueError:
                continue
        return fixed_ids | parsed

    @staticmethod
    def _split_settings_list(raw: str) -> list[str]:
        parts: list[str] = []
        for chunk in raw.replace("\r", "\n").split("\n"):
            for item in chunk.split(","):
                value = item.strip()
                if value:
                    parts.append(value)
        return parts

    @property
    def carousel_forbidden_phrases_list(self) -> list[str]:
        return self._split_settings_list(self.carousel_forbidden_phrases)

    @property
    def carousel_forbidden_visual_motifs_list(self) -> list[str]:
        return self._split_settings_list(self.carousel_forbidden_visual_motifs)


settings = Settings()
