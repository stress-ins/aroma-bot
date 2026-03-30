"""Messages poller — polls Instagram Conversations API for DM messages.

Uses GET /me/conversations?platform=instagram and GET /{conversation_id}/messages
to fetch conversations and messages from the Instagram Graph API.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from bot.services.inbox_store import (
    find_message_by_external_id,
    save_message,
    upsert_conversation,
)
from bot.services.mentions_store import get_token, get_token_for_team
from bot.services.social_trends_store import list_teams_with_social_accounts
from config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.instagram.com/v21.0"


async def _fetch_profile_picture(client: httpx.AsyncClient, user_id: str, access_token: str) -> str:
    """Fetch Instagram profile picture URL for a user."""
    if not user_id:
        return ""
    try:
        r = await client.get(
            f"{GRAPH_API_BASE}/{user_id}",
            params={
                "fields": "profile_picture_url",
                "access_token": access_token,
            },
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("profile_picture_url", "")
    except Exception:
        logger.debug("Could not fetch profile picture for user %s", user_id)
    return ""


async def _resolve_own_user_id(access_token: str, team_id: str | None) -> str:
    """Get our Instagram user ID to filter ourselves from conversation participants."""
    # Try from stored token metadata first
    uid_row = await get_token_for_team("instagram_user_id", team_id) if team_id else None
    if uid_row and uid_row.access_token:
        return uid_row.access_token
    uid_row = await get_token("instagram_user_id")
    if uid_row and uid_row.access_token:
        return uid_row.access_token
    return getattr(settings, "instagram_user_id", "") or ""


async def poll_instagram_conversations(
    access_token: str, team_id: str | None = None
) -> tuple[int, int]:
    """Poll Instagram Conversations API. Returns (conversations_polled, messages_saved)."""
    total_convs = 0
    total_msgs = 0

    own_user_id = await _resolve_own_user_id(access_token, team_id)

    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Get list of conversations
        try:
            r = await client.get(
                f"{GRAPH_API_BASE}/me/conversations",
                params={
                    "platform": "instagram",
                    "fields": "participants,updated_time",
                    "access_token": access_token,
                },
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            logger.warning("messages_poller: failed to fetch conversations", exc_info=True)
            return (0, 0)

        conversations = data.get("data", [])
        total_convs = len(conversations)

        for conv in conversations:
            conv_ext_id = conv.get("id", "")
            if not conv_ext_id:
                continue

            # Extract the OTHER participant (not us)
            participants = conv.get("participants", {}).get("data", [])
            participant = {}
            for p in participants:
                if p.get("id") != own_user_id:
                    participant = p
                    break
            # Fallback: if we couldn't identify ourselves, take second participant
            if not participant and len(participants) > 1:
                participant = participants[1]
            elif not participant and participants:
                participant = participants[0]

            participant_id = participant.get("id", conv_ext_id)
            participant_name = participant.get("name", "")
            participant_username = participant.get("username", participant_name)

            # Fetch profile picture for the participant
            profile_pic_url = await _fetch_profile_picture(client, participant_id, access_token)

            updated_time = conv.get("updated_time")
            last_msg_at = None
            if updated_time:
                try:
                    last_msg_at = datetime.fromisoformat(updated_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    last_msg_at = datetime.now(timezone.utc)

            # Upsert conversation
            conversation_id, _ = await upsert_conversation(
                platform="instagram",
                participant_id=participant_id,
                participant_username=participant_username,
                participant_name=participant_name,
                profile_picture_url=profile_pic_url,
                last_message_at=last_msg_at,
                team_id=team_id,
            )

            # Step 2: Fetch messages for this conversation
            try:
                r2 = await client.get(
                    f"{GRAPH_API_BASE}/{conv_ext_id}/messages",
                    params={
                        "fields": "message,from,created_time",
                        "limit": "20",
                        "access_token": access_token,
                    },
                )
                r2.raise_for_status()
                messages_data = r2.json()
            except Exception:
                logger.warning(
                    "messages_poller: failed to fetch messages for conv %s",
                    conv_ext_id,
                    exc_info=True,
                )
                continue

            for msg in messages_data.get("data", []):
                msg_ext_id = msg.get("id", "")
                if not msg_ext_id:
                    continue

                # Deduplicate
                existing = await find_message_by_external_id(msg_ext_id)
                if existing:
                    continue

                from_data = msg.get("from", {})
                from_id = from_data.get("id", "")

                # Determine sender_type: if from_id matches participant_id -> "user", else "business"
                sender_type = "user" if from_id == participant_id else "business"

                sent_at = None
                created_time = msg.get("created_time")
                if created_time:
                    try:
                        sent_at = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        sent_at = datetime.now(timezone.utc)

                content = msg.get("message", "")
                _, created = await save_message(
                    conversation_id=conversation_id,
                    sender_type=sender_type,
                    content=content,
                    sent_at=sent_at,
                    external_id=msg_ext_id,
                )
                if created:
                    total_msgs += 1

            # Update conversation preview from latest message
            if messages_data.get("data"):
                latest = messages_data["data"][0]
                preview = (latest.get("message") or "")[:200]
                await upsert_conversation(
                    platform="instagram",
                    participant_id=participant_id,
                    participant_username=participant_username,
                    participant_name=participant_name,
                    profile_picture_url=profile_pic_url,
                    last_message_preview=preview,
                    last_message_at=last_msg_at,
                    team_id=team_id,
                )

    return (total_convs, total_msgs)


async def poll_all_teams_inbox() -> dict[str, tuple[int, int]]:
    """Iterate teams and poll Instagram DMs for each."""
    results: dict[str, tuple[int, int]] = {}

    teams = await list_teams_with_social_accounts()
    polled_any = False

    for team in teams:
        team_id = team["team_id"]
        token_row = await get_token_for_team("instagram", team_id)
        if not token_row or not token_row.access_token:
            continue
        polled_any = True
        try:
            results[team_id] = await poll_instagram_conversations(
                token_row.access_token, team_id
            )
        except Exception as exc:
            logger.error("Inbox poll failed for team %s: %s", team_id, exc)
            results[team_id] = (0, 0)
        await asyncio.sleep(2)

    if not polled_any:
        token_row = await get_token("instagram")
        access_token = token_row.access_token if token_row else getattr(settings, "instagram_access_token", "")
        if access_token:
            try:
                results["global"] = await poll_instagram_conversations(access_token)
            except Exception as exc:
                logger.error("Inbox poll (global) failed: %s", exc)
                results["global"] = (0, 0)

    return results
