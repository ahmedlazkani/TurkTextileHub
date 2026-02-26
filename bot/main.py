# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# المرحلة الثانية: إضافة ConversationHandler للموردين ومعالج زر التاجر
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import states
from bot.config import BOT_TOKEN
from bot.handlers import start_handler, supplier_handler
from bot.services.language_service import get_string


# ===================================================
# إعداد نظام السجلات لمتابعة عمل البوت
# ===================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def trader_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعالج الضغط على زر "تاجر" ويُظهر رسالة "قادم قريباً".

    الخطوات:
        1. استخراج callback_query من التحديث
        2. الرد على الزر لإزالة حالة التحميل
        3. تحديد لغة المستخدم
        4. تعديل الرسالة برسالة "تسجيل التجار قادم قريباً"

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت
    """
    query = update.callback_query

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # تحديد لغة المستخدم
    # ===================================================
    lang = query.from_user.language_code or "ar"

    if not lang.startswith(("tr", "en")):
        lang = "ar"
    elif lang.startswith("tr"):
        lang = "tr"
    else:
        lang = "en"

    # تعديل الرسالة الأصلية برسالة "قادم قريباً"
    await query.edit_message_text(
        text=get_string(lang, "trader_coming_soon")
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج الأخطاء العالمي - يعالج جميع الأخطاء أثناء تشغيل البوت.

    السلوك:
        - يتجاهل خطأ BadRequest الذي يحتوي على "Query is too old"
        - يسجل جميع الأخطاء الأخرى في السجلات

    المعاملات:
        update: كائن التحديث (قد يكون None في بعض الحالات)
        context: سياق البوت الذي يحتوي على معلومات الخطأ
    """
    error = context.error

    # تجاهل خطأ الاستعلامات القديمة - يحدث عند الضغط على أزرار منتهية الصلاحية
    if isinstance(error, BadRequest) and "Query is too old" in str(error):
        logger.info("تم تجاهل استعلام قديم (Query is too old)")
        return

    # تسجيل جميع الأخطاء الأخرى مع تفاصيل كاملة
    logger.error(
        "حدث خطأ أثناء معالجة التحديث:",
        exc_info=context.error
    )


def main() -> None:
    """
    الدالة الرئيسية لتشغيل البوت.

    الخطوات:
        1. إنشاء كائن Application باستخدام التوكن
        2. بناء ConversationHandler لتدفق تسجيل الموردين
        3. تسجيل المعالجات بالترتيب الصحيح (مهم جداً)
        4. تسجيل معالج الأخطاء
        5. تشغيل البوت بنظام polling
    """
    logger.info("جاري تشغيل بوت TurkTextileHub - المرحلة الثانية...")

    # إنشاء كائن Application - نقطة تحكم البوت الرئيسية
    application = Application.builder().token(BOT_TOKEN).build()

    # ===================================================
    # بناء ConversationHandler لتدفق تسجيل الموردين
    # per_message=False: مهم لتجنب التحذيرات مع entry_points من نوع CallbackQueryHandler
    # per_chat=True, per_user=True: تتبع المحادثة لكل مستخدم في كل محادثة
    # ===================================================
    supplier_conv = ConversationHandler(
        # نقطة الدخول: الضغط على زر "مورد"
        entry_points=[
            CallbackQueryHandler(
                supplier_handler.start_registration,
                pattern="^supplier$"
            )
        ],
        # تعريف الحالات وما يعالجها من رسائل نصية
        states={
            # المرحلة الأولى: استقبال اسم الشركة
            states.COMPANY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_company_name
                )
            ],
            # المرحلة الثانية: استقبال اسم جهة الاتصال
            states.CONTACT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_contact_name
                )
            ],
            # المرحلة الثالثة: استقبال رقم الهاتف
            states.PHONE_NUMBER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_phone
                )
            ],
        },
        # معالج الإلغاء: يعمل عند كتابة /cancel في أي مرحلة
        fallbacks=[
            CommandHandler("cancel", supplier_handler.cancel)
        ],
        per_message=False,  # مهم: False لتجنب التحذيرات مع CallbackQueryHandler
        per_chat=True,      # تتبع المحادثة لكل محادثة
        per_user=True,      # تتبع المحادثة لكل مستخدم
    )

    # ===================================================
    # تسجيل المعالجات بالترتيب الصحيح - الترتيب مهم جداً
    # supplier_conv يجب أن يُسجَّل قبل أي CallbackQueryHandler منفصل
    # ===================================================

    # 1. معالج أمر /start
    application.add_handler(CommandHandler("start", start_handler.start))

    # 2. محادثة تسجيل الموردين (يجب أن يكون قبل معالج التاجر)
    application.add_handler(supplier_conv)

    # 3. معالج زر "تاجر" (بعد supplier_conv)
    application.add_handler(
        CallbackQueryHandler(trader_handler, pattern="^trader$")
    )

    # 4. معالج الأخطاء العالمي
    application.add_error_handler(error_handler)

    logger.info("تم تسجيل جميع المعالجات بنجاح")
    logger.info("البوت يعمل الآن في وضع polling...")

    # تشغيل البوت - يظل يعمل حتى يتم إيقافه يدوياً
    application.run_polling()


# ===================================================
# نقطة الدخول - يتم التشغيل فقط عند تنفيذ الملف مباشرة
# ===================================================
if __name__ == "__main__":
    main()
