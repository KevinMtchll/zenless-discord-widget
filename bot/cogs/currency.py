"""
/currency. Public chart of Polychrome income by source, across every
month HoYoLAB's diary endpoint has data for. Income only; HoYoLAB doesn't
expose spending/pull history through this endpoint (see docs/currency-tracking.md).
"""

import io
from datetime import datetime
from enum import Enum as PyEnum

import discord
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from discord import app_commands
from discord.ext import commands

from bot.hoyolab import HOYOLAB_SEMAPHORE, build_client
from core.db import collection
from core.user_config import UserConfig

# Source keys come from get_zzz_diary()'s polychrome_incomes; label/color
# chosen for a readable stacked bar chart on Discord's dark theme.
POLYCHROME_SOURCES = {
    "event_rewards": ("Events", "#f7b731"),
    "daily_activity_rewards": ("Dailies", "#3867d6"),
    "hollow_rewards": ("Hollow Zero", "#8854d0"),
    "growth_rewards": ("Growth", "#20bf6b"),
    "shiyu_rewards": ("Shiyu Defense", "#eb3b5a"),
    "mail_rewards": ("Mail", "#0fb9b1"),
    "other_rewards": ("Other", "#a5b1c2"),
}
CHART_BG = "#2b2d31"  # Discord dark theme background color.


def _field_str(value) -> str:
    """genshin.py returns some fields (source/type on diary entries) as
    Enum members rather than plain strings, comparing those directly to
    a string literal silently never matches. Normalize to the underlying
    string either way."""
    return value.value if isinstance(value, PyEnum) else str(value)


def _month_label(month_str: str) -> str:
    """'202607' -> 'Jul 2026'."""
    year, month = int(str(month_str)[:4]), int(str(month_str)[4:])
    return datetime(year, month, 1).strftime("%b %Y")


def _build_income_chart(diaries: dict, months_sorted: list[str]) -> io.BytesIO:
    """Stacked bar chart: one bar per month, segments = income source.
    `diaries` maps month string -> the get_zzz_diary() result for that month."""
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    fig.patch.set_facecolor(CHART_BG)
    ax.set_facecolor(CHART_BG)

    x = range(len(months_sorted))
    bottoms = [0] * len(months_sorted)

    for source, (label, color) in POLYCHROME_SOURCES.items():
        values = []
        for month in months_sorted:
            incomes = diaries[month].income.polychrome_incomes
            entry = next((i for i in incomes if _field_str(i.source) == source), None)
            values.append(entry.num if entry else 0)
        ax.bar(x, values, bottom=bottoms, label=label, color=color)
        bottoms = [b + v for b, v in zip(bottoms, values)]

    ax.set_xticks(list(x))
    ax.set_xticklabels([_month_label(m) for m in months_sorted], color="white")
    ax.set_ylabel("Polychrome", color="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#4a4d55")
    ax.legend(facecolor=CHART_BG, labelcolor="white", fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1))
    ax.set_title("Polychrome Income by Source", color="white")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


class CurrencyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="currency", description="Show your Polychrome income history as a chart")
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    async def currency(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()  # public: the "thinking..." placeholder is visible to the channel

        doc = await collection.find_one({"userId": str(interaction.user.id)})
        if doc is None:
            print(f"/currency: no config found for userId={interaction.user.id}")
            await interaction.followup.send("You need to /register first.", ephemeral=True)
            return

        config = UserConfig.model_validate(doc)
        client = build_client(config)

        try:
            async with HOYOLAB_SEMAPHORE:
                current_diary = await client.get_zzz_diary()
        except Exception as error:
            print(f"/currency: get_zzz_diary failed for userId={interaction.user.id}: {error}")
            await interaction.followup.send(f"Couldn't fetch your currency data from HoYoLAB: {error}", ephemeral=True)
            return

        diaries = {current_diary.data_month: current_diary}
        for month in current_diary.month_options:
            if str(month) == str(current_diary.data_month):
                continue
            try:
                async with HOYOLAB_SEMAPHORE:
                    diaries[month] = await client.get_zzz_diary(month=int(month))
            except Exception as error:
                # Skip a bad month rather than failing the whole command.
                # partial history is still useful.
                print(f"/currency: get_zzz_diary(month={month}) failed for userId={interaction.user.id}: {error}")

        months_sorted = sorted(diaries.keys(), key=str)  # YYYYMM strings sort chronologically

        chart_buf = _build_income_chart(diaries, months_sorted)
        file = discord.File(chart_buf, filename="polychrome_income.png")

        total_this_month = next(
            (c.num for c in current_diary.income.currencies if _field_str(c.type) == "PolychromesData"),
            0,
        )
        await interaction.followup.send(
            f"{interaction.user.mention}'s Polychrome income across the last **{len(months_sorted)}** month(s) "
            f"HoYoLAB has data for. So far this month: **{total_this_month:,}**.\n",
            file=file,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CurrencyCog(bot))