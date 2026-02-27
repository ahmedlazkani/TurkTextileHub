# ===================================================
# bot/handlers/supplier_handler.py
# معالج محادثة متعدد الخطوات لتسجيل الموردين
# المرحلة السادسة: إضافة خطوتي المدينة وموظف المبيعات
# التدفق: اسم الشركة ← اسم المسؤول ← المدينة ← الهاتف ← موظف المبيعات ← (يوزرنيم)
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service, notification_service
from bot.services.language_service import get_string, detect_lang

logger = logging.getLogger(__name__)


def _build_city_keyboard(lang: str) -> InlineKeyboardMarkup:
    """يبني لوحة مفاتيح اختيار المدينة."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "city_istanbul"), callback_data="city_istanbul")],
        [InlineKeyboardButton(text=get_string(lang, "city_bursa"), callback_data="city_bursa")],
        [InlineKeyboardButton(text=get_string(lang, "city_izmir"), callback_data="city_izmir")],
        [InlineKeyboardButton(text=get_string(lang, "city_other"), callback_data="city_other")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_sales_rep_keyboard(lang: str) -> InlineKeyboardMarkup:
    """يبني لوحة مفاتيح سؤال موظف المبيعات."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "sales_rep_yes"), callback_data="sales_rep_yes")],
        [InlineKeyboardButton(text=get_string(lang, "sales_rep_no"), callback_data="sales_rep_no")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق تسجيل المورد عند الضغط على زر 'مورد'.

    التحقق من التسجيل المسبق أولاً، ثم بدء الخطوات إذا كان المستخدم جديداً.

    المُخرجات:
        int: states.COMPANY_NAME أو ConversationHandler.END
    """
    query = update.callback_query

    lang = detect_lang(query.from_user.language_code or "")
    context.user_data["lang"] = lang

    await query.answer()

    # التحقق من التسجيل المسبق
    telegram_id = str(query.from_user.id)

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    if database_service.check_supplier_exists(telegram_id):
        await query.edit_message_text(text=get_string(lang, "already_registered"))
        return ConversationHandler.END

    await query.edit_message_text(text=get_string(lang, "supplier_registration_start"))
    await query.message.reply_text(text=get_string(lang, "prompt_company_name"))

    return states.COMPANY_NAME


async def received_company_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم الشركة وينتقل لمرحلة اسم جهة الاتصال.

    المُخرجات:
        int: states.CONTACT_NAME
    """
    lang = context.user_data.get("lang", "ar")

    company_name = update.message.text.strip()
    context.user_data["company_name"] = company_name

    await update.message.reply_text(text=get_string(lang, "prompt_contact_name"))

    return states.CONTACT_NAME


async def received_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم جهة الاتصال وينتقل لمرحلة اختيار المدينة.

    المُخرجات:
        int: states.SUPPLIER_CITY
    """
    lang = context.user_data.get("lang", "ar")

    contact_name = update.message.text.strip()
    context.user_data["contact_name"] = contact_name

    await update.message.reply_text(
        text=get_string(lang, "ask_city"),
        reply_markup=_build_city_keyboard(lang)
    )

    return states.SUPPLIER_CITY


async def received_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اختيار المدينة من الأزرار وينتقل لمرحلة رقم الهاتف.

    المُخرجات:
        int: states.PHONE_NUMBER
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    # تحديد اسم المدينة من callback_data
    city_map = {
        "city_istanbul": "Istanbul",
        "city_bursa": "Bursa",
        "city_izmir": "Izmir",
        "city_other": "Other",
    }
    city = city_map.get(query.data, query.data)
    context.user_data["city"] = city

    await query.edit_message_text(text=get_string(lang, "prompt_phone"))

    return states.PHONE_NUMBER


async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف وينتقل لمرحلة السؤال عن موظف المبيعات.

    المُخرجات:
        int: states.SALES_REP
    """
    lang = context.user_data.get("lang", "ar")

    phone = update.message.text.strip()
    context.user_data["phone"] = phone

    await update.message.reply_text(
        text=get_string(lang, "ask_sales_rep"),
        reply_markup=_build_sales_rep_keyboard(lang)
    )

    return states.SALES_REP


async def received_sales_rep_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل إجابة موظف المبيعات:
    - إذا "نعم": يطلب يوزرنيم الموظف
    - إذا "لا": يكمل التسجيل مباشرة

    المُخرجات:
        int: states.SALES_REP_USERNAME أو ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    if query.data == "sales_rep_yes":
        # يطلب يوزرنيم الموظف
        await query.edit_message_text(text=get_string(lang, "ask_sales_rep_username"))
        return states.SALES_REP_USERNAME
    else:
        # لا يوجد موظف - أكمل التسجيل
        context.user_data["sales_telegram_id"] = None
        await query.edit_message_text(text="⏳")
        return await _finish_supplier_registration(query.message, context, lang)


async def received_sales_rep_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل يوزرنيم موظف المبيعات ويكمل التسجيل.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")

    username = update.message.text.strip()
    context.user_data["sales_telegram_id"] = username

    return await _finish_supplier_registration(update.message, context, lang)


async def _finish_supplier_registration(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    lang: str
) -> int:
    """
    دالة داخلية: تجمع بيانات المورد وتحفظها في قاعدة البيانات.

    المعاملات:
        message: كائن الرسالة لإرسال الرد
        context: سياق البوت
        lang (str): كود اللغة

    المُخرجات:
        int: ConversationHandler.END
    """
    supplier_data = {
        "telegram_id": str(context._user_id if hasattr(context, '_user_id') else
                          message.chat.id),
        "company_name": context.user_data.get("company_name"),
        "contact_name": context.user_data.get("contact_name"),
        "city": context.user_data.get("city"),
        "phone": context.user_data.get("phone"),
        "sales_telegram_id": context.user_data.get("sales_telegram_id"),
    }

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    # بناء أزرار ما بعد التسجيل للمورد
    post_reg_keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "add_product_now_btn"),
                callback_data="post_reg_add_product"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]
    post_reg_markup = InlineKeyboardMarkup(post_reg_keyboard)

    success = database_service.save_supplier(supplier_data)
    if success:
        logger.info("✅ تم حفظ بيانات المورد: telegram_id=%s", supplier_data["telegram_id"])
        notification_service.notify_new_supplier(supplier_data)
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=get_string(lang, "registration_success"),
            reply_markup=post_reg_markup
        )
    else:
        logger.error("❌ فشل حفظ بيانات المورد: telegram_id=%s", supplier_data["telegram_id"])
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=get_string(lang, "error_general")
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية التسجيل عند كتابة /cancel.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")
    await update.message.reply_text(text=get_string(lang, "cancel"))
    return ConversationHandler.END
