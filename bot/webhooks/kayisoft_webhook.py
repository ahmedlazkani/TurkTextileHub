# ===================================================
# bot/webhooks/kayisoft_webhook.py
# معالج Webhooks القادمة من تطبيق KAYISOFT → البوت
#
# الوصف:
#   يستقبل إشعارات من تطبيق KAYISOFT عند تغيّر حالة المورد/المنتج/الطلب.
#   يُرسل رسائل تليجرام فورية للمورد أو التاجر عند كل تغيير.
#
# الأحداث المدعومة:
#   - supplier.approved     : تمت الموافقة على مورد
#   - supplier.rejected     : تم رفض مورد
#   - product.approved      : تمت الموافقة على منتج
#   - product.rejected      : تم رفض منتج
#   - quote.replied         : رد المورد على طلب عرض سعر
#
# التحقق من الأمان:
#   يتحقق من X-Webhook-Secret في رأس الطلب قبل معالجة أي حدث.
#   إذا غاب المفتاح أو كان خاطئاً → 401 Unauthorized.
#
# الاستخدام:
#   هذا الملف لا يُشغَّل مباشرة — يُدمج في خادم HTTP مستقل
#   (مثال: FastAPI أو Flask) يعمل بجانب البوت.
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import hashlib
import hmac
import logging
import os
from typing import Any, Optional

import requests

from bot.config import BOT_TOKEN

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# إعداد الأمان والثوابت
# ──────────────────────────────────────────────────────────

# المفتاح السري للتحقق من هوية KAYISOFT — يُضبط في Railway
_WEBHOOK_SECRET: str = os.getenv("KAYISOFT_WEBHOOK_SECRET", "")

# رابط Telegram Bot API لإرسال الرسائل مباشرة
_TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# الأحداث المدعومة
SUPPORTED_EVENTS = frozenset({
    "supplier.approved",
    "supplier.rejected",
    "product.approved",
    "product.rejected",
    "quote.replied",
})


# ──────────────────────────────────────────────────────────
# التحقق من صحة Webhook
# ──────────────────────────────────────────────────────────

