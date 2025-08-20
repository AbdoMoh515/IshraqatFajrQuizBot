import logging
import os
import tempfile
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from aiogram import Bot, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import (
    Poll, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
    Message
)

from config import MIN_INTERVAL_BETWEEN_FILES, ADMIN_IDS
from utils import (
    extract_text_from_file, 
    extract_questions_from_text, 
    send_telegram_quizzes, 
    format_quiz_as_text,
    save_questions_to_file,
    get_temp_file_path)
from filedb import is_user_allowed, add_allowed_user_from_user, list_allowed_users, upsert_user
from keyboards import get_main_keyboard, get_admin_keyboard
from handlers_admin import handle_admin_text_message
from states import user_states, States

logger = logging.getLogger(__name__)

# Storage for temporary quiz batches
user_quiz_batches = {}
# Rate limiting
user_last_file_time: Dict[int, float] = {}
quiz_counter: Dict[int, int] = {}  # To manage sequential quiz numbering

# Create keyboards

def get_quiz_creation_keyboard() -> InlineKeyboardMarkup:
    """Create the quiz creation keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Finish Extraction", callback_data="finish_extraction")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_extraction")]
        ]
    )
    return keyboard

def get_file_processing_keyboard() -> InlineKeyboardMarkup:
    """Create the file processing keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Show Extracted Questions", callback_data="show_questions")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_processing")]
        ]
    )
    return keyboard

async def start_command(message: types.Message):
    """Handle /start command. Upsert user into users.json."""
    from filedb import upsert_user
    user_id = message.from_user.id
    username = message.from_user.username or ''
    first_name = message.from_user.first_name if hasattr(message.from_user, 'first_name') else ''
    try:
        success = upsert_user(user_id, username, first_name)
        if not success:
            await message.reply("⚠️ Could not store your user info. Please try again later.")
    except Exception as e:
        import logging
        logging.exception("Failed to upsert user on /start")
        await message.reply("⚠️ Error saving your user info. Please contact admin.")
    user_states[user_id] = States.IDLE
    await message.answer(
        "👋 Welcome to the Quiz Bot!\n\n"
        "This bot can:\n"
        "- Extract quizzes from PDF/text\n"
        "- Extract quizzes from forwarded messages\n"
        "- Format Telegram quizzes as text\n\n"
        "Use the menu or send /help for more info.",
        reply_markup=get_main_keyboard(user_id)
    )

