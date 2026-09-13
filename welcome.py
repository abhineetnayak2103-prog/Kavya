from __future__ import annotations
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Welcome"


def render_placeholders(text: str, member: discord.Member) -> str:
    return (
        text.replace("{user.mention}", member.mention)
        .replace("{user.name}", member.display_name)
        .replace("{user.tag}", str(member))
        .replace("{guild.name}", member.guild.name)
        .replace("{guild.member_count}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    """Welcome new members with custom layouts."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _settings(self, guild_id: int):
        row = await self.bot.db.fetchone("SELECT * FROM welcomer_settings WHERE guild_id = ?", (guild_id,))
        if not row:
            await self.bot.db.execute("INSERT INTO welcomer_settings (guild_id) VALUES (?)", (guild_id,))
            row = await self.bot.db.fetchone("SELECT * FROM welcomer_settings WHERE guild_id = ?", (guild_id,))
        return row

    def _build_embed(self, settings, member: discord.Member) -> discord.Embed:
        message = render_placeholders(settings["message"], member)
        embed = embeds.plain(title=f"Welcome to {member.guild.name}! 👋", description=message)
        embed.set_thumbnail(url=member.display_avatar.url)
        if settings["image_url"]:
            embed.set_image(url=settings["image_url"])
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self._settings(member.guild.id)
        if not settings["enabled"] or not settings["channel_id"]:
            return
        channel = member.guild.get_channel(settings["channel_id"])
        if not channel:
            return
        try:
            await channel.send(embed=self._build_embed(settings, member))
        except discord.Forbidden:
            pass

    @commands.hybrid_group(name="welcomer", description="Setup or toggle a basic server welcomer channel.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def welcomer(self, ctx: commands.Context, channel: discord.TextChannel = None):
        settings = await self._settings(ctx.guild.id)
        if channel:
            await self.bot.db.execute(
                "UPDATE welcomer_settings SET channel_id = ?, enabled = 1 WHERE guild_id = ?",
                (channel.id, ctx.guild.id),
            )
            return await ctx.send(embed=embeds.success(f"Welcomer set to {channel.mention} and enabled."))
        new_val = 0 if settings["enabled"] else 1
        await self.bot.db.execute("UPDATE welcomer_settings SET enabled = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Welcomer is now **{'on' if new_val else 'off'}**."))

    @welcomer.command(name="channel", description="Setup or toggle a basic server welcomer channel.")
    @commands.has_permissions(administrator=True)
    async def welcomer_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE welcomer_settings SET channel_id = ?, enabled = 1 WHERE guild_id = ?", (channel.id, ctx.guild.id)
        )
        await ctx.send(embed=embeds.success(f"Welcomer channel set to {channel.mention}."))

    @welcomer.command(name="message", description="Set a custom welcome message.")
    @commands.has_permissions(administrator=True)
    async def welcomer_message(self, ctx: commands.Context, *, message: str):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE welcomer_settings SET message = ? WHERE guild_id = ?", (message, ctx.guild.id))
        await ctx.send(embed=embeds.success("Welcome message updated.\nPlaceholders: `{user.mention}` `{user.name}` `{guild.name}` `{guild.member_count}`"))

    @welcomer.command(name="image", description="Set a custom welcome image or gif URL.")
    @commands.has_permissions(administrator=True)
    async def welcomer_image(self, ctx: commands.Context, url: str):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE welcomer_settings SET image_url = ? WHERE guild_id = ?", (url, ctx.guild.id))
        await ctx.send(embed=embeds.success("Welcome image updated."))

    @welcomer.command(name="test", description="Test the welcomer message for a user.")
    @commands.has_permissions(administrator=True)
    async def welcomer_test(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        settings = await self._settings(ctx.guild.id)
        await ctx.send(embed=self._build_embed(settings, member))


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
