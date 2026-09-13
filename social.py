from __future__ import annotations
import random
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Social"

ACTIONS = {
    "hug": ("hugs", "🤗"),
    "slap": ("slaps", "✋"),
    "pat": ("pats", "🖐️"),
    "wave": ("waves at", "👋"),
    "highfive": ("high-fives", "🙌"),
}


class Social(commands.Cog):
    """Social & fun member commands."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _do_action(self, ctx: commands.Context, action: str, member: discord.Member):
        verb, emoji = ACTIONS[action]
        target = member or ctx.author
        await ctx.send(embed=embeds.plain(description=f"{emoji} {ctx.author.mention} {verb} {target.mention}!"))

    @commands.hybrid_command(name="hug", description="Hug a member.")
    async def hug(self, ctx: commands.Context, member: discord.Member):
        await self._do_action(ctx, "hug", member)

    @commands.hybrid_command(name="slap", description="Slap a member.")
    async def slap(self, ctx: commands.Context, member: discord.Member):
        await self._do_action(ctx, "slap", member)

    @commands.hybrid_command(name="pat", description="Pat a member.")
    async def pat(self, ctx: commands.Context, member: discord.Member):
        await self._do_action(ctx, "pat", member)

    @commands.hybrid_command(name="wave", description="Wave at a member.")
    async def wave(self, ctx: commands.Context, member: discord.Member):
        await self._do_action(ctx, "wave", member)

    @commands.hybrid_command(name="highfive", description="High-five a member.")
    async def highfive(self, ctx: commands.Context, member: discord.Member):
        await self._do_action(ctx, "highfive", member)

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a question.")
    async def eightball(self, ctx: commands.Context, *, question: str):
        answers = [
            "Yes, definitely.", "It is certain.", "Without a doubt.", "Ask again later.",
            "Cannot predict now.", "Don't count on it.", "My reply is no.", "Very doubtful.",
        ]
        embed = embeds.plain(title="🎱 Magic 8-Ball", description=f"**Q:** {question}\n**A:** {random.choice(answers)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, ctx: commands.Context):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(embed=embeds.plain(description=f"🪙 It landed on **{result}**!"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Social(bot))
