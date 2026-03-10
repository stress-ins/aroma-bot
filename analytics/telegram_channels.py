from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)


class TelegramChannelsCollector(BaseCollector):
    source_name = "Telegram каналы"
    source_key = "telegram_channels"
    icon = "📱"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("telegram_channels"):
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="TELEGRAM_API_ID/HASH или TELEGRAM_CHANNELS не заданы",
            )
        try:
            from telethon import TelegramClient
            from telethon.tl.types import Message

            client = TelegramClient(
                "aroma_monitor",
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )

            items: list[TrendItem] = []
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

            async with client:
                for channel in settings.telegram_channels_list:
                    try:
                        entity = await client.get_entity(channel)
                        async for msg in client.iter_messages(entity, limit=5):
                            if not isinstance(msg, Message) or not msg.text:
                                continue
                            if msg.date and msg.date < cutoff:
                                break
                            views = msg.views or 0
                            text = msg.text[:80].replace("\n", " ")
                            items.append(TrendItem(
                                title=text,
                                url=f"https://t.me/{channel}/{msg.id}",
                                score=f"{views:,} 👁",
                                extra=f"@{channel}",
                            ))
                    except Exception as exc:
                        logger.warning("Telegram channel %s error: %s", channel, exc)

            items.sort(key=lambda x: int(x.score.replace(",", "").split()[0]), reverse=True)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                items=items[:10],
                error="" if items else "Нет свежих постов",
            )
        except Exception as exc:
            logger.warning("TelegramChannels error: %s", exc)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc),
            )
