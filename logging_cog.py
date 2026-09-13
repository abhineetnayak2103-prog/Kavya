from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

CATEGORY = "Logging"

LOG_CATEGORIES = [
    "messages", "member_join", "member_leave", "member_update", "bans",
    "roles", "channels", "voice", "invites", "emoji", "server", "warnings", "commands",
]


class LoggingCog(commands.Cog, name="LoggingCog"):
    """Keep tabs on all events on your server across 13 distinct categories."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _channel_for(self, guild_id: int, category: str):
        row = await self.bot.db.fetchone(
            "SELECT channel_id FROM logging_settings WHERE guild_id = ? AND category = ?", (guild_id, category)
        )
        return row["channel_id"] if row else None

    async def _log(self, guild: discord.Guild, category: str, embed: discord.Embed):
        channel_id = await self._channel_for(guild.id, category)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ---------- example listeners wired into the log system ----------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        embed = embeds.plain(title="🗑️ Message Deleted", description=message.content or "*[no text content]*")
        embed.add_field(name="Author", value=message.author.mention)
        embed.add_field(name="Channel", value=message.channel.mention)
        await self._log(message.guild, "messages", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        embed = embeds.plain(title="📝 Message Edited")
        embed.add_field(name="Before", value=before.content or "*[empty]*", inline=False)
        embed.add_field(name="After", value=after.content or "*[empty]*", inline=False)
        embed.add_field(name="Author", value=before.author.mention)
        embed.add_field(name="Channel", value=before.channel.mention)
        await self._log(before.guild, "messages", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = embeds.success(f"{member.mention} joined the server.", title="📥 Member Joined")
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"))
        await self._log(member.guild, "member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = embeds.warning(f"{member.mention} left the server.", title="📤 Member Left")
        await self._log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = embeds.error(f"{user.mention} was banned.", title="🔨 Member Banned")
        await self._log(guild, "bans", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = embeds.info(f"{user.mention} was unbanned.", title="✅ Member Unbanned")
        await self._log(guild, "bans", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = embeds.success(f"{channel.mention} was created.", title="📁 Channel Created")
        await self._log(channel.guild, "channels", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = embeds.warning(f"#{channel.name} was deleted.", title="📁 Channel Deleted")
        await self._log(channel.guild, "channels", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = embeds.success(f"{role.mention} was created.", title="🎭 Role Created")
        await self._log(role.guild, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = embeds.warning(f"@{role.name} was deleted.", title="🎭 Role Deleted")
        await self._log(role.guild, "roles", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if after.channel and not before.channel:
            embed = embeds.info(f"{member.mention} joined 🔊 {after.channel.name}", title="Voice Join")
        elif before.channel and not after.channel:
            embed = embeds.info(f"{member.mention} left 🔊 {before.channel.name}", title="Voice Leave")
        else:
            embed = embeds.info(f"{member.mention} moved {before.channel.name} → {after.channel.name}", title="Voice Move")
        await self._log(member.guild, "voice", embed)

    # ---------- commands ----------
    @commands.hybrid_group(name="logging", description="View and manage the server logging configuration.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def logging_group(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT category, channel_id FROM logging_settings WHERE guild_id = ?", (ctx.guild.id,))
        configured = {r["category"]: r["channel_id"] for r in rows}
        embed = embeds.plain(title="📜 Logging Configuration")
        lines = []
        for cat in LOG_CATEGORIES:
            ch_id = configured.get(cat)
            ch = ctx.guild.get_channel(ch_id) if ch_id else None
            lines.append(f"**{cat}** — {ch.mention if ch else '❌ not set'}")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @logging_group.command(name="categories", description="View all available logging categories.")
    async def logging_categories(self, ctx: commands.Context):
        await ctx.send(embed=embeds.plain(title="Logging Categories", description=", ".join(f"`{c}`" for c in LOG_CATEGORIES)))

    @logging_group.command(name="enable", description="Enable logging for a specific category to a channel.")
    @app_commands.choices(category=[app_commands.Choice(name=c, value=c) for c in LOG_CATEGORIES])
    @commands.has_permissions(administrator=True)
    async def logging_enable(self, ctx: commands.Context, category: str, channel: discord.TextChannel):
        if category not in LOG_CATEGORIES:
            return await ctx.send(embed=embeds.error(f"Unknown category. Use `{ctx.prefix}logging categories`."))
        await self.bot.db.execute(
            "INSERT INTO logging_settings (guild_id, category, channel_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, category) DO UPDATE SET channel_id = excluded.channel_id",
            (ctx.guild.id, category, channel.id),
        )
        await ctx.send(embed=embeds.success(f"Logging **{category}** → {channel.mention}"))

    @logging_group.command(name="disable", description="Disable logging for a specific category.")
    @app_commands.choices(category=[app_commands.Choice(name=c, value=c) for c in LOG_CATEGORIES])
    @commands.has_permissions(administrator=True)
    async def logging_disable(self, ctx: commands.Context, category: str):
        await self.bot.db.execute(
            "DELETE FROM logging_settings WHERE guild_id = ? AND category = ?", (ctx.guild.id, category)
        )
        await ctx.send(embed=embeds.success(f"Disabled logging for **{category}**."))

    @logging_group.command(name="enableall", description="Enable all logging categories to a single channel.")
    @commands.has_permissions(administrator=True)
    async def logging_enableall(self, ctx: commands.Context, channel: discord.TextChannel):
        for cat in LOG_CATEGORIES:
            await self.bot.db.execute(
                "INSERT INTO logging_settings (guild_id, category, channel_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, category) DO UPDATE SET channel_id = excluded.channel_id",
                (ctx.guild.id, cat, channel.id),
            )
        await ctx.send(embed=embeds.success(f"All logging categories now point to {channel.mention}."))

    @logging_group.command(name="disableall", description="Disable all logging categories.")
    @commands.has_permissions(administrator=True)
    async def logging_disableall(self, ctx: commands.Context):
        await self.bot.db.execute("DELETE FROM logging_settings WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("Disabled all logging categories."))


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
