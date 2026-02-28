"""
bot/handlers/browse_handler.py
معالج تصفح المنتجات وتدفق طلب عرض السعر (RFQ)

الوصف:
    يتيح للتجار تصفح المنتجات والتقدم بطلبات عروض أسعار للموردين.
    يتضمن ConversationHandler كامل لتدفق RFQ متعدد الخطوات.

تدفق RFQ:
    1. التاجر يضغط "طلب عرض سعر" على منتج     → request_quote()
    2. يُسأل عن الكمية                          → handle_quote_quantity()
    3. يُسأل عن اللون                           → handle_quote_color()
    4. يُسأل عن المقاس                          → handle_quote_size()
    5. يُسأل عن تاريخ التسليم المطلوب           → handle_quote_delivery_date()
    6. يُعرض ملخص للتأكيد                       → confirm_quote_request()
    7. يُحفظ الطلب في DB وُيرسَل إشعار للمورد  → (داخل confirm_quote_request)

المتغيرات في context.user_data:
    RFQ_DATA_KEY (dict): {
        "product"         : dict — بيانات المنتج الكاملة
        "trader"          : dict — بيانات التاجر الكاملة
        "quantity"        : str  — الكمية المطلوبة
        "color"           : str  — اللون المطلوب
        "size"            : str  — المقاس المطلوب
        "delivery_date"   : str  — تاريخ التسليم المطلوب
    }
"""

import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from bot.services import database_service, notification_service
from bot.services.language_service import get_string
from bot import states

logger = logging.getLogger(__name__)

# ── مفتاح تخزين بيانات RFQ في user_data ─────────────────────────────────────
RFQ_DATA_KEY = "rfq_data"


# ══════════════════════════════════════════════════════════════════════════════
# 1. نقطة دخول تدفق RFQ — يُفعَّل بضغطة زر "طلب عرض سعر"
# ══════════════════════════════════════════════════════════════════════════════

async def request_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    نقطة دخول تدفق RFQ — تُفعَّل بـ CallbackQueryHandler(pattern="^request_quote_").

    المدخلات:
        update  : يحتوي على callback_query بـ callback_data="request_quote_{product_id}"
        context : context.user_data["browse_products"] — قائمة المنتجات المعروضة حالياً

    المخرجات:
        يحفظ المنتج والتاجر في context.user_data[RFQ_DATA_KEY]
        يُرسل سؤال الكمية
        يعيد states.GETTING_QUOTE_QUANTITY

    المنطق:
        1. استخرج product_id من callback_data
        2. ابحث عن المنتج في browse_products المخزّنة
        3. اجلب بيانات التاجر من DB بـ telegram_id
        4. احفظ المنتج والتاجر في RFQ_DATA_KEY
        5. ابدأ بسؤال الكمية
    """
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    lang    = context.user_data.get("lang", "ar")

    # 1. استخرج product_id من callback_data ("request_quote_{product_id}")
    product_id: str = query.data.replace("request_quote_", "", 1)
    logger.info(f"🛒 طلب عرض سعر | trader={user_id} | product={product_id}")

    # 2. ابحث عن المنتج في قائمة المنتجات المعروضة حالياً
    browse_products: list = context.user_data.get("browse_products", [])
    product: Optional[dict] = next(
        (p for p in browse_products if str(p.get("id")) == product_id),
        None,
    )

    if not product:
        # حاول جلب المنتج من DB إذا لم يوجد في الذاكرة
        try:
            product = database_service.get_product_by_id(product_id)
        except Exception as e:
            logger.error(f"❌ خطأ في جلب المنتج {product_id}: {e}")

    if not product:
        logger.warning(f"⚠️ المنتج {product_id} غير موجود")
        await query.edit_message_text(
            get_string(lang, "product_not_found")
        )
        return ConversationHandler.END

    # 3. اجلب بيانات التاجر من DB
    try:
        trader: Optional[dict] = database_service.get_trader_by_telegram_id(user_id)
    except Exception as e:
        logger.error(f"❌ خطأ في جلب التاجر {user_id}: {e}")
        trader = None

    if not trader:
        logger.warning(f"⚠️ التاجر {user_id} غير مسجّل")
        await query.edit_message_text(
            get_string(lang, "trader_not_registered")
        )
        return ConversationHandler.END

    # ═══ تحقق من حالة حساب التاجر ═══
    trader_status = trader.get("status", "pending")
    if trader_status == "pending":
        logger.warning(f"⚠️ التاجر {user_id} لا يزال حسابه قيد المراجعة")
        await query.edit_message_text(
            f"⏳ {get_string(lang, 'status_pending')}\n\n"
            f"لا يمكن تقديم طلب عرض سعر حتى يتم اعتماد حسابك من قِبَل الإدارة.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    elif trader_status == "rejected":
        logger.warning(f"⚠️ التاجر {user_id} حسابه مرفوض")
        await query.edit_message_text(
            f"❌ {get_string(lang, 'status_rejected')}\n\n"
            f"حسابك مرفوض. للاستفسار تواصل مع الدعم.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    # trader_status == "approved" → متاحة المتابعة
    logger.info(f"✅ حالة التاجر {user_id}: {trader_status} — مسموح بطلب RFQ")

    # 4. احفظ المنتج والتاجر في RFQ_DATA_KEY
    context.user_data[RFQ_DATA_KEY] = {
        "product":       product,
        "trader":        trader,
        "quantity":      None,
        "color":         None,
        "size":          None,
        "delivery_date": None,
    }

    product_title = product.get("title") or product.get("name") or get_string(lang, "unknown_product")
    logger.info(f"✅ RFQ بدأ | منتج: {product_title} | تاجر: {trader.get('id')}")

    # 5. ابدأ بسؤال الكمية
    await query.edit_message_text(
        f"📋 *{get_string(lang, 'rfq_started')}*\n"
        f"🏷 {get_string(lang, 'product')}: *{product_title}*\n\n"
        f"1️⃣ {get_string(lang, 'rfq_ask_quantity')}",
        parse_mode="Markdown",
    )

    return states.GETTING_QUOTE_QUANTITY


# ══════════════════════════════════════════════════════════════════════════════
# 2. استقبال الكمية
# ══════════════════════════════════════════════════════════════════════════════

async def handle_quote_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: رسالة نصية تحتوي على الكمية المطلوبة
    المخرجات: يحفظ الكمية في RFQ_DATA_KEY ويسأل عن اللون
    يعيد: states.GETTING_QUOTE_COLOR
    """
    lang     = context.user_data.get("lang", "ar")
    quantity = update.message.text.strip()

    if not quantity:
        await update.message.reply_text(get_string(lang, "rfq_quantity_required"))
        return states.GETTING_QUOTE_QUANTITY

    context.user_data[RFQ_DATA_KEY]["quantity"] = quantity
    logger.debug(f"✅ RFQ الكمية: {quantity}")

    await update.message.reply_text(
        f"✅ {get_string(lang, 'rfq_quantity_saved')}: *{quantity}*\n\n"
        f"2️⃣ {get_string(lang, 'rfq_ask_color')}",
        parse_mode="Markdown",
    )
    return states.GETTING_QUOTE_COLOR