def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    يتحقق من توقيع Webhook باستخدام HMAC-SHA256.

    المعاملات:
        payload_body     (bytes): جسم الطلب الخام (raw bytes).
        signature_header (str)  : قيمة رأس X-Webhook-Signature من KAYISOFT.

    المُخرجات:
        bool: True إذا كان التوقيع صحيحاً، False في أي حالة أخرى.

    الملاحظة:
        إذا لم يُضبط KAYISOFT_WEBHOOK_SECRET، يتجاوز التحقق دائماً بـ True.
        هذا السلوك مقبول في بيئة التطوير فقط — يجب ضبط المفتاح في الإنتاج.
    """
    if not _WEBHOOK_SECRET:
        logger.warning(
            "⚠️ KAYISOFT_WEBHOOK_SECRET غير مضبوط — "
            "التحقق من التوقيع معطّل (مقبول في التطوير فقط)"
        )
        return True

    if not signature_header:
        logger.warning("⚠️ رأس X-Webhook-Signature مفقود من الطلب")
        return False

    # حساب التوقيع المتوقع
    expected = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    # مقارنة آمنة ضد timing attacks
    is_valid = hmac.compare_digest(expected, signature_header)

    if not is_valid:
        logger.error("❌ توقيع Webhook غير صالح — الطلب مرفوض")

    return is_valid


# ──────────────────────────────────────────────────────────
# إرسال رسائل تليجرام
# ──────────────────────────────────────────────────────────

def _send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """
    دالة داخلية: ترسل رسالة تليجرام عبر Bot API مباشرة.

    المعاملات:
        chat_id    (int): معرّف المستخدم أو المحادثة.
        text       (str): نص الرسالة بصيغة HTML.
        parse_mode (str): نمط التنسيق (افتراضي: HTML).

    المُخرجات:
        bool: True عند النجاح، False عند الفشل.
    """
    try:
        response = requests.post(
            f"{_TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        if response.status_code == 200:
            logger.info(f"✅ رسالة تليجرام أُرسلت إلى {chat_id}")
            return True
        logger.error(
            f"❌ فشل إرسال رسالة تليجرام إلى {chat_id}: "
            f"status={response.status_code}, body={response.text[:200]}"
        )
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال رسالة تليجرام إلى {chat_id}: {e}")
        return False


# ──────────────────────────────────────────────────────────
# معالجات الأحداث
# ──────────────────────────────────────────────────────────

def _handle_supplier_approved(data: dict) -> dict:
    """
    يعالج حدث الموافقة على مورد — يُرسل رسالة تهنئة للمورد.

    المعاملات:
        data (dict): يحتوي على:
            - telegram_id  (int|str): معرّف المورد في تليجرام
            - company_name (str)    : اسم الشركة

    المُخرجات:
        dict: {"status": "ok" | "error", "message": str}
    """
    telegram_id = data.get("telegram_id")
    company_name = data.get("company_name", "شركتكم")

    if not telegram_id:
        logger.error("❌ supplier.approved: telegram_id مفقود في البيانات")
        return {"status": "error", "message": "telegram_id مفقود"}

    text = (
        f"🎉 <b>تهانينا! تمت الموافقة على حسابكم.</b>\n\n"
        f"🏭 <b>{company_name}</b> — مرحباً بكم في TurkTextileHub!\n\n"
        f"يمكنكم الآن:\n"
        f"• ➕ إضافة منتجاتكم\n"
        f"• 🔗 ربط قنوات تليجرام\n"
        f"• 📦 استقبال طلبات عروض الأسعار\n\n"
        f"ابدأ بكتابة /start"
    )

    success = _send_telegram_message(int(telegram_id), text)
    return {"status": "ok" if success else "error", "message": "supplier approval sent"}


def _handle_supplier_rejected(data: dict) -> dict:
    """
    يعالج حدث رفض مورد — يُرسل رسالة إشعار للمورد مع أزرار الدعم.

    المعاملات:
        data (dict): يحتوي على:
            - telegram_id (int|str): معرّف المورد في تليجرام
            - reason      (str)    : سبب الرفض (اختياري)

    المُخرجات:
        dict: {"status": "ok" | "error", "message": str}
    """
    telegram_id = data.get("telegram_id")
    reason = data.get("reason", "")

    if not telegram_id:
        logger.error("❌ supplier.rejected: telegram_id مفقود")
        return {"status": "error", "message": "telegram_id مفقود"}

    reason_line = f"\n📝 <b>السبب:</b> {reason}" if reason else ""

    text = (
        f"⚠️ <b>بخصوص طلب تسجيلكم</b>\n\n"
        f"نأسف لإبلاغكم بأنه لم تتم الموافقة على طلبكم في الوقت الحالي.{reason_line}\n\n"
        f"للمزيد من المعلومات أو لإعادة التقديم، اكتب /start"
    )

    success = _send_telegram_message(int(telegram_id), text)
    return {"status": "ok" if success else "error", "message": "supplier rejection sent"}


def _handle_product_approved(data: dict) -> dict:
    """
    يعالج حدث الموافقة على منتج — يُرسل إشعاراً للمورد.

    المعاملات:
        data (dict): يحتوي على:
            - supplier_telegram_id (int|str): معرّف المورد
            - product_title        (str)    : عنوان المنتج
            - product_id           (str)    : UUID المنتج

    المُخرجات:
        dict: {"status": "ok" | "error", "message": str}
    """
    telegram_id = data.get("supplier_telegram_id")
    product_title = data.get("product_title", "المنتج")

    if not telegram_id:
        logger.error("❌ product.approved: supplier_telegram_id مفقود")
        return {"status": "error", "message": "supplier_telegram_id مفقود"}

    text = (
        f"✅ <b>تمت الموافقة على منتجكم!</b>\n\n"
        f"📦 <b>{product_title}</b>\n\n"
        f"المنتج الآن مرئي للتجار ويمكنهم طلب عروض أسعار."
    )

    success = _send_telegram_message(int(telegram_id), text)
    return {"status": "ok" if success else "error", "message": "product approval sent"}


def _handle_product_rejected(data: dict) -> dict:
    """
    يعالج حدث رفض منتج — يُرسل إشعاراً للمورد مع سبب الرفض.

    المعاملات:
        data (dict): يحتوي على:
            - supplier_telegram_id (int|str): معرّف المورد
            - product_title        (str)    : عنوان المنتج
            - reason               (str)    : سبب الرفض (اختياري)

    المُخرجات:
        dict: {"status": "ok" | "error", "message": str}
    """
    telegram_id = data.get("supplier_telegram_id")
    product_title = data.get("product_title", "المنتج")
    reason = data.get("reason", "")

    if not telegram_id:
        logger.error("❌ product.rejected: supplier_telegram_id مفقود")
        return {"status": "error", "message": "supplier_telegram_id مفقود"}

    reason_line = f"\n📝 <b>السبب:</b> {reason}" if reason else ""

    text = (
        f"❌ <b>لم تتم الموافقة على منتجكم</b>\n\n"
        f"📦 <b>{product_title}</b>{reason_line}\n\n"
        f"يمكنكم تعديله وإعادة إرساله عبر /add_product"
    )

    success = _send_telegram_message(int(telegram_id), text)
    return {"status": "ok" if success else "error", "message": "product rejection sent"}


def _handle_quote_replied(data: dict) -> dict:
    """
    يعالج حدث رد المورد على طلب عرض سعر — يُرسل إشعاراً للتاجر.

    المعاملات:
        data (dict): يحتوي على:
            - trader_telegram_id (int|str): معرّف التاجر
            - supplier_name      (str)    : اسم شركة المورد
            - product_title      (str)    : عنوان المنتج
            - reply_message      (str)    : رسالة الرد من المورد

    المُخرجات:
        dict: {"status": "ok" | "error", "message": str}
    """
    telegram_id = data.get("trader_telegram_id")
    supplier_name = data.get("supplier_name", "المورد")
    product_title = data.get("product_title", "المنتج")
    reply_message = data.get("reply_message", "")

    if not telegram_id:
        logger.error("❌ quote.replied: trader_telegram_id مفقود")
        return {"status": "error", "message": "trader_telegram_id مفقود"}

    text = (
        f"📋 <b>رد على طلب عرض سعرك</b>\n\n"
        f"🏭 <b>المورد:</b> {supplier_name}\n"
        f"📦 <b>المنتج:</b> {product_title}\n\n"
        f"💬 <b>الرد:</b>\n{reply_message}"
    )

    success = _send_telegram_message(int(telegram_id), text)
    return {"status": "ok" if success else "error", "message": "quote reply sent"}


# ──────────────────────────────────────────────────────────
# الدالة الرئيسية — نقطة الدخول لكل Webhook
# ──────────────────────────────────────────────────────────

def process_webhook(event: str, data: dict) -> dict:
    """
    نقطة الدخول الرئيسية — تُوجّه الحدث للمعالج الصحيح.

    المعاملات:
        event (str) : نوع الحدث (مثال: "supplier.approved")
        data  (dict): بيانات الحدث من KAYISOFT

    المُخرجات:
        dict: {"status": "ok" | "error" | "ignored", "message": str}

    المنطق:
        1. تحقق من أن الحدث مدعوم
        2. وجّه للمعالج المناسب
        3. سجّل النتيجة وأعد استجابة JSON
    """
    logger.info(f"📨 Webhook مستلم: event={event}")

    if event not in SUPPORTED_EVENTS:
        logger.warning(f"⚠️ حدث غير مدعوم: {event} — تجاهل")
        return {"status": "ignored", "message": f"حدث غير مدعوم: {event}"}

    # خريطة الأحداث للمعالجات
    _handlers = {
        "supplier.approved": _handle_supplier_approved,
        "supplier.rejected": _handle_supplier_rejected,
        "product.approved":  _handle_product_approved,
        "product.rejected":  _handle_product_rejected,
        "quote.replied":     _handle_quote_replied,
    }

    handler = _handlers[event]

    try:
        result = handler(data)
        logger.info(f"✅ Webhook معالَج: event={event}, status={result.get('status')}")
        return result
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة Webhook event={event}: {e}")
        return {"status": "error", "message": str(e)}
