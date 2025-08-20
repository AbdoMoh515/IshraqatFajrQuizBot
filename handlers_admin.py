from aiogram import types
from aiogram.filters import CommandObject
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from filedb import is_user_allowed, add_allowed_user_from_user, list_allowed_users, list_all_users, get_user_by_id, remove_allowed_user
from config import ADMIN_IDS
from keyboards import get_main_keyboard
from states import user_states, States


async def allow_user_command(message: types.Message, command: CommandObject):
    """Admin: Allow a user by user_id from users.json to allowed_users.json."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("You are not authorized to allow users.")
        return
    if not command.args:
        await message.reply("Usage: /allow_user <user_id>")
        return
    try:
        user_id = int(command.args.strip())
    except Exception:
        await message.reply("Invalid user_id.")
        return
    user = get_user_by_id(user_id)
    if not user:
        await message.reply(f"User <code>{user_id}</code> is not in the users list. They must send /start first.", parse_mode="HTML")
        return
    if add_allowed_user_from_user(user):
        await message.reply(f"User <code>{user_id}</code> (<b>{user['first_name']}</b>) promoted to allowed users.", parse_mode="HTML")
    else:
        await message.reply("Failed to add user to allowed_users.")

async def removeuser_command(message: types.Message, command: CommandObject):
    if message.from_user.id in ADMIN_IDS:
        pass  # Allow admin
    else:
        await message.reply("You are not authorized to remove users.")
        return
    if not command.args:
        await message.reply("Usage: /removeuser <user_id>")
        return
    user_id = int(command.args.strip())
    if remove_allowed_user(user_id):
        await message.reply(f"User {user_id} removed.")
    else:
        await message.reply("Failed to remove user.")

async def listusers_command(message: types.Message):
    """Admin: List all allowed users."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("You are not authorized to list users.")
        return
    users = list_allowed_users()
    if not users:
        await message.reply("No allowed users found.")
        return
    msg = "Allowed users:\n" + "\n".join([
        f"<b>User:</b> {u['username'] or 'N/A'}\n<b>User ID:</b> <code>{u['id']}</code>" for u in users
    ])
    await message.reply(msg, parse_mode="HTML")

async def userlist_command(message: types.Message):
    """Admin: List all users in users.json."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("You are not authorized to list all users.")
        return
    users = list_all_users()
    if not users:
        await message.reply("No users found.")
        return
    msg = "All users in users.json:\n" + "\n".join([
        f"<b>User:</b> {u['username'] or 'N/A'}\n<b>User ID:</b> <code>{u['id']}</code>\n<b>Name:</b> {u['first_name'] or 'N/A'}\n<b>Date Joined:</b> {u['date_joined']}" for u in users
    ])
    await message.reply(msg, parse_mode="HTML")

async def handle_admin_text_message(message: types.Message):
    """Handle text messages for admin panel button presses."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return  # Should not happen if they see the buttons

    text = message.text
    if text == "📋 List Allowed Users":
        await listusers_command(message)
    elif text == "👥 List All Users":
        await userlist_command(message)
    elif text == "✅ Allow User":
        await message.reply("Please use the command: /allow_user <user_id>")
    elif text == "❌ Remove User":
        await message.reply("Please use the command: /removeuser <user_id>")
    elif text == "⬅️ Back to Main Menu":
        user_states[user_id] = States.IDLE
        await message.answer("Returning to the main menu.", reply_markup=get_main_keyboard(user_id))


async def myaccess_command(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.reply("✅ You are the bot admin and have full access.")
        return
    allowed = is_user_allowed(message.from_user.id)
    if allowed:
        await message.reply("✅ You are allowed to use this bot.")
    else:
        await message.reply("❌ You are NOT allowed to use this bot.")

from aiogram.dispatcher.middlewares.base import BaseMiddleware

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Allow /start, /help, and admin commands without restriction
        if hasattr(event, 'text') and event.text and event.text.startswith((
            '/start', '/help', '/allow_user', '/removeuser', '/listusers')):
            return await handler(event, data)

        # Always allow admin
        user_id = getattr(event.from_user, 'id', None)
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        # Check DB-based access for non-admins
        if user_id and is_user_allowed(user_id):
            return await handler(event, data)
            
        await event.reply("❌ You are not authorized to use this bot.")
