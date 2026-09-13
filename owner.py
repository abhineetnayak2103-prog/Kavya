from __future__ import annotations
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

CATEGORY = "Owner"


async def is_guild_owner(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    bot: commands.Bot = interaction.client
    row = await bot.db.fetchone(
        "SELECT 1 FROM bot_admins WHERE guild_id = ? AND user_id = ? AND role = 'owner'",
        (interaction.guild.id, interaction.user.id),
    )
    return bool(row)


class OwnerCheckFailed(app_commands.CheckFailure):
    pass


def owner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_guild_owner(interaction):
            return True
        raise OwnerCheckFailed("Owner-only command.")
    return app_commands.check(predicate)


class OwnerGroup(app_commands.Group):
    def __init__(self, bot: commands.Bot):
        super().__init__(name="owner", description="Owner-only bot & server control.")
        self.bot = bot

    async def _audit(self, interaction: discord.Interaction, action: str, detail: str = ""):
        await self.bot.db.log_owner_action(interaction.guild.id, interaction.user.id, action, detail)

    # ---------- server control ----------
    @app_commands.command(name="lockdown", description="Lock the entire server.")
    @owner_only()
    async def lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite)
            except discord.Forbidden:
                continue
        await self._audit(interaction, "lockdown")
        await interaction.followup.send(embed=embeds.error("🔒 The entire server has been locked down.", title="Server Lockdown"))

    @app_commands.command(name="unlock", description="Unlock the entire server.")
    @owner_only()
    async def unlock(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = None
                await channel.set_permissions(guild.default_role, overwrite=overwrite)
            except discord.Forbidden:
                continue
        await self._audit(interaction, "unlock")
        await interaction.followup.send(embed=embeds.success("🔓 The server has been unlocked."))

    @app_commands.command(name="slowmode-all", description="Set slowmode across every text channel.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
    @owner_only()
    async def slowmode_all(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.response.defer()
        for channel in interaction.guild.text_channels:
            try:
                await channel.edit(slowmode_delay=seconds)
            except discord.Forbidden:
                continue
        await self._audit(interaction, "slowmode-all", f"{seconds}s")
        await interaction.followup.send(embed=embeds.success(f"🐌 Slowmode set to **{seconds}s** across all text channels."))

    @app_commands.command(name="emergency", description="Activate emergency protection.")
    @owner_only()
    async def emergency(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite)
            except discord.Forbidden:
                continue
        await self.bot.db.execute(
            "INSERT INTO antinuke_settings (guild_id, enabled, strict_mode, lockdown, panic_mode) "
            "VALUES (?, 1, 1, 1, 1) ON CONFLICT(guild_id) DO UPDATE SET "
            "enabled = 1, strict_mode = 1, lockdown = 1, panic_mode = 1",
            (guild.id,),
        )
        await self._audit(interaction, "emergency")
        embed = embeds.error(
            "Emergency protection activated:\n"
            "• 🔒 Sensitive channels locked\n"
            "• ⚡ Antinuke enabled (strict + lockdown)\n"
            "• 📜 Detailed security logging started\n"
            "• 🔔 Owner & staff alerted",
            title="🚨 EMERGENCY MODE",
        )
        await interaction.followup.send(embed=embed)

    # ---------- owner management ----------
    @app_commands.command(name="add", description="Add a trusted bot owner for this server.")
    @owner_only()
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO bot_admins (guild_id, user_id, role) VALUES (?, ?, 'owner')",
            (interaction.guild.id, user.id),
        )
        await self._audit(interaction, "owner_add", str(user.id))
        await interaction.response.send_message(embed=embeds.success(f"Added {user.mention} as a bot owner."))

    @app_commands.command(name="remove", description="Remove a trusted bot owner for this server.")
    @owner_only()
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        await self.bot.db.execute(
            "DELETE FROM bot_admins WHERE guild_id = ? AND user_id = ? AND role = 'owner'",
            (interaction.guild.id, user.id),
        )
        await self._audit(interaction, "owner_remove", str(user.id))
        await interaction.response.send_message(embed=embeds.success(f"Removed {user.mention} from bot owners."))

    @app_commands.command(name="list", description="List all trusted bot owners for this server.")
    @owner_only()
    async def list_owners(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT user_id FROM bot_admins WHERE guild_id = ? AND role = 'owner'", (interaction.guild.id,)
        )
        mentions = [f"<@{r['user_id']}>" for r in rows] or ["None — only the server owner has this access."]
        await interaction.response.send_message(embed=embeds.plain(title="Trusted Bot Owners", description="\n".join(mentions)))

    @app_commands.command(name="transfer", description="Transfer primary bot-ownership access to another member.")
    @owner_only()
    async def transfer(self, interaction: discord.Interaction, new_owner: discord.Member):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO bot_admins (guild_id, user_id, role) VALUES (?, ?, 'owner')",
            (interaction.guild.id, new_owner.id),
        )
        await self._audit(interaction, "transfer", str(new_owner.id))
        await interaction.response.send_message(
            embed=embeds.warning(
                f"Bot-owner access transferred/granted to {new_owner.mention}.\n"
                f"Note: actual **Discord server ownership** can only be transferred from Server Settings."
            )
        )

    @app_commands.command(name="permissions", description="Show the bot's permissions in this server.")
    @owner_only()
    async def permissions(self, interaction: discord.Interaction):
        perms = [name.replace("_", " ").title() for name, val in interaction.guild.me.guild_permissions if val]
        embed = embeds.plain(title=f"{self.bot.user.name}'s Permissions", description=", ".join(perms) or "None")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="audit", description="Show sensitive owner actions.")
    @owner_only()
    async def audit(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM owner_audit WHERE guild_id = ? ORDER BY id DESC LIMIT 15", (interaction.guild.id,)
        )
        if not rows:
            return await interaction.response.send_message(embed=embeds.info("No owner actions logged yet."))
        lines = []
        for row in rows:
            when = datetime.fromtimestamp(row["created_at"], tz=timezone.utc)
            lines.append(f"<t:{int(when.timestamp())}:R> <@{row['actor_id']}> — **{row['action']}** {row['detail']}")
        await interaction.response.send_message(embed=embeds.plain(title="👑 Owner Audit Log", description="\n".join(lines)))

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, OwnerCheckFailed):
            await interaction.response.send_message(
                embed=embeds.error("This command is restricted to the server owner or trusted bot owners."),
                ephemeral=True,
            )
            return
        raise error


class Owner(commands.Cog):
    """Owner-only bot & server control (slash commands under /owner)."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = OwnerGroup(bot)
        bot.tree.add_command(self.group)

    async def cog_unload(self):
        self.bot.tree.remove_command("owner")


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
