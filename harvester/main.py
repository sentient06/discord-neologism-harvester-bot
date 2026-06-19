"""
Entry point for the Harvester bot.
Usage:
  python -m harvester.main --days 7    # weekly harvest
  python -m harvester.main --days 28   # monthly review
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .discord_client import DiscordClient
from .harvest import Ledger, harvest_channel
from .formatter import format_harvest_report


async def run(days: int, dry_run: bool = False, threshold_override: int | None = None):
    # ── Load config ───────────────────────────────────────────────
    config_path = Path("config.json")
    if not config_path.exists():
        print("ERROR: config.json not found", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text())
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    guild_id = config["guild_id"]
    threshold = threshold_override if threshold_override is not None else config.get("approval_threshold", 3)
    approval_names = config.get("approval_emojis", [])
    output_channel = config.get("output_channel_id", "")
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # ── Resolve custom emoji name:id pairs ────────────────────────
    client = DiscordClient(token)
    try:
        guild_emojis = await client.fetch_guild_emojis(guild_id)
        emoji_identifiers = []
        for ge in guild_emojis:
            if ge["name"] in approval_names:
                emoji_identifiers.append(f"{ge['name']}:{ge['id']}")

        if not emoji_identifiers:
            print(f"WARNING: No custom emojis matched {approval_names} in guild {guild_id}")
            print("Available emojis:", [e["name"] for e in guild_emojis])

        # ── Harvest each channel ──────────────────────────────────
        ledger = Ledger.load()
        all_results = []

        for ch_key, ch_conf in config["channels"].items():
            ch_id = ch_conf["id"]
            if not ch_id:
                print(f"Skipping {ch_key}: no channel ID configured")
                continue

            print(f"Harvesting #{ch_key} (last {days} days)...")
            posts = await harvest_channel(
                client, guild_id, ch_id, emoji_identifiers, threshold, since, ledger
            )
            print(f"  → {len(posts)} qualifying post(s)")

            report = format_harvest_report(
                posts, days, ch_conf.get("description", ch_key)
            )

            if dry_run:
                print("\n--- DRY RUN OUTPUT ---")
                print(report)
                print("--- END ---\n")
            elif output_channel:
                await client.post_message(output_channel, report)
                print(f"  → Report posted to output channel")

            # Mark new posts in ledger
            for p in posts:
                if not p.previously_harvested:
                    ledger.mark(p.message_id)

            all_results.extend(posts)

        # ── Save ledger ───────────────────────────────────────────
        ledger.save()
        print(f"Ledger saved ({len(ledger.harvested_ids)} total entries)")

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Harvest neologisms from Discord")
    parser.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Print results without posting")
    parser.add_argument("--threshold", type=int, default=None, help="Override approval threshold (default: from config)")
    args = parser.parse_args()

    asyncio.run(run(args.days, args.dry_run, args.threshold))


if __name__ == "__main__":
    main()
