"""
bot/main.py
===========
Main entry point for the TopKap Telegram Bot.

Architecture (v2 — FastAPI-first):
  FastAPI/uvicorn is the MAIN process (Railway sees HTTP server immediately).
  The Telegram Bot runs as an async background task inside FastAPI's lifespan.

  This fixes the Railway "Application not found" error caused by the bot
  blocking the main thread before FastAPI could bind to PORT.

Services:
  1. FastAPI HTTP server (uvicorn) — main process, binds to PORT immediately
     - GET /webapp/product-form  → Mini App HTML form
     - GET /api/attributes/{id}  → Proxy to KAYISOFT attributes API
     - GET /health               → Health check (Railway health probe)
  2. Telegram Bot (python-telegram-bot) — async background task via lifespan

Environment Variables Required:
    TELEGRAM_BOT_TOKEN      -- Telegram bot token from BotFather
    KAYISOFT_API_URL        -- KAYISOFT wholesale API base URL
    TELEGRAM_BOT_API_ENDPOINT_KEY -- KAYISOFT API bearer token

Environment Variables Optional:
    RAILWAY_DOMAIN          -- Public domain of this Railway service
                               (e.g. "hospitable-purpose.up.railway.app")
                               Required for WebApp Mini App to work.
    PORT                    -- HTTP port for FastAPI server (default: 8080)
"""
import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load environment variables from .env file (local dev only)
load_dotenv()

# Configure structured logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTIC — Print all critical env vars at startup
# ══════════════════════════════════════════════════════════════════════════════

