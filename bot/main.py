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
import re
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
class _SecretRedactionFilter(logging.Filter):
    """Redact credential-shaped strings before any handler writes a log record."""

    _telegram_token = re.compile(r"(?:bot)?\d{6,12}:[A-Za-z0-9_-]{20,}")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._telegram_token.sub("<redacted-telegram-token>", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_SecretRedactionFilter())

# PTB uses httpx internally.  Its INFO lines include full request URLs, which
# contain the Telegram bot token for getUpdates/sendMessage endpoints.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTIC — safe startup readiness summary
# ══════════════════════════════════════════════════════════════════════════════

def _validate_production_configuration() -> None:
    """Fail fast only for an explicitly configured production deployment."""
    if os.getenv("APP_ENV", "development").strip().lower() != "production":
        return

    required = {
        "PUBLIC_BASE_URL": bool(os.getenv("PUBLIC_BASE_URL")),
        "TELEGRAM_BOT_TOKEN": bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")),
        "KAYISOFT_API_URL": bool(os.getenv("KAYISOFT_API_URL")),
        "KAYISOFT_API_TOKEN": bool(
            os.getenv("KAYISOFT_API_TOKEN") or os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY")
        ),
        "AI_PROVIDER_KEY": bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "CHANNELS_FILE": bool(os.getenv("CHANNELS_FILE")),
        "LANGS_FILE": bool(os.getenv("LANGS_FILE")),
    }
    missing = [name for name, configured in required.items() if not configured]
    if missing:
        raise RuntimeError(
            "Production configuration is incomplete. Missing environment variables: "
            + ", ".join(missing)
        )


def _log_diagnostics() -> str:
    """Log configuration readiness without exposing values or platform internals."""
    from bot.services.runtime_config import get_public_base_url

    token_present = bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN"))
    kayisoft_token_present = bool(
        os.getenv("KAYISOFT_API_TOKEN") or os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY")
    )
    public_base_url = get_public_base_url()

    logger.info("TopKap startup configuration: bot_token=%s kayisoft_token=%s deepseek=%s public_url=%s port=%s",
                "configured" if token_present else "missing",
                "configured" if kayisoft_token_present else "missing",
                "configured" if os.getenv("DEEPSEEK_API_KEY") else "not-configured",
                "configured" if public_base_url else "missing",
                os.getenv("PORT", "8080"))
    if not kayisoft_token_present:
        logger.error("KAYISOFT API credential is missing; API calls will fail.")
    if not public_base_url:
        logger.warning("PUBLIC_BASE_URL is not configured; Telegram WebApp buttons will be unavailable.")
    return public_base_url


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
    import datetime
    from telegram.ext import ApplicationBuilder, ChatMemberHandler, CommandHandler
    from bot.handlers.start_handler import register_start_handlers
    from bot.handlers.product_handler import get_product_conv_handler
    from bot.handlers.channel_handler import register_channel_handlers, handle_my_chat_member
    from bot.handlers.channel_stats import send_weekly_stats_to_all_suppliers, handle_mystats

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found — bot will not start.")
        return

    logger.info("TopKap Bot initializing (async mode)...")
    # Standard ApplicationBuilder without job_queue to avoid APScheduler blocking issues
    application = ApplicationBuilder().token(token).build()

    # IMPORTANT: ConversationHandler MUST be registered BEFORE start_handler
    application.add_handler(get_product_conv_handler())   # Product upload flow (FIRST)
    register_start_handlers(application)                  # /start + language selection
    register_channel_handlers(application)                # Channel management
    application.add_handler(                              # Detect bot added to channel
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    # /mystats command — on-demand weekly stats for the supplier
    application.add_handler(CommandHandler("mystats", handle_mystats))

    logger.info("TopKap Bot started successfully -- polling for updates...")

    # Share the application instance with FastAPI via a module-level variable
    # so that webapp_routes.py and orders_handler.py can call bot methods directly
    import bot.routes.webapp_routes as _wr
    _wr.set_bot_application(application)

    # Register bot application with orders notification handler
    import bot.handlers.orders_handler as _oh
    _oh.set_bot_application(application)

    # Use async context manager for clean startup/shutdown
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("TopKap Bot polling active.")

        # ── Weekly stats asyncio loop ─────────────────────────────────────────
        # Programmatic note:
        #   We use a pure asyncio loop instead of APScheduler to avoid
        #   dependency issues. The loop wakes up every hour, checks if
        #   it's Monday 09:00 UTC, and sends the weekly report once per week.
        #   A sentinel file /data/.last_weekly_stats prevents double-sending.
        async def _weekly_stats_loop():
            import datetime
            sentinel_path = "/data/.last_weekly_stats"
            while True:
                try:
                    await asyncio.sleep(3600)  # Check every hour
                    now = datetime.datetime.now(datetime.timezone.utc)
                    # Monday = 0, hour = 9
                    if now.weekday() == 0 and now.hour == 9:
                        today_str = now.strftime("%Y-%m-%d")
                        # Check sentinel to avoid double-sending
                        last_sent = ""
                        try:
                            with open(sentinel_path) as _f:
                                last_sent = _f.read().strip()
                        except FileNotFoundError:
                            pass
                        if last_sent != today_str:
                            logger.info("📈 Sending weekly stats report...")
                            await send_weekly_stats_to_all_suppliers(application.bot)
                            with open(sentinel_path, "w") as _f:
                                _f.write(today_str)
                            logger.info("✅ Weekly stats report sent for %s", today_str)
                except asyncio.CancelledError:
                    break
                except Exception as _e:
                    logger.warning("⚠️ Weekly stats loop error: %s", _e)

        _weekly_task = asyncio.create_task(_weekly_stats_loop(), name="weekly-stats")
        logger.info("✅ Weekly stats loop started (checks every hour, sends on Monday 09:00 UTC)")

        # Keep running until cancelled (FastAPI shutdown)
        try:
            await asyncio.Event().wait()  # Wait forever until cancelled
        except asyncio.CancelledError:
            logger.info("TopKap Bot shutting down...")
        finally:
            _weekly_task.cancel()
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

    # Validate before starting either the HTTP server or Telegram polling.
    _validate_production_configuration()
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
    from bot.handlers.orders_handler import router as orders_router

    app = FastAPI(
        title="TopKap WebApp Server",
        description="Serves the Telegram Mini App product form for TopKap wholesale platform",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Register WebApp routes
    app.include_router(webapp_router)

    # Register Orders Webhook routes (POST /webhook/orders)
    app.include_router(orders_router)

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
