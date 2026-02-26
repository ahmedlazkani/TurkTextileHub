# ===================================================
# bot/handlers/trader_handler.py
# معالج محادثة متعدد الخطوات لتسجيل التجار
# المرحلة الخامسة: إضافة إشعار الأدمن عند كل تسجيل ناجح
# تدفق: الاسم الكامل ← رقم الهاتف ← الدولة ← نوع المنتج
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service
from bot.services import notification_service
from bot.services.language_service import get_string

# سجل خاص بهذا المعالج
logger = logging.getLogger(__name__)


async def start_trader_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تسجيل التاجر عند الضغط على زر 'تسجيل كتاجر'.

    الخطوات:
        1. استخراج لغة المستخدم وحفظها
        2. الرد على الزر لإزالة حالة التحميل
        3. التحقق إذا كان المستخدم مسجلاً مسبقاً كتاجر
        4. إذا جديد: تعديل الرسالة وإرسال سؤال الاسم الكامل
        5. إذا مسجل: إرسال رسالة تنبيه وإنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_FULL_NAME للانتقال لمرحلة الاسم، أو END إذا مسجل مسبقاً
    """
    query = update.callback_query

    # ===================================================
    # استخراج لغة المستخدم وتحديد اللغة المناسبة
    # ===================================================
    raw_lang = query.from_user.language_code or "ar"

    if raw_lang.startswith("tr"):
        lang = "tr"
    elif raw_lang.startswith("en"):
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة في بيانات المستخدم لاستخدامها في جميع الخطوات التالية
    context.user_data["lang"] = lang

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # التحقق من أن المستخدم ليس مسجلاً مسبقاً كتاجر
    # ===================================================
    telegram_id = str(query.from_user.id)

    # إظهار مؤشر الكتابة أثناء التحقق من قاعدة البيانات
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action="typing"
    )

    already_exists = database_service.check_trader_exists(telegram_id)

    if already_exists:
        # إرسال رسالة أن المستخدم مسجل مسبقاً وإنهاء المحادثة
        await query.edit_message_text(
            text=get_string(lang, "already_registered")
        )
        return ConversationHandler.END

    # ===================================================
    # تعديل الرسالة الأصلية برسالة الترحيب بتسجيل التجار
    # ===================================================
    await query.edit_message_text(
        text=get_string(lang, "trader_welcome")
    )

    # إرسال سؤال الاسم الكامل كرسالة جديدة
    await query.message.reply_text(
        text=get_string(lang, "ask_trader_name")
    )

    # الانتقال إلى مرحلة استقبال الاسم الكامل
    return states.TRADER_FULL_NAME


async def received_trader_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الاسم الكامل للتاجر ويتحقق من صحته.

    الخطوات:
        1. قراءة الاسم المُرسل والتحقق من أنه لا يقل عن حرفين
        2. حفظ الاسم في context.user_data
        3. إرسال سؤال رقم الهاتف

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_PHONE للانتقال لمرحلة الهاتف،
             أو نفس الحالة إذا كان الاسم غير صالح
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال الاسم والتحقق من صحته (لا يقل عن حرفين)
    # ===================================================
    full_name = update.message.text.strip()

    if len(full_name) < 2:
        # الاسم قصير جداً - إعادة السؤال
        await update.message.reply_text(
            text=get_string(lang, "ask_trader_name")
        )
        return states.TRADER_FULL_NAME

    # حفظ الاسم الكامل في بيانات المستخدم
    context.user_data["trader_full_name"] = full_name

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال رقم الهاتف
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_phone")
    )

    # الانتقال إلى مرحلة استقبال رقم الهاتف
    return states.TRADER_PHONE


async def received_trader_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم هاتف التاجر وينتقل لمرحلة الدولة.

    الخطوات:
        1. قراءة رقم الهاتف المُرسل من المستخدم
        2. حفظه في context.user_data
        3. إرسال سؤال الدولة

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_COUNTRY للانتقال لمرحلة الدولة
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ رقم الهاتف
    # ===================================================
    phone = update.message.text.strip()
    context.user_data["trader_phone"] = phone

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال الدولة
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_country")
    )

    # الانتقال إلى مرحلة استقبال الدولة
    return states.TRADER_COUNTRY


async def received_trader_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل دولة التاجر ويعرض قائمة اختيار نوع المنتج.

    الخطوات:
        1. قراءة الدولة المُرسلة من المستخدم
        2. حفظها في context.user_data
        3. إرسال InlineKeyboard بأربعة خيارات لنوع المنتج

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_PRODUCT للانتقال لمرحلة اختيار المنتج
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ الدولة
    # ===================================================
    country = update.message.text.strip()
    context.user_data["trader_country"] = country

    # ===================================================
    # بناء InlineKeyboard بأربعة أزرار لنوع المنتج
    # callback_data يُستخدم لاحقاً لتحديد الاختيار
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_ready"),
                callback_data="product_ready"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_fabric"),
                callback_data="product_fabric"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_shoes"),
                callback_data="product_shoes"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_misc"),
                callback_data="product_misc"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال نوع المنتج مع الأزرار
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_product"),
        reply_markup=reply_markup
    )

    # الانتقال إلى مرحلة استقبال اختيار المنتج
    return states.TRADER_PRODUCT


async def received_trader_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نوع المنتج عبر InlineKeyboard، يحفظ البيانات في Supabase، ويُرسل إشعاراً للأدمن.

    الخطوات:
        1. استقبال callback_data لمعرفة المنتج المختار
        2. الرد على الزر لإزالة حالة التحميل
        3. تجميع جميع بيانات التاجر وحفظها في Supabase
        4. إرسال إشعار فوري للأدمن عند نجاح الحفظ
        5. إرسال رسالة النجاح مع أزرار العودة للقائمة الرئيسية
        6. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # استقبال اختيار نوع المنتج من callback_data
    # ===================================================
    product_interest = query.data  # مثال: "product_ready"

    # إظهار مؤشر الكتابة أثناء الحفظ في قاعدة البيانات
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action="typing"
    )

    # ===================================================
    # تجميع جميع بيانات التاجر الكاملة
    # ===================================================
    trader_data = {
        "telegram_id": str(query.from_user.id),
        "full_name": context.user_data.get("trader_full_name"),
        "phone": context.user_data.get("trader_phone"),
        "country": context.user_data.get("trader_country"),
        "product_interest": product_interest,
    }

    # ===================================================
    # حفظ بيانات التاجر في Supabase
    # ===================================================
    success = database_service.save_trader(trader_data)

    # ===================================================
    # بناء أزرار العودة للقائمة الرئيسية بعد التسجيل
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
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

    if success:
        logger.info(
            "تم حفظ بيانات التاجر بنجاح: telegram_id=%s",
            trader_data["telegram_id"]
        )
        # ===================================================
        # إرسال إشعار للأدمن بالتسجيل الجديد
        # الفشل لا يوقف البوت - يُسجَّل الخطأ فقط داخل الخدمة
        # ===================================================
        notification_service.notify_new_trader(trader_data)

        # إرسال رسالة نجاح التسجيل مع أزرار العودة
        await query.edit_message_text(
            text=get_string(lang, "trader_success"),
            reply_markup=reply_markup
        )
    else:
        logger.error(
            "فشل حفظ بيانات التاجر: telegram_id=%s",
            trader_data["telegram_id"]
        )
        # إرسال رسالة الخطأ العامة مع أزرار العودة
        await query.edit_message_text(
            text=get_string(lang, "error_general"),
            reply_markup=reply_markup
        )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END


async def cancel_trader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية تسجيل التاجر عند كتابة أمر /cancel.

    الخطوات:
        1. استرجاع اللغة المحفوظة
        2. إرسال رسالة الإلغاء
        3. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يُستدعى من CommandHandler)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    lang = context.user_data.get("lang", "ar")

    # إرسال رسالة الإلغاء مع إرشاد للبدء من جديد
    await update.message.reply_text(
        text=get_string(lang, "cancel")
    )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END
