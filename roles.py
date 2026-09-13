from __future__ import annotations
import asyncio
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Roles"


class Roles(commands.Cog):
    """Manage server roles: colors, icons, renaming, bulk add/remove."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="role", description="Advanced role utility and bulk modification system.", invoke_without_command=True)
    @commands.guild_only()
    async def role(self, ctx: commands.Context):
        embed = embeds.info(
            "Subcommands: `add` `remove` `create` `delete` `colour` `rename` "
            "`all` `bots` `humans` `info` `list`",
            title="🎭 Role Tools",
        )
        await ctx.send(embed=embed)

    @role.command(name="add", description="Adds a role to a user.")
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=embeds.error("I can't assign a role higher than or equal to my own."))
        await member.add_roles(role, reason=f"Added by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Added {role.mention} to {member.mention}."))

    @role.command(name="remove", description="Removes a role from a user.")
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.remove_roles(role, reason=f"Removed by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Removed {role.mention} from {member.mention}."))

    @role.command(name="create", description="Creates a new role.")
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx: commands.Context, *, name: str):
        new_role = await ctx.guild.create_role(name=name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Created role {new_role.mention}."))

    @role.command(name="delete", description="Deletes a role.")
    @commands.has_permissions(manage_roles=True)
    async def role_delete(self, ctx: commands.Context, *, role: discord.Role):
        name = role.name
        await role.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Deleted role **{name}**."))

    @role.command(name="colour", aliases=["color"], description="Changes the color of a role.")
    @commands.has_permissions(manage_roles=True)
    async def role_colour(self, ctx: commands.Context, role: discord.Role, hex_colour: str):
        try:
            colour = discord.Colour(int(hex_colour.lstrip("#"), 16))
        except ValueError:
            return await ctx.send(embed=embeds.error("Provide a valid hex colour, e.g. `#5865F2`."))
        await role.edit(colour=colour, reason=f"Colour changed by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Updated {role.mention}'s colour."))

    @role.command(name="rename", description="Renames a role.")
    @commands.has_permissions(manage_roles=True)
    async def role_rename(self, ctx: commands.Context, role: discord.Role, *, new_name: str):
        old = role.name
        await role.edit(name=new_name, reason=f"Renamed by {ctx.author}")
        await ctx.send(embed=embeds.success(f"Renamed **{old}** → **{new_name}**."))

    async def _bulk(self, ctx: commands.Context, role: discord.Role, targets: list[discord.Member]):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=embeds.error("I can't assign a role higher than or equal to my own."))
        msg = await ctx.send(embed=embeds.info(f"Applying {role.mention} to {len(targets)} member(s)…"))
        applied = 0
        for member in targets:
            try:
                await member.add_roles(role, reason=f"Bulk role add by {ctx.author}")
                applied += 1
                await asyncio.sleep(0.25)  # gentle on rate limits
            except discord.Forbidden:
                continue
        await msg.edit(embed=embeds.success(f"Applied {role.mention} to **{applied}/{len(targets)}** member(s)."))

    @role.command(name="all", description="Give the role to all members.")
    @commands.has_permissions(administrator=True)
    async def role_all(self, ctx: commands.Context, *, role: discord.Role):
        await self._bulk(ctx, role, ctx.guild.members)

    @role.command(name="bots", description="Give the role to all bot members.")
    @commands.has_permissions(administrator=True)
    async def role_bots(self, ctx: commands.Context, *, role: discord.Role):
        await self._bulk(ctx, role, [m for m in ctx.guild.members if m.bot])

    @role.command(name="humans", description="Give the role to all human members.")
    @commands.has_permissions(administrator=True)
    async def role_humans(self, ctx: commands.Context, *, role: discord.Role):
        await self._bulk(ctx, role, [m for m in ctx.guild.members if not m.bot])

    @role.command(name="info", description="Shows detailed information about a role.")
    async def role_info(self, ctx: commands.Context, *, role: discord.Role):
        embed = embeds.plain(title=f"🎭 {role.name}")
        embed.add_field(name="ID", value=str(role.id))
        embed.add_field(name="Colour", value=str(role.colour))
        embed.add_field(name="Members", value=str(len(role.members)))
        embed.add_field(name="Mentionable", value=str(role.mentionable))
        embed.add_field(name="Hoisted", value=str(role.hoist))
        embed.add_field(name="Position", value=str(role.position))
        await ctx.send(embed=embed)

    @role.command(name="list", description="Lists all roles in the server with member counts.")
    async def role_list(self, ctx: commands.Context):
        lines = [f"{r.mention} — {len(r.members)}" for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
        embed = embeds.plain(title=f"Roles ({len(lines)})", description="\n".join(lines[:25]) or "None")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
