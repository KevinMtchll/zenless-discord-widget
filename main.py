import asyncio

from bot.hoyolab import build_client
from core.config import APP_ID
from core.db import collection
from core.user_config import UserConfig
from core.widget import IMAGE_FIELDS, build_widget_fields, push_widget_fields


async def update_discord_widget() -> None:
    print("Connected to MongoDB.")
    try:
        doc = await collection.find_one()
        if doc is None:
            raise RuntimeError("No user config found in MongoDB!")

        config = UserConfig.model_validate(doc)
        client = build_client(config)

        print("Fetching ZZZ Data...")
        record = await client.get_zzz_user(config.hoyoUid)
        agents = await client.get_zzz_agents(config.hoyoUid)

        widget_fields = await build_widget_fields(client, config.hoyoUid, record, agents, config.selectedAgentIds)

        await push_widget_fields(
            app_id=APP_ID,
            user_id=config.userId,
            fields=widget_fields,
            image_fields=IMAGE_FIELDS,
        )

    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    asyncio.run(update_discord_widget())