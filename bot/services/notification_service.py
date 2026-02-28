# ===================================================
# bot/services/notification_service.py
# خدمة الإشعارات الفورية للأدمن عبر Telegram Bot API مباشرة
# تُرسل إشعاراً فورياً لكل تسجيل جديد (مورد أو تاجر)
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from datetime import datetime

import requests

from bot.config import BOT_TOKEN, ADMIN_TELEGRAM_ID

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# رابط Telegram Bot API
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def _send_admin_message(text: str) -> bool:
    """
    دالة داخلية: ترسل رسالة HTML للأدمن عبر Telegram API.

    المعاملات:
        text (str): نص الرسالة بصيغة HTML

    المُخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    if not ADMIN_TELEGRAM_ID:
        logger.warning("⚠️ ADMIN_TELEGRAM_ID غير مضبوط - تم تخطي إشعار الأدمن")
        return False

    payload = {
        "chat_id": ADMIN_TELEGRAM_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(TELEGRAM_API_URL, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("✅ تم إرسال الإشعار للأدمن بنجاح")
            return True

        logger.error(
            "❌ فشل إرسال الإشعار للأدمن: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال بـ Telegram API: %s", str(e))
        return False


def notify_new_supplier(supplier_data: dict) -> bool:
    """
    يُرسل إشعاراً للأدمن عند تسجيل مورد جديد.

    المعاملات:
        supplier_data (dict): بيانات المورد (company_name, contact_name, city, phone, telegram_id)

    المُخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    message_text = (
        "🏭 <b>مورد جديد تسجّل!</b>\n\n"
        f"👤 <b>اسم الشركة:</b> {supplier_data.get('company_name', 'غير محدد')}\n"
        f"🙋 <b>جهة الاتصال:</b> {supplier_data.get('contact_name', 'غير محدد')}\n"
        f"📍 <b>المدينة:</b> {supplier_data.get('city', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {supplier_data.get('phone', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {supplier_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    return _send_admin_message(message_text)


def notify_new_trader(trader_data: dict) -> bool:
    """
    يُرسل إشعاراً للأدمن عند تسجيل تاجر جديد.

    المعاملات:
        trader_data (dict): بيانات التاجر (full_name, phone, country, business_type, telegram_id)

    المُخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    message_text = (
        "🛒 <b>تاجر جديد تسجّل!</b>\n\n"
        f"👤 <b>الاسم الكامل:</b> {trader_data.get('full_name', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {trader_data.get('phone', 'غير محدد')}\n"
        f"🌍 <b>الدولة:</b> {trader_data.get('country', 'غير محدد')}\n"
        f"💼 <b>نوع النشاط:</b> {trader_data.get('business_type', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {trader_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    return _send_admin_message(message_text)


def notify_new_product(supplier_data: dict, product_data: dict) -> bool:
    """
    يُرسل إشعاراً للأدمن عند إضافة منتج جديد.

    المعاملات:
        supplier_data (dict): بيانات المورد
        product_data (dict): بيانات المنتج (category, price)

    المُخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    publish_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    message_text = (
        "📦 <b>منتج جديد تم نشره!</b>\n\n"
        f"🏭 <b>المورد:</b> {supplier_data.get('company_name', 'غير محدد')}\n"
        f"📁 <b>الفئة:</b> {product_data.get('category', 'غير محدد')}\n"
        f"💰 <b>السعر:</b> {product_data.get('price', 'غير محدد')}\n"
        f"📅 <b>وقت النشر:</b> {publish_time}"
    )

    return _send_admin_message(message_text)

# ===================================================
# إشعارات طلبات عروض الأسعار - RFQ
# المرحلة السابعة
# ===================================================

def notify_quote_request_to_supplier(
    supplier_telegram_id: int,
    trader_name: str,
    trader_phone: str,
    trader_telegram_id: int,
    product_id: int,
    product_name: str,
    product_url,
    supplier_id: int,
    quantity=None,
    color=None,
    size=None,
    delivery_date=None,
) -> bool:
    """
    يرسل إشعار طلب عرض السعر للمورد مع زر تواصل مع التاجر.
    المُخرجات:
        bool: True إذا نجح الإرسال، False إذا فشل
    """
    try:
        lines = [
            "🔔 <b>طلب عرض سعر جديد!</b>",
            "",
            f"👤 <b>التاجر:</b> {trader_name}",
            f"📱 <b>الهاتف:</b> {trader_phone}",
            f"🛍 <b>المنتج:</b> {product_name} (#{product_id})",
            "",
            "📋 <b>تفاصيل الطلب:</b>",
        ]

        if quantity:
            lines.append(f"  📦 الكمية: {quantity}")
        if color:
            lines.append(f"  🎨 اللون: {color}")
        if size:
            lines.append(f"  📐 المقاس: {size}")
        if delivery_date:
            lines.append(f"  📅 تاريخ التسليم: {delivery_date}")

        if not any([quantity, color, size, delivery_date]):
            lines.append("  (لم يتم تحديد تفاصيل إضافية)")

        message_text = "\n".join(lines)

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "📞 تواصل مع التاجر",
                        "url": f"tg://user?id={trader_telegram_id}",
                    }
                ]
            ]
        }

        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": supplier_telegram_id,
                "text": message_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            },
            timeout=10,
        )
        response.raise_for_status()
        logger.info(
            "✅ تم إرسال إشعار RFQ للمورد %s للمنتج %s من التاجر %s",
            supplier_telegram_id, product_id, trader_telegram_id
        )
        return True

    except Exception as e:
        logger.error("❌ خطأ في إرسال إشعار RFQ للمورد: %s", str(e))
        return False


