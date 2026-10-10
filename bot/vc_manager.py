import logging
import asyncio
from typing import Dict
from pyrogram import Client
from pytgcalls import PyTgCalls, idle
from pytgcalls.types import MediaStream, AudioQuality
from pytgcalls.exceptions import PyTgCallsException
from bot.client_manager import client_manager
from bot.config import Config
from bot.database import db

logger = logging.getLogger("VCManager")

class VCManager:
    """
    Manages active PyTgCalls instances and their associated voice chats.
    Maintains a registry to prevent duplicate joining tasks and handle graceful exits.
    """
    def __init__(self):
        # Format: {session_id: PyTgCalls}
        self.calls: Dict[str, PyTgCalls] = {}
        # Track which chat each session is connected to: {session_id: chat_id}
        self.active_chats: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def _init_call(self, session_id: str, client: Client) -> PyTgCalls:
        """Initializes and caches a PyTgCalls instance for a specific client."""
        if session_id in self.calls:
            return self.calls[session_id]

        call = PyTgCalls(client)
        await call.start()
        self.calls[session_id] = call
        logger.info(f"PyTgCalls initialized for session {session_id}")
        return call

    async def join_vc(self, session_id: str, chat_id: int, stream_url: str = None) -> bool:
        """
        Joins a voice chat in a specific channel/group.
        Requires the client to be a member or admin with necessary permissions.
        """
        async with self._lock:
            # Check if this session is already in a call
            if session_id in self.active_chats:
                if self.active_chats[session_id] == chat_id:
                    logger.warning(f"Session {session_id} is already in VC for {chat_id}.")
                    return True
                else:
                    await self.leave_vc(session_id)

            # Retrieve the underlying Pyrogram client
            client = await client_manager.get_or_start_client(session_id, await self._get_session_string(session_id))
            if not client:
                logger.error(f"Cannot join VC: Client for session {session_id} is unavailable.")
                return False

            call = await self._init_call(session_id, client)

            try:
                # Add joining delay if configured
                if Config.VC_JOIN_DELAY_SECONDS > 0:
                    await asyncio.sleep(Config.VC_JOIN_DELAY_SECONDS)

                # Prepare the audio stream (silent/fallback audio if none provided)
                # PyTgCalls requires a MediaStream.
                media = MediaStream(
                    media_path=stream_url or "http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4", # Fallback for demo/silent. In production, provide a local silent raw file.
                    audio_parameters=AudioQuality.STUDIO
                )

                await call.play(chat_id, media)
                
                self.active_chats[session_id] = chat_id
                
                # Persist state
                await db.active_voice_chats.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"session_id": session_id, "status": "playing", "stream_url": stream_url}},
                    upsert=True
                )
                
                logger.info(f"Session {session_id} joined VC in {chat_id}.")
                return True

            except PyTgCallsException as e:
                logger.error(f"PyTgCalls error joining VC in {chat_id} with session {session_id}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error joining VC: {e}")
                return False

    async def leave_vc(self, session_id: str):
        """Leaves a voice chat and releases the PyTgCalls resource."""
        async with self._lock:
            if session_id not in self.calls:
                return

            call = self.calls[session_id]
            chat_id = self.active_chats.pop(session_id, None)

            if chat_id:
                try:
                    await call.leave_call(chat_id)
                    logger.info(f"Session {session_id} left VC in {chat_id}.")
                except Exception as e:
                    logger.error(f"Error leaving VC for session {session_id}: {e}")
                
                await db.active_voice_chats.delete_one({"chat_id": chat_id})

    async def _get_session_string(self, session_id: str) -> str:
        """Helper to fetch session string from DB."""
        session_data = await db.sessions.find_one({"_id": session_id})
        if session_data:
            return session_data.get("session_string")
        return ""

    async def stop_all(self):
        """Cleanly disconnects all active voice calls."""
        session_ids = list(self.calls.keys())
        for sid in session_ids:
            await self.leave_vc(sid)
            # PyTgCalls automatically handles resource cleanup when the underlying client stops,
            # but we can explicitly clear the references.
            self.calls.pop(sid, None)

vc_manager = VCManager()
