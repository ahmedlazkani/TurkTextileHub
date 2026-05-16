"""
bot/main.py
===========
Main entry point for the TopKap Telegram Bot.

Environment Variables Required:
    TELEGRAM_BOT_TOKEN  — Telegram bot token from BotFather
    KAYISOFT_API_URL    — KAYISOFT wholesale API base URL
    TELEGRAM_BOT_API_ENDPOINT_KEY — KAYISOFT API bearer token
    DEEPSEEK_API_KEY    — DeepSeek AI API key
"""
import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, ChatMemberHandler

# Load environment variables from .env file (local dev only)
load_dotenv()

# Configure structured logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from bot.handlers.start_handler import register_start_handlers
from bot.handlers.product_handler import get_product_conv_handler
from bot.handlers.channel_handler import register_channel_handlers, handle_my_chat_member


def main():
    # Support both TELEGRAM_BOT_TOKEN (Railway) and BOT_TOKEN (legacy .env)
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        logger.error("ERROR — TELEGRAM_BOT_TOKEN not found in environment variables.")
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot.")

    logger.info("TopKap Bot initializing...")

    application = ApplicationBuilder().token(token).build()

    # ── Register all handlers ──────────────────────────────────────────────
    register_start_handlers(application)           # /start + language selection
    application.add_handler(get_product_conv_handler())  # Product upload flow
    register_channel_handlers(application)         # Channel management
    application.add_handler(                       # Detect bot added to channel
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    logger.info("TopKap Bot started successfully — polling for updates...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