def _log_diagnostics() -> str:
    """Logs all critical env vars and returns the resolved Railway domain."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    kayisoft_token = (
        os.getenv("KAYISOFT_API_TOKEN") or
        os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or
        ""
    )
    kayisoft_url = os.getenv("KAYISOFT_API_URL", "NOT SET")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")

    # Auto-detect Railway domain from multiple env vars
    _raw_static = os.getenv("RAILWAY_STATIC_URL", "")
    _static_domain = _raw_static.replace("https://", "").replace("http://", "").rstrip("/")
    railway_domain = (
        os.getenv("RAILWAY_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or _static_domain
        or "NOT SET"
    )
    webapp_port = os.getenv("PORT", "8080")

    logger.info("=" * 60)
    logger.info("DIAGNOSTIC -- Environment Variables at startup:")
    logger.info("  KAYISOFT_API_URL              = %s", kayisoft_url)
    logger.info("  KAYISOFT_API_TOKEN            = %s", kayisoft_token[:8] + "..." if kayisoft_token else "EMPTY !!!")
    logger.info("  TELEGRAM_BOT_API_ENDPOINT_KEY = %s", (os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or "NOT SET")[:8] + "...")
    logger.info("  DEEPSEEK_API_KEY              = %s", "SET" if deepseek_key else "NOT SET")
    logger.info("  BOT_TOKEN (first 8 chars)     = %s...", token[:8] if token else "MISSING!")
    logger.info("  RAILWAY_DOMAIN (manual)       = %s", os.getenv("RAILWAY_DOMAIN", "NOT SET"))
    logger.info("  RAILWAY_PUBLIC_DOMAIN (auto)  = %s", os.getenv("RAILWAY_PUBLIC_DOMAIN", "NOT SET"))
    logger.info("  RAILWAY_STATIC_URL (legacy)   = %s", os.getenv("RAILWAY_STATIC_URL", "NOT SET"))
    logger.info("  RAILWAY_DOMAIN (resolved)     = %s", railway_domain)
    logger.info("  PORT (FastAPI)                = %s", webapp_port)

    # Log ALL Railway-prefixed env vars for debugging
    railway_vars = {k: v for k, v in os.environ.items() if k.startswith("RAILWAY_")}
    if railway_vars:
        logger.info("  All RAILWAY_* env vars: %s", railway_vars)
    else:
        logger.warning("  No RAILWAY_* env vars found (not running on Railway or none injected)")

    if not kayisoft_token:
        logger.error("  *** KAYISOFT_API_TOKEN IS EMPTY -- all API calls will fail with 401 ***")

    if railway_domain == "NOT SET":
        logger.warning(
            "  *** RAILWAY_DOMAIN could not be auto-detected -- WebApp Mini App button will be disabled ***\n"
            "  Fix: In Railway Dashboard → your service → Variables, add:\n"
            "  RAILWAY_DOMAIN = <your-service>.up.railway.app\n"
            "  (Find your domain in Railway Dashboard → your service → Settings → Domains)"
        )
    else:
        logger.info("  ✅ WebApp Mini App URL will be: https://%s/webapp/product-form", railway_domain)

    logger.info("=" * 60)
    return railway_domain


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT — runs as async background task inside FastAPI lifespan
# ══════════════════════════════════════════════════════════════════════════════

_bot_task: asyncio.Task | None = None


async def _run_telegram_bot() -> None:
    """
    Runs the Telegram bot using python-telegram-bot's async polling.
    This function is started as an asyncio Task inside FastAPI's lifespan,
    so it runs concurrently with the FastAPI HTTP server.
    """
    from telegram.ext import ApplicationBuilder, ChatMemberHandler
    from bot.handlers.start_handler import register_start_handlers
    from bot.handlers.product_handler import get_product_conv_handler
    from bot.handlers.channel_handler import register_channel_handlers, handle_my_chat_member

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found — bot will not start.")
        return

    logger.info("TopKap Bot initializing (async mode)...")
    application = ApplicationBuilder().token(token).build()

    # IMPORTANT: ConversationHandler MUST be registered BEFORE start_handler
    application.add_handler(get_product_conv_handler())   # Product upload flow (FIRST)
    register_start_handlers(application)                  # /start + language selection
    register_channel_handlers(application)                # Channel management
    application.add_handler(                              # Detect bot added to channel
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    logger.info("TopKap Bot started successfully -- polling for updates...")

    # Share the application instance with FastAPI via a module-level variable
    # so that webapp_routes.py can call bot methods directly
    import bot.routes.webapp_routes as _wr
    _wr.set_bot_application(application)

    # Use async context manager for clean startup/shutdown
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("TopKap Bot polling active.")

        # Keep running until cancelled (FastAPI shutdown)
        try:
            await asyncio.Event().wait()  # Wait forever until cancelled
        except asyncio.CancelledError:
            logger.info("TopKap Bot shutting down...")
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            logger.info("TopKap Bot stopped cleanly.")


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI LIFESPAN — starts bot on startup, stops on shutdown
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan context manager.
    - On startup: log diagnostics, start Telegram bot as background task
    - On shutdown: cancel bot task gracefully
    """
    global _bot_task

    # Log diagnostics
    _log_diagnostics()

    # Start Telegram bot as background async task
    logger.info("Starting Telegram bot as background task...")
    _bot_task = asyncio.create_task(_run_telegram_bot(), name="telegram-bot")

    logger.info("FastAPI server ready. Bot running in background.")
    yield  # FastAPI serves requests here

    # Shutdown: cancel bot task
    if _bot_task and not _bot_task.done():
        logger.info("Cancelling Telegram bot task...")
        _bot_task.cancel()
        try:
            await asyncio.wait_for(_bot_task, timeout=10.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    logger.info("Shutdown complete.")


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP — main HTTP server
# ══════════════════════════════════════════════════════════════════════════════

def create_app():
    """Creates and configures the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from bot.routes.webapp_routes import router as webapp_router

    app = FastAPI(
        title="TopKap WebApp Server",
        description="Serves the Telegram Mini App product form for TopKap wholesale platform",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Register WebApp routes
    app.include_router(webapp_router)

    # Health check endpoint (Railway uses this to verify the service is alive)
    @app.get("/health", tags=["System"])
    async def health_check():
        bot_running = _bot_task is not None and not _bot_task.done()
        return JSONResponse({
            "status": "ok",
            "service": "TopKap WebApp",
            "bot_running": bot_running,
        })

    @app.get("/", tags=["System"])
    async def root():
        return JSONResponse({
            "service": "TopKap Wholesale Bot",
            "status": "running",
            "webapp": "/webapp/product-form",
            "health": "/health",
        })

    return app


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Main entry point.
    Starts uvicorn with the FastAPI app (which starts the bot via lifespan).
    FastAPI binds to PORT immediately so Railway sees a live HTTP server.
    """
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting TopKap server on port %d (FastAPI-first architecture)...", port)

    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == '__main__':
    main()
