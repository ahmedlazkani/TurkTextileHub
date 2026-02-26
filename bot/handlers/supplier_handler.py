# ===================================================
# bot/handlers/supplier_handler.py
# معالج محادثة متعدد الخطوات لتسجيل الموردين
# يتعامل مع تدفق: اسم الشركة ← اسم جهة الاتصال ← رقم الهاتف
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services.language_service import get_string

# سجل خاص بهذا المعالج
logger = logging.getLogger(__name__)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق تسجيل المورد عند الضغط على زر "مورد".

    الخطوات:
        1. استخراج لغة المستخدم من بيانات المستخدم في تليجرام
        2. حفظ اللغة في context.user_data للاستخدام في الخطوات التالية
        3. الرد على الزر (query.answer) لإزالة حالة التحميل
        4. تعديل الرسالة الأصلية برسالة بداية التسجيل
        5. إرسال سؤال اسم الشركة

    المعاملات:
        update: كائن التحديث من تليجرام (يحتوي على callback_query)
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
    # استرجاع اللغة المحفوظة مع العربية كقيمة افتراضية
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

    # الانتقال إلى مرحلة استقبال اسم جهة الاتصال
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
    # استرجاع اللغة المحفوظة مع العربية كقيمة افتراضية
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

    # الانتقال إلى مرحلة استقبال رقم الهاتف
    return states.PHONE_NUMBER


async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف ويُنهي عملية التسجيل.

    الخطوات:
        1. قراءة رقم الهاتف المُرسل من المستخدم
        2. حفظ رقم الهاتف في context.user_data
        3. تجميع جميع بيانات المورد في قاموس
        4. طباعة البيانات في السجلات (مؤقتاً - سيتم الحفظ في قاعدة البيانات في المرحلة الثالثة)
        5. إرسال رسالة نجاح التسجيل
        6. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    # استرجاع اللغة المحفوظة مع العربية كقيمة افتراضية
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ رقم الهاتف
    # ===================================================
    phone = update.message.text
    context.user_data["phone"] = phone

    # ===================================================
    # تجميع بيانات المورد الكاملة
    # ملاحظة: سيتم ربط قاعدة البيانات في المرحلة الثالثة
    # ===================================================
    supplier_data = {
        "telegram_id": str(update.effective_user.id),
        "company_name": context.user_data.get("company_name"),
        "contact_name": context.user_data.get("contact_name"),
        "phone": context.user_data.get("phone"),
    }

    # طباعة البيانات في السجلات (مؤقتاً بدلاً من حفظها في قاعدة البيانات)
    logger.info("📋 بيانات مورد جديد: %s", supplier_data)

    # إرسال رسالة نجاح التسجيل للمستخدم
    await update.message.reply_text(
        text=get_string(lang, "registration_success")
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
    # استرجاع اللغة المحفوظة مع العربية كقيمة افتراضية
    lang = context.user_data.get("lang", "ar")

    # إرسال رسالة الإلغاء مع إرشاد للبدء من جديد
    await update.message.reply_text(
        text=get_string(lang, "cancel")
    )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END
