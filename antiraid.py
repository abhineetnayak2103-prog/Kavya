from __future__ import annotations
import time
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

CATEGORY = "Antiraid"


class Antiraid(commands.Cog):
    """Protects against mass-join raids, suspicious accounts & bot waves."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_windows: dict[int, deque] = {}

    async def _settings(self, guild_id: int):
        row = await self.bot.db.fetchone("SELECT * FROM antiraid_settings WHERE guild_id = ?", (guild_id,))
        if not row:
            await self.bot.db.execute("INSERT INTO antiraid_settings (guild_id) VALUES (?)", (guild_id,))
            row = await self.bot.db.fetchone("SELECT * FROM antiraid_settings WHERE guild_id = ?", (guild_id,))
        return row

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        settings = await self._settings(guild.id)
        if not settings["enabled"]:
            return

        # account age check
        age_limit = settings["age_limit_days"]
        if age_limit and age_limit > 0:
            account_age_days = (discord.utils.utcnow() - member.created_at).days
            if account_age_days < age_limit:
                await self._punish(member, settings, f"Account under {age_limit} days old")
                return

        # avatar check (default avatar = higher risk)
        if settings["avatar_check"] and member.avatar is None:
            await self._punish(member, settings, "No custom avatar set")
            return

        # mass-join threshold tracking
        window = self.join_windows.setdefault(guild.id, deque())
        now = time.time()
        window.append(now)
        while window and now - window[0] > settings["window_seconds"]:
            window.popleft()

        if len(window) >= settings["threshold"]:
            if settings["delete_invites"]:
                try:
                    for inv in await guild.invites():
                        await inv.delete(reason="Antiraid: raid detected")
                except discord.Forbidden:
                    pass
            if settings["verification_upgrade"]:
                try:
                    await guild.edit(verification_level=discord.VerificationLevel.highest)
                except discord.Forbidden:
                    pass
            if settings["lockdown"]:
                for channel in guild.text_channels:
                    try:
                        overwrite = channel.overwrites_for(guild.default_role)
                        overwrite.send_messages = False
                        await channel.set_permissions(guild.default_role, overwrite=overwrite)
                    except discord.Forbidden:
                        continue
            await self._punish(member, settings, "Mass-join raid threshold exceeded")

    async def _punish(self, member: discord.Member, settings, reason: str):
        action = settings["action"] or "kick"
        try:
            if action == "ban":
                await member.ban(reason=f"Antiraid: {reason}")
            else:
                await member.kick(reason=f"Antiraid: {reason}")
        except discord.Forbidden:
            pass

    @commands.hybrid_group(name="antiraid", description="Show antiraid overview & command guide.", invoke_without_command=True)
    @commands.guild_only()
    async def antiraid(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        embed = embeds.plain(title="🚨 Antiraid", description="Protects against mass-join raids and suspicious accounts.")
        embed.add_field(name="Status", value="🟢 Enabled" if s["enabled"] else "🔴 Disabled")
        embed.add_field(name="Action", value=s["action"])
        embed.add_field(name="Threshold", value=f"{s['threshold']} joins / {s['window_seconds']}s")
        embed.add_field(name="Min Account Age", value=f"{s['age_limit_days']}d" if s["age_limit_days"] else "Disabled")
        embed.add_field(name="Avatar Check", value="On" if s["avatar_check"] else "Off")
        embed.add_field(name="Delete Invites", value="On" if s["delete_invites"] else "Off")
        embed.add_field(name="Verification Upgrade", value="On" if s["verification_upgrade"] else "Off")
        embed.add_field(name="Lockdown", value="On" if s["lockdown"] else "Off")
        embed.add_field(
            name="Subcommands",
            value="`enable` `disable` `status` `action` `threshold` `lockdown` "
                  "`age_limit` `verification` `avatar_check` `delete_invites`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @antiraid.command(name="enable", description="Enable antiraid protection.")
    @commands.has_permissions(administrator=True)
    async def enable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antiraid_settings SET enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("🚨 Antiraid protection enabled."))

    @antiraid.command(name="disable", description="Disable antiraid protection.")
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antiraid_settings SET enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.warning("Antiraid protection disabled."))

    @antiraid.command(name="status", description="Show detailed antiraid status & configuration.")
    async def status(self, ctx: commands.Context):
        await self.antiraid(ctx)

    @antiraid.command(name="action", description="Set the action for antiraid punishments.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Ban", value="ban"),
    ])
    @commands.has_permissions(administrator=True)
    async def action(self, ctx: commands.Context, action: str):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antiraid_settings SET action = ? WHERE guild_id = ?", (action, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Antiraid action set to **{action}**."))

    @antiraid.command(name="threshold", description="Set the raid join threshold.")
    @app_commands.describe(joins="Number of joins", seconds="Detection window in seconds")
    @commands.has_permissions(administrator=True)
    async def threshold(self, ctx: commands.Context, joins: int, seconds: int = 10):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE antiraid_settings SET threshold = ?, window_seconds = ? WHERE guild_id = ?",
            (joins, seconds, ctx.guild.id),
        )
        await ctx.send(embed=embeds.success(f"Raid threshold set to **{joins} joins / {seconds}s**."))

    @antiraid.command(name="lockdown", description="Toggle server lockdown (block all new joins/messages during raids).")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        new_val = 0 if s["lockdown"] else 1
        await self.bot.db.execute("UPDATE antiraid_settings SET lockdown = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Antiraid lockdown response is now **{'on' if new_val else 'off'}**."))

    @antiraid.command(name="age_limit", description="Set the minimum account age in days to join (0 to disable).")
    async def age_limit(self, ctx: commands.Context, days: int):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antiraid_settings SET age_limit_days = ? WHERE guild_id = ?", (days, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Minimum account age set to **{days}** day(s)." if days else "Account age check disabled."))

    @antiraid.command(name="verification", description="Toggle verification level upgrade during raids.")
    @commands.has_permissions(administrator=True)
    async def verification(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        new_val = 0 if s["verification_upgrade"] else 1
        await self.bot.db.execute("UPDATE antiraid_settings SET verification_upgrade = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Verification upgrade is now **{'on' if new_val else 'off'}**."))

    @antiraid.command(name="avatar_check", description="Toggle avatar filtering for joining users.")
    @commands.has_permissions(administrator=True)
    async def avatar_check(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        new_val = 0 if s["avatar_check"] else 1
        await self.bot.db.execute("UPDATE antiraid_settings SET avatar_check = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Avatar check is now **{'on' if new_val else 'off'}**."))

    @antiraid.command(name="delete_invites", description="Toggle invite deletion upon raid detection.")
    @commands.has_permissions(administrator=True)
    async def delete_invites(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        new_val = 0 if s["delete_invites"] else 1
        await self.bot.db.execute("UPDATE antiraid_settings SET delete_invites = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Invite deletion on raid is now **{'on' if new_val else 'off'}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Antiraid(bot))
