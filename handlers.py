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

from config import MIN_INTERVAL_BETWEEN_FILES
from utils import (
    extract_text_from_file, 
    extract_questions_from_text, 
    send_telegram_quizzes, 
    format_quiz_as_text,
    save_questions_to_file,
    get_temp_file_path)
from db import is_user_allowed, add_user, remove_user, list_allowed_users, upsert_user

logger = logging.getLogger(__name__)

# Storage for temporary quiz batches
user_quiz_batches = {}
# Rate limiting
user_last_file_time = {}
# User states
user_states = {}

# Define state constants
class States:
    IDLE = "idle"
    WAITING_FOR_FILE = "waiting_for_file"
    EXTRACTING_QUIZZES = "extracting_quizzes"
    COLLECTING_FORWARDED_QUIZZES = "collecting_forwarded_quizzes"

# Create keyboards
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Create the main keyboard"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Create Quiz")],
            [KeyboardButton(text="📥 Extract Quizzes from Forwards")],
            [KeyboardButton(text="❓ Help")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

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
    """Handle /start command. Upsert user into users table."""
    from db import upsert_user
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name if hasattr(message.from_user, 'full_name') else None
    try:
        success = upsert_user(user_id, username, full_name)
        if not success:
            await message.reply("⚠️ Could not store your user info in the database. Please try again later.")
    except Exception as e:
        import logging
        logging.exception("Failed to upsert user on /start")
        await message.reply("⚠️ Error saving your user info. Please contact admin.")
    user_states[user_id] = States.IDLE
    await message.answer(
        "👋 Welcome to the Quiz Bot!\n\n"
        "This bot can:\n"
        "1. Create quizzes from PDF or text files\n"
        "2. Extract forwarded quizzes into text format\n\n"
        "Use the keyboard below to control the bot.",
        reply_markup=get_main_keyboard()
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
        reply_markup=get_main_keyboard()
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

async def handle_file(message: types.Message):
    """Process PDF or text file"""
    try:
        user_id = message.from_user.id
        
        # Check if user is in the correct state
        if user_id not in user_states or user_states[user_id] != States.WAITING_FOR_FILE:
            return
        
        # Rate limiting
        current_time = datetime.now().timestamp()
        if user_id in user_last_file_time:
            if (diff := current_time - user_last_file_time[user_id]) < MIN_INTERVAL_BETWEEN_FILES:
                await message.reply(f"⏳ Please wait {int(MIN_INTERVAL_BETWEEN_FILES - diff)} seconds")
                return
        
        user_last_file_time[user_id] = current_time

        # Validate file type
        file_name = message.document.file_name.lower()
        if not (file_name.endswith('.pdf') or file_name.endswith('.txt')):
            await message.reply("❌ Please send only PDF or text files")
            return

        processing_msg = await message.reply("🔄 Processing file...")

        # Download file
        file_stream = BytesIO()
        await message.bot.download(message.document, destination=file_stream)

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_file.write(file_stream.getvalue())
            temp_path = temp_file.name

        # Extract text
        text = await extract_text_from_file(temp_path)
        if not text.strip():
            await message.reply("❌ No text found in the file")
            return

        logger.info(f"Extracted text:\n{text[:500]}...")

        # Extract questions
        questions, skipped = extract_questions_from_text(text)
        if not questions:
            await message.reply(
                "❌ No questions found\n\n"
                "Make sure the format is:\n"
                "1. Question text?\n"
                "a) First option\n"
                "b) Second option\n"
                "c) Third option\n"
                "d) Fourth option\n"
                "Answer: c) correct answer"
            )
            return

        # Store extracted questions in user data for later reference
        if 'extracted_data' not in user_states:
            user_states['extracted_data'] = {}
        
        user_states['extracted_data'][user_id] = {
            'questions': questions,
            'skipped': skipped,
            'timestamp': datetime.now()
        }

        # Send as quizzes
        sent, failed, failed_questions = await send_telegram_quizzes(message.bot, questions, message.chat.id)
        
        # Prepare result message
        result_msg = f"✅ Successfully extracted {len(questions)} questions\n"
        result_msg += f"- Sent as quizzes: {sent}\n"
        
        # Add information about failed questions
        if failed > 0:
            result_msg += f"- Failed to send: {failed}\n"
            if failed_questions:
                result_msg += f"  Failed question numbers: {', '.join(map(str, failed_questions))}\n"
        
        # Add information about skipped questions
        if skipped:
            result_msg += f"\n⚠️ Skipped {len(skipped)} questions due to format issues:\n"
            # Show up to 5 skipped questions to avoid very long messages
            display_skipped = skipped[:5]
            result_msg += f"Questions {', '.join(map(str, display_skipped))}"
            if len(skipped) > 5:
                result_msg += f" and {len(skipped) - 5} more"
        
        # Add keyboard for showing extracted questions
        await message.reply(result_msg, reply_markup=get_file_processing_keyboard())
        
        # Update user state but don't reset completely
        user_states[user_id] = States.EXTRACTING_QUIZZES

    except Exception as e:
        logger.error(f"File processing error: {e}", exc_info=True)
        await message.reply("❌ Error processing the file")
    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except Exception as e:
                logger.error(f"Error deleting processing message: {e}")
                pass

async def handle_forwarded_quiz(message: types.Message):
    """Store forwarded quizzes temporarily"""
    try:
        user_id = message.from_user.id
        
        # Check if user is in the correct state
        if user_id not in user_states or user_states[user_id] != States.COLLECTING_FORWARDED_QUIZZES:
            return
            
        if not (message.forward_origin and message.poll and message.poll.type == 'quiz'):
            return

        # Initialize if not exists
        if user_id not in user_quiz_batches:
            user_quiz_batches[user_id] = {
                'quizzes': [],
                'expires_at': datetime.now() + timedelta(hours=1)
            }

        quiz = message.poll
        
        # Log details about the quiz for debugging
        logger.info(f"Received forwarded quiz: {quiz.question[:30]}...")
        logger.info(f"Quiz options count: {len(quiz.options)}")
        logger.info(f"Quiz has correct_option_id: {hasattr(quiz, 'correct_option_id')}")
        if hasattr(quiz, 'correct_option_id'):
            logger.info(f"Correct option ID: {quiz.correct_option_id}")
        
        # Store the quiz
        user_quiz_batches[user_id]['quizzes'].append(quiz)

        count = len(user_quiz_batches[user_id]['quizzes'])
        await message.reply(
            f"📥 Quiz saved ({count})\n"
            "Press 'Finish Extraction' when done",
            reply_markup=get_quiz_creation_keyboard()
        )

    except Exception as e:
        logger.error(f"Quiz storage error: {e}", exc_info=True)
        await message.reply("❌ Error saving the quiz")

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
    await callback_query.message.reply("❌ Quiz extraction cancelled", reply_markup=get_main_keyboard())

async def cancel_processing_callback(callback_query: types.CallbackQuery):
    """Handle cancel processing button press"""
    user_id = callback_query.from_user.id
    
    # Clear user data if exists
    if 'extracted_data' in user_states and user_id in user_states['extracted_data']:
        del user_states['extracted_data'][user_id]
    
    # Reset user state
    user_states[user_id] = States.IDLE
    
    await callback_query.answer("Processing cancelled")
    await callback_query.message.reply("❌ Processing cancelled", reply_markup=get_main_keyboard())

async def handle_direct_quiz(message: types.Message):
    """
    Process quizzes sent directly (not forwarded) and show the correct answer.
    """
    try:
        quiz = message.poll
        quiz_text = await format_quiz_as_text(quiz)
        await message.reply(f"Extracted Quiz:\n\n{quiz_text}")
    except Exception as e:
        logger.error(f"Error processing direct quiz: {e}", exc_info=True)
        await message.reply("❌ Error processing the direct quiz")

async def handle_text_message(message: types.Message):
    """Handle text messages for button presses"""
    text = message.text
    
    if text == "📝 Create Quiz":
        await handle_create_quiz_button(message)
    elif text == "📥 Extract Quizzes from Forwards":
        await handle_extract_quizzes_button(message)
    elif text == "❓ Help":
        await help_command(message)
    else:
        # For any other text message, remind the user to use the keyboard
        await message.reply("Please use the keyboard buttons to interact with the bot.", 
                           reply_markup=get_main_keyboard())
