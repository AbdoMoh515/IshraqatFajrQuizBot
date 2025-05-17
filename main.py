import asyncio
import logging
import signal
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from config import TELEGRAM_TOKEN, LOG_CHANNEL_ID
from handlers import (
    start_command, 
    help_command, 
    handle_file, 
    handle_forwarded_quiz,
    handle_direct_quiz,  # <-- import the new handler
    finish_extraction_callback,
    cancel_extraction_callback,
    show_questions_callback,
    cancel_processing_callback,
    handle_text_message
)
from handlers_admin import (
    allow_user_command,
    removeuser_command,
    listusers_command,
    myaccess_command,
    userlist_command,
    AccessControlMiddleware
)

# Initialize logging
logger = logging.getLogger(__name__)

# Create temp directory if it doesn't exist
os.makedirs("temp", exist_ok=True)

# Initialize bot with default properties
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Register command handlers
dp.message.register(start_command, CommandStart())
dp.message.register(help_command, Command("help"))

# Register message handlers
dp.message.register(handle_file, lambda m: m.document)
dp.message.register(handle_forwarded_quiz, lambda m: m.forward_origin and m.poll and m.poll.type == 'quiz')
dp.message.register(handle_direct_quiz, lambda m: m.poll and m.poll.type == 'quiz' and not m.forward_origin)
dp.message.register(handle_text_message, lambda m: m.text and not m.text.startswith('/'))
dp.message.register(allow_user_command, Command("allow_user"))
dp.message.register(removeuser_command, Command("removeuser"))
dp.message.register(listusers_command, Command("listusers"))
dp.message.register(myaccess_command, Command("myaccess"))
dp.message.register(userlist_command, Command("userlist"))
dp.message.middleware(AccessControlMiddleware())

# Register callback query handlers
dp.callback_query.register(finish_extraction_callback, lambda c: c.data == "finish_extraction")
dp.callback_query.register(cancel_extraction_callback, lambda c: c.data == "cancel_extraction")
dp.callback_query.register(show_questions_callback, lambda c: c.data == "show_questions")
dp.callback_query.register(cancel_processing_callback, lambda c: c.data == "cancel_processing")

# Enhanced error handler
@dp.error()
async def error_handler(event, exception):
    error_message = (
        f"❌ Exception in handler {event.handler.__name__ if hasattr(event, 'handler') else 'unknown'}:\n"
        f"Type: {type(exception).__name__}\n"
        f"Message: {str(exception)}"
    )
    logger.error(error_message, exc_info=True)
    
    # Send error to the logging channel
    try:
        await bot.send_message(LOG_CHANNEL_ID, error_message)
    except Exception as e:
        logger.error(f"Failed to send error to log channel: {e}")

async def set_commands():
    """Set bot commands in the menu"""
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help information")
    ]
    await bot.set_my_commands(commands)

async def main():
    logger.info("✅ Bot is starting...")
    
    # Delete webhook before starting polling
    logger.info("Deleting webhook...")
    await bot.delete_webhook()
    
    # Set bot commands
    await set_commands()
    
    # Send startup notification
    try:
        await bot.send_message(LOG_CHANNEL_ID, "🚀 Bot has started successfully!")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")

    await dp.start_polling(bot)

async def shutdown(signal, loop):
    """Safely shutdown the bot when receiving termination signal"""
    logger.warning(f"Received {signal.name} signal...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    if tasks:
        logger.info(f"Cancelling {len(tasks)} pending tasks...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
    logger.info("Bot shutdown successful!")
    loop.stop()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
        except NotImplementedError:
            pass
    
    try:
        loop.run_until_complete(main())
    except Exception as e:
        logger.critical(f"Fatal error in main loop: {e}")
    finally:
        logger.info("Closing event loop")
        loop.close()
