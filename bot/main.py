# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# المرحلة الرابعة: إضافة ConversationHandler للتجار + معالج تغيير اللغة
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
from bot.handlers import start_handler, supplier_handler, trader_handler


# ===================================================
# إعداد نظام السجلات لمتابعة عمل البوت
# ===================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج الأخطاء العالمي - يعالج جميع الأخطاء أثناء تشغيل البوت.

    السلوك:
        - يتجاهل خطأ BadRequest الذي يحتوي على 'Query is too old'
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
        1. إنشاء كائن Application
        2. بناء ConversationHandler للموردين
        3. بناء ConversationHandler للتجار (جديد في المرحلة الرابعة)
        4. تسجيل المعالجات بالترتيب الصحيح
        5. تشغيل البوت بنظام polling
    """
    logger.info("جاري تشغيل بوت TurkTextileHub - المرحلة الرابعة...")

    # إنشاء كائن Application - نقطة تحكم البوت الرئيسية
    application = Application.builder().token(BOT_TOKEN).build()

    # ===================================================
    # ConversationHandler لتسجيل الموردين
    # per_message=False: مهم لتجنب التحذيرات مع CallbackQueryHandler
    # ===================================================
    supplier_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                supplier_handler.start_registration,
                pattern="^supplier$"
            )
        ],
        states={
            states.COMPANY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_company_name
                )
            ],
            states.CONTACT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_contact_name
                )
            ],
            states.PHONE_NUMBER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_phone
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", supplier_handler.cancel)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # ConversationHandler لتسجيل التجار (جديد - المرحلة الرابعة)
    # TRADER_PRODUCT يستخدم CallbackQueryHandler لأزرار الاختيار
    # ===================================================
    trader_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                trader_handler.start_trader_registration,
                pattern="^trader$"
            )
        ],
        states={
            # مرحلة استقبال الاسم الكامل
            states.TRADER_FULL_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_name
                )
            ],
            # مرحلة استقبال رقم الهاتف
            states.TRADER_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_phone
                )
            ],
            # مرحلة استقبال الدولة
            states.TRADER_COUNTRY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_country
                )
            ],
            # مرحلة اختيار نوع المنتج عبر InlineKeyboard
            states.TRADER_PRODUCT: [
                CallbackQueryHandler(
                    trader_handler.received_trader_product,
                    pattern="^product_(ready|fabric|shoes|misc)$"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", trader_handler.cancel_trader)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # معالج تغيير اللغة (جديد - المرحلة الرابعة)
    # ===================================================
    change_lang_handler = CallbackQueryHandler(
        start_handler.change_language,
        pattern="^change_language$"
    )

    # معالج اختيار لغة محددة (ar/tr/en)
    set_lang_handler = CallbackQueryHandler(
        start_handler.set_language,
        pattern="^lang_(ar|tr|en)$"
    )

    # ===================================================
    # تسجيل المعالجات بالترتيب الصحيح - الترتيب مهم جداً
    # ConversationHandlers يجب أن تُسجَّل قبل أي CallbackQueryHandler منفصل
    # ===================================================

    # 1. معالج أمر /start
    application.add_handler(CommandHandler("start", start_handler.start))

    # 2. محادثة تسجيل الموردين
    application.add_handler(supplier_conv)

    # 3. محادثة تسجيل التجار (جديد)
    application.add_handler(trader_conv)

    # 4. معالج تغيير اللغة (جديد)
    application.add_handler(change_lang_handler)

    # 5. معالج اختيار لغة محددة (جديد)
    application.add_handler(set_lang_handler)

    # 6. معالج الأخطاء العالمي
    application.add_error_handler(error_handler)

    logger.info("✅ تم تسجيل جميع المعالجات بنجاح")
    logger.info("🔄 البوت يعمل الآن في وضع polling...")

    # تشغيل البوت - يظل يعمل حتى يتم إيقافه يدوياً
    application.run_polling()


# ===================================================
# نقطة الدخول - يتم التشغيل فقط عند تنفيذ الملف مباشرة
# ===================================================
if __name__ == "__main__":
    main()
