# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
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
from bot.handlers import (
    start_handler,
    supplier_handler,
    trader_handler,
    product_handler,
    browse_handler,
    channel_handler,
    channel_post_handler,
)

# ===================================================
# إعداد نظام السجلات
# ===================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج الأخطاء العالمي.
    يتجاهل خطأ 'Query is too old' ويسجل جميع الأخطاء الأخرى.
    """
    error = context.error

    if isinstance(error, BadRequest) and "Query is too old" in str(error):
        logger.info("تم تجاهل استعلام قديم (Query is too old)")
        return

    logger.error("حدث خطأ أثناء معالجة التحديث:", exc_info=context.error)


def main() -> None:
    """
    الدالة الرئيسية لتشغيل البوت.
    تُسجّل جميع المعالجات بالترتيب الصحيح وتشغّل البوت.
    """
    logger.info("🚀 جاري تشغيل بوت TurkTextileHub...")

    application = Application.builder().token(BOT_TOKEN).build()

    # ===================================================
    # 1. ConversationHandler: تسجيل الموردين
    # التدفق: اسم الشركة ← المسؤول ← المدينة ← الهاتف ← موظف المبيعات ← (يوزرنيم)
    # ===================================================
    supplier_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(supplier_handler.start_registration, pattern="^supplier$")
        ],
        states={
            states.COMPANY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_company_name)
            ],
            states.CONTACT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_contact_name)
            ],
            states.SUPPLIER_CITY: [
                CallbackQueryHandler(
                    supplier_handler.received_city,
                    pattern="^city_(istanbul|bursa|izmir|other)$"
                )
            ],
            states.PHONE_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_phone)
            ],
            states.SALES_REP: [
                CallbackQueryHandler(
                    supplier_handler.received_sales_rep_answer,
                    pattern="^sales_rep_(yes|no)$"
                )
            ],
            states.SALES_REP_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_sales_rep_username)
            ],
        },
        fallbacks=[CommandHandler("cancel", supplier_handler.cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # 2. ConversationHandler: تسجيل التجار
    # التدفق: الاسم ← الهاتف ← الدولة ← نوع النشاط
    # ===================================================
    trader_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(trader_handler.start_trader_registration, pattern="^trader$")
        ],
        states={
            states.TRADER_FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trader_handler.received_trader_name)
            ],
            states.TRADER_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trader_handler.received_trader_phone)
            ],
            states.TRADER_COUNTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trader_handler.received_trader_country)
            ],
            states.TRADER_BUSINESS_TYPE: [
                CallbackQueryHandler(
                    trader_handler.received_trader_business_type,
                    pattern="^business_(online|physical|distributor|other)$"
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", trader_handler.cancel_trader)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # 3. ConversationHandler: إضافة منتج
    # التدفق: /add_product أو زر لوحة التحكم ← الصور ← الفئة ← السعر ← معاينة ← نشر
    # ===================================================
    product_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_product", product_handler.start_add_product),
            # زر "إضافة منتج جديد" من لوحة تحكم المورد
            CallbackQueryHandler(
                product_handler.start_add_product_from_button,
                pattern="^post_reg_add_product$"
            ),
        ],
        states={
            states.GETTING_IMAGES: [
                MessageHandler(filters.PHOTO, product_handler.get_images)
            ],
            states.GETTING_CATEGORY: [
                CallbackQueryHandler(
                    product_handler.get_category,
                    pattern="^cat_(abayas|dresses|hijab|sets|other)$"
                )
            ],
            states.GETTING_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_handler.get_price),
                CallbackQueryHandler(product_handler.skip_price, pattern="^price_skip$"),
            ],
            states.CONFIRM_ADD_PRODUCT: [
                CallbackQueryHandler(product_handler.finish_add_product, pattern="^product_confirm_yes$"),
                CallbackQueryHandler(product_handler.cancel_add_product, pattern="^product_confirm_no$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", product_handler.cancel_add_product)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # 4. ConversationHandler: تصفح المنتجات + RFQ
    # التدفق: /browse أو زر لوحة التحكم ← اختيار الفئة ← تصفح ← طلب عرض سعر
    # ===================================================
    browse_conv = browse_handler.get_browse_conversation_handler()

    # ===================================================
    # 5. ConversationHandler: ربط القناة
    # التدفق: /connect_channel ← تعليمات ← اسم القناة ← تحقق ثلاثي ← تأكيد ← حفظ
    # ===================================================
    channel_conv = channel_handler.get_channel_conversation_handler()

    # ===================================================
    # تسجيل المعالجات بالترتيب الصحيح
    # ConversationHandlers أولاً، ثم المعالجات المستقلة
    # ===================================================

    # أمر /start
    application.add_handler(CommandHandler("start", start_handler.start))

    # محادثات التسجيل
    application.add_handler(supplier_conv)
    application.add_handler(trader_conv)

    # محادثات المنتجات والتصفح (تشمل أزرار لوحة التحكم كـ entry_points)
    application.add_handler(product_conv)
    application.add_handler(browse_conv)

    # محادثة ربط القناة (للموردين المعتمدين فقط)
    application.add_handler(channel_conv)

    # معالجات تغيير اللغة
    application.add_handler(
        CallbackQueryHandler(start_handler.change_language, pattern="^change_language$")
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.set_language, pattern="^set_lang_(ar|tr|en)$")
    )

    # معالجات لوحة تحكم المورد — قنواتي والعودة للوحة
    application.add_handler(
        CallbackQueryHandler(start_handler.show_my_channels, pattern="^my_channels$")
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.back_to_dashboard, pattern="^back_to_dashboard$")
    )

    # ===================================================
    # 6. معالجات منشورات القناة — الخطوة 6
    # يلتقط المنشورات من القنوات المربوطة ويرسلها للمورد للموافقة
    # ===================================================

    # مستمع منشورات القناة
    application.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & (
                filters.PHOTO |
                filters.VIDEO |
                filters.Document.IMAGE |
                filters.TEXT
            ),
            channel_post_handler.handle_channel_post,
        )
    )

    # معالج الموافقة على المنشور
    application.add_handler(
        CallbackQueryHandler(
            channel_post_handler.handle_post_approval,
            pattern="^approve_post_",
        )
    )

    # معالج رفض المنشور
    application.add_handler(
        CallbackQueryHandler(
            channel_post_handler.handle_post_rejection,
            pattern="^reject_post_",
        )
    )

    # ConversationHandler لتعديل المنشور
    post_edit_conv = channel_post_handler.get_post_edit_conversation_handler()
    application.add_handler(post_edit_conv)

    # معالج الأخطاء العالمي
    application.add_error_handler(error_handler)

    logger.info("✅ تم تسجيل جميع المعالجات بنجاح")
    logger.info("🔄 البوت يعمل الآن في وضع polling...")

    application.run_polling(
        allowed_updates=["message", "channel_post", "callback_query", "inline_query"],
        drop_pending_updates=True,
        close_loop=False,
    )


# ===================================================
# نقطة الدخول
# ===================================================
if __name__ == "__main__":
    main()
