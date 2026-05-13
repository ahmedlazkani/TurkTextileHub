"""
bot/main.py
===========
Bot Entry Point & Handler Registration
========================================

Purpose:
    Initialises the Telegram Application, registers every
    ConversationHandler and standalone handler in the correct priority
    order, and starts the polling loop.

Handler Registration Order (important — PTB matches top-to-bottom):
    1. /start command
    2. Supplier registration ConversationHandler
    3. Trader registration ConversationHandler
    4. Product addition ConversationHandler  (KAYISOFT API flow)
    5. Product browsing + RFQ ConversationHandler
    6. Channel connection ConversationHandler
    7. Standalone channel handlers (post-connect actions)
    8. Stock / Order / Stats handlers
    9. Language & dashboard callback handlers
    10. Channel post listener (channel messages → product extraction)
    11. Global error handler

Environment Variables Required:
    BOT_TOKEN          — Telegram Bot token from @BotFather
    KAYISOFT_API_KEY   — Static API key provided by KAYISOFT team
    KAYISOFT_BASE_URL  — KAYISOFT backend base URL (staging or production)
    SUPABASE_URL       — Supabase project URL (fallback database)
    SUPABASE_KEY       — Supabase anon/service key
    AI_PROVIDER        — "deepseek" | "gemini" | "openai"  (default: gemini)
    AI_API_KEY         — API key for the chosen AI provider

Apps:
    TopKap  — Supplier-facing mobile app  (https://topkap.app)
    TopGate — Buyer-facing mobile app     (https://topgate.app)

Author:
    TurkTextileHub Engineering Team
"""

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import states
from bot.config import BOT_TOKEN
from bot.handlers import (
    browse_handler,
    channel_handler,
    channel_post_handler,
    order_handler,
    product_handler,
    start_handler,
    stats_handler,
    stock_handler,
    supplier_handler,
    trader_handler,
)
from bot.services import kayisoft_api

