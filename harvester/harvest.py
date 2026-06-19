"""
Core harvest logic:
 - Fetch messages from configured channels
 - Count approval reactions (faenorel + morfaenorel)
 - Extract neologisms (S. / Q. patterns)
 - Strip spoiler tags
 - Track already-harvested message IDs
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .discord_client import DiscordClient, message_link

LEDGER_PATH = Path("harvested.json")

# ── Data structures ───────────────────────────────────────────────

@dataclass
class HarvestedPost:
    message_id: str
    channel_id: str
    guild_id: str
    author: str
    author_id: str
    content: str
    clean_content: str
    neologisms: list[str]
    approval_count: int
    link: str
    harvested_at: str
    previously_harvested: bool = False


@dataclass
class Ledger:
    """Persistent record of harvested message IDs."""
    harvested_ids: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path = LEDGER_PATH) -> "Ledger":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(harvested_ids=set(data.get("harvested_ids", [])))
        return cls()

    def save(self, path: Path = LEDGER_PATH):
        path.write_text(json.dumps(
            {"harvested_ids": sorted(self.harvested_ids)},
            indent=2
        ))

    def is_known(self, message_id: str) -> bool:
        return message_id in self.harvested_ids

    def mark(self, message_id: str):
        self.harvested_ids.add(message_id)


# ── Text processing ──────────────────────────────────────────────

SPOILER_RE = re.compile(r"\|\|(.+?)\|\|", re.DOTALL)
NEOLOGISM_RE = re.compile(r"\b([SQ])\.\s+(\S+)", re.IGNORECASE)


def strip_spoilers(text: str) -> str:
    """Remove Discord spoiler tags, keeping the inner text."""
    return SPOILER_RE.sub(r"\1", text)


def extract_neologisms(text: str) -> list[str]:
    """Extract neologisms marked as S. <word> or Q. <word>."""
    clean = strip_spoilers(text)
    matches = NEOLOGISM_RE.findall(clean)
    # Return as "Q. word" or "S. word"
    return [f"{lang.upper()}. {word}" for lang, word in matches]


# ── Harvest engine ────────────────────────────────────────────────

async def harvest_channel(
    client: DiscordClient,
    guild_id: str,
    channel_id: str,
    emoji_identifiers: list[str],
    threshold: int,
    since: datetime,
    ledger: Ledger,
) -> list[HarvestedPost]:
    """
    Harvest qualifying posts from a single channel.
    `emoji_identifiers` should be in "name:id" format for custom emoji.
    """
    messages = await client.fetch_all_messages_since(channel_id, since)
    results: list[HarvestedPost] = []

    for msg in messages:
        # Count combined approval reactions
        approval_count = 0
        for reaction in msg.get("reactions", []):
            emoji = reaction.get("emoji", {})
            emoji_key = f"{emoji.get('name')}:{emoji.get('id')}"
            if emoji_key in emoji_identifiers or emoji.get("name") in [
                e.split(":")[0] for e in emoji_identifiers
            ]:
                approval_count += reaction["count"]

        if approval_count < threshold:
            continue

        author = msg.get("author", {})
        content = msg.get("content", "")
        clean = strip_spoilers(content)
        neos = extract_neologisms(content)
        link = message_link(guild_id, channel_id, msg["id"])

        post = HarvestedPost(
            message_id=msg["id"],
            channel_id=channel_id,
            guild_id=guild_id,
            author=author.get("username", "unknown"),
            author_id=author.get("id", ""),
            content=content,
            clean_content=clean,
            neologisms=neos,
            approval_count=approval_count,
            link=link,
            harvested_at=datetime.now(timezone.utc).isoformat(),
            previously_harvested=ledger.is_known(msg["id"]),
        )
        results.append(post)

    return results
