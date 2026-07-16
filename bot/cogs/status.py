"""
/status. Public stat card image built from get_zzz_notes(): battery
charge, engagement, weekly task progress, Hollow Zero bounty commission,
member card status, and temple running level, rendered onto a pre-made
background PNG (see core/status_card.py).
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot.hoyolab import HOYOLAB_SEMAPHORE, build_client
from core.db import collection
from core.status_card import build_status_card
from core.user_config import UserConfig


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="status", description="Show your current ZZZ status card")
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()  # public: visible "thinking..." placeholder

        doc = await collection.find_one({"userId": str(interaction.user.id)})
        if doc is None:
            print(f"/status: no config found for userId={interaction.user.id}")
            await interaction.followup.send("You need to /register first.", ephemeral=True)
            return

        config = UserConfig.model_validate(doc)
        client = build_client(config)

        try:
            async with HOYOLAB_SEMAPHORE:
                notes = await client.get_zzz_notes()
        except Exception as error:
            print(f"/status: get_zzz_notes failed for userId={interaction.user.id}: {error}")
            await interaction.followup.send(f"Couldn't fetch your status from HoYoLAB: {error}", ephemeral=True)
            return

        try:
            card_buf = build_status_card(notes)
        except FileNotFoundError as error:
            print(f"/status: asset missing: {error}")
            await interaction.followup.send(
                "Status card assets aren't set up yet -- ping the bot owner.",
                ephemeral=True,
            )
            return

        file = discord.File(card_buf, filename="status.png")
        await interaction.followup.send(
            f"{interaction.user.mention}'s current status:",
            file=file,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusCog(bot))