from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_IDS

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Create the main keyboard, adding admin buttons if applicable."""
    keyboard_buttons = [
        [KeyboardButton(text="📝 Create Quiz")],
        [KeyboardButton(text="📥 Extract Quizzes from Forwards")],
        [KeyboardButton(text="❓ Help")]
    ]

    # Add admin button if the user is an admin
    if user_id in ADMIN_IDS:
        keyboard_buttons.append([KeyboardButton(text="👑 Admin Panel")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Create the admin panel keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 List Allowed Users"), KeyboardButton(text="👥 List All Users")],
            [KeyboardButton(text="✅ Allow User"), KeyboardButton(text="❌ Remove User")],
            [KeyboardButton(text="⬅️ Back to Main Menu")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard
