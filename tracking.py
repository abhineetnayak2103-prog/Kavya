from __future__ import annotations
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

CATEGORY = "Tracking"


class Tracking(commands.Cog):
    """Track member message volumes and view profile stats."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self.bot.db.execute(
            "INSERT INTO message_stats (guild_id, user_id, day, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, user_id, day) DO UPDATE SET count = count + 1",
            (message.guild.id, message.author.id, day),
        )

    @commands.hybrid_command(name="leaderboard", description="View various server leaderboards.")
    @app_commands.describe(kind="messages (all-time) or daily (today only)")
    @app_commands.choices(kind=[
        app_commands.Choice(name="All-time Messages", value="messages"),
        app_commands.Choice(name="Today's Messages", value="daily"),
    ])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context, kind: str = "messages"):
        if kind == "daily":
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            rows = await self.bot.db.fetchall(
                "SELECT user_id, count FROM message_stats WHERE guild_id = ? AND day = ? "
                "ORDER BY count DESC LIMIT 10",
                (ctx.guild.id, day),
            )
            title = "📊 Today's Message Leaderboard"
        else:
            rows = await self.bot.db.fetchall(
                "SELECT user_id, SUM(count) as total FROM message_stats WHERE guild_id = ? "
                "GROUP BY user_id ORDER BY total DESC LIMIT 10",
                (ctx.guild.id,),
            )
            title = "📊 All-Time Message Leaderboard"
        if not rows:
            return await ctx.send(embed=embeds.info("No message data tracked yet."))
        lines = []
        for i, row in enumerate(rows, start=1):
            count = row["count"] if "count" in row.keys() else row["total"]
            lines.append(f"**#{i}** <@{row['user_id']}> — {count} messages")
        await ctx.send(embed=embeds.plain(title=title, description="\n".join(lines)))

    @commands.hybrid_command(name="viewuser", description="View user profile statistics.")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def viewuser(self, ctx: commands.Context, member: discord.Member):
        row = await self.bot.db.fetchone(
            "SELECT SUM(count) as total FROM message_stats WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        total = row["total"] if row and row["total"] else 0
        warn_row = await self.bot.db.fetchone(
            "SELECT COUNT(*) as c FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id)
        )
        embed = embeds.plain(title=f"Profile — {member.display_name}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Total Messages", value=str(total))
        embed.add_field(name="Warnings", value=str(warn_row["c"] if warn_row else 0))
        embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown")
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="adminview", description="View all bot-only administrators.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def adminview(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT user_id FROM bot_admins WHERE guild_id = ? AND role = 'admin'", (ctx.guild.id,))
        mentions = [f"<@{r['user_id']}>" for r in rows] or ["None set."]
        await ctx.send(embed=embeds.plain(title="Bot Administrators", description="\n".join(mentions)))

    @commands.hybrid_command(name="modview", description="View all bot-only moderators.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def modview(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT user_id FROM bot_admins WHERE guild_id = ? AND role = 'mod'", (ctx.guild.id,))
        mentions = [f"<@{r['user_id']}>" for r in rows] or ["None set."]
        await ctx.send(embed=embeds.plain(title="Bot Moderators", description="\n".join(mentions)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tracking(bot))