# ══════════════════════════════════════════════════════════════════════════════
# 3. استقبال اللون
# ══════════════════════════════════════════════════════════════════════════════

async def handle_quote_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: رسالة نصية تحتوي على اللون المطلوب
    المخرجات: يحفظ اللون في RFQ_DATA_KEY ويسأل عن المقاس
    يعيد: states.GETTING_QUOTE_SIZE
    """
    lang  = context.user_data.get("lang", "ar")
    color = update.message.text.strip()

    if not color:
        await update.message.reply_text(get_string(lang, "rfq_color_required"))
        return states.GETTING_QUOTE_COLOR

    context.user_data[RFQ_DATA_KEY]["color"] = color
    logger.debug(f"✅ RFQ اللون: {color}")

    await update.message.reply_text(
        f"✅ {get_string(lang, 'rfq_color_saved')}: *{color}*\n\n"
        f"3️⃣ {get_string(lang, 'rfq_ask_size')}",
        parse_mode="Markdown",
    )
    return states.GETTING_QUOTE_SIZE


# ══════════════════════════════════════════════════════════════════════════════
# 4. استقبال المقاس
# ══════════════════════════════════════════════════════════════════════════════

async def handle_quote_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: رسالة نصية تحتوي على المقاس المطلوب
    المخرجات: يحفظ المقاس في RFQ_DATA_KEY ويسأل عن تاريخ التسليم
    يعيد: states.GETTING_QUOTE_DELIVERY_DATE
    """
    lang = context.user_data.get("lang", "ar")
    size = update.message.text.strip()

    if not size:
        await update.message.reply_text(get_string(lang, "rfq_size_required"))
        return states.GETTING_QUOTE_SIZE

    context.user_data[RFQ_DATA_KEY]["size"] = size
    logger.debug(f"✅ RFQ المقاس: {size}")

    await update.message.reply_text(
        f"✅ {get_string(lang, 'rfq_size_saved')}: *{size}*\n\n"
        f"4️⃣ {get_string(lang, 'rfq_ask_delivery_date')}\n"
        f"_({get_string(lang, 'rfq_date_format_hint')})_",
        parse_mode="Markdown",
    )
    return states.GETTING_QUOTE_DELIVERY_DATE