# ──────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# ERROR HANDLER
# ──────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler.

    Silently ignores stale callback queries ("Query is too old") and
    logs all other exceptions with full traceback for debugging.
    """
    error = context.error

    if isinstance(error, BadRequest) and "Query is too old" in str(error):
        logger.debug("Ignored stale callback query (Query is too old).")
        return

    logger.error(
        "Unhandled exception while processing update.",
        exc_info=context.error,
    )


# ──────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────

def main() -> None:
    """
    Build the Application, register all handlers, and start polling.

    This function is the single entry point for the bot process.
    It should only be called once (guarded by __name__ == "__main__").
    """
    logger.info("🚀 Starting TurkTextileHub bot…")

    # ── Startup health-check ──────────────────────────────
    if kayisoft_api.health_check():
        logger.info("✅ KAYISOFT API reachable — full integration mode.")
    else:
        logger.warning(
            "⚠️  KAYISOFT API unreachable — running in Supabase-only fallback mode."
        )

    # ── Build Application ─────────────────────────────────
    application = Application.builder().token(BOT_TOKEN).build()

    # ══════════════════════════════════════════════════════
    # 1. SUPPLIER REGISTRATION
    #    Flow: company_name → contact_name → city → phone
    #          → sales_rep → [sales_rep_username]
    # ══════════════════════════════════════════════════════
    supplier_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                supplier_handler.start_registration,
                pattern="^supplier$",
            )
        ],
        states={
            states.COMPANY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_company_name,
                )
            ],
            states.CONTACT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_contact_name,
                )
            ],
            states.SUPPLIER_CITY: [
                CallbackQueryHandler(
                    supplier_handler.received_city,
                    pattern="^city_(istanbul|bursa|izmir|other)$",
                )
            ],
            states.PHONE_NUMBER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_phone,
                )
            ],
            states.SALES_REP: [
                CallbackQueryHandler(
                    supplier_handler.received_sales_rep_answer,
                    pattern="^sales_rep_(yes|no)$",
                )
            ],
            states.SALES_REP_USERNAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_sales_rep_username,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", supplier_handler.cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ══════════════════════════════════════════════════════
    # 2. TRADER REGISTRATION
    #    Flow: full_name → phone → country → business_type
    # ══════════════════════════════════════════════════════
    trader_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                trader_handler.start_trader_registration,
                pattern="^trader$",
            )
        ],
        states={
            states.TRADER_FULL_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_name,
                )
            ],
            states.TRADER_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_phone,
                )
            ],
            states.TRADER_COUNTRY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_country,
                )
            ],
            states.TRADER_BUSINESS_TYPE: [
                CallbackQueryHandler(
                    trader_handler.received_trader_business_type,
                    pattern="^business_(online|physical|distributor|other)$",
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", trader_handler.cancel_trader)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ══════════════════════════════════════════════════════
    # 3. PRODUCT ADDITION  (KAYISOFT API flow)
    #    Flow: /add_product
    #          → main_category → [sub_category]
    #          → attributes (form, field by field)
    #          → images (per variant)
    #          → confirm → publish to KAYISOFT + channel
    #
    #    Deep links published in channel post:
    #      TopKap  : https://topkap.app/product/{id}
    #      TopGate : https://topgate.app/product/{id}
    # ══════════════════════════════════════════════════════
    product_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_product", product_handler.start_add_product),
            CallbackQueryHandler(
                product_handler.start_add_product_from_button,
                pattern="^post_reg_add_product$",
            ),
            # Reply Keyboard shortcut
            MessageHandler(
                filters.Regex(r"^(➕ Add Product|➕ إضافة منتج|➕ Ürün Ekle)$"),
                product_handler.start_add_product,
            ),
        ],
        states={
            # ── Step 1: Root category selection ──────────
            states.GETTING_MAIN_CATEGORY: [
                CallbackQueryHandler(
                    product_handler.get_main_category,
                    pattern="^kcat_main_",
                ),
            ],
            # ── Step 2: Sub-category selection ───────────
            states.GETTING_SUB_CATEGORY: [
                CallbackQueryHandler(
                    product_handler.get_sub_category,
                    pattern="^kcat_sub_",
                ),
                CallbackQueryHandler(
                    product_handler.skip_sub_category,
                    pattern="^kcat_no_sub$",
                ),
            ],
            # ── Step 3: Attribute form (one field/message) ─
            states.GETTING_ATTRIBUTES: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    product_handler.get_attribute_value,
                ),
                CallbackQueryHandler(
                    product_handler.skip_attribute,
                    pattern="^attr_skip$",
                ),
                CallbackQueryHandler(
                    product_handler.select_attribute_option,
                    pattern="^attr_opt_",
                ),
            ],
            # ── Step 4: Images (per variant or general) ──
            states.GETTING_IMAGES: [
                MessageHandler(filters.PHOTO, product_handler.get_product_image),
                CallbackQueryHandler(
                    product_handler.finish_images,
                    pattern="^images_done$",
                ),
            ],
            # ── Step 5: Minimum order quantity ───────────
            states.GETTING_MIN_QUANTITY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    product_handler.get_min_quantity,
                ),
                CallbackQueryHandler(
                    product_handler.skip_min_quantity,
                    pattern="^moq_skip$",
                ),
            ],
            # ── Step 6: Final confirmation ────────────────
            states.CONFIRM_KAYISOFT_PRODUCT: [
                CallbackQueryHandler(
                    product_handler.confirm_and_publish,
                    pattern="^product_confirm_yes$",
                ),
                CallbackQueryHandler(
                    product_handler.edit_product_before_publish,
                    pattern="^product_edit$",
                ),
                CallbackQueryHandler(
                    product_handler.cancel_add_product,
                    pattern="^product_confirm_no$",
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", product_handler.cancel_add_product)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ══════════════════════════════════════════════════════
    # 4. PRODUCT BROWSING + RFQ
    # ══════════════════════════════════════════════════════
    browse_conv = browse_handler.get_rfq_conversation_handler()

    # ══════════════════════════════════════════════════════
    # 5. CHANNEL CONNECTION
    # ══════════════════════════════════════════════════════
    channel_conv = channel_handler.get_channel_conversation_handler()

    # ══════════════════════════════════════════════════════
    # REGISTER ALL HANDLERS
    # ══════════════════════════════════════════════════════

    # /start — must be first
    application.add_handler(CommandHandler("start", start_handler.start))

    # Registration flows
    application.add_handler(supplier_conv)
    application.add_handler(trader_conv)

    # Product & browsing flows
    application.add_handler(product_conv)
    application.add_handler(browse_conv)

    # Channel flow
    application.add_handler(channel_conv)
    channel_handler.register_channel_standalone_handlers(application)

    # ── Operational handlers ──────────────────────────────
    stock_handler.register_stock_handlers(application)
    order_handler.register_order_handlers(application)
    stats_handler.register_stats_handlers(application)

    # ── Reply Keyboard text routing ───────────────────────
    # Routes text from the persistent bottom-bar keyboard to the
    # appropriate handler without requiring slash commands.
    application.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(📦 My Products|📦 منتجاتي|📦 Ürünlerim)$"
            ),
            stats_handler.show_my_products,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(📊 Statistics|📊 إحصائياتي|📊 İstatistikler)$"
            ),
            stats_handler.show_stats,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(🔗 Manage Channel|🔗 إدارة القناة|🔗 Kanal Yönetimi)$"
            ),
            channel_handler.manage_channel_menu,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(🔍 Browse Products|🔍 تصفح المنتجات|🔍 Ürünlere Göz At)$"
            ),
            browse_handler.start_browse,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(📲 Open TopGate App|📲 فتح تطبيق TopGate|📲 TopGate Uygulamasını Aç)$"
            ),
            start_handler.open_topgate,
        )
    )

    # ── Language & dashboard callbacks ────────────────────
    application.add_handler(
        CallbackQueryHandler(start_handler.change_language, pattern="^change_language$")
    )
    application.add_handler(
        CallbackQueryHandler(
            start_handler.set_language,
            pattern="^set_lang_(ar|tr|en)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.show_my_channels, pattern="^my_channels$")
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.back_to_dashboard, pattern="^back_to_dashboard$")
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.supplier_reapply, pattern="^supplier_reapply$")
    )
    application.add_handler(
        CallbackQueryHandler(
            start_handler.supplier_contact_admin,
            pattern="^supplier_contact_admin$",
        )
    )

    # Connect channel button (from stats / dashboard)
    if hasattr(channel_handler, "start_connect_channel_from_button"):
        application.add_handler(
            CallbackQueryHandler(
                channel_handler.start_connect_channel_from_button,
                pattern="^connect_channel_btn$",
            )
        )

    # ── Channel post listener ─────────────────────────────
    # Listens to posts published in connected supplier channels.
    # Passes them to the AI extraction pipeline → KAYISOFT API.
    application.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL
            & (
                filters.PHOTO
                | filters.VIDEO
                | filters.Document.IMAGE
                | filters.TEXT
            ),
            channel_post_handler.handle_channel_post,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_post_handler.handle_post_approval,
            pattern="^approve_post_",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_post_handler.handle_post_rejection,
            pattern="^reject_post_",
        )
    )

    post_edit_conv = channel_post_handler.get_post_edit_conversation_handler()
    application.add_handler(post_edit_conv)

    # ── Global error handler ──────────────────────────────
    application.add_error_handler(error_handler)

    # ══════════════════════════════════════════════════════
    # START POLLING
    # ══════════════════════════════════════════════════════
    logger.info("✅ All handlers registered. Bot is now polling…")
    application.run_polling(
        allowed_updates=["message", "channel_post", "callback_query", "inline_query"],
        drop_pending_updates=True,
        close_loop=False,
    )


# ──────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
