"""
/register and /unregister. RegisterModal collects a user's
Hoyoverse/ZZZ cookies and saves an encrypted UserConfig into MongoDB.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.config import APP_ID, OAUTH_REDIRECT_URI
from core.db import collection
from core.user_config import HoyoCookies, UserConfig


class RegisterModal(discord.ui.Modal, title="Link your Hoyoverse account"):
    hoyo_uid = discord.ui.TextInput(
        label="ZZZ UID",
        required=True,
        max_length=12,
    )
    ltoken_v2 = discord.ui.TextInput(
        label="ltoken_v2 cookie",
        required=True,
    )
    ltuid_v2 = discord.ui.TextInput(
        label="ltuid_v2 cookie",
        required=True,
        max_length=12,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            hoyo_uid_int = int(self.hoyo_uid.value.strip())
            ltuid_v2_int = int(self.ltuid_v2.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "UID and ltuid_v2 need to be plain numbers -- double check what you pasted.",
                ephemeral=True,
            )
            return

        cookies = HoyoCookies(
            ltoken_v2=self.ltoken_v2.value.strip(),
            ltuid_v2=ltuid_v2_int,
        )

        config = UserConfig(
            userId=str(interaction.user.id),
            appId=str(APP_ID),
            hoyoCookies=cookies.to_encrypted(),
            hoyoUid=hoyo_uid_int,
        )

        doc = config.model_dump()
        await collection.update_one(
            {"userId": config.userId},
            {"$set": doc},
            upsert=True,
        )
        print(f"/register: saved config for userId={config.userId}, hoyoUid={config.hoyoUid}")

        oauth_url = (
            "https://discord.com/oauth2/authorize"
            f"?client_id={APP_ID}"
            "&response_type=token"
            f"&redirect_uri={OAUTH_REDIRECT_URI}"
            "&scope=openid%20sdk.social_layer"
        )

        await interaction.response.send_message(
            "Saved your Hoyoverse account. One more step: authorize the widget "
            f"to appear on your profile by opening this link and accepting: {oauth_url}\n"
            "Without this step the widget push will save data but nothing will show "
            "on your profile.",
            ephemeral=True,
        )


class RegistrationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="register", description="Link your Hoyoverse/ZZZ account for widget updates")
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: i.user.id)
    async def register(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RegisterModal())

    @app_commands.command(name="unregister", description="Remove your linked account and stop widget updates")
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: i.user.id)
    async def unregister(self, interaction: discord.Interaction) -> None:
        result = await collection.delete_one({"userId": str(interaction.user.id)})
        if result.deleted_count:
            await interaction.response.send_message(
                "Unregistered. Your account will no longer be picked up by widget updates.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("You weren't registered.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegistrationCog(bot))