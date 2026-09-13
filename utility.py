from __future__ import annotations
import discord
from discord.ext import commands

import config
from utils import embeds

CATEGORY = "Utility"


class Utility(commands.Cog):
    """Prefix settings, permission checks, admin lists & bot info."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="myperms", description="Show all your permissions in this server.")
    @commands.guild_only()
    async def myperms(self, ctx: commands.Context):
        perms = [name.replace("_", " ").title() for name, val in ctx.author.guild_permissions if val]
        embed = embeds.plain(title=f"{ctx.author.display_name}'s Permissions", description=", ".join(perms) or "None")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="viewperms", description="Show all permissions of a tagged member.")
    @commands.guild_only()
    async def viewperms(self, ctx: commands.Context, member: discord.Member):
        perms = [name.replace("_", " ").title() for name, val in member.guild_permissions if val]
        embed = embeds.plain(title=f"{member.display_name}'s Permissions", description=", ".join(perms) or "None")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="botperms", description="Show the bot's permissions in this server.")
    @commands.guild_only()
    async def botperms(self, ctx: commands.Context):
        perms = [name.replace("_", " ").title() for name, val in ctx.guild.me.guild_permissions if val]
        embed = embeds.plain(title=f"{self.bot.user.name}'s Permissions", description=", ".join(perms) or "None")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="listadmins", description="Show all members with Administrator permissions, divided by humans and bots.")
    @commands.guild_only()
    async def listadmins(self, ctx: commands.Context):
        humans, bots = [], []
        for m in ctx.guild.members:
            if m.guild_permissions.administrator:
                (bots if m.bot else humans).append(m.mention)
        embed = embeds.plain(title="Server Administrators")
        embed.add_field(name=f"👤 Humans ({len(humans)})", value="\n".join(humans) or "None", inline=False)
        embed.add_field(name=f"🤖 Bots ({len(bots)})", value="\n".join(bots) or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="viewroles", description="Show all roles in the server (or for a specific user).")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def viewroles(self, ctx: commands.Context, member: discord.Member = None):
        if member:
            roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
            embed = embeds.plain(title=f"{member.display_name}'s Roles ({len(roles)})", description=", ".join(roles) or "None")
        else:
            roles = [f"{r.mention} — {len(r.members)} member(s)" for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
            embed = embeds.plain(title=f"Server Roles ({len(roles)})", description="\n".join(roles[:25]) or "None")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="prefix", description="View or manage the server's prefix.", invoke_without_command=True)
    @commands.guild_only()
    async def prefix(self, ctx: commands.Context):
        current = await self.bot.db.get_prefix(ctx.guild.id, config.DEFAULT_PREFIX)
        await ctx.send(embed=embeds.info(f"My prefix here is `{current}`"))

    @prefix.command(name="set", description="Set a custom prefix for this server.")
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx: commands.Context, new_prefix: str):
        if len(new_prefix) > 5:
            return await ctx.send(embed=embeds.error("Prefix must be 5 characters or fewer."))
        await self.bot.db.set_prefix(ctx.guild.id, new_prefix)
        await ctx.send(embed=embeds.success(f"Prefix updated to `{new_prefix}`"))

    @prefix.command(name="reset", description="Reset the server's prefix back to '!'.")
    @commands.has_permissions(administrator=True)
    async def prefix_reset(self, ctx: commands.Context):
        await self.bot.db.set_prefix(ctx.guild.id, config.DEFAULT_PREFIX)
        await ctx.send(embed=embeds.success(f"Prefix reset to `{config.DEFAULT_PREFIX}`"))

    @commands.hybrid_command(name="botsettings", description="Show the Bot Settings menu.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def botsettings(self, ctx: commands.Context):
        current = await self.bot.db.get_prefix(ctx.guild.id, config.DEFAULT_PREFIX)
        embed = embeds.plain(title=f"⚙️ {config.BOT_NAME} Settings")
        embed.add_field(name="Prefix", value=f"`{current}`")
        embed.add_field(name="Guilds Served", value=str(len(self.bot.guilds)))
        embed.add_field(name="Commands", value=str(sum(1 for _ in self.bot.walk_commands())))
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
