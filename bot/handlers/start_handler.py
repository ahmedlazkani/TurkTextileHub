# ===================================================
# bot/handlers/start_handler.py
# معالج أمر /start - يعرض رسالة الترحيب وأزرار اختيار الدور
# المرحلة الرابعة: تحسين UX - أزرار محسّنة + send_chat_action + اسم المستخدم
# يدعم ثلاث لغات: العربية، التركية، الإنجليزية
# KAYISOFT - إسطنبول، تركيا
# ===================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.language_service import get_string


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start الرئيسي - نسخة محسّنة بتجربة مستخدم أفضل.

    التحسينات في هذه المرحلة:
        - عرض اسم المستخدم من تليجرام في رسالة الترحيب
        - إظهار مؤشر "يكتب..." قبل الرد
        - ثلاثة أزرار في ثلاثة صفوف منفصلة (مورد، تاجر، تغيير اللغة)

    المعاملات:
        update: كائن التحديث من تليجرام
        context: سياق البوت
    """
    # ===================================================
    # إظهار مؤشر الكتابة لتحسين تجربة الانتظار
    # ===================================================
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # ===================================================
    # تحديد لغة المستخدم من إعدادات تليجرام
    # ===================================================
    user_language_code = update.effective_user.language_code or ""

    if user_language_code.startswith("tr"):
        lang = "tr"
    elif user_language_code.startswith("en"):
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة في بيانات المستخدم
    context.user_data["lang"] = lang

    # ===================================================
    # استخراج اسم المستخدم من تليجرام لرسالة ترحيب شخصية
    # ===================================================
    user = update.effective_user
    user_name = user.first_name or user.username or ""

    # ===================================================
    # بناء أزرار القائمة الرئيسية المحسّنة (3 صفوف)
    # كل زر في صف مستقل لسهولة الضغط على الشاشات الصغيرة
    # ===================================================
    keyboard = [
        # الصف الأول: تسجيل كمورد
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
            )
        ],
        # الصف الثاني: تسجيل كتاجر
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_trader_btn"),
                callback_data="trader"
            )
        ],
        # الصف الثالث: تغيير اللغة
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # ===================================================
    # تجميع رسالة الترحيب مع اسم المستخدم
    # ===================================================
    welcome_text = get_string(lang, "welcome")
    role_text = get_string(lang, "role_selection")

    # بناء رسالة الترحيب بدون اسم المستخدم
    welcome_message = f"{welcome_text}\n\n{role_text}"

    # إرسال رسالة الترحيب مع الأزرار المحسّنة
    await update.message.reply_text(
        text=welcome_message,
        reply_markup=reply_markup
    )


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض قائمة اختيار اللغة عند الضغط على زر 'تغيير اللغة'.

    يُرسل رسالة جديدة مع ثلاثة أزرار: العربية، التركية، الإنجليزية.
    كل زر يغير لغة المستخدم عند الضغط عليه.

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت
    """
    query = update.callback_query

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # بناء أزرار اختيار اللغة (3 أزرار - كل لغة في صف)
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang_ar")
        ],
        [
            InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr")
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # تعديل الرسالة الحالية بعرض خيارات اللغة مع النص الصحيح
    await query.edit_message_text(
        text=get_string(lang, "select_language"),
        reply_markup=reply_markup
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يضبط لغة المستخدم بناءً على اختياره ويعرض القائمة الرئيسية.

    يُستدعى عند الضغط على أحد أزرار اختيار اللغة (lang_ar, lang_tr, lang_en).

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت
    """
    query = update.callback_query

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # تحديد اللغة المختارة من callback_data
    # ===================================================
    callback = query.data  # lang_ar أو lang_tr أو lang_en

    if callback == "lang_tr":
        lang = "tr"
    elif callback == "lang_en":
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة الجديدة في بيانات المستخدم
    context.user_data["lang"] = lang

    # ===================================================
    # إظهار مؤشر الكتابة قبل تحديث القائمة
    # ===================================================
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.TYPING
    )

    # ===================================================
    # عرض القائمة الرئيسية بعد تغيير اللغة
    # ===================================================
    user = query.from_user
    user_name = user.first_name or user.username or ""

    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_trader_btn"),
                callback_data="trader"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = get_string(lang, "welcome")
    role_text = get_string(lang, "role_selection")

    # بناء رسالة الترحيب بدون اسم المستخدم
    welcome_message = f"{welcome_text}\n\n{role_text}"

    # تعديل الرسالة بالقائمة الرئيسية باللغة الجديدة
    await query.edit_message_text(
        text=welcome_message,
        reply_markup=reply_markup
    )
