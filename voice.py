from __future__ import annotations
import asyncio
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Voice"


class Voice(commands.Cog):
    """Deafen, mute, kick, or pull voice members, and configure voice roles."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _voice_channel_of(self, member: discord.Member) -> discord.VoiceChannel | None:
        return member.voice.channel if member.voice else None

    @commands.hybrid_command(name="vckick", description="Disconnect a member from their voice channel.")
    @commands.has_permissions(move_members=True)
    @commands.guild_only()
    async def vckick(self, ctx: commands.Context, member: discord.Member):
        if not self._voice_channel_of(member):
            return await ctx.send(embed=embeds.error(f"{member.mention} isn't in a voice channel."))
        await member.move_to(None, reason=f"VC kicked by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Disconnected {member.mention} from voice."))

    @commands.hybrid_command(name="vcpull", description="Pull a member into your voice channel.")
    @commands.has_permissions(move_members=True)
    @commands.guild_only()
    async def vcpull(self, ctx: commands.Context, member: discord.Member):
        channel = self._voice_channel_of(ctx.author)
        if not channel:
            return await ctx.send(embed=embeds.error("Join a voice channel first."))
        await member.move_to(channel, reason=f"VC pulled by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Pulled {member.mention} into {channel.mention}."))

    @commands.hybrid_command(name="vcmute", description="Server voice-mute a member.")
    @commands.has_permissions(mute_members=True)
    @commands.guild_only()
    async def vcmute(self, ctx: commands.Context, member: discord.Member):
        await member.edit(mute=True, reason=f"VC muted by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Voice-muted {member.mention}."))

    @commands.hybrid_command(name="vcdeafen", description="Server voice-deafen a member.")
    @commands.has_permissions(deafen_members=True)
    @commands.guild_only()
    async def vcdeafen(self, ctx: commands.Context, member: discord.Member):
        await member.edit(deafen=True, reason=f"VC deafened by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Voice-deafened {member.mention}."))

    @commands.hybrid_command(name="vcpullall", description="Pull everyone from a voice channel into yours.")
    @commands.has_permissions(move_members=True)
    @commands.guild_only()
    async def vcpullall(self, ctx: commands.Context, source: discord.VoiceChannel):
        dest = self._voice_channel_of(ctx.author)
        if not dest:
            return await ctx.send(embed=embeds.error("Join a voice channel first."))
        moved = 0
        for member in list(source.members):
            try:
                await member.move_to(dest, reason=f"VC pull-all by {ctx.author}")
                moved += 1
                await asyncio.sleep(0.25)
            except discord.HTTPException:
                continue
        await ctx.send(embed=embeds.success(f"Pulled **{moved}** member(s) into {dest.mention}."))

    @commands.hybrid_command(name="vckickall", description="Disconnect everyone from a voice channel.")
    @commands.has_permissions(move_members=True)
    @commands.guild_only()
    async def vckickall(self, ctx: commands.Context, channel: discord.VoiceChannel):
        moved = 0
        for member in list(channel.members):
            try:
                await member.move_to(None, reason=f"VC kick-all by {ctx.author}")
                moved += 1
                await asyncio.sleep(0.25)
            except discord.HTTPException:
                continue
        await ctx.send(embed=embeds.success(f"Disconnected **{moved}** member(s) from {channel.mention}."))

    @commands.hybrid_command(name="vcdeafenall", description="Server voice-deafen everyone in a voice channel.")
    @commands.has_permissions(deafen_members=True)
    @commands.guild_only()
    async def vcdeafenall(self, ctx: commands.Context, channel: discord.VoiceChannel):
        count = 0
        for member in channel.members:
            try:
                await member.edit(deafen=True, reason=f"VC deafen-all by {ctx.author}")
                count += 1
                await asyncio.sleep(0.25)
            except discord.HTTPException:
                continue
        await ctx.send(embed=embeds.success(f"Deafened **{count}** member(s) in {channel.mention}."))

    # ---------- vc role ----------
    @commands.hybrid_group(name="vcrole", description="Configure roles given to users when they join voice channels.", invoke_without_command=True)
    @commands.guild_only()
    async def vcrole(self, ctx: commands.Context):
        row = await self.bot.db.fetchone("SELECT role_id FROM vcrole_settings WHERE guild_id = ?", (ctx.guild.id,))
        role = ctx.guild.get_role(row["role_id"]) if row else None
        await ctx.send(embed=embeds.info(f"Current VC role: {role.mention if role else 'Not set'}"))

    @vcrole.command(name="add", description="Set the role given to members when they join a voice channel.")
    @commands.has_permissions(manage_roles=True)
    async def vcrole_add(self, ctx: commands.Context, role: discord.Role):
        await self.bot.db.execute(
            "INSERT INTO vcrole_settings (guild_id, role_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET role_id = excluded.role_id",
            (ctx.guild.id, role.id),
        )
        await ctx.send(embed=embeds.success(f"VC role set to {role.mention}."))

    @vcrole.command(name="remove", description="Disable and remove the voice role setting.")
    @commands.has_permissions(manage_roles=True)
    async def vcrole_remove(self, ctx: commands.Context):
        await self.bot.db.execute("DELETE FROM vcrole_settings WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=embeds.success("VC role setting removed."))

    @vcrole.command(name="show", description="Show the current voice role configuration.")
    async def vcrole_show(self, ctx: commands.Context):
        await self.vcrole(ctx)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        row = await self.bot.db.fetchone("SELECT role_id FROM vcrole_settings WHERE guild_id = ?", (member.guild.id,))
        if not row:
            return
        role = member.guild.get_role(row["role_id"])
        if not role:
            return
        try:
            if after.channel and not before.channel:
                await member.add_roles(role, reason="Joined voice")
            elif before.channel and not after.channel:
                await member.remove_roles(role, reason="Left voice")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
