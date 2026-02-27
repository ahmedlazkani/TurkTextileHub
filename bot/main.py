# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# المرحلة السابعة: إضافة معالجات أزرار ما بعد التسجيل
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
from bot.handlers import (
    start_handler,
    supplier_handler,
    trader_handler,
    product_handler,
    browse_handler,
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


async def _handle_post_reg_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعالج ضغطة زر 'إضافة منتج الآن' بعد تسجيل المورد.
    يوجه المورد مباشرةً لتدفق إضافة المنتج.
    """
    query = update.callback_query
    await query.answer()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="استخدم الأمر /add_product لإضافة منتجك الأول الآن!"
    )


async def _handle_post_reg_trader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعالج ضغط أزرار ما بعد التسجيل للتاجر.
    - browse_products: يوجه لتدفق التصفح
    - contact_supplier و featured_products: يعرض رسالة 'قيد التطوير'
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    from bot.services.language_service import get_string

    if query.data == "post_reg_browse_products":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="استخدم الأمر /browse لتصفح المنتجات المتاحة الآن!"
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_string(lang, "coming_soon")
        )


def main() -> None:
    """
    الدالة الرئيسية لتشغيل البوت.

    تُسجّل جميع المعالجات بالترتيب الصحيح وتشغّل البوت.
    """
    logger.info("🚀 جاري تشغيل بوت TurkTextileHub - المرحلة السابعة...")

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
    # التدفق: /add_product ← الصور ← الفئة ← السعر ← معاينة ← نشر
    # ===================================================
    product_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_product", product_handler.start_add_product)
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
    # 4. ConversationHandler: تصفح المنتجات
    # التدفق: /browse ← اختيار الفئة ← التنقل بين المنتجات
    # ===================================================
    browse_conv = ConversationHandler(
        entry_points=[
            CommandHandler("browse", browse_handler.start_browse)
        ],
        states={
            states.BROWSING_CATEGORY: [
                CallbackQueryHandler(browse_handler.browse_by_category, pattern="^browse_cat_"),
            ],
            states.BROWSING_PRODUCTS: [
                CallbackQueryHandler(browse_handler.next_product, pattern="^browse_next$"),
                CallbackQueryHandler(browse_handler.prev_product, pattern="^browse_prev$"),
                CallbackQueryHandler(browse_handler.request_quote, pattern="^browse_request_quote$"),
                CallbackQueryHandler(browse_handler.back_to_categories, pattern="^browse_back$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", browse_handler.cancel_browse)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # تسجيل المعالجات بالترتيب الصحيح
    # ConversationHandlers أولاً، ثم المعالجات المستقلة
    # ===================================================

    # أمر /start
    application.add_handler(CommandHandler("start", start_handler.start))

    # محادثات التسجيل
    application.add_handler(supplier_conv)
    application.add_handler(trader_conv)

    # محادثات المنتجات
    application.add_handler(product_conv)
    application.add_handler(browse_conv)

    # معالجات أزرار ما بعد التسجيل (مستقلة)
    application.add_handler(
        CallbackQueryHandler(_handle_post_reg_supplier, pattern="^post_reg_add_product$")
    )
    application.add_handler(
        CallbackQueryHandler(
            _handle_post_reg_trader,
            pattern="^post_reg_(browse_products|contact_supplier|featured_products)$"
        )
    )

    # معالجات تغيير اللغة (مستقلة عن ConversationHandlers)
    application.add_handler(
        CallbackQueryHandler(start_handler.change_language, pattern="^change_language$")
    )
    application.add_handler(
        CallbackQueryHandler(start_handler.set_language, pattern="^lang_(ar|tr|en)$")
    )

    # معالج الأخطاء العالمي
    application.add_error_handler(error_handler)

    logger.info("✅ تم تسجيل جميع المعالجات بنجاح")
    logger.info("🔄 البوت يعمل الآن في وضع polling...")

    application.run_polling(
        drop_pending_updates=True,  # يمنع تعارض نسختين عند إعادة النشر
        close_loop=False,
    )


# ===================================================
# نقطة الدخول
# ===================================================
if __name__ == "__main__":
    main()
