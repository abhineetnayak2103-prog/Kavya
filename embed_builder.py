from __future__ import annotations
import json
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Embed"


class EmbedBuilder(commands.Cog):
    """Build & send custom embeds."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="embed", description="Create and send a custom embed.")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def embed(self, ctx: commands.Context, channel: discord.TextChannel = None, *,
                     title: str = None, description: str = None, color: str = None,
                     image: str = None, thumbnail: str = None, footer: str = None):
        channel = channel or ctx.channel
        if not title and not description:
            return await ctx.send(embed=embeds.error("Provide at least a `title` or `description`."))
        try:
            embed_color = int(color.lstrip("#"), 16) if color else None
        except ValueError:
            embed_color = None
        embed = embeds.plain(title=title, description=description, color=embed_color or embeds.config.COLOR_PRIMARY)
        if image:
            embed.set_image(url=image)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if footer:
            embed.set_footer(text=footer)
        await channel.send(embed=embed)
        if channel != ctx.channel:
            await ctx.send(embed=embeds.success(f"Embed sent to {channel.mention}."))

    @commands.hybrid_command(name="embedsave", description="Save a custom embed by name for reuse.")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def embedsave(self, ctx: commands.Context, name: str, *, title: str = None, description: str = None):
        data = {"title": title, "description": description}
        await self.bot.db.execute(
            "INSERT INTO saved_embeds (guild_id, name, embed_json) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET embed_json = excluded.embed_json",
            (ctx.guild.id, name.lower(), json.dumps(data)),
        )
        await ctx.send(embed=embeds.success(f"Saved embed **{name}**. Use `{ctx.prefix}embedsend {name}` to send it."))

    @commands.hybrid_command(name="embedsend", description="Send a previously saved embed.")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def embedsend(self, ctx: commands.Context, name: str, channel: discord.TextChannel = None):
        row = await self.bot.db.fetchone(
            "SELECT embed_json FROM saved_embeds WHERE guild_id = ? AND name = ?", (ctx.guild.id, name.lower())
        )
        if not row:
            return await ctx.send(embed=embeds.error(f"No saved embed named **{name}**."))
        data = json.loads(row["embed_json"])
        channel = channel or ctx.channel
        await channel.send(embed=embeds.plain(title=data.get("title"), description=data.get("description")))
        if channel != ctx.channel:
            await ctx.send(embed=embeds.success(f"Sent to {channel.mention}."))

    @commands.hybrid_command(name="embedlist", description="List all saved embeds.")
    @commands.guild_only()
    async def embedlist(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT name FROM saved_embeds WHERE guild_id = ?", (ctx.guild.id,))
        names = ", ".join(f"`{r['name']}`" for r in rows) or "None saved yet."
        await ctx.send(embed=embeds.plain(title="Saved Embeds", description=names))


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedBuilder(bot))
