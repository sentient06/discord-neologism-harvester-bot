"""
Format harvest results for posting back to Discord.
"""

from .harvest import HarvestedPost


def format_harvest_report(
    posts: list[HarvestedPost],
    days: int,
    channel_name: str = "",
) -> str:
    """Format a list of harvested posts into a Discord message."""
    if not posts:
        return f"📭 **Harvest ({channel_name}, last {days} days):** No qualifying posts found."

    new_posts = [p for p in posts if not p.previously_harvested]
    old_posts = [p for p in posts if p.previously_harvested]

    lines = [f"🌾 **Harvest — {channel_name} — last {days} days**"]
    lines.append(f"Found **{len(posts)}** qualifying post(s) "
                 f"({len(new_posts)} new, {len(old_posts)} previously harvested).\n")

    if new_posts:
        lines.append("**── New ──**")
        for p in new_posts:
            lines.append(_format_post(p))
        lines.append("")

    if old_posts:
        lines.append("**── Previously harvested ──**")
        for p in old_posts:
            lines.append(_format_post(p, earmark=True))

    return "\n".join(lines)


def _format_post(post: HarvestedPost, earmark: bool = False) -> str:
    """Format a single post entry."""
    prefix = "🔖 " if earmark else "• "
    neo_str = ", ".join(f"**{n}**" for n in post.neologisms) if post.neologisms else ""
    author_str = f"by <@{post.author_id}>"

    parts = [prefix]
    if neo_str:
        parts.append(f"{neo_str} ")
    parts.append(f"{author_str}")
    parts.append(f" — {post.approval_count} approval(s)")
    parts.append(f" — [link]({post.link})")

    return "".join(parts)
