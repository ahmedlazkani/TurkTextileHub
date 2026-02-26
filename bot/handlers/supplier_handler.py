# ===================================================
# bot/handlers/supplier_handler.py
# معالج محادثة متعدد الخطوات لتسجيل الموردين
# المرحلة الخامسة: إضافة إشعار الأدمن عند كل تسجيل ناجح
# يتعامل مع تدفق: اسم الشركة ← اسم جهة الاتصال ← رقم الهاتف
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service
from bot.services import notification_service
from bot.services.language_service import get_string

# سجل خاص بهذا المعالج
logger = logging.getLogger(__name__)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق تسجيل المورد عند الضغط على زر 'مورد'.

    الخطوات:
        1. استخراج لغة المستخدم من بيانات تليجرام وحفظها
        2. الرد على الزر لإزالة حالة التحميل
        3. تعديل الرسالة الأصلية برسالة بداية التسجيل
        4. إرسال سؤال اسم الشركة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت (يُستخدم لحفظ بيانات المستخدم)

    المُخرجات:
        int: states.COMPANY_NAME للانتقال إلى مرحلة استقبال اسم الشركة
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

    # الرد على الزر لإزالة حالة التحميل الدوارة في تليجرام
    await query.answer()

    # تعديل الرسالة الأصلية برسالة بداية التسجيل كمورد
    await query.edit_message_text(
        text=get_string(lang, "supplier_registration_start")
    )

    # إرسال سؤال اسم الشركة كرسالة جديدة
    await query.message.reply_text(
        text=get_string(lang, "prompt_company_name")
    )

    # الانتقال إلى مرحلة استقبال اسم الشركة
    return states.COMPANY_NAME


async def received_company_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم الشركة من المستخدم وينتقل لمرحلة اسم جهة الاتصال.

    الخطوات:
        1. قراءة النص المُرسل من المستخدم
        2. حفظ اسم الشركة في context.user_data
        3. إرسال سؤال اسم جهة الاتصال

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.CONTACT_NAME للانتقال إلى مرحلة اسم جهة الاتصال
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ اسم الشركة
    # ===================================================
    company_name = update.message.text
    context.user_data["company_name"] = company_name

    # إرسال سؤال اسم جهة الاتصال
    await update.message.reply_text(
        text=get_string(lang, "prompt_contact_name")
    )

    return states.CONTACT_NAME


async def received_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم جهة الاتصال وينتقل لمرحلة رقم الهاتف.

    الخطوات:
        1. قراءة النص المُرسل من المستخدم
        2. حفظ اسم جهة الاتصال في context.user_data
        3. إرسال سؤال رقم الهاتف

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.PHONE_NUMBER للانتقال إلى مرحلة رقم الهاتف
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ اسم جهة الاتصال
    # ===================================================
    contact_name = update.message.text
    context.user_data["contact_name"] = contact_name

    # إرسال سؤال رقم الهاتف مع مثال على الصيغة الصحيحة
    await update.message.reply_text(
        text=get_string(lang, "prompt_phone")
    )

    return states.PHONE_NUMBER


async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف، يحفظ البيانات في Supabase، ويُرسل إشعاراً للأدمن.

    الخطوات:
        1. قراءة رقم الهاتف وحفظه
        2. تجميع بيانات المورد الكاملة
        3. التحقق من التسجيل المسبق
        4. حفظ البيانات في Supabase إذا كان المستخدم جديداً
        5. إرسال إشعار فوري للأدمن عند نجاح الحفظ
        6. إرسال الرسالة المناسبة للمستخدم وإنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ رقم الهاتف
    # ===================================================
    phone = update.message.text
    context.user_data["phone"] = phone

    # ===================================================
    # تجميع بيانات المورد الكاملة للحفظ في قاعدة البيانات
    # ===================================================
    supplier_data = {
        "telegram_id": str(update.effective_user.id),
        "company_name": context.user_data.get("company_name"),
        "contact_name": context.user_data.get("contact_name"),
        "phone": context.user_data.get("phone"),
    }

    # ===================================================
    # التحقق أولاً إذا كان المورد مسجلاً مسبقاً في Supabase
    # ===================================================
    already_exists = database_service.check_supplier_exists(supplier_data["telegram_id"])

    if already_exists:
        # إرسال رسالة أن المورد مسجل مسبقاً
        await update.message.reply_text(
            text=get_string(lang, "already_registered")
        )
    else:
        # ===================================================
        # حفظ بيانات المورد في قاعدة البيانات Supabase
        # ===================================================
        success = database_service.save_supplier(supplier_data)

        if success:
            logger.info(
                "تم حفظ بيانات المورد بنجاح: telegram_id=%s",
                supplier_data["telegram_id"]
            )
            # ===================================================
            # إرسال إشعار للأدمن بالتسجيل الجديد
            # الفشل لا يوقف البوت - يُسجَّل الخطأ فقط داخل الخدمة
            # ===================================================
            notification_service.notify_new_supplier(supplier_data)

            await update.message.reply_text(
                text=get_string(lang, "registration_success")
            )
        else:
            logger.error(
                "فشل حفظ بيانات المورد: telegram_id=%s",
                supplier_data["telegram_id"]
            )
            await update.message.reply_text(
                text=get_string(lang, "error_general")
            )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية التسجيل عند كتابة أمر /cancel.

    الخطوات:
        1. استرجاع اللغة المحفوظة
        2. إرسال رسالة إلغاء العملية
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

    return ConversationHandler.END
