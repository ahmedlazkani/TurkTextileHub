# ===================================================
# bot/handlers/stats_handler.py
# معالج الإحصائيات — مسميات فقط بدون أرقام + Deep Link للتطبيق
#
# الوصف:
#   يعرض ملخصاً نصياً لإحصائيات المورد بدون أرقام حساسة.
#   الأرقام الكاملة والتحليلات في تطبيق KAYISOFT فقط.
#
# الفلسفة (v5.4 ثابتة):
#   /stats → مسميات فقط (منتجاتك، طلباتك، قنواتك)
#   لا أرقام في البوت — Deep Link للتفاصيل الكاملة
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
)

from bot.services import database_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# نقطة الدخول: /stats
# ──────────────────────────────────────────────────────────

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض ملخص إحصائيات المورد (مسميات فقط — بدون أرقام).

    المنطق (v5.4):
        - يعرض ما إذا كان للمورد منتجات / طلبات / قنوات
        - لا يكشف الأرقام الفعلية في البوت
        - زر Deep Link للتفاصيل الكاملة في التطبيق

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
            "⚠️ يجب أن تكون مورداً مسجلاً لعرض إحصائياتك.\n"
            "اكتب /start للتسجيل."
        )
        return

    if supplier.get("status") != "approved":
        await update.message.reply_text(
            "⏳ حسابكم قيد المراجعة. سيتم إشعاركم عند الموافقة."
        )
        return

    supplier_id = supplier.get("id")
    company_name = supplier.get("company_name", "شركتكم")

    # جلب ملخص الحالة (وجود/عدم وجود — لا أرقام)
    stats_summary = _get_stats_summary(supplier_id)

    # بناء رسالة المسميات
    lines = [
        f"📊 <b>ملخص حساب {company_name}</b>\n",
        f"{'✅' if stats_summary['has_products'] else '➕'} المنتجات: "
        f"{'لديك منتجات نشطة' if stats_summary['has_products'] else 'لا توجد منتجات بعد'}",

        f"{'📋' if stats_summary['has_pending_orders'] else '⚪'} الطلبات: "
        f"{'لديك طلبات تنتظر ردك' if stats_summary['has_pending_orders'] else 'لا طلبات معلقة'}",

        f"{'🔗' if stats_summary['has_channels'] else '➕'} القنوات: "
        f"{'قناة مربوطة' if stats_summary['has_channels'] else 'لا قنوات مربوطة'}",

        f"\n💡 <i>للإحصائيات الكاملة والتحليلات — افتح التطبيق</i>",
    ]

    text = "\n".join(lines)

    keyboard = [[
        InlineKeyboardButton(
            "📱 الإحصائيات الكاملة في التطبيق ←",
            url=f"https://app.kayisoft.com/dashboard"
        )
    ]]

    # أزرار الإجراءات السريعة
    quick_actions = []
    if not stats_summary["has_products"]:
        quick_actions.append(
            InlineKeyboardButton("➕ أضف منتج", callback_data="post_reg_add_product")
        )
    if not stats_summary["has_channels"]:
        quick_actions.append(
            InlineKeyboardButton("🔗 اربط قناة", callback_data="connect_channel_btn")
        )
    if quick_actions:
        keyboard.append(quick_actions)

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ──────────────────────────────────────────────────────────
# دوال مساعدة
# ──────────────────────────────────────────────────────────

def _get_stats_summary(supplier_id: str) -> dict:
    """
    يجلب ملخص بولياني لحالة المورد (وجود/عدم وجود فقط — لا أرقام).

    المدخلات:
        supplier_id (str): UUID المورد

    المخرجات:
        dict: {
            has_products       (bool): هل للمورد منتجات نشطة؟
            has_pending_orders (bool): هل لديه طلبات معلقة؟
            has_channels       (bool): هل لديه قنوات مربوطة؟
        }
    """
    result = {
        "has_products": False,
        "has_pending_orders": False,
        "has_channels": False,
    }

    try:
        import requests as req
        from bot.config import SUPABASE_URL
        from bot.services.database_service import HEADERS

        # فحص المنتجات النشطة (limit=1 للكفاءة)
        r = req.get(
            f"{SUPABASE_URL}/rest/v1/products"
            f"?supplier_id=eq.{supplier_id}&status=eq.active&select=id&limit=1",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200 and r.json():
            result["has_products"] = True

        # فحص الطلبات المعلقة
        r = req.get(
            f"{SUPABASE_URL}/rest/v1/quote_requests"
            f"?supplier_id=eq.{supplier_id}&status=eq.pending&select=id&limit=1",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200 and r.json():
            result["has_pending_orders"] = True

        # فحص القنوات المربوطة
        channels = database_service.get_supplier_channels(supplier_id)
        result["has_channels"] = len(channels) > 0

    except Exception as e:
        logger.error(f"❌ خطأ في جلب ملخص إحصائيات المورد {supplier_id}: {e}")

    return result


# ──────────────────────────────────────────────────────────
# تسجيل المعالجات
# ──────────────────────────────────────────────────────────

def register_stats_handlers(application) -> None:
    """
    يُسجّل معالجات الإحصائيات في التطبيق.

    المدخلات:
        application: كائن Application من python-telegram-bot

    المخرجات: لا شيء
    """
    application.add_handler(CommandHandler("stats", show_stats))
    logger.info("✅ تم تسجيل معالجات الإحصائيات")
