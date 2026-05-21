"""
bot/main.py
===========
Main entry point for the TopKap Telegram Bot.

Runs two services concurrently in the same process:
  1. Telegram Bot (python-telegram-bot polling)
  2. FastAPI HTTP server (uvicorn) -- serves the WebApp Mini App form

Environment Variables Required:
    TELEGRAM_BOT_TOKEN      -- Telegram bot token from BotFather
    KAYISOFT_API_URL        -- KAYISOFT wholesale API base URL
    TELEGRAM_BOT_API_ENDPOINT_KEY -- KAYISOFT API bearer token
    DEEPSEEK_API_KEY        -- DeepSeek AI API key

Environment Variables Optional:
    RAILWAY_DOMAIN          -- Public domain of this Railway service
                               (e.g. "topkap.up.railway.app")
                               Required for WebApp Mini App to work.
    PORT                    -- HTTP port for FastAPI server (default: 8080)
"""
import os
import logging
import threading
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


def _start_fastapi_server() -> None:
    """
    Starts the FastAPI/uvicorn HTTP server in a background daemon thread.

    Serves:
      - GET /webapp/product-form  -> Mini App HTML form
      - GET /api/attributes/{id}  -> Proxy to KAYISOFT attributes API
      - GET /health               -> Health check endpoint
    """
    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from bot.routes.webapp_routes import router as webapp_router

        app = FastAPI(
            title="TopKap WebApp Server",
            description="Serves the Telegram Mini App product form",
            version="1.0.0",
        )

        # Register WebApp routes
        app.include_router(webapp_router)

        # Health check endpoint
        @app.get("/health", tags=["System"])
        async def health_check():
            return JSONResponse({"status": "ok", "service": "TopKap WebApp"})

        port = int(os.getenv("PORT", "8080"))
        logger.info("Starting FastAPI server on port %d ...", port)

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True,
        )
    except ImportError as exc:
        logger.warning(
            "FastAPI/uvicorn not available -- WebApp Mini App will be disabled. "
            "Install with: pip install fastapi uvicorn httpx\n%s", exc
        )
    except Exception as exc:
        logger.error("FastAPI server crashed: %s", exc, exc_info=True)


def main():
    # Support both TELEGRAM_BOT_TOKEN (Railway) and BOT_TOKEN (legacy .env)
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        logger.error("ERROR -- TELEGRAM_BOT_TOKEN not found in environment variables.")
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot.")

    # ── DIAGNOSTIC: print all critical env vars at startup ──────────────────
    kayisoft_token = (
        os.getenv("KAYISOFT_API_TOKEN") or
        os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or
        ""
    )
    kayisoft_url   = os.getenv("KAYISOFT_API_URL", "NOT SET")
    deepseek_key   = os.getenv("DEEPSEEK_API_KEY", "")
    railway_domain = os.getenv("RAILWAY_DOMAIN", "NOT SET")
    webapp_port    = os.getenv("PORT", "8080")

    logger.info("=" * 60)
    logger.info("DIAGNOSTIC -- Environment Variables at startup:")
    logger.info("  KAYISOFT_API_URL              = %s", kayisoft_url)
    logger.info("  KAYISOFT_API_TOKEN            = %s", kayisoft_token[:8] + "..." if kayisoft_token else "EMPTY !!!")
    logger.info("  TELEGRAM_BOT_API_ENDPOINT_KEY = %s", (os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or "NOT SET")[:8] + "...")
    logger.info("  DEEPSEEK_API_KEY              = %s", "SET" if deepseek_key else "NOT SET")
    logger.info("  BOT_TOKEN (first 8 chars)     = %s...", token[:8])
    logger.info("  RAILWAY_DOMAIN                = %s", railway_domain)
    logger.info("  PORT (FastAPI)                = %s", webapp_port)
    if not kayisoft_token:
        logger.error("  *** KAYISOFT_API_TOKEN IS EMPTY -- all API calls will fail with 401 ***")
    if railway_domain == "NOT SET":
        logger.warning(
            "  *** RAILWAY_DOMAIN not set -- WebApp Mini App button will be disabled ***\n"
            "  Set RAILWAY_DOMAIN=<your-service>.up.railway.app in Railway environment variables."
        )
    logger.info("=" * 60)
    # ── END DIAGNOSTIC ───────────────────────────────────────────────────────

    # ── Start FastAPI server in background thread ──────────────────────────
    fastapi_thread = threading.Thread(
        target=_start_fastapi_server,
        daemon=True,
        name="fastapi-webapp-server",
    )
    fastapi_thread.start()
    logger.info("FastAPI WebApp server thread started.")

    # ── Build Telegram bot application ────────────────────────────────────
    logger.info("TopKap Bot initializing...")
    application = ApplicationBuilder().token(token).build()

    # ── Register all handlers ──────────────────────────────────────────────
    # IMPORTANT: ConversationHandler MUST be registered BEFORE start_handler
    # so it intercepts "add product" button before handle_menu_button
    application.add_handler(get_product_conv_handler())  # Product upload flow (FIRST)
    register_start_handlers(application)                 # /start + language selection
    register_channel_handlers(application)               # Channel management
    application.add_handler(                             # Detect bot added to channel
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    logger.info("TopKap Bot started successfully -- polling for updates...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
