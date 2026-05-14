"""
bot/handlers/channel_handler.py
===============================
Handles channel connection and management.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from bot.services.language_service import get_string
from bot.services.session_manager import get_user_lang
from bot.services.kayisoft_api import KayisoftAPI

logger = logging.getLogger(__name__)

async def start_channel_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instructs the user to add the bot to their channel as an admin."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    await update.message.reply_text(get_string(lang, "channel_add_admin"))

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Triggered when the bot's status in a chat changes.
    Used to detect when the bot is added to a channel as an admin.
    """
    result = update.my_chat_member
    if not result:
        return
        
    chat = result.chat
    new_status = result.new_chat_member.status
    
    # Check if it's a channel and the bot was made an administrator
    if chat.type == "channel" and new_status == "administrator":
        # The user who added the bot
        user = result.from_user
        user_id = str(user.id)
        lang = get_user_lang(user_id) or "tr"
        
        channel_id = str(chat.id)
        channel_title = chat.title
        
        logger.info(f"Bot added to channel {channel_title} ({channel_id}) by user {user_id}")
        
        # Register channel with KAYISOFT API
        api = KayisoftAPI(telegram_user_id=user_id, language=lang)
        response = await api.create_channel(channel_id=channel_id, channel_name=channel_title)
        
        try:
            if response is not None:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=get_string(lang, "channel_connected") + f"\nKanal: {channel_title}"
                )
            else:
                await context.bot.send_message(
                    chat_id=user.id,
                    text="Kanal kaydedilirken bir hata oluştu. Lütfen hesabınızı bağladığınızdan emin olun."
                )
        except Exception as e:
            logger.error(f"Could not send confirmation to user {user_id}: {e}")

def register_channel_handlers(application) -> None:
    application.add_handler(MessageHandler(filters.Regex(r'^(🔗 Kanal Yönetimi|🔗 Channel Management|🔗 إدارة القناة)$'), start_channel_connection))
    application.add_handler(CommandHandler('channel', start_channel_connection))
