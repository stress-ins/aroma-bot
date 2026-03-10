from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrendItem:
    title: str
    url: str = ""
    score: str = ""          # views, upvotes, growth % etc.
    extra: str = ""          # secondary info (date, subreddit, etc.)
    summary: str = ""        # short AI-generated summary in Russian


@dataclass
class SourceResult:
    source_name: str         # display name, e.g. "Google Trends"
    source_key: str          # internal key, e.g. "google_trends"
    icon: str                # emoji for the report header
    items: list[TrendItem] = field(default_factory=list)
    error: str = ""          # non-empty if collection failed

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.items)


class BaseCollector(ABC):
    source_name: str
    source_key: str
    icon: str

    @abstractmethod
    async def collect(self) -> SourceResult:
        """Collect trends and return a SourceResult.
        Must never raise — catch all exceptions internally."""
