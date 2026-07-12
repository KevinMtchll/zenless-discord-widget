"""
Loads the environment variables.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
APP_ID = os.environ["APP_ID"]
DB_NAME = os.environ.get("MONGO_DB_NAME", "test")
COLLECTION_NAME = "userconfigs"
OAUTH_REDIRECT_URI = "https://discord.com"