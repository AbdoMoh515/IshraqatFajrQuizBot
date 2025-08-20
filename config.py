import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
print("DEBUG TELEGRAM_TOKEN:", repr(TELEGRAM_TOKEN))  # Debug print for troubleshooting
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1002300659776"))
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(',') if admin_id]

# Rate limiting
MIN_INTERVAL_BETWEEN_FILES = int(os.getenv("MIN_INTERVAL_BETWEEN_FILES", "60"))  # seconds

# Bot version
BOT_VERSION = "1.2"

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Validate configuration
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set in environment variables")
