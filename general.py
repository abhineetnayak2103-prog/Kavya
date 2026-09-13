from __future__ import annotations
import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds

CATEGORY = "General"


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label=name,
                description=meta["description"][:100],
                emoji=meta["emoji"],
            )
            for name, meta in config.CATEGORIES.items()
        ]
        super().__init__(placeholder="Browse a category…", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = build_category_embed(self.bot, category)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(HelpSelect(bot))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=embeds.error("This help menu isn't yours. Run the command yourself!"),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


def build_home_embed(bot: commands.Bot) -> discord.Embed:
    prefix = config.DEFAULT_PREFIX
    total = sum(1 for c in bot.walk_commands())
    embed = embeds.plain(
        title=f"{config.BOT_NAME} — Help Menu",
        description=(
            f"Hey, I'm **{config.BOT_NAME}**.\n"
            f"• My prefix here is `{prefix}` (slash commands also work everywhere)\n"
            f"• Use the dropdown below to browse a category\n"
            f"• **{total}** commands total"
        ),
    )
    lines = [f"{meta['emoji']} **{name}** — {meta['description']}" for name, meta in config.CATEGORIES.items()]
    # split into two columns for readability
    half = (len(lines) + 1) // 2
    embed.add_field(name="Categories", value="\n".join(lines[:half]), inline=True)
    embed.add_field(name="\u200b", value="\n".join(lines[half:]), inline=True)
    return embed


def build_category_embed(bot: commands.Bot, category: str) -> discord.Embed:
    meta = config.CATEGORIES.get(category, {"emoji": "❓", "description": ""})
    embed = embeds.plain(
        title=f"{meta['emoji']} {category} Commands",
        description=meta["description"],
    )
    found = []
    for cmd in bot.walk_commands():
        if getattr(cmd.cog, "category", None) == category and not cmd.hidden:
            usage = f"`{config.DEFAULT_PREFIX}{cmd.qualified_name}`"
            desc = cmd.short_doc or "No description provided."
            found.append(f"{usage} — {desc}")

    # Owner tools live purely as slash commands (app_commands.Group), not
    # prefix commands, so pull them from the command tree separately.
    if category == "Owner":
        owner_group = bot.tree.get_command("owner")
        if owner_group is not None:
            for sub in owner_group.commands:
                found.append(f"`/owner {sub.name}` — {sub.description}")

    if not found:
        embed.add_field(name="Commands", value="No commands registered here yet.", inline=False)
    else:
        # Discord field values cap at 1024 chars — chunk if needed
        chunk, chunks, length = [], [], 0
        for line in found:
            if length + len(line) + 1 > 1000:
                chunks.append(chunk)
                chunk, length = [], 0
            chunk.append(line)
            length += len(line) + 1
        if chunk:
            chunks.append(chunk)
        for i, c in enumerate(chunks):
            name = "Commands" if i == 0 else "\u200b"
            embed.add_field(name=name, value="\n".join(c), inline=False)
    return embed


class General(commands.Cog):
    """Everyday utility & fun tools."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.snipes: dict[int, dict] = {}
        self.esnipes: dict[int, dict] = {}

    # ---------- help ----------
    @commands.hybrid_command(name="help", description="Show Kavya's interactive help menu.")
    @app_commands.describe(context="Optional category or command name to jump straight to.")
    async def help_cmd(self, ctx: commands.Context, *, context: str | None = None):
        if context:
            if context.title() in config.CATEGORIES:
                embed = build_category_embed(self.bot, context.title())
                return await ctx.send(embed=embed, view=HelpView(self.bot, ctx.author.id))
            cmd = self.bot.get_command(context.lower())
            if cmd:
                embed = embeds.plain(
                    title=f"{config.DEFAULT_PREFIX}{cmd.qualified_name}",
                    description=cmd.help or cmd.short_doc or "No description provided.",
                )
                embed.add_field(name="Category", value=getattr(cmd.cog, "category", "Uncategorized"))
                return await ctx.send(embed=embed)
            return await ctx.send(embed=embeds.error(f"No category or command called `{context}` found."))
        embed = build_home_embed(self.bot)
        await ctx.send(embed=embed, view=HelpView(self.bot, ctx.author.id))

    # ---------- ping ----------
    @commands.hybrid_command(name="ping", description="Show the latency of the bot in ms.")
    async def ping(self, ctx: commands.Context):
        start = time.perf_counter()
        msg = await ctx.send(embed=embeds.info("Pinging…"))
        elapsed = (time.perf_counter() - start) * 1000
        embed = embeds.info(
            f"🏓 **Websocket:** {self.bot.latency * 1000:.0f}ms\n**Message round-trip:** {elapsed:.0f}ms",
            title="Pong!",
        )
        await msg.edit(embed=embed)

    # ---------- avatar / banner ----------
    @commands.hybrid_command(name="av", description="Show a user's avatar in full size.")
    @app_commands.describe(user="The user to look up (defaults to you).")
    async def avatar(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        embed = embeds.plain(title=f"{user.display_name}'s Avatar")
        embed.set_image(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ab", description="Show a user's banner in full size.")
    @app_commands.describe(user="The user to look up (defaults to you).")
    async def banner(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        fetched = await self.bot.fetch_user(user.id)
        if not fetched.banner:
            return await ctx.send(embed=embeds.warning(f"{user.mention} doesn't have a banner set."))
        embed = embeds.plain(title=f"{user.display_name}'s Banner")
        embed.set_image(url=fetched.banner.url)
        await ctx.send(embed=embed)

    # ---------- poll ----------
    @commands.hybrid_command(name="poll", description="Create a simple yes/no poll.")
    @app_commands.describe(question="The question to poll.")
    async def poll(self, ctx: commands.Context, *, question: str):
        embed = embeds.plain(title="📊 Poll", description=question)
        embed.set_footer(text=f"Poll started by {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

    # ---------- invite ----------
    @commands.hybrid_command(name="botinvite", description="Get the invite link for the bot.")
    async def botinvite(self, ctx: commands.Context):
        perms = discord.Permissions(administrator=True)
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        embed = embeds.plain(title=f"Invite {config.BOT_NAME}", description=f"[Click here to invite me]({url})")
        await ctx.send(embed=embed)

    # ---------- serverinfo ----------
    @commands.hybrid_command(name="serverinfo", description="Show detailed information about this server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        embed = embeds.plain(title=g.name)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=str(g.owner) if g.owner else "Unknown")
        embed.add_field(name="Members", value=str(g.member_count))
        embed.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"))
        embed.add_field(name="Text Channels", value=str(len(g.text_channels)))
        embed.add_field(name="Voice Channels", value=str(len(g.voice_channels)))
        embed.add_field(name="Roles", value=str(len(g.roles)))
        embed.add_field(name="Boost Level", value=str(g.premium_tier))
        embed.add_field(name="Boosts", value=str(g.premium_subscription_count))
        embed.add_field(name="Server ID", value=str(g.id))
        await ctx.send(embed=embed)

    # ---------- afk ----------
    @commands.hybrid_command(name="afk", description="Set your status to AFK (away from keyboard).")
    @app_commands.describe(reason="Why you're AFK.")
    @commands.guild_only()
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK"):
        await self.bot.db.execute(
            "INSERT INTO afk_status (guild_id, user_id, reason, since) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET reason = excluded.reason, since = excluded.since",
            (ctx.guild.id, ctx.author.id, reason, int(time.time())),
        )
        await ctx.send(embed=embeds.success(f"You're now AFK: {reason}"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # clear AFK if the (previously) AFK user speaks again
        row = await self.bot.db.fetchone(
            "SELECT * FROM afk_status WHERE guild_id = ? AND user_id = ?",
            (message.guild.id, message.author.id),
        )
        if row:
            await self.bot.db.execute(
                "DELETE FROM afk_status WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, message.author.id),
            )
            try:
                await message.reply(embed=embeds.info("Welcome back — I removed your AFK status."),
                                     mention_author=False)
            except discord.HTTPException:
                pass

        # notify if a mentioned user is AFK
        for user in message.mentions:
            row = await self.bot.db.fetchone(
                "SELECT * FROM afk_status WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, user.id),
            )
            if row:
                await message.channel.send(
                    embed=embeds.info(f"{user.display_name} is AFK: {row['reason']}"),
                )

        # track for snipe
        self.snipes.setdefault(message.channel.id, None)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        self.snipes[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "time": discord.utils.utcnow(),
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
        self.esnipes[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": before.author,
            "time": discord.utils.utcnow(),
        }

    @commands.hybrid_command(name="snipe", description="Snipe the last deleted message in the channel.")
    async def snipe(self, ctx: commands.Context):
        data = self.snipes.get(ctx.channel.id)
        if not data:
            return await ctx.send(embed=embeds.warning("There's nothing to snipe here."))
        embed = embeds.plain(description=data["content"] or "*[no text content]*")
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        embed.timestamp = data["time"]
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="esnipe", description="Snipe the last edited message in the channel.")
    async def esnipe(self, ctx: commands.Context):
        data = self.esnipes.get(ctx.channel.id)
        if not data:
            return await ctx.send(embed=embeds.warning("There's nothing to snipe here."))
        embed = embeds.plain(title="Edited Message")
        embed.add_field(name="Before", value=data["before"] or "*[empty]*", inline=False)
        embed.add_field(name="After", value=data["after"] or "*[empty]*", inline=False)
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        embed.timestamp = data["time"]
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
