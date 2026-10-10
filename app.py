import asyncio
import logging
import signal
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

from bot.config import Config
from bot.database import db
from bot.client_manager import client_manager
from bot.vc_manager import vc_manager
from bot.workers.channel_monitor import channel_monitor
from web.server import start_web_server
from bot.state_machine import state_manager, AuthState
from bot.handlers.auth import handle_add_account, process_phone_number, process_login_code, process_password

# Setup basic logging for the entry point
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MainApp")

class TelegramManagerBot:
    def __init__(self):
        self.bot = Client(
            name="manager_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            in_memory=True
        )
        self.web_runner = None
        self._register_handlers()

    def _register_handlers(self):
        """Binds incoming Pyrogram updates to handler functions."""
        
        # Simple start/ping command
        async def on_start(client, message):
            await message.reply_text("👋 Welcome to the Advanced Telegram Account Manager.")
        
        self.bot.add_handler(MessageHandler(on_start, filters.command("start") & filters.private))
        
        # Auth initialization
        self.bot.add_handler(MessageHandler(handle_add_account, filters.command("add_account") & filters.private))
        
        # Dynamic State Router for Auth Flow
        async def state_router(client, message):
            if message.text and message.text.startswith("/"):
                # Handle command cancellation
                if message.text == "/cancel":
                    state_manager.clear_state(message.from_user.id)
                    await message.reply_text("Action cancelled.")
                return

            state = state_manager.get_state(message.from_user.id)
            
            if state == AuthState.WAITING_PHONE:
                await process_phone_number(client, message)
            elif state == AuthState.WAITING_CODE:
                await process_login_code(client, message)
            elif state == AuthState.WAITING_PASSWORD:
                await process_password(client, message)
                
        # Register the state router for all private text messages that aren't commands
        self.bot.add_handler(MessageHandler(state_router, filters.text & filters.private & ~filters.command("start") & ~filters.command("add_account")))

    async def start(self):
        """Initializes all services and starts the application."""
        logger.info("Validating configuration...")
        Config.validate()

        logger.info("Initializing database...")
        await db.initialize_indexes()

        logger.info("Starting web server...")
        self.web_runner = await start_web_server()

        logger.info("Starting background workers...")
        await channel_monitor.start()

        logger.info("Starting main controller bot...")
        await self.bot.start()
        logger.info("Bot is now running.")

    async def stop(self):
        """Performs a graceful shutdown of all services."""
        logger.info("Initiating graceful shutdown...")
        
        # Stop background workers
        await channel_monitor.stop()

        # Stop PyTgCalls and clear voice chats
        logger.info("Releasing voice chat resources...")
        await vc_manager.stop_all()

        # Stop all user sessions
        logger.info("Closing active Pyrogram sessions...")
        await client_manager.stop_all()

        # Stop main controller bot
        if self.bot.is_connected:
            logger.info("Stopping main bot...")
            await self.bot.stop()

        # Stop web server
        if self.web_runner:
            logger.info("Stopping web server...")
            await self.web_runner.cleanup()

        # Close database
        logger.info("Closing database connections...")
        await db.close()

        logger.info("Shutdown complete.")

async def main():
    app = TelegramManagerBot()
    
    # Handle shutdown signals for Docker/Linux environments
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received termination signal.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # add_signal_handler is not implemented on Windows
            pass

    try:
        await app.start()
        # Keep the application running until a signal is received
        await stop_event.wait()
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)
    finally:
        await app.stop()

if __name__ == "__main__":
    # Ensure uvloop is used if available (recommended for performance, though not strictly required)
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
        
    asyncio.run(main())