# ══════════════════════════════════════════════════════
# إشعارات الخطوة 6 — مستمع القناة
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
# مساعد داخلي — إرسال رسالة تليجرام
# ══════════════════════════════════════════════════════

def _send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """
    المدخلات:
        chat_id    (int): معرف المحادثة
        text       (str): نص الرسالة
        parse_mode (str): نمط التنسيق (HTML افتراضياً)
    المخرجات: True عند النجاح، False عند الفشل
    المنطق: دالة مساعدة داخلية لإرسال رسائل عبر Telegram Bot API مباشرة
    """
    try:
        response = requests.post(
            f"{_TELEGRAM_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        response.raise_for_status()
        logger.debug(f"✅ رسالة أُرسلت إلى {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال رسالة تليجرام إلى {chat_id}: {e}")
        return False


# ══════════════════════════════════════════════════════
# إشعار الأدمن عند نشر منتج من قناة
# ══════════════════════════════════════════════════════

def notify_channel_post_approved(
    admin_id: int,
    supplier_name: str,
    product_title: str,
) -> bool:
    """
    المدخلات:
        admin_id      (int): معرف الأدمن في تليجرام
        supplier_name (str): اسم شركة المورد
        product_title (str): عنوان المنتج المنشور
    المخرجات: True عند نجاح الإرسال، False عند الفشل
    المنطق: يُرسل إشعاراً للأدمن عند موافقة المورد على نشر منتج من قناته
    """
    text = (
        f"✅ <b>منتج جديد منشور!</b>\n\n"
        f"🏢 المورد: <b>{supplier_name}</b>\n"
        f"📦 المنتج: <b>{product_title}</b>\n\n"
        f"وافق المورد على نشر المنتج من قناته تلقائياً."
    )
    logger.info(f"📣 إشعار أدمن: {supplier_name} — {product_title}")
    return _send_message(admin_id, text)


# ══════════════════════════════════════════════════════
# تحذير المورد عند تجاوز الحد اليومي
# ══════════════════════════════════════════════════════

def notify_rate_limit_exceeded(
    supplier_telegram_id: int,
    lang: str = "ar",
) -> bool:
    """
    المدخلات:
        supplier_telegram_id (int): معرف المورد في تليجرام
        lang                 (str): لغة الرسالة — ar|tr|en (افتراضي: ar)
    المخرجات: True عند نجاح الإرسال، False عند الفشل
    المنطق: يُرسل تحذيراً للمورد عند تجاوز الحد اليومي للمنشورات (10 منشورات/يوم)
    """
    messages = {
        "ar": (
            "⚠️ لقد تجاوزت الحد اليومي (10 منشورات). يتجدد الحد غداً.\n\n"
            "📌 للحصول على حد أعلى، تواصل مع الدعم."
        ),
        "tr": (
            "⚠️ Günlük limitinizi aştınız (10 gönderi). Limit yarın yenilenir.\n\n"
            "📌 Daha yüksek bir limit için destek ile iletişime geçin."
        ),
        "en": (
            "⚠️ You've exceeded the daily limit (10 posts). The limit resets tomorrow.\n\n"
            "📌 Contact support for a higher limit."
        ),
    }
    text = messages.get(lang, messages["ar"])
    logger.warning(f"⚠️ تحذير rate limit للمورد {supplier_telegram_id}")
    return _send_message(supplier_telegram_id, text)
