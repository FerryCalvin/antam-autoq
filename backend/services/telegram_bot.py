import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

async def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Sends an asynchronous Telegram alert using python-telegram-bot v20+.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not configured. Skipping alert.")
        return False
        
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info("Telegram alert sent successfully.")
        return True
    except TelegramError as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram alert: {e}")
        return False
