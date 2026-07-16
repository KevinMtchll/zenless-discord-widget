"""
Shared logic for building the Discord profile-widget field payload and
pushing it via the PATCH /users/@me/... profile endpoint.

Used by:
  - main.py                -- scheduled full refresh for every registered user
  - bot/cogs/agents.py      -- immediate refresh right after /set_agents saves a
                               manual agent pick, so the widget doesn't wait for
                               the next scheduled run
"""

import asyncio
import os
from urllib.parse import quote

import aiohttp
from dotenv import load_dotenv

# Self-contained load, same reasoning as crypto_utils.py: this module may be
# imported before an entry point's own load_dotenv() call has run.
load_dotenv()

DISCORD_BOT_TOKEN = os.environ["BOT_TOKEN"]

DISCORD_API_BASE = "https://discord.com/api/v9"
# Required by Discord for bot requests; the URL is just their documented example UA, not something you need to change.
DISCORD_USER_AGENT = "DiscordBot (https://github.com/discord/discord-api-docs, 1.0.0)"

# Discord field types for the "dynamic" array.
FIELD_TYPE_STRING = 1
FIELD_TYPE_NUMBER = 2
FIELD_TYPE_IMAGE = 3

IMAGE_FIELDS = {"acc_avatar", "agent_1_image", "agent_2_image", "agent_3_image", "agent_4_image"}
AVATAR_ZOOM_MARGIN_PCT = 13

def _zoomed_avatar_url(avatar_url: str, margin_pct: int = AVATAR_ZOOM_MARGIN_PCT) -> str:
    crop_pct = 100 - (2 * margin_pct)
    return (
        f"https://wsrv.nl/?url={quote(avatar_url, safe='')}"
        f"&cx={margin_pct}%25&cy={margin_pct}%25"
        f"&cw={crop_pct}%25&ch={crop_pct}%25"
        f"&precrop"
    )


def _content_aware_agent_url(
    icon_url: str,
    size: tuple[int, int] = (260, 260),
    strategy: str = "attention",
) -> str:
    w, h = size
    return (
        f"https://wsrv.nl/?url={quote(icon_url, safe='')}"
        f"&w={w}&h={h}&fit=cover&a={strategy}"
    )


async def push_widget_fields(
    app_id: str,
    user_id: str,
    fields: dict[str, str | int],
    image_fields: set[str] = frozenset(),
    max_retries: int = 3,
) -> None:
    url = f"{DISCORD_API_BASE}/applications/{app_id}/users/{user_id}/identities/0/profile"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "User-Agent": DISCORD_USER_AGENT,
    }

    dynamic = []
    for name, value in fields.items():
        if name in image_fields:
            dynamic.append({"type": FIELD_TYPE_IMAGE, "name": name, "value": {"url": value}})
        elif isinstance(value, (int, float)):
            dynamic.append({"type": FIELD_TYPE_NUMBER, "name": name, "value": value})
        else:
            dynamic.append({"type": FIELD_TYPE_STRING, "name": name, "value": value})

    body = {"data": {"dynamic": dynamic}}

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries + 1):
            async with session.patch(url, headers=headers, json=body) as resp:
                if resp.status == 429:
                    payload = await resp.json()
                    retry_after = payload.get("retry_after", 5)
                    if attempt == max_retries:
                        raise RuntimeError(f"Widget push rate limited after {max_retries} retries")
                    print(f"Rate limited, waiting {retry_after}s before retry...")
                    await asyncio.sleep(retry_after)
                    continue

                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Widget push failed ({resp.status}): {text}")
                print(f"Pushed fields to widget: {fields}")
                return


def build_agent_slot_fields(agents: list, selected_agent_ids: list[int | None] | None) -> dict:
    """Return agent_1..agent_4 name/image/lvl fields (values may be None,
    meaning "leave this field out of the payload").

    Slots are filled in this priority per slot:
      1. A manual pick from /set_agents (selected_agent_ids), if set
      2. Otherwise, auto-fill from S-rarity agents first, then A-rarity,
         newest (highest ID) first within each tier
    Auto-fill skips any agent already placed manually so the same agent
    can't fill two slots.
    """
    rarity_rank = {"S": 0, "A": 1}
    ranked_agents = [a for a in agents if a.rarity in rarity_rank]
    ranked_agents.sort(key=lambda a: (rarity_rank[a.rarity], -a.id))

    agent_by_id = {a.id: a for a in agents}
    manual_ids = list(selected_agent_ids) if selected_agent_ids else [None, None, None, None]
    manual_ids = (manual_ids + [None, None, None, None])[:4]  # normalize to exactly 4 slots

    used_ids = {aid for aid in manual_ids if aid is not None}
    auto_fill = iter(a for a in ranked_agents if a.id not in used_ids)

    top_agents = [
        agent_by_id[manual_id] if manual_id is not None and manual_id in agent_by_id
        else next(auto_fill, None)
        for manual_id in manual_ids
    ]

    fields = {}
    for i, agent in enumerate(top_agents, start=1):
        if agent is not None:
            fields.update({
                f"agent_{i}_name": agent.name,
                f"agent_{i}_image": _content_aware_agent_url(agent.square_icon),
                f"agent_{i}_lvl": f"Lvl. {agent.level} • M{agent.rank}",
            })
        else:
            # Fewer than 4 S/A-rank agents combined -> Leave these fields
            # out of the payload entirely (filtered by the caller) rather
            # than pushing blanks, using the fallback value instead.
            fields.update({f"agent_{i}_name": None, f"agent_{i}_image": None, f"agent_{i}_lvl": None})

    return fields


async def build_widget_fields(
    client, hoyo_uid: int, record, agents: list, selected_agent_ids: list[int | None] | None
) -> dict:
    """Full widget field set for one user: account info + agent slots.
    None-valued fields are dropped before returning."""
    widget_fields = {}
    accounts = await client.get_game_accounts()
    for acc in accounts:
        if acc.game_biz.startswith("nap"):
            widget_fields = {
                "acc_name": f"{acc.nickname}",
                "acc_uid": f"UID: {hoyo_uid}",
                "acc_lvl": f"Lvl. {acc.level}",
                "acc_server": acc.server_name,
            }
            break
    widget_fields.update({"acc_avatar": _zoomed_avatar_url(record.in_game_avatar)})
    widget_fields.update(build_agent_slot_fields(agents, selected_agent_ids))

    return {k: v for k, v in widget_fields.items() if v is not None}