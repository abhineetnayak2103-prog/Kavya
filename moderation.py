from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds
from utils.checks import higher_top_role

CATEGORY = "Moderation"


class Moderation(commands.Cog):
    """Warnings, purges, locks & member actions."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locked_nicks: set[tuple[int, int]] = set()

    # ---------- kick / ban / unban ----------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Reason for the kick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if not await higher_top_role(ctx.author, member):
            return await ctx.send(embed=embeds.error("You can't act on someone with an equal/higher role."))
        await member.kick(reason=f"{ctx.author} — {reason}")
        await ctx.send(embed=embeds.success(f"👢 Kicked {member.mention}\n**Reason:** {reason}"))

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="Member to ban", reason="Reason for the ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if not await higher_top_role(ctx.author, member):
            return await ctx.send(embed=embeds.error("You can't act on someone with an equal/higher role."))
        await member.ban(reason=f"{ctx.author} — {reason}", delete_message_seconds=0)
        await ctx.send(embed=embeds.success(f"🔨 Banned {member.mention}\n**Reason:** {reason}"))

    @commands.hybrid_command(name="unban", description="Unban a user from the server.")
    @app_commands.describe(user_id="The ID of the user to unban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
        except (discord.NotFound, ValueError):
            return await ctx.send(embed=embeds.error("That user isn't banned or the ID is invalid."))
        await ctx.send(embed=embeds.success(f"✅ Unbanned **{user}**"))

    # ---------- mute / unmute (timeout) ----------
    @commands.hybrid_command(name="mute", description="Mute a member in the server (timeout).")
    @app_commands.describe(member="Member to mute", minutes="Duration in minutes", reason="Reason")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, member: discord.Member, minutes: int = 10,
                    *, reason: str = "No reason provided"):
        if not await higher_top_role(ctx.author, member):
            return await ctx.send(embed=embeds.error("You can't act on someone with an equal/higher role."))
        duration = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(duration, reason=f"{ctx.author} — {reason}")
        await ctx.send(embed=embeds.success(f"🔇 Muted {member.mention} for **{minutes}m**\n**Reason:** {reason}"))

    @commands.hybrid_command(name="unmute", description="Unmute a member in the server.")
    @app_commands.describe(member="Member to unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        await member.timeout(None, reason=f"Unmuted by {ctx.author}")
        await ctx.send(embed=embeds.success(f"🔊 Unmuted {member.mention}"))

    # ---------- warnings ----------
    @commands.hybrid_command(name="warn", description="Warn a member.")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await self.bot.db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, member.id, ctx.author.id, reason, int(time.time())),
        )
        await ctx.send(embed=embeds.success(f"⚠️ Warned {member.mention}\n**Reason:** {reason}"))
        try:
            await member.send(embed=embeds.warning(f"You were warned in **{ctx.guild.name}**\n**Reason:** {reason}"))
        except discord.Forbidden:
            pass

    @commands.hybrid_command(name="warnings", description="View warnings for a member.")
    @app_commands.describe(member="Member to look up")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warnings_cmd(self, ctx: commands.Context, member: discord.Member):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(f"{member.mention} has no warnings."))
        embed = embeds.plain(title=f"Warnings — {member.display_name}")
        for row in rows[:15]:
            mod = ctx.guild.get_member(row["moderator_id"])
            when = datetime.fromtimestamp(row["created_at"], tz=timezone.utc)
            embed.add_field(
                name=f"ID {row['id']} • {discord.utils.format_dt(when, 'R')}",
                value=f"**Reason:** {row['reason']}\n**Moderator:** {mod.mention if mod else row['moderator_id']}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="delwarn", description="Delete a specific warning by ID.")
    @app_commands.describe(warning_id="The warning ID to delete")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def delwarn(self, ctx: commands.Context, warning_id: int):
        row = await self.bot.db.fetchone(
            "SELECT * FROM warnings WHERE id = ? AND guild_id = ?", (warning_id, ctx.guild.id)
        )
        if not row:
            return await ctx.send(embed=embeds.error(f"No warning with ID `{warning_id}` found."))
        await self.bot.db.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        await ctx.send(embed=embeds.success(f"🗑️ Deleted warning `{warning_id}`."))

    @commands.hybrid_command(name="clearwarnings", description="Clear all warnings for a member.")
    @app_commands.describe(member="Member to clear warnings for")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        await self.bot.db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id)
        )
        await ctx.send(embed=embeds.success(f"🧹 Cleared all warnings for {member.mention}."))

    # ---------- nickname ----------
    @commands.hybrid_group(name="nick", description="Change or lock a member's nickname.", invoke_without_command=True)
    @commands.has_permissions(manage_nicknames=True)
    @commands.guild_only()
    async def nick(self, ctx: commands.Context, member: discord.Member, *, new_nick: str = None):
        await member.edit(nick=new_nick, reason=f"Changed by {ctx.author}")
        await ctx.send(embed=embeds.success(f"✏️ Nickname for {member.mention} updated."))

    @nick.command(name="lock", description="Lock a user's nickname so they cannot change it.")
    @commands.has_permissions(manage_nicknames=True)
    async def nick_lock(self, ctx: commands.Context, member: discord.Member):
        self._locked_nicks.add((ctx.guild.id, member.id))
        await ctx.send(embed=embeds.success(f"🔒 Locked {member.mention}'s nickname."))

    @nick.command(name="unlock", description="Unlock a user's nickname.")
    @commands.has_permissions(manage_nicknames=True)
    async def nick_unlock(self, ctx: commands.Context, member: discord.Member):
        self._locked_nicks.discard((ctx.guild.id, member.id))
        await ctx.send(embed=embeds.success(f"🔓 Unlocked {member.mention}'s nickname."))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick and (after.guild.id, after.id) in self._locked_nicks:
            try:
                await after.edit(nick=before.nick, reason="Nickname is locked")
            except discord.Forbidden:
                pass

    # ---------- purge ----------
    @commands.hybrid_command(name="purge", description="Purge messages. !purge <N>, !purge bot, !purge @user <N>")
    @app_commands.describe(amount="Number of messages to delete", target="'bot' or a member (optional)")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def purge(self, ctx: commands.Context, target: str = None, amount: int = 25):
        await ctx.defer(ephemeral=True) if ctx.interaction else None

        def check_bot(m): return m.author.bot
        def check_user(m, uid): return m.author.id == uid

        if target is None:
            deleted = await ctx.channel.purge(limit=25)
        elif target.lower() == "bot":
            deleted = await ctx.channel.purge(limit=amount, check=check_bot)
        else:
            member = await commands.MemberConverter().convert(ctx, target)
            deleted = await ctx.channel.purge(limit=amount, check=lambda m: check_user(m, member.id))
        msg = await ctx.send(embed=embeds.success(f"🧹 Deleted **{len(deleted)}** messages."))
        await msg.delete(delay=4)

    # ---------- channel lock/hide ----------
    async def _set_channel_perm(self, channel: discord.TextChannel, **overwrite_kwargs):
        overwrite = channel.overwrites_for(channel.guild.default_role)
        for k, v in overwrite_kwargs.items():
            setattr(overwrite, k, v)
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)

    @commands.hybrid_command(name="lock", description="Lock a text channel to prevent messages.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self._set_channel_perm(channel, send_messages=False)
        await ctx.send(embed=embeds.success(f"🔒 Locked {channel.mention}"))

    @commands.hybrid_command(name="unlock", description="Unlock a text channel to allow messages.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self._set_channel_perm(channel, send_messages=None)
        await ctx.send(embed=embeds.success(f"🔓 Unlocked {channel.mention}"))

    @commands.hybrid_command(name="hide", description="Hide a text channel from regular members.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def hide(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self._set_channel_perm(channel, view_channel=False)
        await ctx.send(embed=embeds.success(f"🙈 Hid {channel.mention}"))

    @commands.hybrid_command(name="unhide", description="Unhide a text channel to make it visible.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unhide(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self._set_channel_perm(channel, view_channel=None)
        await ctx.send(embed=embeds.success(f"👁️ Unhid {channel.mention}"))

    @commands.hybrid_command(name="lockall", description="Lock all text channels in the server.")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lockall(self, ctx: commands.Context):
        await ctx.defer() if ctx.interaction else None
        for channel in ctx.guild.text_channels:
            try:
                await self._set_channel_perm(channel, send_messages=False)
            except discord.Forbidden:
                continue
        await ctx.send(embed=embeds.success("🔒 Locked all text channels."))

    @commands.hybrid_command(name="unlockall", description="Unlock all text channels in the server.")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlockall(self, ctx: commands.Context):
        await ctx.defer() if ctx.interaction else None
        for channel in ctx.guild.text_channels:
            try:
                await self._set_channel_perm(channel, send_messages=None)
            except discord.Forbidden:
                continue
        await ctx.send(embed=embeds.success("🔓 Unlocked all text channels."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
