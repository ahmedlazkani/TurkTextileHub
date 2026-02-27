# أمر Claude: تحسين تجربة المستخدم بعد التسجيل

مرحباً Claude،

أحتاج منك إجراء تحسينات على تجربة المستخدم في بوت تليجرام مبني بلغة Python ومكتبة `python-telegram-bot`. الهدف هو توجيه المستخدمين بعد إكمال التسجيل بدلاً من تركهم في فراغ.

## القسم الأول: الكود الحالي

هذا هو الكود الحالي لملفات `supplier_handler.py` و `trader_handler.py` و `main.py`:

```python
# === bot/handlers/supplier_handler.py ===
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

    success = database_service.save_supplier(supplier_data)

    if success:
        logger.info("✅ تم حفظ بيانات المورد: telegram_id=%s", supplier_data["telegram_id"])
        notification_service.notify_new_supplier(supplier_data)
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=get_string(lang, "registration_success")
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

# === bot/handlers/trader_handler.py ===
# ===================================================
# bot/handlers/trader_handler.py
# معالج محادثة متعدد الخطوات لتسجيل التجار
# المرحلة السادسة: تغيير product_interest إلى business_type
# التدفق: الاسم ← الهاتف ← الدولة ← نوع النشاط التجاري
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service, notification_service
from bot.services.language_service import get_string, detect_lang

logger = logging.getLogger(__name__)


def _build_business_type_keyboard(lang: str) -> InlineKeyboardMarkup:
    """يبني لوحة مفاتيح اختيار نوع النشاط التجاري."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "business_online"), callback_data="business_online")],
        [InlineKeyboardButton(text=get_string(lang, "business_physical"), callback_data="business_physical")],
        [InlineKeyboardButton(text=get_string(lang, "business_distributor"), callback_data="business_distributor")],
        [InlineKeyboardButton(text=get_string(lang, "business_other"), callback_data="business_other")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_trader_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تسجيل التاجر عند الضغط على زر 'تسجيل كتاجر'.

    يتحقق من التسجيل المسبق قبل البدء.

    المُخرجات:
        int: states.TRADER_FULL_NAME أو ConversationHandler.END
    """
    query = update.callback_query

    lang = detect_lang(query.from_user.language_code or "")
    context.user_data["lang"] = lang

    await query.answer()

    telegram_id = str(query.from_user.id)

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    if database_service.check_trader_exists(telegram_id):
        await query.edit_message_text(text=get_string(lang, "already_registered"))
        return ConversationHandler.END

    await query.edit_message_text(text=get_string(lang, "trader_welcome"))
    await query.message.reply_text(text=get_string(lang, "ask_trader_name"))

    return states.TRADER_FULL_NAME


async def received_trader_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الاسم الكامل ويتحقق من صحته.

    المُخرجات:
        int: states.TRADER_PHONE أو نفس الحالة إذا كان الاسم غير صالح
    """
    lang = context.user_data.get("lang", "ar")

    full_name = update.message.text.strip()

    if len(full_name) < 2:
        await update.message.reply_text(text=get_string(lang, "ask_trader_name"))
        return states.TRADER_FULL_NAME

    context.user_data["trader_full_name"] = full_name

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(text=get_string(lang, "ask_trader_phone"))

    return states.TRADER_PHONE


async def received_trader_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف وينتقل لمرحلة الدولة.

    المُخرجات:
        int: states.TRADER_COUNTRY
    """
    lang = context.user_data.get("lang", "ar")

    phone = update.message.text.strip()
    context.user_data["trader_phone"] = phone

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(text=get_string(lang, "ask_trader_country"))

    return states.TRADER_COUNTRY


async def received_trader_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الدولة ويعرض قائمة اختيار نوع النشاط التجاري.

    المُخرجات:
        int: states.TRADER_BUSINESS_TYPE
    """
    lang = context.user_data.get("lang", "ar")

    country = update.message.text.strip()
    context.user_data["trader_country"] = country

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    await update.message.reply_text(
        text=get_string(lang, "ask_business_type"),
        reply_markup=_build_business_type_keyboard(lang)
    )

    return states.TRADER_BUSINESS_TYPE


async def received_trader_business_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نوع النشاط التجاري، يحفظ بيانات التاجر، ويُرسل إشعار للأدمن.

    المُخرجات:
        int: ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    business_type = query.data  # مثال: "business_online"

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    trader_data = {
        "telegram_id": str(query.from_user.id),
        "full_name": context.user_data.get("trader_full_name"),
        "phone": context.user_data.get("trader_phone"),
        "country": context.user_data.get("trader_country"),
        "business_type": business_type,
    }

    # بناء أزرار العودة للقائمة الرئيسية
    keyboard = [
        [InlineKeyboardButton(
            text=get_string(lang, "register_supplier_btn"),
            callback_data="supplier"
        )],
        [InlineKeyboardButton(
            text=get_string(lang, "change_language"),
            callback_data="change_language"
        )],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    success = database_service.save_trader(trader_data)

    if success:
        logger.info("✅ تم حفظ بيانات التاجر: telegram_id=%s", trader_data["telegram_id"])
        notification_service.notify_new_trader(trader_data)
        await query.edit_message_text(
            text=get_string(lang, "trader_success"),
            reply_markup=reply_markup
        )
    else:
        logger.error("❌ فشل حفظ بيانات التاجر: telegram_id=%s", trader_data["telegram_id"])
        await query.edit_message_text(
            text=get_string(lang, "error_general"),
            reply_markup=reply_markup
        )

    return ConversationHandler.END


async def cancel_trader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية تسجيل التاجر عند كتابة /cancel.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")
    await update.message.reply_text(text=get_string(lang, "cancel"))
    return ConversationHandler.END

# === bot/main.py ===
# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# المرحلة السادسة: إضافة ConversationHandlers للمنتجات والتصفح
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


def main() -> None:
    """
    الدالة الرئيسية لتشغيل البوت.

    تُسجّل جميع المعالجات بالترتيب الصحيح وتشغّل البوت.
    """
    logger.info("🚀 جاري تشغيل بوت TurkTextileHub - المرحلة السادسة...")

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
    # 3. ConversationHandler: إضافة منتج (جديد)
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
    # 4. ConversationHandler: تصفح المنتجات (جديد)
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

    # محادثات المنتجات (جديد)
    application.add_handler(product_conv)
    application.add_handler(browse_conv)

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

    application.run_polling()


# ===================================================
# نقطة الدخول
# ===================================================
if __name__ == "__main__":
    main()
```

