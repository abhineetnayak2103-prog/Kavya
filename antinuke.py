from __future__ import annotations
import time
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

CATEGORY = "Antinuke"

# actions per rolling 30-second window before punishment triggers (non-strict mode)
DEFAULT_THRESHOLD = 3
WINDOW_SECONDS = 30


class Antinuke(commands.Cog):
    """Protects the server from malicious administrators."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- internal helpers ----------
    async def _settings(self, guild_id: int):
        row = await self.bot.db.fetchone(
            "SELECT * FROM antinuke_settings WHERE guild_id = ?", (guild_id,)
        )
        if not row:
            await self.bot.db.execute(
                "INSERT INTO antinuke_settings (guild_id) VALUES (?)", (guild_id,)
            )
            row = await self.bot.db.fetchone(
                "SELECT * FROM antinuke_settings WHERE guild_id = ?", (guild_id,)
            )
        return row

    async def _is_whitelisted(self, guild: discord.Guild, member: discord.Member) -> bool:
        if member.id == guild.owner_id or member.id == self.bot.user.id:
            return True
        owner_row = await self.bot.db.fetchone(
            "SELECT 1 FROM antinuke_owners WHERE guild_id = ? AND user_id = ?", (guild.id, member.id)
        )
        if owner_row:
            return True
        wl_user = await self.bot.db.fetchone(
            "SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND entity_id = ? AND entity_type = 'user'",
            (guild.id, member.id),
        )
        if wl_user:
            return True
        role_ids = [r.id for r in member.roles]
        if role_ids:
            placeholders = ",".join("?" * len(role_ids))
            wl_role = await self.bot.db.fetchone(
                f"SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND entity_type = 'role' "
                f"AND entity_id IN ({placeholders})",
                (guild.id, *role_ids),
            )
            if wl_role:
                return True
        return False

    async def _punish(self, guild: discord.Guild, member: discord.Member, settings, reason: str):
        log_ch = guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None
        punishment = settings["punishment"] or "ban"
        acted = "none"
        try:
            if punishment == "ban":
                await guild.ban(member, reason=f"Antinuke: {reason}")
                acted = "banned"
            elif punishment == "kick":
                await guild.kick(member, reason=f"Antinuke: {reason}")
                acted = "kicked"
            elif punishment == "striproles":
                await member.edit(roles=[], reason=f"Antinuke: {reason}")
                acted = "stripped of roles"
        except discord.Forbidden:
            acted = "detected but I lack permission to act"
        if log_ch:
            embed = embeds.error(
                f"**Member:** {member.mention} (`{member.id}`)\n"
                f"**Trigger:** {reason}\n**Action taken:** {acted}",
                title="🛡️ Antinuke Triggered",
            )
            try:
                await log_ch.send(embed=embed)
            except discord.Forbidden:
                pass

    async def _flag(self, guild: discord.Guild, actor: discord.Member, reason: str):
        settings = await self._settings(guild.id)
        if not settings["enabled"]:
            return
        if await self._is_whitelisted(guild, actor):
            return

        if settings["strict_mode"]:
            await self._punish(guild, actor, settings, reason)
            return

        now = int(time.time())
        row = await self.bot.db.fetchone(
            "SELECT * FROM antinuke_offenses WHERE guild_id = ? AND user_id = ?", (guild.id, actor.id)
        )
        if row and now - row["window_start"] < WINDOW_SECONDS:
            count = row["count"] + 1
        else:
            count = 1
        await self.bot.db.execute(
            "INSERT INTO antinuke_offenses (guild_id, user_id, count, window_start) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET count = excluded.count, window_start = excluded.window_start",
            (guild.id, actor.id, count, now if count == 1 else row["window_start"]),
        )
        if count >= DEFAULT_THRESHOLD:
            await self._punish(guild, actor, settings, reason)

    # ---------- listeners: the actual protection ----------
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if isinstance(entry.user, discord.Member):
                await self._flag(channel.guild, entry.user, "Deleted a channel")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            if isinstance(entry.user, discord.Member):
                await self._flag(channel.guild, entry.user, "Created a channel")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            if isinstance(entry.user, discord.Member):
                await self._flag(role.guild, entry.user, "Deleted a role")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            if isinstance(entry.user, discord.Member):
                await self._flag(role.guild, entry.user, "Created a role")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if isinstance(entry.user, discord.Member):
                await self._flag(guild, entry.user, "Banned a member")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if isinstance(entry.user, discord.Member) and (discord.utils.utcnow() - entry.created_at).total_seconds() < 5:
                await self._flag(guild, entry.user, "Kicked a member")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
            if isinstance(entry.user, discord.Member):
                await self._flag(after, entry.user, "Modified server settings")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
            if isinstance(entry.user, discord.Member):
                await self._flag(member.guild, entry.user, f"Added a bot ({member})")

    # ---------- commands ----------
    @commands.hybrid_group(name="antinuke", description="Show antinuke overview & command guide.", invoke_without_command=True)
    @commands.guild_only()
    async def antinuke(self, ctx: commands.Context):
        settings = await self._settings(ctx.guild.id)
        embed = embeds.plain(title="⚡ Antinuke", description="Protects your server against malicious administrators.")
        embed.add_field(name="Status", value="🟢 Enabled" if settings["enabled"] else "🔴 Disabled")
        embed.add_field(name="Punishment", value=settings["punishment"])
        embed.add_field(name="Strict Mode", value="On" if settings["strict_mode"] else "Off")
        log_ch = ctx.guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set")
        embed.add_field(
            name="Subcommands",
            value="`setup` `enable` `disable` `status` `owner` `whitelist` `wlrole` "
                  "`punishment` `logging` `strict` `lockdown` `panic` `recover`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @antinuke.command(name="setup", description="Interactive antinuke setup wizard.")
    @commands.has_permissions(administrator=True)
    async def antinuke_setup(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET enabled = 1 WHERE guild_id = ?", (ctx.guild.id,)
        )
        embed = embeds.info(
            "Antinuke has been enabled with default settings.\n\n"
            "Next steps:\n"
            "1️⃣ `antinuke logging #channel` — set where alerts go\n"
            "2️⃣ `antinuke punishment ban|kick|striproles` — choose the response\n"
            "3️⃣ `antinuke owner add @user` — add trusted co-owners\n"
            "4️⃣ `antinuke whitelist add @user` — exempt trusted staff",
            title="⚡ Antinuke Setup",
        )
        await ctx.send(embed=embed)

    @antinuke.command(name="enable", description="Enable antinuke protection.")
    @commands.has_permissions(administrator=True)
    async def antinuke_enable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antinuke_settings SET enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("⚡ Antinuke protection enabled."))

    @antinuke.command(name="disable", description="Disable antinuke protection.")
    @commands.has_permissions(administrator=True)
    async def antinuke_disable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE antinuke_settings SET enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.warning("Antinuke protection disabled."))

    @antinuke.command(name="status", description="Show detailed antinuke status & configuration.")
    async def antinuke_status(self, ctx: commands.Context):
        await self.antinuke(ctx)

    @antinuke.group(name="owner", description="Antinuke owner management.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_owner(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT user_id FROM antinuke_owners WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=embeds.info("No antinuke owners set. Use `antinuke owner add @user`."))
        mentions = [f"<@{r['user_id']}>" for r in rows]
        await ctx.send(embed=embeds.plain(title="Antinuke Owners", description="\n".join(mentions)))

    @antinuke_owner.command(name="add", description="Add an antinuke owner (fully exempt).")
    @commands.has_permissions(administrator=True)
    async def antinuke_owner_add(self, ctx: commands.Context, member: discord.Member):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO antinuke_owners (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, member.id)
        )
        await ctx.send(embed=embeds.success(f"Added {member.mention} as an antinuke owner."))

    @antinuke_owner.command(name="remove", description="Remove an antinuke owner.")
    @commands.has_permissions(administrator=True)
    async def antinuke_owner_remove(self, ctx: commands.Context, member: discord.Member):
        await self.bot.db.execute(
            "DELETE FROM antinuke_owners WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id)
        )
        await ctx.send(embed=embeds.success(f"Removed {member.mention} from antinuke owners."))

    @antinuke.group(name="whitelist", description="Whitelist a user from antinuke actions.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall(
            "SELECT entity_id FROM antinuke_whitelist WHERE guild_id = ? AND entity_type = 'user'", (ctx.guild.id,)
        )
        mentions = [f"<@{r['entity_id']}>" for r in rows] or ["None"]
        await ctx.send(embed=embeds.plain(title="Antinuke Whitelisted Users", description="\n".join(mentions)))

    @antinuke_whitelist.command(name="add", description="Whitelist a user.")
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_add(self, ctx: commands.Context, member: discord.Member):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO antinuke_whitelist (guild_id, entity_id, entity_type) VALUES (?, ?, 'user')",
            (ctx.guild.id, member.id),
        )
        await ctx.send(embed=embeds.success(f"Whitelisted {member.mention}."))

    @antinuke_whitelist.command(name="remove", description="Remove a user from the whitelist.")
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_remove(self, ctx: commands.Context, member: discord.Member):
        await self.bot.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND entity_id = ? AND entity_type = 'user'",
            (ctx.guild.id, member.id),
        )
        await ctx.send(embed=embeds.success(f"Removed {member.mention} from the whitelist."))

    @antinuke.group(name="wlrole", description="Whitelist an entire role from antinuke actions.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_wlrole(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall(
            "SELECT entity_id FROM antinuke_whitelist WHERE guild_id = ? AND entity_type = 'role'", (ctx.guild.id,)
        )
        mentions = [f"<@&{r['entity_id']}>" for r in rows] or ["None"]
        await ctx.send(embed=embeds.plain(title="Antinuke Whitelisted Roles", description="\n".join(mentions)))

    @antinuke_wlrole.command(name="add", description="Whitelist a role.")
    @commands.has_permissions(administrator=True)
    async def antinuke_wlrole_add(self, ctx: commands.Context, role: discord.Role):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO antinuke_whitelist (guild_id, entity_id, entity_type) VALUES (?, ?, 'role')",
            (ctx.guild.id, role.id),
        )
        await ctx.send(embed=embeds.success(f"Whitelisted the {role.mention} role."))

    @antinuke_wlrole.command(name="remove", description="Remove a role from the whitelist.")
    @commands.has_permissions(administrator=True)
    async def antinuke_wlrole_remove(self, ctx: commands.Context, role: discord.Role):
        await self.bot.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND entity_id = ? AND entity_type = 'role'",
            (ctx.guild.id, role.id),
        )
        await ctx.send(embed=embeds.success(f"Removed the {role.mention} role from the whitelist."))

    @antinuke.command(name="punishment", description="Set the punishment for detected nukers.")
    @app_commands.describe(action="ban, kick, or striproles")
    @app_commands.choices(action=[
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Strip Roles", value="striproles"),
    ])
    @commands.has_permissions(administrator=True)
    async def antinuke_punishment(self, ctx: commands.Context, action: str):
        if action not in ("ban", "kick", "striproles"):
            return await ctx.send(embed=embeds.error("Choose one of: `ban`, `kick`, `striproles`."))
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET punishment = ? WHERE guild_id = ?", (action, ctx.guild.id)
        )
        await ctx.send(embed=embeds.success(f"Antinuke punishment set to **{action}**."))

    @antinuke.command(name="logging", description="Set the antinuke log channel.")
    @commands.has_permissions(administrator=True)
    async def antinuke_logging(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET log_channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id)
        )
        await ctx.send(embed=embeds.success(f"Antinuke alerts will be sent to {channel.mention}."))

    @antinuke.command(name="strict", description="Toggle strict mode (immediate action on single violation).")
    @commands.has_permissions(administrator=True)
    async def antinuke_strict(self, ctx: commands.Context):
        settings = await self._settings(ctx.guild.id)
        new_val = 0 if settings["strict_mode"] else 1
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET strict_mode = ? WHERE guild_id = ?", (new_val, ctx.guild.id)
        )
        await ctx.send(embed=embeds.success(f"Strict mode is now **{'on' if new_val else 'off'}**."))

    @antinuke.command(name="lockdown", description="Toggle server lockdown (block all new joins).")
    @commands.has_permissions(administrator=True)
    async def antinuke_lockdown(self, ctx: commands.Context):
        settings = await self._settings(ctx.guild.id)
        new_val = 0 if settings["lockdown"] else 1
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET lockdown = ? WHERE guild_id = ?", (new_val, ctx.guild.id)
        )
        try:
            invites = await ctx.guild.invites()
            if new_val:
                for inv in invites:
                    await inv.delete(reason="Antinuke lockdown")
        except discord.Forbidden:
            pass
        await ctx.send(embed=embeds.success(f"Server lockdown is now **{'ON' if new_val else 'OFF'}**."))

    @antinuke.command(name="panic", description="Activate instant maximum server lockdown (emergency mode).")
    @commands.has_permissions(administrator=True)
    async def antinuke_panic(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET enabled = 1, strict_mode = 1, lockdown = 1, panic_mode = 1 "
            "WHERE guild_id = ?", (ctx.guild.id,)
        )
        for channel in ctx.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            except discord.Forbidden:
                continue
        await ctx.send(embed=embeds.error("🚨 **PANIC MODE ACTIVATED** — server locked, strict mode & lockdown on.",
                                           title="Emergency Lockdown"))

    @antinuke.command(name="recover", description="Recover security settings back to normal from panic mode.")
    @commands.has_permissions(administrator=True)
    async def antinuke_recover(self, ctx: commands.Context):
        await self.bot.db.execute(
            "UPDATE antinuke_settings SET strict_mode = 0, lockdown = 0, panic_mode = 0 WHERE guild_id = ?",
            (ctx.guild.id,),
        )
        for channel in ctx.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = None
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            except discord.Forbidden:
                continue
        await ctx.send(embed=embeds.success("✅ Server recovered from panic mode. Channels unlocked."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Antinuke(bot))
