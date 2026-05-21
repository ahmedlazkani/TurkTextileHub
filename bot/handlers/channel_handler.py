"""
bot/handlers/channel_handler.py
===============================
Handles channel connection and management.

FIX (2026-05-21): Persist channel_id to /data/user_channels.json so it
survives Railway restarts. bot_data is in-memory only and is lost on redeploy.
"""
import json
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from bot.services.language_service import get_string, get_user_lang, detect_lang
from bot.services.kayisoft_api import KayisoftAPI

logger = logging.getLogger(__name__)

# ── Persistent storage path ───────────────────────────────────────────────────
# Railway provides a writable /data volume (or falls back to /tmp if not mounted)
_CHANNELS_FILE = os.environ.get("CHANNELS_FILE", "/data/user_channels.json")


def _load_channels() -> dict:
    """Load persisted user→channel mapping from disk."""
    try:
        with open(_CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_channels(channels: dict) -> None:
    """Persist user→channel mapping to disk."""
    try:
        os.makedirs(os.path.dirname(_CHANNELS_FILE), exist_ok=True)
        with open(_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels, f, ensure_ascii=False, indent=2)
        logger.info("Saved user_channels to %s", _CHANNELS_FILE)
    except Exception as exc:
        logger.error("Failed to save user_channels: %s", exc)


def get_channel_id_for_user(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Return the channel_id for a given user_id.

    Lookup order:
      1. context.bot_data["user_channels"]  (in-memory, fast)
      2. Persistent JSON file               (survives Railway restarts)
    """
    # 1. In-memory cache
    channel_id = context.bot_data.get("user_channels", {}).get(user_id)
    if channel_id:
        return channel_id

    # 2. Disk fallback
    channels = _load_channels()
    channel_id = channels.get(user_id)
    if channel_id:
        # Warm the in-memory cache so subsequent calls are fast
        if "user_channels" not in context.bot_data:
            context.bot_data["user_channels"] = {}
        context.bot_data["user_channels"][user_id] = channel_id
        logger.info(
            "Loaded channel_id=%s for user_id=%s from disk (cache warmed)",
            channel_id, user_id
        )
    return channel_id


async def start_channel_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instructs the user to add the bot to their channel as an admin."""
    user = update.effective_user
    user_id = str(user.id)
    # Resolve language: prefer saved lang, fallback to Telegram language_code
    lang = get_user_lang(user_id)
    if lang == "tr" and user.language_code:
        detected = detect_lang(user.language_code)
        if detected != "tr":
            lang = detected
    
    await update.message.reply_text(
        get_string(lang, "channel_add_admin"),
        parse_mode="HTML"
    )

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
        # Use language_code from Telegram directly (more reliable than in-memory cache)
        lang = get_user_lang(user_id)
        if lang == "tr" and user.language_code:
            detected = detect_lang(user.language_code)
            if detected != "tr":
                lang = detected
        logger.info("Channel handler: user_id=%s lang=%s language_code=%s", user_id, lang, user.language_code)
        
        channel_id = str(chat.id)
        channel_title = chat.title
        
        logger.info(
            "Bot added to channel: title=%s | channel_id=%s | by user_id=%s",
            channel_title, channel_id, user_id
        )
        
        # Register channel with KAYISOFT API
        api = KayisoftAPI(telegram_user_id=user_id, language=lang)
        logger.info(
            "Calling create_channel: channel_id=%s | channel_name=%s | telegram_user_id=%s | token=%s...",
            channel_id, channel_title, user_id,
            api.token[:8] if api.token else 'EMPTY'
        )
        response = await api.create_channel(channel_id=channel_id, channel_name=channel_title)
        logger.info("create_channel response: %s", response)
        
        try:
            if response is not None:
                # ── 1. Save to in-memory bot_data (fast, lost on restart) ─────
                if "user_channels" not in context.bot_data:
                    context.bot_data["user_channels"] = {}
                context.bot_data["user_channels"][user_id] = channel_id
                logger.info(
                    "Saved channel_id=%s for user_id=%s in bot_data (memory)",
                    channel_id, user_id
                )

                # ── 2. Persist to disk (survives Railway restarts) ────────────
                channels = _load_channels()
                channels[user_id] = channel_id
                _save_channels(channels)

                # Use {channel_name} placeholder from locale string
                success_text = get_string(lang, "channel_connected").replace(
                    "{channel_name}", channel_title
                )
                await context.bot.send_message(
                    chat_id=user.id,
                    text=success_text,
                    parse_mode="HTML"
                )
            else:
                logger.error(
                    "create_channel FAILED for user_id=%s channel_id=%s",
                    user_id, channel_id
                )
                error_text = get_string(lang, "channel_error")
                await context.bot.send_message(
                    chat_id=user.id,
                    text=error_text,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Could not send confirmation to user {user_id}: {e}")

def register_channel_handlers(application) -> None:
    application.add_handler(MessageHandler(filters.Regex(r'^(🔗 Kanal Yönetimi|🔗 Channel Management|🔗 إدارة القناة)$'), start_channel_connection))
    application.add_handler(CommandHandler('channel', start_channel_connection))
