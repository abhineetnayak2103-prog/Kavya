from __future__ import annotations
import asyncio
import time
import discord
from discord.ext import commands

from utils import embeds

CATEGORY = "Tickets"


class TicketPanelView(discord.ui.View):
    """Persistent view — must be re-added on bot startup via bot.add_view()."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.blurple, emoji="🎫", custom_id="kavya:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("Tickets")
        await cog.create_ticket(interaction)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, emoji="🙋", custom_id="kavya:claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("Tickets")
        await cog.claim_ticket(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, emoji="🔒", custom_id="kavya:close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("Tickets")
        await cog.close_ticket(interaction)


class Tickets(commands.Cog, name="Tickets"):
    """Support ticket system."""
    category = CATEGORY

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketPanelView())
        bot.add_view(TicketControlView())

    async def _settings(self, guild_id: int):
        row = await self.bot.db.fetchone("SELECT * FROM tickets_settings WHERE guild_id = ?", (guild_id,))
        if not row:
            await self.bot.db.execute("INSERT INTO tickets_settings (guild_id) VALUES (?)", (guild_id,))
            row = await self.bot.db.fetchone("SELECT * FROM tickets_settings WHERE guild_id = ?", (guild_id,))
        return row

    async def create_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        settings = await self._settings(guild.id)
        existing = await self.bot.db.fetchone(
            "SELECT * FROM active_tickets WHERE guild_id = ? AND user_id = ?", (guild.id, interaction.user.id)
        )
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                return await interaction.response.send_message(
                    embed=embeds.warning(f"You already have an open ticket: {channel.mention}"), ephemeral=True
                )
        category = guild.get_channel(settings["category_id"]) if settings["category_id"] else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        support_role = guild.get_role(settings["support_role_id"]) if settings["support_role_id"] else None
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        counter = settings["ticket_counter"] + 1
        channel = await guild.create_text_channel(
            name=f"ticket-{counter:04d}", category=category, overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user}"
        )
        await self.bot.db.execute("UPDATE tickets_settings SET ticket_counter = ? WHERE guild_id = ?", (counter, guild.id))
        await self.bot.db.execute(
            "INSERT INTO active_tickets (channel_id, guild_id, user_id, opened_at) VALUES (?, ?, ?, ?)",
            (channel.id, guild.id, interaction.user.id, int(time.time())),
        )
        embed = embeds.info(
            f"{interaction.user.mention} thanks for reaching out! Support will be with you shortly.\n"
            f"Use the buttons below to claim or close this ticket.",
            title=f"🎫 Ticket #{counter:04d}",
        )
        await channel.send(content=support_role.mention if support_role else None, embed=embed, view=TicketControlView())
        await interaction.response.send_message(embed=embeds.success(f"Ticket created: {channel.mention}"), ephemeral=True)

        if settings["log_channel_id"]:
            log_ch = guild.get_channel(settings["log_channel_id"])
            if log_ch:
                await log_ch.send(embed=embeds.info(f"{interaction.user.mention} opened {channel.mention}", title="Ticket Opened"))

    async def claim_ticket(self, interaction: discord.Interaction):
        row = await self.bot.db.fetchone("SELECT * FROM active_tickets WHERE channel_id = ?", (interaction.channel.id,))
        if not row:
            return await interaction.response.send_message(embed=embeds.error("This isn't an active ticket channel."), ephemeral=True)
        await self.bot.db.execute("UPDATE active_tickets SET claimed_by = ? WHERE channel_id = ?", (interaction.user.id, interaction.channel.id))
        await interaction.response.send_message(embed=embeds.success(f"🙋 {interaction.user.mention} claimed this ticket."))

    async def close_ticket(self, interaction: discord.Interaction):
        row = await self.bot.db.fetchone("SELECT * FROM active_tickets WHERE channel_id = ?", (interaction.channel.id,))
        if not row:
            return await interaction.response.send_message(embed=embeds.error("This isn't an active ticket channel."), ephemeral=True)
        settings = await self._settings(interaction.guild.id)
        await interaction.response.send_message(embed=embeds.warning("🔒 Closing ticket in 5 seconds…"))
        await self.bot.db.execute("DELETE FROM active_tickets WHERE channel_id = ?", (interaction.channel.id,))
        if settings["log_channel_id"]:
            log_ch = interaction.guild.get_channel(settings["log_channel_id"])
            if log_ch:
                await log_ch.send(embed=embeds.warning(
                    f"Ticket {interaction.channel.name} closed by {interaction.user.mention}", title="Ticket Closed"))
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            pass

    # ---------- setup commands ----------
    @commands.hybrid_group(name="tickets", description="Configure the ticket system.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def tickets(self, ctx: commands.Context):
        s = await self._settings(ctx.guild.id)
        embed = embeds.plain(title="🎫 Ticket System")
        cat = ctx.guild.get_channel(s["category_id"]) if s["category_id"] else None
        log = ctx.guild.get_channel(s["log_channel_id"]) if s["log_channel_id"] else None
        role = ctx.guild.get_role(s["support_role_id"]) if s["support_role_id"] else None
        embed.add_field(name="Category", value=cat.mention if cat else "Not set")
        embed.add_field(name="Log Channel", value=log.mention if log else "Not set")
        embed.add_field(name="Support Role", value=role.mention if role else "Not set")
        embed.add_field(
            name="Setup",
            value="`tickets category #cat` • `tickets logs #ch` • `tickets role @role` • `tickets panel #ch`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @tickets.command(name="category", description="Set the category tickets are created under.")
    @commands.has_permissions(administrator=True)
    async def tickets_category(self, ctx: commands.Context, category: discord.CategoryChannel):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE tickets_settings SET category_id = ? WHERE guild_id = ?", (category.id, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Tickets will be created under **{category.name}**."))

    @tickets.command(name="logs", description="Set the ticket log channel.")
    @commands.has_permissions(administrator=True)
    async def tickets_logs(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE tickets_settings SET log_channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Ticket logs will go to {channel.mention}."))

    @tickets.command(name="role", description="Set the support role that can see tickets.")
    @commands.has_permissions(administrator=True)
    async def tickets_role(self, ctx: commands.Context, role: discord.Role):
        await self._settings(ctx.guild.id)
        await self.bot.db.execute("UPDATE tickets_settings SET support_role_id = ? WHERE guild_id = ?", (role.id, ctx.guild.id))
        await ctx.send(embed=embeds.success(f"Support role set to {role.mention}."))

    @tickets.command(name="panel", description="Send the ticket-opening panel to a channel.")
    @commands.has_permissions(administrator=True)
    async def tickets_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        embed = embeds.plain(
            title="🎫 Need Help?",
            description="Click the button below to open a private support ticket.",
        )
        msg = await channel.send(embed=embed, view=TicketPanelView())
        await self._settings(ctx.guild.id)
        await self.bot.db.execute(
            "UPDATE tickets_settings SET panel_channel_id = ?, panel_message_id = ? WHERE guild_id = ?",
            (channel.id, msg.id, ctx.guild.id),
        )
        if channel != ctx.channel:
            await ctx.send(embed=embeds.success(f"Ticket panel posted in {channel.mention}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
