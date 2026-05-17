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

    # ── DIAGNOSTIC: print all critical env vars at startup ──────────────────
    kayisoft_token = (
        os.getenv("KAYISOFT_API_TOKEN") or
        os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or
        ""
    )
    kayisoft_url = os.getenv("KAYISOFT_API_URL", "NOT SET")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")

    logger.info("=" * 60)
    logger.info("DIAGNOSTIC — Environment Variables at startup:")
    logger.info("  KAYISOFT_API_URL            = %s", kayisoft_url)
    logger.info("  KAYISOFT_API_TOKEN          = %s", kayisoft_token[:8] + "..." if kayisoft_token else "EMPTY !!!")
    logger.info("  TELEGRAM_BOT_API_ENDPOINT_KEY = %s", (os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or "NOT SET")[:8] + "...")
    logger.info("  DEEPSEEK_API_KEY            = %s", "SET" if deepseek_key else "NOT SET")
    logger.info("  BOT_TOKEN (first 8 chars)   = %s...", token[:8])
    if not kayisoft_token:
        logger.error("  *** KAYISOFT_API_TOKEN IS EMPTY — all API calls will fail with 401 ***")
    logger.info("=" * 60)
    # ── END DIAGNOSTIC ───────────────────────────────────────────────────────

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
