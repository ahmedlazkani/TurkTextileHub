"""
bot/handlers/start_handler.py
=============================
Handles the /start command, language selection, and account connection.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from bot.services.language_service import get_string, detect_lang
from bot.services.session_manager import get_user_lang, set_user_lang
from bot.keyboards import language_keyboard, supplier_main_keyboard, trader_main_keyboard

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
        reply_markup=language_keyboard()
    )

async def handle_account_connection(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: str, token: str) -> None:
    """
    Handles the account connection flow using the token from the deep link.
    """
    lang = get_user_lang(telegram_id) or "tr"
    # TODO: Call KAYISOFT API to connect account using the token
    # For now, we mock the success
    success = True
    
    if success:
        await update.message.reply_text(
            get_string(lang, "connect_success"),
            reply_markup=supplier_main_keyboard(lang)
        )
    else:
        await update.message.reply_text(get_string(lang, "connect_error"))

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
    # Assuming supplier for now, logic can be expanded based on user role
    await query.message.reply_text(
        get_string(lang, "main_menu_supplier"),
        reply_markup=supplier_main_keyboard(lang)
    )

def register_start_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_"))
