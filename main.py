"""
Kavya — main entrypoint.

Run with:  python main.py
Requires a .env file next to this script containing:
    KAVYA_TOKEN=your-bot-token-here
"""
from __future__ import annotations
import asyncio
import logging
import discord
from discord.ext import commands

import config
from database.py import Database
from utils import embeds

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("kavya")

INITIAL_COGS = [
    "cogs.general",
    "cogs.moderation",
    "cogs.antinuke",
    "cogs.antiraid",
    "cogs.automod",
    "cogs.tickets",
    "cogs.welcome",
    "cogs.logging_cog",
    "cogs.embed_builder",
    "cogs.social",
    "cogs.utility",
    "cogs.roles",
    "cogs.join2create",
    "cogs.tracking",
    "cogs.voice",
    "cogs.owner",
]


async def get_prefix(bot: "Kavya", message: discord.Message):
    if message.guild is None:
        return commands.when_mentioned_or(config.DEFAULT_PREFIX)(bot, message)
    prefix = await bot.db.get_prefix(message.guild.id, config.DEFAULT_PREFIX)
    return commands.when_mentioned_or(prefix)(bot, message)


class Kavya(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,  # custom help lives in cogs/general.py
            case_insensitive=True,
        )
        self.db = Database(config.DB_PATH)

    async def setup_hook(self):
        await self.db.connect()
        for ext in INITIAL_COGS:
            try:
                await self.load_extension(ext)
                log.info(f"Loaded {ext}")
            except Exception as e:
                log.exception(f"Failed to load {ext}: {e}")
        # Sync slash commands globally. For instant per-guild sync during
        # development, copy_global_to + sync(guild=...) on a test guild instead.
        try:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} application commands.")
        except Exception as e:
            log.exception(f"Slash command sync failed: {e}")

    async def on_ready(self):
        log.info(f"{self.user} is online — serving {len(self.guilds)} guild(s).")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{config.DEFAULT_PREFIX}help | /help",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=embeds.error("You don't have permission to use this command."))
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=embeds.error("You don't have permission to use this command."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error(f"Missing argument: `{error.param.name}`.\n"
                                               f"Use `{ctx.prefix}help {ctx.command}` for usage."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=embeds.error(str(error)))
            return
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.send(embed=embeds.error(f"I'm missing permissions: `{missing}`."))
            return
        log.exception(f"Unhandled error in command {ctx.command}: {error}")
        await ctx.send(embed=embeds.error("Something went wrong running that command."))

    async def close(self):
        await self.db.close()
        await super().close()


async def main():
    if not config.TOKEN:
        raise SystemExit(
            "No token found. Create a .env file with:\n  KAVYA_TOKEN=your-bot-token-here"
        )
    bot = Kavya()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