async def help_command(message: types.Message):
    """Handle /help command"""
    await message.answer(
        "📚 Help:\n\n"
        "For PDF/Text Files:\n"
        "- Send a PDF or text file with questions\n"
        "- Required format:\n"
        "  1. Question text?\n"
        "  a) First option\n"
        "  b) Second option\n"
        "  c) Third option\n"
        "  d) Fourth option\n"
        "  Answer: c) correct answer\n\n"
        "For Telegram Quizzes:\n"
        "- Forward quizzes to me\n"
        "- Press 'Finish Extraction' when done\n"
        "- I'll send all quizzes in a single text message",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

async def handle_create_quiz_button(message: types.Message):
    """Handle the Create Quiz button press"""
    user_id = message.from_user.id
    user_states[user_id] = States.WAITING_FOR_FILE
    
    await message.answer(
        "📤 Please send me a PDF or text file with questions.\n\n"
        "The file should contain questions in this format:\n"
        "1. Question text?\n"
        "a) First option\n"
        "b) Second option\n"
        "c) Third option\n"
        "d) Fourth option\n"
        "Answer: c) correct answer"
    )

async def handle_extract_quizzes_button(message: types.Message):
    """Handle the Extract Quizzes button press"""
    user_id = message.from_user.id
    user_states[user_id] = States.COLLECTING_FORWARDED_QUIZZES
    
    # Initialize or clear the user's quiz batch
    user_quiz_batches[user_id] = {
        'quizzes': [],
        'expires_at': datetime.now() + timedelta(hours=1)
    }
    
    await message.answer(
        "📥 Please forward me Telegram quizzes.\n"
        "I'll collect them until you press 'Finish Extraction'.",
        reply_markup=get_quiz_creation_keyboard()
    )

async def process_quiz_extraction(message: types.Message, text: str):
    """Helper function to process extracted text and send quizzes."""
    user_id = message.from_user.id
    try:
        if not text.strip():
            await message.reply("❌ The provided text is empty.")
            return

        logger.info(f"Processing text for quiz extraction (user: {user_id})...")
        
        # Reset the quiz counter for the user at the start of a new extraction
        quiz_counter[user_id] = 1
        
        questions, skipped = extract_questions_from_text(text)

        if not questions:
            await message.reply(
                "❌ No valid questions found. Please check the format and try again.",
                reply_markup=get_main_keyboard(user_id)
            )
            user_states[user_id] = States.IDLE
            return

        # Store data for potential later use (e.g., showing questions as text)
        if 'extracted_data' not in user_states:
            user_states['extracted_data'] = {}
        user_states['extracted_data'][user_id] = {
            'questions': questions,
            'skipped': skipped,
            'timestamp': datetime.now()
        }

        sent, failed, failed_questions = await send_telegram_quizzes(
            message.bot, questions, message.chat.id, quiz_counter
        )

        result_msg = f"✅ Successfully extracted {len(questions)} questions.\n"
        result_msg += f"- Sent as quizzes: {sent}\n"
        if failed > 0:
            result_msg += f"- Failed to send: {failed} (Numbers: {', '.join(map(str, failed_questions))})\n"
        if skipped:
            result_msg += f"\n⚠️ Skipped {len(skipped)} questions:\n"
            for item in skipped[:5]:
                result_msg += f"- Q#{item.get('number', '?')}: {item.get('reason', 'Unknown')}\n"
            if len(skipped) > 5:
                result_msg += f"...and {len(skipped) - 5} more."

        await message.reply(result_msg, reply_markup=get_file_processing_keyboard())
        user_states[user_id] = States.EXTRACTING_QUIZZES

    except Exception as e:
        logger.error(f"Error during quiz extraction processing for user {user_id}: {e}", exc_info=True)
        await message.reply("❌ An unexpected error occurred while processing the questions.")
        user_states[user_id] = States.IDLE

async def handle_file(message: types.Message):
    """Process PDF or text file."""
    user_id = message.from_user.id
    if user_states.get(user_id) != States.WAITING_FOR_FILE:
        return

    # Rate limiting
    current_time = datetime.now().timestamp()
    if user_id in user_last_file_time and (diff := current_time - user_last_file_time.get(user_id, 0)) < MIN_INTERVAL_BETWEEN_FILES:
        await message.reply(f"⏳ Please wait {int(MIN_INTERVAL_BETWEEN_FILES - diff)} seconds.")
        return
    user_last_file_time[user_id] = current_time

    file_name = message.document.file_name.lower()
    if not (file_name.endswith('.pdf') or file_name.endswith('.txt')):
        await message.reply("❌ Please send only PDF or text files.")
        return

    processing_msg = await message.reply("🔄 Processing file...")
    temp_path = None
    try:
        file_stream = BytesIO()
        await message.bot.download(message.document, destination=file_stream)
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_file.write(file_stream.getvalue())
            temp_path = temp_file.name

        text = await extract_text_from_file(temp_path)
        await process_quiz_extraction(message, text)

    except Exception as e:
        logger.error(f"File processing error for user {user_id}: {e}", exc_info=True)
        await message.reply("❌ Error processing the file.")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        try:
            await processing_msg.delete()
        except Exception:
            pass

async def handle_quiz_message(message: types.Message):
    """
    Handle all incoming quizzes (direct or forwarded).
    Stores quizzes temporarily in a per-user buffer and shows the 'Finish' button.
    """
    try:
        user_id = message.from_user.id
        
        # Check if user is in the correct state to collect quizzes
        if user_id not in user_states or user_states[user_id] != States.COLLECTING_FORWARDED_QUIZZES:
            return
            
        quiz = message.poll
        
        # Initialize a new batch if one doesn't exist for the user
        if user_id not in user_quiz_batches:
            user_quiz_batches[user_id] = {
                'quizzes': [],
                'expires_at': datetime.now() + timedelta(hours=1)
            }
        
        # Add the quiz to the user's batch
        user_quiz_batches[user_id]['quizzes'].append(quiz)
        
        count = len(user_quiz_batches[user_id]['quizzes'])
        
        # Reply to the user with the current count and the keyboard
        await message.reply(
            f"📥 Quiz saved ({count}).\n"
            "Forward more quizzes or press 'Finish Extraction' when you are done.",
            reply_markup=get_quiz_creation_keyboard()
        )

    except Exception as e:
        logger.error(f"Error processing quiz message: {e}", exc_info=True)
        await message.reply("❌ An error occurred while saving the quiz.")

async def finish_extraction_callback(callback_query: types.CallbackQuery):
    """Handle finish extraction button press"""
    try:
        user_id = callback_query.from_user.id
        
        # Check if user has quizzes
        if user_id not in user_quiz_batches or not user_quiz_batches[user_id]['quizzes']:
            await callback_query.message.reply("❌ No quizzes saved")
            await callback_query.answer()
            return

        await callback_query.answer("Processing quizzes...")
        
        quizzes = user_quiz_batches.pop(user_id)['quizzes']
        formatted_quizzes = []
        skipped_quizzes = []
        
        for i, quiz in enumerate(quizzes, 1):
            try:
                quiz_text = await format_quiz_as_text(quiz, i)
                formatted_quizzes.append(quiz_text)
            except Exception as e:
                logger.error(f"Error formatting quiz {i}: {e}")
                skipped_quizzes.append(str(i))

        # Create a summary message
        summary = f"✅ Extracted {len(formatted_quizzes)} quizzes out of {len(quizzes)} forwarded"
        if skipped_quizzes:
            summary += f"\n⚠️ Skipped questions: {', '.join(skipped_quizzes)}"
        
        # Send as text message(s)
        message_text = "\n\n".join(formatted_quizzes)
        
        # Split if too long
        if len(message_text) > 4000:
            # Save to file and send as document
            file_path = get_temp_file_path(user_id)
            if save_questions_to_file(formatted_quizzes, file_path):
                await callback_query.message.reply_document(
                    FSInputFile(file_path, filename="extracted_quizzes.txt"),
                    caption=summary
                )
                # Clean up the file
                os.remove(file_path)
            else:
                # If file saving fails, send in parts
                parts = [message_text[i:i+4000] for i in range(0, len(message_text), 4000)]
                await callback_query.message.reply(summary)
                for i, part in enumerate(parts, 1):
                    await callback_query.message.reply(f"Part {i}/{len(parts)}:\n\n{part}")
        else:
            await callback_query.message.reply(f"{summary}\n\n{message_text}")
        
        # Reset user state
        user_states[user_id] = States.IDLE

    except Exception as e:
        logger.error(f"Quiz extraction error: {e}", exc_info=True)
        await callback_query.message.reply("❌ Error creating the summary")
    
async def show_questions_callback(callback_query: types.CallbackQuery):
    """Handle show extracted questions button press"""
    try:
        user_id = callback_query.from_user.id
        
        # Check if user has extracted data
        if 'extracted_data' not in user_states or user_id not in user_states['extracted_data']:
            await callback_query.message.reply("❌ No extracted questions available")
            await callback_query.answer()
            return

        await callback_query.answer("Showing extracted questions...")
        
        extracted_data = user_states['extracted_data'][user_id]
        questions = extracted_data['questions']
        skipped = extracted_data['skipped']
        
        # Format questions as text
        formatted_questions = []
        for i, q in enumerate(questions, 1):
            question_text = f"{i}. {q['question']}\n"
            for j, option in enumerate(q['options']):
                question_text += f"{chr(97 + j)}) {option}\n"
            correct_letter = chr(97 + q['correct_option_id'])
            question_text += f"Answer: {correct_letter}) {q['options'][q['correct_option_id']]}"
            formatted_questions.append(question_text)
        
        # Create summary message
        summary = f"📊 Showing {len(questions)} extracted questions"
        if skipped:
            summary += f"\n⚠️ {len(skipped)} questions were skipped due to format issues"
        
        # Send as text or file depending on length
        message_text = "\n\n".join(formatted_questions)
        
        if len(message_text) > 4000:
            # Save to file and send as document
            file_path = get_temp_file_path(user_id, prefix="extracted_")
            if save_questions_to_file(formatted_questions, file_path):
                await callback_query.message.reply_document(
                    FSInputFile(file_path, filename="extracted_questions.txt"),
                    caption=summary
                )
                # Clean up the file
                os.remove(file_path)
            else:
                # If file saving fails, send in parts
                parts = [message_text[i:i+4000] for i in range(0, len(message_text), 4000)]
                await callback_query.message.reply(summary)
                for i, part in enumerate(parts, 1):
                    await callback_query.message.reply(f"Part {i}/{len(parts)}:\n\n{part}")
        else:
            await callback_query.message.reply(f"{summary}\n\n{message_text}")
    
    except Exception as e:
        logger.error(f"Show questions error: {e}", exc_info=True)
        await callback_query.message.reply("❌ Error showing extracted questions")

async def cancel_extraction_callback(callback_query: types.CallbackQuery):
    """Handle cancel extraction button press"""
    user_id = callback_query.from_user.id
    
    # Clear user data
    if user_id in user_quiz_batches:
        del user_quiz_batches[user_id]
    
    # Reset user state
    user_states[user_id] = States.IDLE
    
    await callback_query.answer("Extraction cancelled")
    await callback_query.message.reply("❌ Quiz extraction cancelled", reply_markup=get_main_keyboard(user_id))

async def cancel_processing_callback(callback_query: types.CallbackQuery):
    """Handle cancel processing button press"""
    user_id = callback_query.from_user.id
    
    # Clear user data if exists
    if 'extracted_data' in user_states and user_id in user_states['extracted_data']:
        del user_states['extracted_data'][user_id]
    
    # Reset user state
    user_states[user_id] = States.IDLE
    
    await callback_query.answer("Processing cancelled")
    await callback_query.message.reply("❌ Processing cancelled", reply_markup=get_main_keyboard(user_id))


async def handle_admin_panel_button(message: types.Message):
    """Handle the Admin Panel button press."""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        user_states[user_id] = States.ADMIN_PANEL
        await message.answer("👑 Welcome to the Admin Panel!", reply_markup=get_admin_keyboard())


async def handle_text_message(message: types.Message):
    """Handle text messages for button presses or direct quiz text."""
    user_id = message.from_user.id
    text = message.text

    # Check for button presses first
    if text == "📝 Create Quiz":
        await handle_create_quiz_button(message)
        return
    elif text == "📥 Extract Quizzes from Forwards":
        await handle_extract_quizzes_button(message)
        return
    elif text == "❓ Help":
        await help_command(message)
        return
    elif text == "👑 Admin Panel":
        await handle_admin_panel_button(message)
        return

    # Route to admin handler if in admin panel
    if user_states.get(user_id) == States.ADMIN_PANEL:
        await handle_admin_text_message(message)
        return

    # If not a button, check if user is in a state to send quiz text
    if user_states.get(user_id) == States.WAITING_FOR_FILE:
        processing_msg = await message.reply("🔄 Processing text...")
        await process_quiz_extraction(message, text)
        await processing_msg.delete()
    else:
        # For any other text message, remind the user to use the keyboard
        await message.reply("Please use the keyboard buttons or send /start to begin.", 
                           reply_markup=get_main_keyboard(user_id))
