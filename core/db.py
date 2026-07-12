"""
Shared MongoDB client and collection handle.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from core.config import COLLECTION_NAME, DB_NAME, MONGO_URI

_mongo_client = AsyncIOMotorClient(MONGO_URI)
collection = _mongo_client[DB_NAME][COLLECTION_NAME]