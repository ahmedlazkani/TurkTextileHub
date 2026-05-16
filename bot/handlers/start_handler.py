"""
bot/handlers/start_handler.py
=============================
Handles the /start command, language selection, and account connection.
"""
import logging
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.services.language_service import get_string, detect_lang, get_user_lang, set_user_lang
from bot.keyboards import language_keyboard, supplier_main_keyboard
from bot.services.kayisoft_api import KayisoftAPI

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Entry point for the bot.
    Handles:
    1. Direct start (/start) -> Shows language selection.
    2. Deep link start (/start TOKEN) -> Connects account.
    """
    user = update.effective_user
    telegram_id = str(user.id)
    
    # Check if there's a deep link token (e.g., /start abc123token)
    args = context.args
    if args and len(args) > 0:
        token = args[0]
        await handle_account_connection(update, context, telegram_id, token)
        return

    # Normal start: Ask for language
    lang = get_user_lang(telegram_id) or detect_lang(user.language_code)
    set_user_lang(telegram_id, lang)
    
    welcome_text = get_string(lang, "welcome_message")
    await update.message.reply_text(
        welcome_text,
        reply_markup=language_keyboard(),
        parse_mode=ParseMode.HTML,
    )

async def handle_account_connection(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: str, token: str) -> None:
    """
    Handles the account connection flow using the token from the deep link.
    """
    lang = get_user_lang(telegram_id) or "tr"
    user_name = update.effective_user.username or update.effective_user.first_name
    
    api = KayisoftAPI(telegram_user_id=telegram_id, language=lang)
    response = await api.connect_account(deep_link_token=token, telegram_user_name=user_name)
    
    if response is not None:
        await update.message.reply_text(
            get_string(lang, "connect_success"),
            reply_markup=supplier_main_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            get_string(lang, "connect_error"),
            parse_mode=ParseMode.HTML,
        )

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles language selection from the inline keyboard.
    """
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(query.from_user.id)
    data = query.data
    
    if data == "set_lang_tr":
        lang = "tr"
    elif data == "set_lang_ar":
        lang = "ar"
    else:
        lang = "en"
        
    set_user_lang(telegram_id, lang)
    
    # Show main menu after language selection
    await query.message.reply_text(
        get_string(lang, "main_menu_supplier"),
        reply_markup=supplier_main_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )

async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Routes supplier main menu button presses to the correct action.
    Matches button text across all 3 languages (tr/ar/en).
    """
    telegram_id = str(update.effective_user.id)
    lang = get_user_lang(telegram_id) or "tr"
    text = update.message.text

    # Build a text → action map for all 3 languages
    btn_map = {}
    for _lang in ["tr", "ar", "en"]:
        btn_map[get_string(_lang, "btn_add_product")]    = "add_product"
        btn_map[get_string(_lang, "btn_my_products")]   = "my_products"
        btn_map[get_string(_lang, "btn_statistics")]    = "statistics"
        btn_map[get_string(_lang, "btn_manage_channel")] = "channel"
        btn_map[get_string(_lang, "btn_settings")]      = "settings"
        btn_map[get_string(_lang, "btn_subscription")]  = "subscription"

    action = btn_map.get(text)

    if action == "add_product":
        from bot.handlers.product_handler import start_add_product
        await start_add_product(update, context)

    elif action == "my_products":
        await update.message.reply_text(
            "📦 <b>" + get_string(lang, "btn_my_products") + "</b>\n\n🔜 Yakında aktif olacak.",
            parse_mode=ParseMode.HTML,
        )

    elif action == "statistics":
        await update.message.reply_text(
            "📊 <b>" + get_string(lang, "btn_statistics") + "</b>\n\n🔜 Yakında aktif olacak.",
            parse_mode=ParseMode.HTML,
        )

    elif action == "channel":
        from bot.handlers.channel_handler import start_channel_connection
        await start_channel_connection(update, context)

    elif action == "settings":
        await update.message.reply_text(
            "⚙️ <b>" + get_string(lang, "btn_settings") + "</b>\n\n" + get_string(lang, "btn_language"),
            reply_markup=language_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "subscription":
        await update.message.reply_text(
            "💎 <b>" + get_string(lang, "btn_subscription") + "</b>\n\n🔜 Yakında aktif olacak.",
            parse_mode=ParseMode.HTML,
        )

    else:
        # Fallback: show main menu
        await update.message.reply_text(
            get_string(lang, "main_menu_supplier"),
            reply_markup=supplier_main_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )


def register_start_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_"))

    # Build regex pattern for all menu button texts (all 3 languages)
    menu_buttons = []
    for _lang in ["tr", "ar", "en"]:
        for key in ["btn_add_product", "btn_my_products", "btn_statistics",
                    "btn_manage_channel", "btn_settings", "btn_subscription"]:
            menu_buttons.append(get_string(_lang, key))

    pattern = "^(" + "|".join(re.escape(b) for b in menu_buttons) + ")$"
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(pattern), handle_menu_button)
    )
