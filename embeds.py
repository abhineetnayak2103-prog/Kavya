"""
utils/embeds.py — Every embed Kavya sends goes through here.
Keeping ONE place that builds embeds is what gives the whole bot a
consistent, professional look instead of every cog rolling its own style.
"""
from __future__ import annotations
import discord
from datetime import datetime, timezone
import config


def _base(color: int, title: str | None, description: str | None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=config.FOOTER_TEXT, icon_url=config.FOOTER_ICON)
    return embed


def success(description: str, title: str = "Success") -> discord.Embed:
    return _base(config.COLOR_SUCCESS, f"✅ {title}", description)


def error(description: str, title: str = "Error") -> discord.Embed:
    return _base(config.COLOR_ERROR, f"❌ {title}", description)


def warning(description: str, title: str = "Warning") -> discord.Embed:
    return _base(config.COLOR_WARNING, f"⚠️ {title}", description)


def info(description: str, title: str = "Info") -> discord.Embed:
    return _base(config.COLOR_INFO, f"ℹ️ {title}", description)


def plain(title: str | None = None, description: str | None = None,
          color: int = config.COLOR_PRIMARY) -> discord.Embed:
    """A blank branded embed for cogs that need full control over fields."""
    return _base(color, title, description)


def paginated_footer(embed: discord.Embed, page: int, total_pages: int) -> discord.Embed:
    embed.set_footer(text=f"{config.FOOTER_TEXT} • Page {page}/{total_pages}",
                      icon_url=config.FOOTER_ICON)
    return embed
