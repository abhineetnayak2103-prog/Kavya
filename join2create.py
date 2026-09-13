from __future__ import annotations
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Join2Create"


class Join2Create(commands.Cog):
    """Dynamic voice channel creation — join the trigger channel to get your own room."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _settings(self, guild_id: int):
        return await self.bot.db.fetchone("SELECT * FROM join2create_settings WHERE guild_id = ?", (guild_id,))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        settings = await self._settings(member.guild.id)
        if not settings:
            return

        # user joined the trigger channel -> create them a room
        if after.channel and after.channel.id == settings["trigger_channel_id"]:
            category = member.guild.get_channel(settings["category_id"]) if settings["category_id"] else after.channel.category
            name = settings["name_template"].replace("{user.name}", member.display_name)
            new_channel = await member.guild.create_voice_channel(
                name=name, category=category,
                overwrites={member: discord.PermissionOverwrite(manage_channels=True, move_members=True)},
                reason=f"Join2Create for {member}",
            )
            await self.bot.db.execute(
                "INSERT INTO join2create_channels (channel_id, guild_id, owner_id) VALUES (?, ?, ?)",
                (new_channel.id, member.guild.id, member.id),
            )
            try:
                await member.move_to(new_channel)
            except discord.HTTPException:
                pass

        # user left a J2C-created channel -> delete it if empty
        if before.channel:
            row = await self.bot.db.fetchone(
                "SELECT * FROM join2create_channels WHERE channel_id = ?", (before.channel.id,)
            )
            if row and len(before.channel.members) == 0:
                await self.bot.db.execute("DELETE FROM join2create_channels WHERE channel_id = ?", (before.channel.id,))
                try:
                    await before.channel.delete(reason="Join2Create room empty")
                except discord.HTTPException:
                    pass

    @commands.hybrid_group(name="join2create", description="Configure the join-to-create voice system.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def join2create(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        embed = embeds.plain(title="🔊 Join2Create")
        if s:
            trig = ctx.guild.get_channel(s["trigger_channel_id"])
            embed.add_field(name="Trigger Channel", value=trig.mention if trig else "Deleted")
            embed.add_field(name="Name Template", value=f"`{s['name_template']}`")
        else:
            embed.description = "Not configured. Use `join2create setup #trigger-channel`."
        await ctx.send(embed=embed)

    @join2create.command(name="setup", description="Set the voice channel that triggers room creation.")
    @commands.has_permissions(administrator=True)
    async def join2create_setup(self, ctx: commands.Context, trigger_channel: discord.VoiceChannel):
        await self.bot.db.execute(
            "INSERT INTO join2create_settings (guild_id, trigger_channel_id, category_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET trigger_channel_id = excluded.trigger_channel_id, "
            "category_id = excluded.category_id",
            (ctx.guild.id, trigger_channel.id, trigger_channel.category_id),
        )
        await ctx.send(embed=embeds.success(f"Join2Create set up on {trigger_channel.mention}."))

    @join2create.command(name="template", description="Set the name template for created rooms.")
    @commands.has_permissions(administrator=True)
    async def join2create_template(self, ctx: commands.Context, *, template: str):
        await self.bot.db.execute(
            "UPDATE join2create_settings SET name_template = ? WHERE guild_id = ?", (template, ctx.guild.id)
        )
        await ctx.send(embed=embeds.success(f"Room name template set to `{template}` (use `{{user.name}}`)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Join2Create(bot))
