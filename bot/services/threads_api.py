from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.threads.net"

PROFILE_FIELDS = "id,username,name,is_verified,threads_profile_picture_url,threads_biography"
THREAD_FIELDS = "id,text,timestamp,permalink,username,media_type,media_product_type,shortcode,has_replies,is_reply"
REPLY_FIELDS = (
    "id,text,timestamp,permalink,username,has_replies,is_reply,is_reply_owned_by_me,"
    "root_post,replied_to"
)


class ThreadsAPIError(RuntimeError):
    pass


@dataclass
class ThreadsCandidate:
    thread_id: str
    source: str
    author: str
    text: str
    permalink: str
    timestamp: str
    root_text: str = ""


class ThreadsClient:
    def __init__(self, access_token: str | None = None) -> None:
        token = access_token or settings.threads_access_token
        if not token:
            raise ThreadsAPIError("THREADS_ACCESS_TOKEN не задан")
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=30.0,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.request(method, path, params=params)
        if response.status_code >= 400:
            raise ThreadsAPIError(f"Threads API {response.status_code}: {response.text[:200]}")
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise ThreadsAPIError(str(payload["error"])[:200])
        return payload

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/me", params={"fields": PROFILE_FIELDS})

    def lookup_profile(self, username: str) -> dict[str, Any]:
        return self._request("GET", "/profile_lookup", params={"username": username})

    def get_mentions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._request("GET", "/me/mentions", params={"fields": THREAD_FIELDS, "limit": limit})
        return payload.get("data", [])

    def get_threads(self, *, limit: int = 10) -> list[dict[str, Any]]:
        payload = self._request("GET", "/me/threads", params={"fields": THREAD_FIELDS, "limit": limit})
        return payload.get("data", [])

    def get_replies(self, thread_id: str, *, limit: int = 20, reverse: bool = False) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/{thread_id}/replies",
            params={"fields": REPLY_FIELDS, "limit": limit, "reverse": str(reverse).lower()},
        )
        return payload.get("data", [])

    def create_text_container(self, text: str, *, reply_to_id: str | None = None) -> str:
        """Deprecated: Use bot.services.publisher for standalone posts. Kept for reply publishing."""
        params: dict[str, Any] = {
            "media_type": "TEXT",
            "text": text,
        }
        if reply_to_id:
            params["reply_to_id"] = reply_to_id
        payload = self._request("POST", "/me/threads", params=params)
        return str(payload["id"])

    def publish_container(self, creation_id: str) -> str:
        """Deprecated: Use bot.services.publisher for standalone posts. Kept for reply publishing."""
        payload = self._request("POST", "/me/threads_publish", params={"creation_id": creation_id})
        return str(payload["id"])

    def publish_text_post(self, text: str, *, reply_to_id: str | None = None) -> str:
        """Deprecated for standalone posts: Use bot.services.publisher. Kept for reply publishing."""
        creation_id = self.create_text_container(text, reply_to_id=reply_to_id)
        return self.publish_container(creation_id)


    def search_threads(self, keyword: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Search public Threads posts by keyword. Placeholder — returns [] until Meta adds endpoint."""
        if not settings.threads_keyword_search_enabled:
            logger.debug("search_threads('%s') — keyword search disabled", keyword)
            return []
        try:
            payload = self._request("GET", "/keyword_search", params={"q": keyword, "search_type": "TOP", "fields": THREAD_FIELDS, "limit": limit})
            return payload.get("data", [])
        except ThreadsAPIError:
            return []

    def get_thread_conversation(self, thread_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Get replies to a thread (conversation context)."""
        try:
            payload = self._request("GET", f"/{thread_id}/conversation", params={"fields": REPLY_FIELDS, "limit": limit})
            return payload.get("data", [])
        except ThreadsAPIError:
            return []


async def post_reply(parent_id: str, text: str) -> str:
    """Post a reply to a Threads post. Runs sync ThreadsClient in executor."""
    import asyncio

    loop = asyncio.get_running_loop()

    def _do():
        client = ThreadsClient()
        return client.publish_text_post(text, reply_to_id=parent_id)

    return await loop.run_in_executor(None, _do)


async def post_thread(text: str) -> str:
    """Post a standalone Threads post. Runs sync ThreadsClient in executor."""
    import asyncio

    loop = asyncio.get_running_loop()

    def _do():
        client = ThreadsClient()
        return client.publish_text_post(text)

    return await loop.run_in_executor(None, _do)


WATCH_KEYWORDS: list[str] = [
    "ароматерапия", "эфирные масла", "гонг медитация",
    "aromatherapy", "essential oils", "gong meditation",
    "звуковое исцеление", "sound healing",
]


def collect_inbox_candidates_sync(limit_threads: int = 5, limit_replies: int = 10) -> tuple[dict[str, Any], list[ThreadsCandidate]]:
    client = ThreadsClient()
    me = client.get_me()
    username = str(me.get("username", "")).lower()

    candidates: list[ThreadsCandidate] = []
    seen: set[str] = set()

    for item in client.get_mentions(limit=15):
        thread_id = str(item.get("id", ""))
        text = str(item.get("text", "")).strip()
        author = str(item.get("username", "")).strip()
        if not thread_id or not text or author.lower() == username or thread_id in seen:
            continue
        seen.add(thread_id)
        candidates.append(
            ThreadsCandidate(
                thread_id=thread_id,
                source="mention",
                author=author,
                text=text,
                permalink=str(item.get("permalink", "")),
                timestamp=str(item.get("timestamp", "")),
            )
        )

    for post in client.get_threads(limit=limit_threads):
        post_id = str(post.get("id", ""))
        post_text = str(post.get("text", "")).strip()
        if not post_id:
            continue
        for reply in client.get_replies(post_id, limit=limit_replies, reverse=False):
            reply_id = str(reply.get("id", ""))
            reply_text = str(reply.get("text", "")).strip()
            author = str(reply.get("username", "")).strip()
            if not reply_id or not reply_text or author.lower() == username or reply_id in seen:
                continue

            already_handled = False
            if reply.get("has_replies"):
                try:
                    child_replies = client.get_replies(reply_id, limit=5, reverse=False)
                    already_handled = any(str(item.get("username", "")).lower() == username for item in child_replies)
                except ThreadsAPIError:
                    already_handled = False
            if already_handled:
                continue

            seen.add(reply_id)
            candidates.append(
                ThreadsCandidate(
                    thread_id=reply_id,
                    source="reply",
                    author=author,
                    text=reply_text,
                    permalink=str(reply.get("permalink", "")),
                    timestamp=str(reply.get("timestamp", "")),
                    root_text=post_text,
                )
            )

    candidates.sort(key=lambda item: item.timestamp, reverse=True)
    return me, candidates[:15]
