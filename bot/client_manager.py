import logging
from typing import Dict, Optional
from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, SessionRevoked, SessionExpired, UserDeactivated
from bot.config import Config
from bot.database import db

logger = logging.getLogger("ClientManager")

class ClientManager:
    """
    Manages active Pyrogram user client instances.
    Ensures single-instance connections per session and handles lifecycle gracefully.
    """
    def __init__(self):
        # Format: {session_id (str): Client}
        self.active_clients: Dict[str, Client] = {}

    async def get_or_start_client(self, session_id: str, session_string: str) -> Optional[Client]:
        """
        Retrieves an active client or starts a new one using the provided session string.
        Validates the session string upon startup.
        """
        if session_id in self.active_clients:
            client = self.active_clients[session_id]
            if client.is_connected:
                return client

        client = Client(
            name=f"session_{session_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=session_string,
            in_memory=True,
            no_updates=True # We primarily use these clients for explicit actions/calls, not polling all updates here
        )

        try:
            await client.start()
            
            # Validate session
            me = await client.get_me()
            if not me:
                raise ValueError("Session valid but unable to retrieve user info.")
                
            self.active_clients[session_id] = client
            logger.info(f"Client started successfully for session {session_id} (User: {me.id})")
            return client

        except (AuthKeyUnregistered, SessionRevoked, SessionExpired, UserDeactivated) as e:
            logger.warning(f"Session {session_id} is invalid or revoked: {e}")
            await self._mark_session_invalid(session_id)
            if client.is_connected:
                await client.stop()
            return None
        except Exception as e:
            logger.error(f"Unexpected error starting client {session_id}: {e}")
            if client.is_connected:
                await client.stop()
            return None

    async def stop_client(self, session_id: str):
        """Stops and removes an active client safely."""
        client = self.active_clients.pop(session_id, None)
        if client:
            try:
                if client.is_connected:
                    await client.stop()
                logger.info(f"Client stopped for session {session_id}")
            except Exception as e:
                logger.error(f"Error stopping client {session_id}: {e}")

    async def _mark_session_invalid(self, session_id: str):
        """Updates the database to reflect that a session is no longer usable."""
        try:
            await db.sessions.update_one(
                {"_id": session_id},
                {"$set": {"is_valid": False, "status": "revoked"}}
            )
        except Exception as e:
            logger.error(f"Failed to update session validity in DB for {session_id}: {e}")

    async def stop_all(self):
        """Cleanly stops all active clients. Crucial for application shutdown."""
        session_ids = list(self.active_clients.keys())
        for session_id in session_ids:
            await self.stop_client(session_id)

client_manager = ClientManager()
