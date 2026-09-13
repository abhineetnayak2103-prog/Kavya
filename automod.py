from __future__ import annotations
import re
import time
from collections import defaultdict, deque
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "AutoMod"
LINK_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
SPAM_MSG_COUNT = 5
SPAM_WINDOW_SECONDS = 5


class AutoMod(commands.Cog):
    """Automated filters for links, spam messages, and bad words."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_msgs: dict[tuple[int, int], deque] = defaultdict(deque)

    async def _settings(self, guild_id: int):
        row = await self.bot.db.fetchone("SELECT * FROM automod_settings WHERE guild_id = ?", (guild_id,))
        if not row:
            await self.bot.db.execute("INSERT INTO automod_settings (guild_id) VALUES (?)", (guild_id,))
            row = await self.bot.db.fetchone("SELECT * FROM automod_settings WHERE guild_id = ?", (guild_id,))
        return row

    async def _is_whitelisted(self, guild_id: int, module: str, member: discord.Member) -> bool:
        role_ids = [r.id for r in member.roles]
        placeholders = ",".join("?" * len(role_ids)) if role_ids else "0"
        row = await self.bot.db.fetchone(
            f"SELECT 1 FROM automod_whitelist WHERE guild_id = ? AND module = ? AND "
            f"((entity_type = 'user' AND entity_id = ?) OR (entity_type = 'role' AND entity_id IN ({placeholders})))",
            (guild_id, module, member.id, *role_ids),
        )
        return bool(row)

    async def _punish(self, message: discord.Message, settings, reason: str):
        punishment = settings["punishment"] or "warn"
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        try:
            if punishment == "warn":
                await self.bot.db.execute(
                    "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                    (message.guild.id, message.author.id, self.bot.user.id, reason, int(time.time())),
                )
            elif punishment == "mute":
                from datetime import timedelta
                await message.author.timeout(timedelta(minutes=10), reason=reason)
            elif punishment == "kick":
                await message.author.kick(reason=reason)
        except discord.Forbidden:
            pass
        try:
            await message.channel.send(
                embed=embeds.warning(f"{message.author.mention}, that message was removed: **{reason}**"),
                delete_after=6,
            )
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator:
            return

        settings = await self._settings(message.guild.id)

        if settings["antilink_enabled"] and LINK_RE.search(message.content):
            if not await self._is_whitelisted(message.guild.id, "antilink", message.author):
                return await self._punish(message, settings, "Posting links is not allowed here")

        if settings["antiword_enabled"]:
            words = await self.bot.db.fetchall("SELECT word FROM bad_words WHERE guild_id = ?", (message.guild.id,))
            lowered = message.content.lower()
            for row in words:
                if row["word"].lower() in lowered:
                    if not await self._is_whitelisted(message.guild.id, "antiword", message.author):
                        return await self._punish(message, settings, "Used a filtered word")
                    break

        if settings["antispam_enabled"]:
            if not await self._is_whitelisted(message.guild.id, "antispam", message.author):
                key = (message.guild.id, message.author.id)
                dq = self.recent_msgs[key]
                now = time.time()
                dq.append(now)
                while dq and now - dq[0] > SPAM_WINDOW_SECONDS:
                    dq.popleft()
                if len(dq) >= SPAM_MSG_COUNT:
                    dq.clear()
                    return await self._punish(message, settings, "Sending messages too quickly")

    # ---------- automod (general) ----------
    @commands.hybrid_command(name="automod", description="Configure and manage automod punishments.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def automod(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        embed = embeds.plain(title="🤖 AutoMod Overview")
        embed.add_field(name="Antispam", value="🟢 On" if s["antispam_enabled"] else "🔴 Off")
        embed.add_field(name="Antilink", value="🟢 On" if s["antilink_enabled"] else "🔴 Off")
        embed.add_field(name="Antiword", value="🟢 On" if s["antiword_enabled"] else "🔴 Off")
        embed.add_field(name="Punishment", value=s["punishment"], inline=False)
        embed.add_field(
            name="See also", value="`antispam`, `antilink`, `antiword` — each has `enable`/`disable`/`wl add`/`wl remove`/`wl list`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="automodpunishment", description="Set the automod punishment: warn, mute, or kick.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def automod_punishment(self, ctx: commands.Context, action: str):
        if action not in ("warn", "mute", "kick"):
            return await ctx.send(embed=embeds.error("Choose one of: `warn`, `mute`, `kick`."))
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET punishment = ? WHERE guild_id = ?", (action, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"AutoMod punishment set to **{action}**."))

    # ---------- antispam / antilink / antiword ----------
    @commands.hybrid_group(name="antispam", description="Configure and manage antispam system.", invoke_without_command=True)
    @commands.guild_only()
    async def antispam(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        await ctx.send(embed=embeds.info(f"Antispam is currently **{'on' if s['antispam_enabled'] else 'off'}**."))

    @antispam.command(name="enable", description="Enable antispam detection.")
    @commands.has_permissions(administrator=True)
    async def antispam_enable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antispam_enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("Antispam enabled."))

    @antispam.command(name="disable", description="Disable antispam detection.")
    @commands.has_permissions(administrator=True)
    async def antispam_disable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antispam_enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.warning("Antispam disabled."))

    @antispam.group(name="wl", description="Manage the antispam whitelist.", invoke_without_command=True)
    async def antispam_wl(self, ctx: commands.Context):
        await self._wl_list(ctx, "antispam")

    @antispam_wl.command(name="add", description="Add a user or role to the antispam whitelist.")
    @commands.has_permissions(administrator=True)
    async def antispam_wl_add(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_add(ctx, "antispam", target)

    @antispam_wl.command(name="remove", description="Remove a user or role from the antispam whitelist.")
    @commands.has_permissions(administrator=True)
    async def antispam_wl_remove(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_remove(ctx, "antispam", target)

    @antispam_wl.command(name="list", description="List all whitelisted users and roles for antispam.")
    async def antispam_wl_list(self, ctx: commands.Context):
        await self._wl_list(ctx, "antispam")

    @commands.hybrid_group(name="antilink", description="Configure and manage antilink system.", invoke_without_command=True)
    @commands.guild_only()
    async def antilink(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        await ctx.send(embed=embeds.info(f"Antilink is currently **{'on' if s['antilink_enabled'] else 'off'}**."))

    @antilink.command(name="enable", description="Enable antilink detection.")
    @commands.has_permissions(administrator=True)
    async def antilink_enable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antilink_enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("Antilink enabled."))

    @antilink.command(name="disable", description="Disable antilink detection.")
    @commands.has_permissions(administrator=True)
    async def antilink_disable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antilink_enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.warning("Antilink disabled."))

    @antilink.group(name="wl", description="Manage the antilink whitelist.", invoke_without_command=True)
    async def antilink_wl(self, ctx: commands.Context):
        await self._wl_list(ctx, "antilink")

    @antilink_wl.command(name="add", description="Add a user or role to the antilink whitelist.")
    @commands.has_permissions(administrator=True)
    async def antilink_wl_add(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_add(ctx, "antilink", target)

    @antilink_wl.command(name="remove", description="Remove a user or role from the antilink whitelist.")
    @commands.has_permissions(administrator=True)
    async def antilink_wl_remove(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_remove(ctx, "antilink", target)

    @antilink_wl.command(name="list", description="List all whitelisted users and roles for antilink.")
    async def antilink_wl_list(self, ctx: commands.Context):
        await self._wl_list(ctx, "antilink")

    @commands.hybrid_group(name="antiword", description="Configure and manage bad words filter.", invoke_without_command=True)
    @commands.guild_only()
    async def antiword(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        await ctx.send(embed=embeds.info(f"Antiword is currently **{'on' if s['antiword_enabled'] else 'off'}**."))

    @antiword.command(name="enable", description="Enable antiword detection.")
    @commands.has_permissions(administrator=True)
    async def antiword_enable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antiword_enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("Antiword enabled."))

    @antiword.command(name="disable", description="Disable antiword detection.")
    @commands.has_permissions(administrator=True)
    async def antiword_disable(self, ctx: commands.Context):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE automod_settings SET antiword_enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.warning("Antiword disabled."))

    @antiword.command(name="add", description="Add a bad word to the filter.")
    @commands.has_permissions(administrator=True)
    async def antiword_add(self, ctx: commands.Context, *, word: str):
        await self.bot.db.execute("INSERT OR IGNORE INTO bad_words (guild_id, word) VALUES (?, ?)", (ctx.guild.id, word.lower()))
        await ctx.send(embed=embeds.success(f"Added `{word}` to the filtered words list."))

    @antiword.command(name="remove", description="Remove a bad word from the filter.")
    @commands.has_permissions(administrator=True)
    async def antiword_remove(self, ctx: commands.Context, *, word: str):
        await self.bot.db.execute("DELETE FROM bad_words WHERE guild_id = ? AND word = ?", (ctx.guild.id, word.lower()))
        await ctx.send(embed=embeds.success(f"Removed `{word}` from the filtered words list."))

    @antiword.command(name="list", description="List all bad words.")
    @commands.has_permissions(administrator=True)
    async def antiword_list(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT word FROM bad_words WHERE guild_id = ?", (ctx.guild.id,))
        words = ", ".join(f"`{r['word']}`" for r in rows) or "None set."
        await ctx.send(embed=embeds.plain(title="Filtered Words", description=words))

    @antiword.group(name="wl", description="Manage the antiword whitelist.", invoke_without_command=True)
    async def antiword_wl(self, ctx: commands.Context):
        await self._wl_list(ctx, "antiword")

    @antiword_wl.command(name="add", description="Add a user or role to the antiword whitelist.")
    @commands.has_permissions(administrator=True)
    async def antiword_wl_add(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_add(ctx, "antiword", target)

    @antiword_wl.command(name="remove", description="Remove a user or role from the antiword whitelist.")
    @commands.has_permissions(administrator=True)
    async def antiword_wl_remove(self, ctx: commands.Context, target: discord.Member | discord.Role):
        await self._wl_remove(ctx, "antiword", target)

    @antiword_wl.command(name="list", description="List all whitelisted users and roles for antiword.")
    async def antiword_wl_list(self, ctx: commands.Context):
        await self._wl_list(ctx, "antiword")

    # ---------- shared whitelist helpers ----------
    async def _wl_add(self, ctx: commands.Context, module: str, target):
        etype = "role" if isinstance(target, discord.Role) else "user"
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO automod_whitelist (guild_id, module, entity_id, entity_type) VALUES (?, ?, ?, ?)",
            (ctx.guild.id, module, target.id, etype),
        )
        await ctx.send(embed=embeds.success(f"Whitelisted {target.mention} for **{module}**."))

    async def _wl_remove(self, ctx: commands.Context, module: str, target):
        etype = "role" if isinstance(target, discord.Role) else "user"
        await self.bot.db.execute(
            "DELETE FROM automod_whitelist WHERE guild_id = ? AND module = ? AND entity_id = ? AND entity_type = ?",
            (ctx.guild.id, module, target.id, etype),
        )
        await ctx.send(embed=embeds.success(f"Removed {target.mention} from the **{module}** whitelist."))

    async def _wl_list(self, ctx: commands.Context, module: str):
        rows = await self.bot.db.fetchall(
            "SELECT entity_id, entity_type FROM automod_whitelist WHERE guild_id = ? AND module = ?",
            (ctx.guild.id, module),
        )
        if not rows:
            return await ctx.send(embed=embeds.info(f"No whitelisted users/roles for **{module}**."))
        lines = [f"<@{'&' if r['entity_type']=='role' else ''}{r['entity_id']}>" for r in rows]
        await ctx.send(embed=embeds.plain(title=f"{module.title()} Whitelist", description="\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
