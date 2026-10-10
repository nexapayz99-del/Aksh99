import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI")
    DB_NAME = os.getenv("DB_NAME", "telegram_manager")
    
    try:
        OWNER_ID = int(os.getenv("OWNER_ID", "0"))
    except ValueError:
        OWNER_ID = 0

    CHANNEL_POST_POLL_SECONDS = int(os.getenv("CHANNEL_POST_POLL_SECONDS", "10"))
    VC_LIVESTREAM_POLL_SECONDS = int(os.getenv("VC_LIVESTREAM_POLL_SECONDS", "5"))
    VC_JOIN_DELAY_SECONDS = int(os.getenv("VC_JOIN_DELAY_SECONDS", "1"))
    
    PORT = int(os.getenv("PORT", "7860"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.API_ID: missing.append("API_ID")
        if not cls.API_HASH: missing.append("API_HASH")
        if not cls.BOT_TOKEN: missing.append("BOT_TOKEN")
        if not cls.MONGO_URI: missing.append("MONGO_URI")
        if not cls.OWNER_ID: missing.append("OWNER_ID")

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AppConfig")
