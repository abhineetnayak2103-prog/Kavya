"""
utils/checks.py — reusable permission gates.

Both prefix and slash (hybrid) commands can use these because they operate
on `commands.Context`-compatible / `discord.Interaction`-compatible checks
via `commands.check` for prefix/hybrid commands.
"""
from __future__ import annotations
import discord
from discord.ext import commands


def is_admin():
    """Server Administrator permission OR the guild owner."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)


def is_mod():
    """Users with kick/ban/manage_messages, or admins."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        perms = ctx.author.guild_permissions
        return (
            perms.administrator
            or perms.kick_members
            or perms.ban_members
            or perms.manage_messages
        )
    return commands.check(predicate)


def bot_has_permissions(**required):
    return commands.bot_has_permissions(**required)


async def higher_top_role(actor: discord.Member, target: discord.Member) -> bool:
    """True if actor can act on target based on role hierarchy."""
    if actor.id == actor.guild.owner_id:
        return True
    return actor.top_role > target.top_role
