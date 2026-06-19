"""
Lightweight Discord REST API client.
No gateway / websocket needed — we only read messages and post results.
"""

import aiohttp
import asyncio
from datetime import datetime, timezone

BASE = "https://discord.com/api/v10"


class DiscordClient:
    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Fetch messages ────────────────────────────────────────────

    async def fetch_messages(
        self, channel_id: str, after_snowflake: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Fetch up to `limit` messages from a channel, optionally after a snowflake."""
        await self._ensure_session()
        params: dict = {"limit": min(limit, 100)}
        if after_snowflake:
            params["after"] = after_snowflake
        url = f"{BASE}/channels/{channel_id}/messages"
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def fetch_all_messages_since(
        self, channel_id: str, since: datetime
    ) -> list[dict]:
        """Paginate through all messages in a channel since `since` (UTC)."""
        since_snowflake = datetime_to_snowflake(since)
        all_messages: list[dict] = []
        cursor = since_snowflake

        while True:
            batch = await self.fetch_messages(channel_id, after_snowflake=cursor)
            if not batch:
                break
            all_messages.extend(batch)
            # Messages come newest-first; the oldest in this batch is last
            cursor = batch[-1]["id"]
            if len(batch) < 100:
                break
            await asyncio.sleep(0.5)  # rate-limit courtesy

        return all_messages

    # ── Fetch reactions ───────────────────────────────────────────

    async def fetch_reaction_users(
        self, channel_id: str, message_id: str, emoji: str, limit: int = 100
    ) -> list[dict]:
        """Fetch users who reacted with `emoji` on a message.
        For custom emoji, use name:id format."""
        await self._ensure_session()
        url = f"{BASE}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}"
        params = {"limit": min(limit, 100)}
        async with self._session.get(url, params=params) as resp:
            if resp.status == 404:
                return []
            resp.raise_for_status()
            return await resp.json()

    # ── Post message ──────────────────────────────────────────────

    async def post_message(self, channel_id: str, content: str) -> dict:
        """Post a message to a channel. Splits if >2000 chars."""
        await self._ensure_session()
        url = f"{BASE}/channels/{channel_id}/messages"
        results = []
        for chunk in _split_message(content):
            async with self._session.post(url, json={"content": chunk}) as resp:
                resp.raise_for_status()
                results.append(await resp.json())
            await asyncio.sleep(0.3)
        return results[0] if len(results) == 1 else results

    # ── Resolve custom emoji IDs ──────────────────────────────────

    async def fetch_guild_emojis(self, guild_id: str) -> list[dict]:
        """Fetch all custom emojis for a guild."""
        await self._ensure_session()
        url = f"{BASE}/guilds/{guild_id}/emojis"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()


# ── Helpers ───────────────────────────────────────────────────────

DISCORD_EPOCH = 1420070400000  # ms


def datetime_to_snowflake(dt: datetime) -> str:
    """Convert a datetime to a Discord snowflake (for pagination)."""
    ts_ms = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return str((ts_ms - DISCORD_EPOCH) << 22)


def snowflake_to_datetime(snowflake: str) -> datetime:
    """Convert a Discord snowflake to a UTC datetime."""
    ts_ms = (int(snowflake) >> 22) + DISCORD_EPOCH
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _split_message(content: str, limit: int = 2000) -> list[str]:
    """Split a message into chunks of at most `limit` characters, breaking at newlines."""
    if len(content) <= limit:
        return [content]
    chunks = []
    while content:
        if len(content) <= limit:
            chunks.append(content)
            break
        split_at = content.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(content[:split_at])
        content = content[split_at:].lstrip("\n")
    return chunks