# ══════════════════════════════════════════════════════════════════════════════
# 5. استقبال تاريخ التسليم
# ══════════════════════════════════════════════════════════════════════════════

async def handle_quote_delivery_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: رسالة نصية تحتوي على تاريخ التسليم المطلوب
    المخرجات: يحفظ التاريخ في RFQ_DATA_KEY ويعرض ملخص التأكيد
    يعيد: states.CONFIRM_QUOTE_REQUEST
    """
    lang          = context.user_data.get("lang", "ar")
    delivery_date = update.message.text.strip()

    if not delivery_date:
        await update.message.reply_text(get_string(lang, "rfq_date_required"))
        return states.GETTING_QUOTE_DELIVERY_DATE

    context.user_data[RFQ_DATA_KEY]["delivery_date"] = delivery_date
    logger.debug(f"✅ RFQ تاريخ التسليم: {delivery_date}")

    # بناء ملخص التأكيد
    rfq = context.user_data[RFQ_DATA_KEY]
    product = rfq["product"]
    product_title = product.get("title") or product.get("name") or get_string(lang, "unknown_product")

    summary = (
        f"📋 *{get_string(lang, 'rfq_confirm_title')}*\n\n"
        f"🏷 {get_string(lang, 'product')}: *{product_title}*\n"
        f"📦 {get_string(lang, 'rfq_quantity')}: *{rfq['quantity']}*\n"
        f"🎨 {get_string(lang, 'rfq_color')}: *{rfq['color']}*\n"
        f"📐 {get_string(lang, 'rfq_size')}: *{rfq['size']}*\n"
        f"📅 {get_string(lang, 'rfq_delivery_date')}: *{delivery_date}*\n\n"
        f"{get_string(lang, 'rfq_confirm_prompt')}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"✅ {get_string(lang, 'rfq_confirm_btn')}",
                callback_data="rfq_confirm",
            ),
            InlineKeyboardButton(
                f"❌ {get_string(lang, 'rfq_cancel_btn')}",
                callback_data="rfq_cancel",
            ),
        ]
    ])

    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=keyboard)
    return states.CONFIRM_QUOTE_REQUEST


# ══════════════════════════════════════════════════════════════════════════════
# 6. التأكيد النهائي — يحفظ في DB ويُرسل إشعار للمورد
# ══════════════════════════════════════════════════════════════════════════════

async def confirm_quote_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: callback_query بـ data="rfq_confirm" أو "rfq_cancel"
    المخرجات:
        - عند التأكيد: يحفظ الطلب في DB، يُرسل إشعار للمورد، يُظهر رسالة نجاح
        - عند الإلغاء: يُلغي التدفق ويُظهر رسالة إلغاء
    يعيد: ConversationHandler.END

    المنطق (عند التأكيد):
        1. استخرج بيانات RFQ من context.user_data[RFQ_DATA_KEY]
        2. استخرج supplier_id من المنتج
        3. استخرج trader_id من التاجر (trader["id"] UUID في جدول traders)
        4. استدع add_quote_request بجميع البيانات
        5. استدع notify_quote_request_to_supplier بـ trader_telegram_id
        6. امسح RFQ_DATA_KEY من user_data
    """
    query = update.callback_query
    await query.answer()

    lang   = context.user_data.get("lang", "ar")
    action = query.data  # "rfq_confirm" أو "rfq_cancel"

    # ── الإلغاء ────────────────────────────────────────────────────────────
    if action == "rfq_cancel":
        context.user_data.pop(RFQ_DATA_KEY, None)
        logger.info(f"❌ RFQ ملغى | user={query.from_user.id}")
        await query.edit_message_text(
            f"❌ {get_string(lang, 'rfq_cancelled')}"
        )
        return ConversationHandler.END

    # ── التأكيد ────────────────────────────────────────────────────────────
    rfq = context.user_data.get(RFQ_DATA_KEY)
    if not rfq:
        logger.error("❌ RFQ_DATA_KEY مفقود عند التأكيد")
        await query.edit_message_text(get_string(lang, "rfq_session_expired"))
        return ConversationHandler.END

    product = rfq["product"]
    trader  = rfq["trader"]

    # 2. supplier_id من المنتج
    supplier_id: Optional[str] = product.get("supplier_id")
    if not supplier_id:
        logger.error(f"❌ supplier_id مفقود في المنتج {product.get('id')}")
        await query.edit_message_text(get_string(lang, "rfq_error"))
        return ConversationHandler.END

    # 3. trader_id = UUID في جدول traders، trader_telegram_id = Telegram ID
    trader_id: Optional[str]            = trader.get("id")
    trader_telegram_id: Optional[int]   = trader.get("telegram_id")

    if not trader_id or not trader_telegram_id:
        logger.error(f"❌ بيانات التاجر ناقصة: id={trader_id}, telegram_id={trader_telegram_id}")
        await query.edit_message_text(get_string(lang, "rfq_error"))
        return ConversationHandler.END

    # 4. حفظ الطلب في DB
    quote_data = {
        "product_id":    product.get("id"),
        "supplier_id":   supplier_id,          # UUID المورد
        "trader_id":     trader_telegram_id,   # bigint = Telegram ID (كما في schema)
        "quantity":      rfq["quantity"],
        "color":         rfq["color"],
        "size":          rfq["size"],
        "delivery_date": rfq["delivery_date"],
        "status":        "pending",
    }

    try:
        saved_quote = database_service.add_quote_request(quote_data)
        quote_id    = saved_quote.get("id") if saved_quote else "N/A"
        logger.info(f"✅ طلب RFQ حُفظ | id={quote_id} | product={product.get('id')}")
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ طلب RFQ: {e}")
        await query.edit_message_text(get_string(lang, "rfq_save_error"))
        return ConversationHandler.END

    # 5. إرسال إشعار للمورد
    try:
        notification_service.notify_quote_request_to_supplier(
            supplier_id=supplier_id,
            trader_telegram_id=trader_telegram_id,  # يُمرَّر للإشعار
            quote_data={
                "product_title": product.get("title") or product.get("name", ""),
                "quantity":      rfq["quantity"],
                "color":         rfq["color"],
                "size":          rfq["size"],
                "delivery_date": rfq["delivery_date"],
                "quote_id":      quote_id,
            },
        )
        logger.info(f"📣 إشعار أُرسل للمورد {supplier_id}")
    except Exception as e:
        # الإشعار اختياري — لا يُوقف التدفق
        logger.error(f"⚠️ خطأ في إشعار المورد (غير مُوقِف): {e}")

    # 6. امسح RFQ_DATA_KEY
    context.user_data.pop(RFQ_DATA_KEY, None)

    # رسالة النجاح للتاجر
    product_title = product.get("title") or product.get("name") or get_string(lang, "unknown_product")
    await query.edit_message_text(
        f"✅ *{get_string(lang, 'rfq_success_title')}*\n\n"
        f"🏷 {get_string(lang, 'product')}: *{product_title}*\n"
        f"🔖 {get_string(lang, 'rfq_reference')}: `{quote_id}`\n\n"
        f"ℹ️ {get_string(lang, 'rfq_success_note')}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# 7. إلغاء تدفق RFQ بـ /cancel
# ══════════════════════════════════════════════════════════════════════════════

async def cancel_rfq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: أمر /cancel أو أي رسالة خارج السياق
    المخرجات: ينهي ConversationHandler ويمسح RFQ_DATA_KEY
    يعيد: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")
    context.user_data.pop(RFQ_DATA_KEY, None)
    logger.info(f"🚫 RFQ ملغى بـ /cancel | user={update.effective_user.id}")

    if update.message:
        await update.message.reply_text(f"❌ {get_string(lang, 'rfq_cancelled')}")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# 8. ConversationHandler الكامل لـ RFQ
# ══════════════════════════════════════════════════════════════════════════════

def get_rfq_conversation_handler() -> ConversationHandler:
    """
    المدخلات: لا يوجد
    المخرجات: ConversationHandler جاهز للتسجيل في main.py

    الحالات:
        GETTING_QUOTE_QUANTITY  : انتظار الكمية
        GETTING_QUOTE_COLOR     : انتظار اللون
        GETTING_QUOTE_SIZE      : انتظار المقاس
        GETTING_QUOTE_DELIVERY_DATE: انتظار تاريخ التسليم
        CONFIRM_QUOTE_REQUEST   : انتظار التأكيد أو الإلغاء

    نقطة الدخول: callback_data يبدأ بـ "request_quote_"
    """
    text_filter = filters.TEXT & ~filters.COMMAND

    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_quote, pattern="^request_quote_"),
        ],
        states={
            states.GETTING_QUOTE_QUANTITY: [
                MessageHandler(text_filter, handle_quote_quantity),
            ],
            states.GETTING_QUOTE_COLOR: [
                MessageHandler(text_filter, handle_quote_color),
            ],
            states.GETTING_QUOTE_SIZE: [
                MessageHandler(text_filter, handle_quote_size),
            ],
            states.GETTING_QUOTE_DELIVERY_DATE: [
                MessageHandler(text_filter, handle_quote_delivery_date),
            ],
            states.CONFIRM_QUOTE_REQUEST: [
                CallbackQueryHandler(confirm_quote_request, pattern="^rfq_(confirm|cancel)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_rfq),
            MessageHandler(filters.COMMAND, cancel_rfq),
        ],
        per_message=False,
        name="rfq_conversation",
    )