## القسم الثاني: المتطلبات الفنية

الرجاء اتباع المتطلبات التفصيلية الموجودة في هذا الملف:

```markdown
# متطلبات تحسين تجربة ما بعد التسجيل

**تاريخ:** 27 فبراير 2026

## 1. الهدف

تحسين تجربة المستخدم بعد إكمال التسجيل كمورد أو تاجر، من خلال توجيهه مباشرة لخطوات مفيدة ومحفزة بدلاً من تركه في فراغ.

## 2. المتطلبات الفنية

### أ. تعديل رسالة نجاح تسجيل المورد

**الملف:** `bot/handlers/supplier_handler.py`

**الدالة:** `_finish_supplier_registration`

**التغيير:**
1.  تغيير نص `registration_success` في ملفات الترجمة (ar.json, en.json, tr.json) ليصبح:
    *   **ar:** "✅ تم تسجيلك كمورد بنجاح!\n\n📦 الخطوة التالية: أضف منتجاتك الآن!"
    *   **en:** "✅ You have been successfully registered as a supplier!\n\n📦 Next step: Add your products now!"
    *   **tr:** "✅ Tedarikçi olarak başarıyla kaydoldunuz!\n\n📦 Sonraki adım: Ürünlerinizi şimdi ekleyin!"
2.  إضافة لوحة مفاتيح `InlineKeyboardMarkup` لرسالة النجاح تحتوي على زر واحد:
    *   **النص:** `➕ إضافة منتج الآن` (من ملف الترجمة)
    *   **callback_data:** `add_product_now`

### ب. تعديل رسالة نجاح تسجيل التاجر

**الملف:** `bot/handlers/trader_handler.py`

**الدالة:** `received_trader_business_type`

**التغيير:**
1.  تغيير نص `trader_success` في ملفات الترجمة ليصبح:
    *   **ar:** "✅ تم تسجيلك كتاجر بنجاح!\n\n🎯 ماذا يمكنك فعله الآن؟"
    *   **en:** "✅ You have been successfully registered as a trader!\n\n🎯 What can you do now?"
    *   **tr:** "✅ Tüccar olarak başarıyla kaydoldunuz!\n\n🎯 Şimdi ne yapabilirsiniz?"
2.  تغيير لوحة المفاتيح `InlineKeyboardMarkup` الحالية لتتضمن الأزرار التالية:
    *   **الزر 1:**
        *   **النص:** `🔍 تصفح المنتجات` (من ملف الترجمة)
        *   **callback_data:** `browse_products_now`
    *   **الزر 2:**
        *   **النص:** `📞 تواصل مع مورد` (من ملف الترجمة)
        *   **callback_data:** `contact_supplier`
    *   **الزر 3:**
        *   **النص:** `⭐ المنتجات المميزة` (من ملف الترجمة)
        *   **callback_data:** `featured_products`

### ج. إضافة معالجات للأزرار الجديدة

**الملف:** `bot/main.py`

**التغيير:**
1.  إضافة `CallbackQueryHandler` جديد في `main` function (خارج أي `ConversationHandler`) لمعالجة الأزرار الجديدة:
    *   `add_product_now`: يستدعي دالة `start_product_registration` من `product_handler`.
    *   `browse_products_now`: يستدعي دالة `start_browsing` من `browse_handler`.
    *   `contact_supplier` و `featured_products`: حالياً، فقط أرسل رسالة "قيد الإنشاء" (سيتم بناؤها في مرحلة لاحقة).

## 3. ملفات الترجمة (JSON)

يجب إضافة المفاتيح الجديدة التالية لملفات `ar.json`, `en.json`, `tr.json` مع ترجمتها المناسبة:

*   `add_product_now_btn`
*   `browse_products_btn`
*   `contact_supplier_btn`
*   `featured_products_btn`
*   `coming_soon`

```

## القسم الثالث: المخرجات المطلوبة

أريد منك تزويدي بالنسخ المحدثة والكاملة للملفات التالية:

1.  `bot/handlers/supplier_handler.py`
2.  `bot/handlers/trader_handler.py`
3.  `bot/main.py`
4.  `bot/translations/ar.json`
5.  `bot/translations/en.json`
6.  `bot/translations/tr.json`

شكراً لك!
