# ===================================================
# bot/handlers/start_handler.py
# معالج أمر /start - رسالة ترحيب مدمجة مع الأزرار في رسالة واحدة
# المرحلة السادسة: إصلاح رسالة الترحيب + استخدام detect_lang
# KAYISOFT - إسطنبول، تركيا
# ===================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.language_service import get_string, detect_lang


def _build_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    """
    يبني لوحة المفاتيح الرئيسية بثلاثة أزرار.

    المعاملات:
        lang (str): كود اللغة

    المُخرجات:
        InlineKeyboardMarkup: لوحة المفاتيح الجاهزة
    """
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "register_supplier_btn"), callback_data="supplier")],
        [InlineKeyboardButton(text=get_string(lang, "register_trader_btn"), callback_data="trader")],
        [InlineKeyboardButton(text=get_string(lang, "change_language"), callback_data="change_language")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_welcome_message(lang: str) -> str:
    """
    يبني نص رسالة الترحيب.

    المعاملات:
        lang (str): كود اللغة

    المُخرجات:
        str: نص الترحيب المدمج
    """
    return f"{get_string(lang, 'welcome')}\n\n{get_string(lang, 'role_selection')}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start - يعرض رسالة ترحيب واحدة مع الأزرار.

    الإصلاح في هذه المرحلة:
        - رسالة واحدة فقط تجمع النص والأزرار (لا رسالتين منفصلتين)

    المعاملات:
        update: كائن التحديث من تليجرام
        context: سياق البوت
    """
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # تحديد اللغة وحفظها
    lang = detect_lang(update.effective_user.language_code or "")
    context.user_data["lang"] = lang

    # إرسال رسالة واحدة تجمع الترحيب والأزرار
    await update.message.reply_text(
        text=_build_welcome_message(lang),
        reply_markup=_build_main_keyboard(lang)
    )


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض قائمة اختيار اللغة عند الضغط على زر 'تغيير اللغة'.

    المعاملات:
        update: كائن التحديث (callback_query)
        context: سياق البوت
    """
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ar")

    keyboard = [
        [InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang_ar")],
        [InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    ]

    await query.edit_message_text(
        text=get_string(lang, "select_language"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يضبط لغة المستخدم ويعيد عرض القائمة الرئيسية.

    المعاملات:
        update: كائن التحديث (callback_query)
        context: سياق البوت
    """
    query = update.callback_query
    await query.answer()

    # تحديد اللغة من callback_data
    callback = query.data
    if callback == "lang_tr":
        lang = "tr"
    elif callback == "lang_en":
        lang = "en"
    else:
        lang = "ar"

    context.user_data["lang"] = lang

    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.TYPING
    )

    # تعديل الرسالة بالقائمة الرئيسية باللغة الجديدة
    await query.edit_message_text(
        text=_build_welcome_message(lang),
        reply_markup=_build_main_keyboard(lang)
    )
