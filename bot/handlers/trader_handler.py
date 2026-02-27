# ===================================================
# bot/handlers/trader_handler.py
# معالج محادثة متعدد الخطوات لتسجيل التجار
# المرحلة السادسة: تغيير product_interest إلى business_type
# التدفق: الاسم ← الهاتف ← الدولة ← نوع النشاط التجاري
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service, notification_service
from bot.services.language_service import get_string, detect_lang

logger = logging.getLogger(__name__)


def _build_business_type_keyboard(lang: str) -> InlineKeyboardMarkup:
    """يبني لوحة مفاتيح اختيار نوع النشاط التجاري."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "business_online"), callback_data="business_online")],
        [InlineKeyboardButton(text=get_string(lang, "business_physical"), callback_data="business_physical")],
        [InlineKeyboardButton(text=get_string(lang, "business_distributor"), callback_data="business_distributor")],
        [InlineKeyboardButton(text=get_string(lang, "business_other"), callback_data="business_other")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_trader_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تسجيل التاجر عند الضغط على زر 'تسجيل كتاجر'.

    يتحقق من التسجيل المسبق قبل البدء.

    المُخرجات:
        int: states.TRADER_FULL_NAME أو ConversationHandler.END
    """
    query = update.callback_query

    lang = detect_lang(query.from_user.language_code or "")
    context.user_data["lang"] = lang

    await query.answer()

    telegram_id = str(query.from_user.id)

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    if database_service.check_trader_exists(telegram_id):
        await query.edit_message_text(text=get_string(lang, "already_registered"))
        return ConversationHandler.END

    await query.edit_message_text(text=get_string(lang, "trader_welcome"))
    await query.message.reply_text(text=get_string(lang, "ask_trader_name"))

    return states.TRADER_FULL_NAME


async def received_trader_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الاسم الكامل ويتحقق من صحته.

    المُخرجات:
        int: states.TRADER_PHONE أو نفس الحالة إذا كان الاسم غير صالح
    """
    lang = context.user_data.get("lang", "ar")

    full_name = update.message.text.strip()

    if len(full_name) < 2:
        await update.message.reply_text(text=get_string(lang, "ask_trader_name"))
        return states.TRADER_FULL_NAME

    context.user_data["trader_full_name"] = full_name

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(text=get_string(lang, "ask_trader_phone"))

    return states.TRADER_PHONE


async def received_trader_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف وينتقل لمرحلة الدولة.

    المُخرجات:
        int: states.TRADER_COUNTRY
    """
    lang = context.user_data.get("lang", "ar")

    phone = update.message.text.strip()
    context.user_data["trader_phone"] = phone

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(text=get_string(lang, "ask_trader_country"))

    return states.TRADER_COUNTRY


async def received_trader_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الدولة ويعرض قائمة اختيار نوع النشاط التجاري.

    المُخرجات:
        int: states.TRADER_BUSINESS_TYPE
    """
    lang = context.user_data.get("lang", "ar")

    country = update.message.text.strip()
    context.user_data["trader_country"] = country

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    await update.message.reply_text(
        text=get_string(lang, "ask_business_type"),
        reply_markup=_build_business_type_keyboard(lang)
    )

    return states.TRADER_BUSINESS_TYPE


async def received_trader_business_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نوع النشاط التجاري، يحفظ بيانات التاجر، ويُرسل إشعار للأدمن.

    المُخرجات:
        int: ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    business_type = query.data  # مثال: "business_online"

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    trader_data = {
        "telegram_id": str(query.from_user.id),
        "full_name": context.user_data.get("trader_full_name"),
        "phone": context.user_data.get("trader_phone"),
        "country": context.user_data.get("trader_country"),
        "business_type": business_type,
    }

    # بناء أزرار ما بعد التسجيل للتاجر (محفزة وموجهة)
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "browse_products_btn"),
                callback_data="post_reg_browse_products"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "contact_supplier_btn"),
                callback_data="post_reg_contact_supplier"
            ),
            InlineKeyboardButton(
                text=get_string(lang, "featured_products_btn"),
                callback_data="post_reg_featured_products"
            ),
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    success = database_service.save_trader(trader_data)

    if success:
        logger.info("✅ تم حفظ بيانات التاجر: telegram_id=%s", trader_data["telegram_id"])
        notification_service.notify_new_trader(trader_data)
        await query.edit_message_text(
            text=get_string(lang, "trader_success"),
            reply_markup=reply_markup
        )
    else:
        logger.error("❌ فشل حفظ بيانات التاجر: telegram_id=%s", trader_data["telegram_id"])
        await query.edit_message_text(
            text=get_string(lang, "error_general"),
            reply_markup=reply_markup
        )

    return ConversationHandler.END


async def cancel_trader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية تسجيل التاجر عند كتابة /cancel.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")
    await update.message.reply_text(text=get_string(lang, "cancel"))
    return ConversationHandler.END
