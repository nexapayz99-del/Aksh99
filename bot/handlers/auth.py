import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, PasswordHashInvalid
from bot.state_machine import state_manager, AuthState
from bot.database import db

logger = logging.getLogger("AuthHandler")

# Note: In a full plugin structure, these are registered via a blueprint or dispatcher.
# For clarity, we define them as standalone async functions assuming standard Pyrogram routing.

async def handle_add_account(client: Client, message: Message):
    """Initiates the login process for a new user account."""
    user_id = message.from_user.id
    state_manager.set_state(user_id, AuthState.WAITING_PHONE)
    await message.reply_text(
        "Please send the phone number of the account you want to add (e.g., +1234567890).",
        reply_markup=None # Remove inline keyboards to capture plain text
    )

async def process_phone_number(client: Client, message: Message):
    """Processes the submitted phone number and requests a login code."""
    user_id = message.from_user.id
    phone_number = message.text.strip()
    
    # Create a temporary in-memory client to generate the code
    temp_client = Client(
        name=f"temp_{user_id}",
        api_id=client.api_id,
        api_hash=client.api_hash,
        in_memory=True
    )
    
    await temp_client.connect()
    
    try:
        sent_code = await temp_client.send_code(phone_number)
        
        # Store temporary state required for next steps
        state_manager.set_state(user_id, AuthState.WAITING_CODE, {
            "phone_number": phone_number,
            "phone_code_hash": sent_code.phone_code_hash,
            "temp_client": temp_client # Keep client alive for the next step
        })
        
        await message.reply_text(
            "Code sent to your Telegram app. Please reply with the code.\n\n"
            "**Note:** To prevent formatting issues, send the code with spaces between numbers (e.g., `1 2 3 4 5`)."
        )
    except Exception as e:
        logger.error(f"Failed to send code to {phone_number}: {e}")
        await message.reply_text(f"Failed to send code: {e}")
        await temp_client.disconnect()
        state_manager.clear_state(user_id)

async def process_login_code(client: Client, message: Message):
    """Processes the login code and handles 2FA if required."""
    user_id = message.from_user.id
    code = message.text.replace(" ", "").strip()
    
    data = state_manager.get_data(user_id, "temp_client")
    if not data:
        await message.reply_text("Session expired. Please try adding the account again.")
        state_manager.clear_state(user_id)
        return

    temp_client: Client = data
    phone_number = state_manager.get_data(user_id, "phone_number")
    phone_code_hash = state_manager.get_data(user_id, "phone_code_hash")

    try:
        await temp_client.sign_in(phone_number, phone_code_hash, code)
        await finalize_login(message, temp_client, user_id)
        
    except SessionPasswordNeeded:
        # Requires 2FA
        state_manager.set_state(user_id, AuthState.WAITING_PASSWORD)
        await message.reply_text("This account has Two-Step Verification enabled. Please send your password.")
        
    except (PhoneCodeInvalid, PhoneCodeExpired) as e:
        await message.reply_text(f"Invalid or expired code: {e}. Please start over.")
        await temp_client.disconnect()
        state_manager.clear_state(user_id)
    except Exception as e:
        logger.error(f"Login failed: {e}")
        await message.reply_text(f"An error occurred: {e}")
        await temp_client.disconnect()
        state_manager.clear_state(user_id)

async def process_password(client: Client, message: Message):
    """Processes the 2FA password."""
    user_id = message.from_user.id
    password = message.text.strip()
    
    temp_client: Client = state_manager.get_data(user_id, "temp_client")
    if not temp_client:
        await message.reply_text("Session expired. Please start over.")
        state_manager.clear_state(user_id)
        return

    try:
        await temp_client.check_password(password)
        await finalize_login(message, temp_client, user_id)
        
        # Immediately delete the message containing the password for security
        await message.delete()
        
    except PasswordHashInvalid:
        await message.reply_text("Incorrect password. Please try again or type /cancel.")
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        await message.reply_text(f"An error occurred: {e}")
        await temp_client.disconnect()
        state_manager.clear_state(user_id)

async def finalize_login(message: Message, temp_client: Client, owner_id: int):
    """Extracts the session string and saves it securely to the database."""
    try:
        me = await temp_client.get_me()
        session_string = await temp_client.export_session_string()
        
        # Generate a unique ID for this session (using the authorized account's ID)
        session_id = str(me.id)
        
        # Save to database
        await db.sessions.update_one(
            {"_id": session_id},
            {"$set": {
                "user_id": me.id,
                "owner_id": owner_id,
                "first_name": me.first_name,
                "username": me.username,
                "phone": me.phone_number,
                "session_string": session_string,
                "is_valid": True,
                "status": "active"
            }},
            upsert=True
        )
        
        await message.reply_text(f"✅ Successfully authorized account: **{me.first_name}** (`{me.id}`).")
        logger.info(f"User {owner_id} successfully added account {me.id}.")
        
    except Exception as e:
        logger.error(f"Failed to finalize login: {e}")
        await message.reply_text("Login succeeded, but failed to save session data.")
    finally:
        await temp_client.disconnect()
        state_manager.clear_state(owner_id)
