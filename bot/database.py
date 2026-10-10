import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from bot.config import Config

logger = logging.getLogger("Database")

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(
            Config.MONGO_URI,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.client[Config.DB_NAME]
        
        # Collections
        self.users = self.db.users
        self.sessions = self.db.sessions
        self.admins = self.db.admins
        self.settings = self.db.settings
        self.monitored_channels = self.db.monitored_channels
        self.processed_posts = self.db.processed_posts
        self.active_voice_chats = self.db.active_voice_chats
        self.task_history = self.db.task_history

    async def initialize_indexes(self):
        """Creates unique indexes to prevent duplicate processing and data corruption."""
        try:
            # Prevent duplicate sessions for the same user account
            await self.sessions.create_index(
                [("user_id", 1), ("owner_id", 1)], 
                unique=True
            )
            
            # Prevent duplicate post processing
            await self.processed_posts.create_index(
                [("channel_id", 1), ("message_id", 1), ("action_type", 1)], 
                unique=True
            )
            
            # Ensure only one active VC tracking per chat
            await self.active_voice_chats.create_index("chat_id", unique=True)
            
            # Fast lookup for monitored channels
            await self.monitored_channels.create_index("channel_id", unique=True)

            logger.info("Database indexes verified.")
            
            # Ensure owner exists in admins collection
            await self.admins.update_one(
                {"user_id": Config.OWNER_ID},
                {"$set": {"role": "OWNER"}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to initialize database indexes: {e}")
            raise

    async def check_health(self) -> bool:
        try:
            await self.client.admin.command('ping')
            return True
        except ConnectionFailure:
            return False

    async def close(self):
        self.client.close()

db = Database()
