"""
bot/main.py
===========
Main entry point for the TopKap Telegram Bot.
"""
import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from bot.handlers.start_handler import register_start_handlers
from bot.handlers.product_handler import get_product_conv_handler
from bot.handlers.channel_handler import register_channel_handlers, handle_my_chat_member
from telegram.ext import ChatMemberHandler

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found in environment variables.")
        return

    application = ApplicationBuilder().token(token).build()

    # Register handlers
    register_start_handlers(application)
    application.add_handler(get_product_conv_handler())
    register_channel_handlers(application)
    
    # Register chat member handler for channel admin detection
    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("Starting TopKap Bot...")
    application.run_polling()

if __name__ == '__main__':
    main()
