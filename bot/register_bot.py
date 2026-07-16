"""
Discord bot entrypoint. Long-running process, separate from main.py.
main.py is a one-shot job run on a schedule to push widget updates; this
bot stays connected to Discord waiting for slash commands, now organized
as cogs under bot/cogs/:

    bot/cogs/registration.py -- /register, /unregister
    bot/cogs/agents.py       -- /set_agents
    bot/cogs/currency.py     -- /currency
    bot/cogs/status.py       -- /status

Uses the SAME bot token / application as the widget push in main.py, since
config.appId (stored per user) has to match the application whose bot
token you use to PATCH the widget later.

Run as a module from the repo root so the `core`/`bot` package imports
resolve:
    python -m bot.register_bot
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from core.config import APP_ID, DISCORD_BOT_TOKEN

COGS = [
    "bot.cogs.registration",
    "bot.cogs.agents",
    "bot.cogs.currency",
    "bot.cogs.status",
]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)  # prefix unused; slash commands only


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Centralized handler for every slash command's errors means no
    cog needs its own try/except just to catch cooldowns."""
    if isinstance(error, app_commands.CommandOnCooldown):
        message = f"Slow down a bit -- try again in {error.retry_after:.0f}s."
    else:
        print(f"Unhandled app command error in {interaction.command}: {error!r}")
        message = "Something went wrong running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (application ID {APP_ID})")


async def main() -> None:
    for cog in COGS:
        await bot.load_extension(cog)
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())