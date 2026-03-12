# ===================================================
# bot/handlers/stock_handler.py
# معالج إدارة المخزون — تحديث حالة المنتجات
#
# الوصف:
#   يتيح للموردين المعتمدين تحديث حالة منتجاتهم (متاح/نفذ).
#   التحكم الكامل يبقى في تطبيق KAYISOFT — البوت للإدخال السريع فقط.
#
# التدفق:
#   /my_products ← قائمة المنتجات ← تحديث الحالة ← إشعار
#
# الفلسفة:
#   تيليغرام = إدخال سريع + إشعارات
#   KAYISOFT = مركز القرار والإدارة الكاملة
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
from bot.services.language_service import get_string

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# نقطة الدخول: /my_products
# ──────────────────────────────────────────────────────────

async def show_my_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض قائمة منتجات المورد مع إمكانية تحديث الحالة.

    المنطق:
        1. التحقق من تسجيل المورد
        2. جلب منتجاته من قاعدة البيانات
        3. عرض القائمة مع أزرار التحديث
        4. زر "إدارة كاملة في التطبيق" للتفاصيل

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
            "⚠️ يجب أن تكون مورداً مسجلاً لعرض منتجاتك.\n"
            "اكتب /start للتسجيل."
        )
        return

    if supplier.get("status") != "approved":
        await update.message.reply_text(
            "⏳ حسابكم قيد المراجعة.\n"
            "سيتم إشعاركم عند الموافقة."
        )
        return

    # جلب منتجات المورد
    supplier_id = supplier.get("id")
    products = _get_supplier_products(supplier_id)

    if not products:
        keyboard = [[
            InlineKeyboardButton("➕ أضف منتجك الأول", callback_data="post_reg_add_product")
        ]]
        await update.message.reply_text(
            "📦 <b>لا توجد منتجات بعد</b>\n\n"
            "ابدأ بإضافة أول منتج لك.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # بناء رسالة القائمة
    text = f"📦 <b>منتجاتك</b> ({len(products)} منتج)\n\n"

    keyboard = []
    for product in products[:10]:  # بحد أقصى 10 منتجات في الرسالة
        title = product.get("title") or "منتج بدون اسم"
        status = product.get("status", "unknown")
        status_emoji = _get_status_emoji(status)
        product_id = product.get("id", "")

        text += f"{status_emoji} {title[:40]}\n"

        # زر تحديث الحالة لكل منتج
        if status == "active":
            keyboard.append([
                InlineKeyboardButton(
                    f"🔴 إيقاف: {title[:25]}",
                    callback_data=f"stock_deactivate_{product_id}"
                )
            ])
        elif status in ("inactive", "out_of_stock"):
            keyboard.append([
                InlineKeyboardButton(
                    f"🟢 تفعيل: {title[:25]}",
                    callback_data=f"stock_activate_{product_id}"
                )
            ])

    # زر الإدارة الكاملة في التطبيق
    keyboard.append([
        InlineKeyboardButton(
            "📱 إدارة كاملة في التطبيق ←",
            url="https://app.kayisoft.com/products"
        )
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ──────────────────────────────────────────────────────────
# معالجات الأزرار
# ──────────────────────────────────────────────────────────

async def handle_stock_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعالج أزرار تفعيل/إيقاف المنتجات.

    الأنماط المدعومة:
        stock_activate_{product_id}   — تفعيل منتج
        stock_deactivate_{product_id} — إيقاف منتج

    المدخلات:
        update  (Update)              : تحديث تليجرام (callback_query)
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات: لا شيء — يُحدّث الرسالة مباشرة
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    # التحقق من المورد
    supplier = database_service.get_supplier_by_telegram_id(str(user_id))
    if not supplier or supplier.get("status") != "approved":
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return

    # تحليل الإجراء ومعرّف المنتج
    if data.startswith("stock_activate_"):
        product_id = data.replace("stock_activate_", "")
        new_status = "active"
        action_text = "✅ تم تفعيل المنتج"
    elif data.startswith("stock_deactivate_"):
        product_id = data.replace("stock_deactivate_", "")
        new_status = "inactive"
        action_text = "🔴 تم إيقاف المنتج مؤقتاً"
    else:
        return

    # تحديث حالة المنتج
    success = _update_product_status(product_id, new_status, str(user_id))

    if success:
        await query.edit_message_text(
            f"{action_text}\n\n"
            f"💡 للإدارة الكاملة، استخدم تطبيق KAYISOFT.",
            parse_mode="HTML",
        )
    else:
        await query.answer("❌ فشل تحديث الحالة — حاول مرة أخرى", show_alert=True)


# ──────────────────────────────────────────────────────────
# دوال مساعدة
# ──────────────────────────────────────────────────────────

def _get_supplier_products(supplier_id: str) -> list:
    """
    يجلب منتجات مورد معين من قاعدة البيانات.

    المدخلات:
        supplier_id (str): UUID المورد

    المخرجات:
        list: قائمة المنتجات، أو قائمة فارغة عند الفشل
    """
    try:
        import requests as req
        from bot.config import SUPABASE_URL, SUPABASE_KEY
        from bot.services.database_service import HEADERS

        url = (
            f"{SUPABASE_URL}/rest/v1/products"
            f"?supplier_id=eq.{supplier_id}"
            f"&select=id,title,status,category,created_at"
            f"&order=created_at.desc"
            f"&limit=20"
        )
        response = req.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"❌ خطأ في جلب منتجات المورد {supplier_id}: {e}")
        return []


def _update_product_status(product_id: str, new_status: str, supplier_telegram_id: str) -> bool:
    """
    يحدّث حالة منتج في قاعدة البيانات مع التحقق من الملكية.

    المدخلات:
        product_id            (str): UUID المنتج
        new_status            (str): الحالة الجديدة — active|inactive
        supplier_telegram_id  (str): telegram_id المورد (للتحقق من الملكية)

    المخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    try:
        import requests as req
        from datetime import datetime
        from bot.config import SUPABASE_URL
        from bot.services.database_service import HEADERS

        url = f"{SUPABASE_URL}/rest/v1/products?id=eq.{product_id}"
        payload = {
            "status": new_status,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        response = req.patch(url, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ تم تحديث المنتج {product_id} → {new_status}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث حالة المنتج {product_id}: {e}")
        return False


def _get_status_emoji(status: str) -> str:
    """
    يُعيد رمز تعبيري يمثّل حالة المنتج.

    المدخلات:
        status (str): حالة المنتج

    المخرجات:
        str: رمز تعبيري مناسب
    """
    return {
        "active":        "🟢",
        "inactive":      "🔴",
        "pending":       "⏳",
        "out_of_stock":  "⚠️",
        "rejected":      "❌",
    }.get(status, "⚪")


# ──────────────────────────────────────────────────────────
# تسجيل المعالجات
# ──────────────────────────────────────────────────────────

def register_stock_handlers(application) -> None:
    """
    يُسجّل جميع معالجات إدارة المخزون في التطبيق.

    المدخلات:
        application: كائن Application من python-telegram-bot

    المخرجات: لا شيء
    """
    application.add_handler(CommandHandler("my_products", show_my_products))
    application.add_handler(
        CallbackQueryHandler(handle_stock_action, pattern="^stock_(activate|deactivate)_")
    )
    logger.info("✅ تم تسجيل معالجات إدارة المخزون")
