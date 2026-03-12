# ===================================================
# bot/handlers/order_handler.py
# معالج إشعارات الطلبات — عرض سريع + Deep Link للتطبيق
#
# الوصف:
#   يعرض إشعارات طلبات عروض الأسعار للموردين.
#   القرار الكامل (قبول/رفض/تفاوض) في تطبيق KAYISOFT فقط.
#
# الفلسفة (v5.4 ثابتة):
#   - البوت يُظهر الإشعار فقط
#   - زر واحد: "إدارة الطلب في التطبيق" ← Deep Link
#   - لا قرارات في البوت
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.services import database_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# نقطة الدخول: /my_orders
# ──────────────────────────────────────────────────────────

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض آخر طلبات عروض الأسعار للمورد مع Deep Link للتطبيق.

    المنطق:
        1. التحقق من تسجيل المورد وموافقته
        2. جلب آخر طلبات عروض الأسعار المعلقة
        3. عرض ملخص سريع لكل طلب
        4. زر واحد لكل طلب → Deep Link في KAYISOFT

    المدخلات:
        update  (Update)              : تحديث تليجرام
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات: لا شيء — يُرسل رسالة تليجرام مباشرة
    """
    user_id = update.effective_user.id

    # التحقق من تسجيل المورد
    supplier = database_service.get_supplier_by_telegram_id(str(user_id))
    if not supplier:
        await update.message.reply_text(
            "⚠️ يجب أن تكون مورداً مسجلاً لعرض طلباتك.\n"
            "اكتب /start للتسجيل."
        )
        return

    if supplier.get("status") != "approved":
        await update.message.reply_text(
            "⏳ حسابكم قيد المراجعة. سيتم إشعاركم عند الموافقة."
        )
        return

    # جلب الطلبات المعلقة
    supplier_id = supplier.get("id")
    orders = _get_pending_orders(supplier_id)

    if not orders:
        keyboard = [[
            InlineKeyboardButton(
                "📱 عرض كل الطلبات في التطبيق",
                url="https://app.kayisoft.com/orders"
            )
        ]]
        await update.message.reply_text(
            "📋 <b>لا توجد طلبات معلقة</b>\n\n"
            "جميع طلبات عروض الأسعار ستظهر هنا فور وصولها.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # عرض الطلبات
    text = f"📋 <b>طلبات عروض الأسعار المعلقة</b> ({len(orders)})\n\n"
    keyboard = []

    for order in orders[:5]:  # بحد أقصى 5 طلبات
        order_id = order.get("id", "")
        product = order.get("products") or {}
        product_title = product.get("title") or "منتج"
        quantity = order.get("quantity") or "—"
        created_at = order.get("created_at", "")[:10]  # YYYY-MM-DD فقط

        text += (
            f"🔹 <b>{product_title[:35]}</b>\n"
            f"   الكمية: {quantity} | {created_at}\n\n"
        )

        # زر واحد فقط — Deep Link للتطبيق
        keyboard.append([
            InlineKeyboardButton(
                f"📱 إدارة الطلب في التطبيق ←",
                url=f"https://app.kayisoft.com/orders/{order_id}"
            )
        ])

    # زر عرض الكل
    if len(orders) > 5:
        text += f"... و{len(orders) - 5} طلبات أخرى\n"

    keyboard.append([
        InlineKeyboardButton(
            "📱 عرض كل الطلبات",
            url="https://app.kayisoft.com/orders"
        )
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ──────────────────────────────────────────────────────────
# إرسال إشعار طلب جديد للمورد (تُستدعى من webhook)
# ──────────────────────────────────────────────────────────

async def notify_supplier_new_order(
    bot,
    supplier_telegram_id: int,
    order_data: dict,
) -> bool:
    """
    يُرسل إشعار طلب عرض سعر جديد للمورد.

    يُستدعى من kayisoft_webhook عند وصول طلب جديد.

    المنطق (v5.4):
        - رسالة مختصرة بمعلومات الطلب
        - زر واحد: "إدارة الطلب في التطبيق"
        - لا أزرار قبول/رفض في البوت

    المدخلات:
        bot                  (Bot) : كائن البوت
        supplier_telegram_id (int) : telegram_id المورد
        order_data           (dict): بيانات الطلب

    المخرجات:
        bool: True عند نجاح الإرسال، False عند الفشل
    """
    try:
        order_id = order_data.get("id", "")
        product_title = order_data.get("product_title", "منتج")
        trader_country = order_data.get("trader_country", "—")
        quantity = order_data.get("quantity", "—")

        text = (
            f"🔔 <b>طلب عرض سعر جديد!</b>\n\n"
            f"📦 <b>المنتج:</b> {product_title}\n"
            f"🌍 <b>الدولة:</b> {trader_country}\n"
            f"📊 <b>الكمية:</b> {quantity}\n\n"
            f"💡 للرد والتفاصيل الكاملة — افتح التطبيق"
        )

        keyboard = [[
            InlineKeyboardButton(
                "📱 إدارة الطلب في التطبيق ←",
                url=f"https://app.kayisoft.com/orders/{order_id}"
            )
        ]]

        await bot.send_message(
            chat_id=supplier_telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        logger.info(f"✅ إشعار طلب جديد أُرسل للمورد {supplier_telegram_id}")
        return True

    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار طلب للمورد {supplier_telegram_id}: {e}")
        return False


# ──────────────────────────────────────────────────────────
# دوال مساعدة
# ──────────────────────────────────────────────────────────

def _get_pending_orders(supplier_id: str) -> list:
    """
    يجلب طلبات عروض الأسعار المعلقة لمورد معين.

    المدخلات:
        supplier_id (str): UUID المورد

    المخرجات:
        list: قائمة الطلبات المعلقة مع بيانات المنتج، أو قائمة فارغة
    """
    try:
        import requests as req
        from bot.config import SUPABASE_URL
        from bot.services.database_service import HEADERS

        url = (
            f"{SUPABASE_URL}/rest/v1/quote_requests"
            f"?supplier_id=eq.{supplier_id}"
            f"&status=eq.pending"
            f"&select=id,quantity,color,size,created_at,products(title,category)"
            f"&order=created_at.desc"
            f"&limit=10"
        )
        response = req.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"❌ خطأ في جلب طلبات المورد {supplier_id}: {e}")
        return []


# ──────────────────────────────────────────────────────────
# تسجيل المعالجات
# ──────────────────────────────────────────────────────────

def register_order_handlers(application) -> None:
    """
    يُسجّل معالجات الطلبات في التطبيق.

    المدخلات:
        application: كائن Application من python-telegram-bot

    المخرجات: لا شيء
    """
    application.add_handler(CommandHandler("my_orders", show_my_orders))
    logger.info("✅ تم تسجيل معالجات الطلبات")
