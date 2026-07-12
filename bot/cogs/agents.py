"""
/set_agents lets a registered user pick which agents fill the widget's
4 slots, via a per-slot dropdown + Save button. Pushes an immediate widget
refresh on save so the profile doesn't wait for the next scheduled run.
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot.hoyolab import HOYOLAB_SEMAPHORE, build_client
from core.config import APP_ID
from core.db import collection
from core.user_config import UserConfig
from core.widget import IMAGE_FIELDS, build_widget_fields, push_widget_fields

# Discord select menus cap out at 25 options per component.
MAX_SELECT_OPTIONS = 25
WIDGET_SLOT_COUNT = 4


def _sort_agents_for_picker(agents: list) -> list:
    """S-rarity first, then A, then everything else; alphabetical within
    each tier so the dropdown is easy to scan."""
    rarity_order = {"S": 0, "A": 1}
    return sorted(agents, key=lambda a: (rarity_order.get(a.rarity, 2), a.name))


class AgentSelect(discord.ui.Select):
    """One dropdown per widget slot (agent_1 .. agent_4)."""

    def __init__(self, agents: list, slot: int, current_id: int | None) -> None:
        self.slot = slot
        options = [
            discord.SelectOption(
                label=f"{agent.name} ({agent.rarity})",
                value=str(agent.id),
                default=(agent.id == current_id),
            )
            for agent in agents
        ]
        super().__init__(
            placeholder=f"Agent {slot}" + (" (currently empty / auto-fill)" if current_id is None else ""),
            min_values=0,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AgentPickerView = self.view
        view.selections[self.slot - 1] = int(self.values[0]) if self.values else None
        await interaction.response.defer()  # menu stays open; Save commits the choice


class SaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Save", style=discord.ButtonStyle.success, row=WIDGET_SLOT_COUNT)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AgentPickerView = self.view
        await collection.update_one(
            {"userId": view.user_id},
            {"$set": {"selectedAgentIds": view.selections}},
        )

        agent_names = {agent.id: agent.name for agent in view.full_agents}
        lines = []
        for i, agent_id in enumerate(view.selections, start=1):
            label = agent_names.get(agent_id, "auto-fill") if agent_id is not None else "auto-fill"
            lines.append(f"Slot {i}: {label}")

        try:
            widget_fields = await build_widget_fields(
                view.client, view.hoyo_uid, view.record, view.full_agents, view.selections
            )
            await push_widget_fields(
                app_id=APP_ID,
                user_id=view.user_id,
                fields=widget_fields,
                image_fields=IMAGE_FIELDS,
            )
            push_status = "Widget updated."
            print(f"/set_agents: widget push succeeded for userId={view.user_id}")
        except Exception as error:
            # Selections are already saved in Mongo either way. This just
            # means the profile widget itself didn't refresh immediately
            # (e.g. the user hasn't completed the OAuth linking step yet).
            # The next scheduled main.py run will pick up the saved
            # selections and try the push again.
            print(f"/set_agents: widget push failed for userId={view.user_id}: {error}")
            push_status = f"Saved, but couldn't refresh the widget right now ({error}). It'll catch up on the next scheduled update."

        await interaction.response.edit_message(
            content=f"{push_status}\n\nWidget slot assignments:\n" + "\n".join(lines),
            view=None,
        )


class AgentPickerView(discord.ui.View):
    def __init__(
        self,
        agents: list,
        user_id: str,
        current_selections: list[int | None],
        client,
        hoyo_uid: int,
        record,
        full_agents: list,
    ) -> None:
        super().__init__(timeout=300)
        self.agents = agents
        self.full_agents = full_agents
        self.user_id = user_id
        self.selections: list[int | None] = list(current_selections)
        # Reused by SaveButton to push an immediate widget update without re-fetching from HoYoLAB.
        self.client = client
        self.hoyo_uid = hoyo_uid
        self.record = record

        for slot in range(1, WIDGET_SLOT_COUNT + 1):
            current_id = self.selections[slot - 1] if slot - 1 < len(self.selections) else None
            select = AgentSelect(agents, slot, current_id)
            select.row = slot - 1
            self.add_item(select)

        self.add_item(SaveButton())


class AgentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="set_agents", description="Choose which agents appear in widget slots 1-4")
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    async def set_agents(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        doc = await collection.find_one({"userId": str(interaction.user.id)})
        if doc is None:
            print(f"/set_agents: no config found for userId={interaction.user.id}")
            await interaction.followup.send("You need to /register first.", ephemeral=True)
            return

        config = UserConfig.model_validate(doc)
        client = build_client(config)

        try:
            async with HOYOLAB_SEMAPHORE:
                record = await client.get_zzz_user(config.hoyoUid)
                record2 = await client.get_zzz_agents(config.hoyoUid)
        except Exception as error:
            print(f"/set_agents: get_zzz_user failed for userId={interaction.user.id}, hoyoUid={config.hoyoUid}: {error}")
            await interaction.followup.send(f"Couldn't fetch your agents from HoYoLAB: {error}", ephemeral=True)
            return

        full_agents = _sort_agents_for_picker(record2)
        if not full_agents:
            await interaction.followup.send("No agents found on your account.", ephemeral=True)
            return

        picker_agents = full_agents
        note = ""
        if len(picker_agents) > MAX_SELECT_OPTIONS:
            note = (
                f"\n(You have {len(picker_agents)} agents; only the top {MAX_SELECT_OPTIONS} "
                "S/A-rarity ones are listed below due to Discord's dropdown limit.)"
            )
            picker_agents = picker_agents[:MAX_SELECT_OPTIONS]

        selections = list(config.selectedAgentIds) if config.selectedAgentIds else [None] * WIDGET_SLOT_COUNT
        while len(selections) < WIDGET_SLOT_COUNT:
            selections.append(None)

        view = AgentPickerView(
            picker_agents, str(interaction.user.id), selections, client, config.hoyoUid, record, full_agents
        )
        await interaction.followup.send(
            "Pick an agent for each widget slot. Clear a dropdown to let that "
            "slot auto-fill with your highest-rarity agents instead.\n"
            f"Hit **Save** when you're done.{note}",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AgentsCog(bot))