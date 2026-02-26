# ===================================================
# bot/services/notification_service.py
# خدمة الإشعارات الفورية للأدمن عبر Telegram Bot API مباشرة
# تُرسل إشعاراً فورياً لكل تسجيل جديد (مورد أو تاجر)
# تستخدم requests مباشرة بدون python-telegram-bot
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from datetime import datetime

import requests

from bot.config import BOT_TOKEN, ADMIN_TELEGRAM_ID

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# ===================================================
# رابط Telegram Bot API لإرسال الرسائل
# يُستخدم مباشرة بدون أي مكتبة وسيطة
# ===================================================
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def _send_admin_message(text: str) -> bool:
    """
    دالة داخلية مساعدة: ترسل رسالة نصية HTML للأدمن عبر Telegram API.

    تُستخدم من قِبل notify_new_supplier و notify_new_trader.
    الإشعار الفاشل لا يوقف البوت - يُسجَّل الخطأ فقط.

    المعاملات:
        text (str): نص الرسالة بصيغة HTML

    المُخرجات:
        bool: True إذا وصلت الرسالة بنجاح، False في أي حالة أخرى
    """
    # التحقق من أن معرف الأدمن مضبوط قبل المحاولة
    if not ADMIN_TELEGRAM_ID:
        logger.warning("⚠️ ADMIN_TELEGRAM_ID غير مضبوط - تم تخطي إشعار الأدمن")
        return False

    # ===================================================
    # تجهيز جسم الطلب بصيغة JSON
    # parse_mode=HTML لتفعيل التنسيق (Bold, Italic...)
    # ===================================================
    payload = {
        "chat_id": ADMIN_TELEGRAM_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        # إرسال الطلب مع timeout لتجنب التعليق اللانهائي
        response = requests.post(TELEGRAM_API_URL, json=payload, timeout=10)

        # التحقق من نجاح الإرسال
        if response.status_code == 200:
            logger.info("✅ تم إرسال الإشعار للأدمن بنجاح")
            return True

        # تسجيل تفاصيل الخطأ دون إيقاف البوت
        logger.error(
            "❌ فشل إرسال الإشعار للأدمن: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال - لا تُوقف البوت
        logger.error("❌ خطأ في الاتصال بـ Telegram API عند إرسال الإشعار: %s", str(e))
        return False


def notify_new_supplier(supplier_data: dict) -> bool:
    """
    يُرسل إشعاراً فورياً للأدمن عند تسجيل مورد جديد.

    يُنسّق رسالة HTML بتفاصيل المورد ويُرسلها لمعرّف الأدمن المضبوط.
    في حال الفشل يُسجَّل الخطأ فقط دون إيقاف البوت.

    المعاملات:
        supplier_data (dict): قاموس يحتوي على:
            - company_name: اسم الشركة أو المتجر
            - contact_name: اسم جهة الاتصال
            - phone: رقم الهاتف
            - telegram_id: معرّف تليجرام

    المُخرجات:
        bool: True عند نجاح الإرسال، False عند الفشل
    """
    # ===================================================
    # تجهيز الوقت الحالي بصيغة موحدة للتقارير
    # ===================================================
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ===================================================
    # بناء نص الرسالة بصيغة HTML مع إيموجي توضيحية
    # ===================================================
    message_text = (
        "🏭 <b>مورد جديد تسجّل!</b>\n\n"
        f"👤 <b>اسم الشركة:</b> {supplier_data.get('company_name', 'غير محدد')}\n"
        f"🙋 <b>جهة الاتصال:</b> {supplier_data.get('contact_name', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {supplier_data.get('phone', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {supplier_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    # إرسال الرسالة عبر الدالة المساعدة المشتركة
    return _send_admin_message(message_text)


def notify_new_trader(trader_data: dict) -> bool:
    """
    يُرسل إشعاراً فورياً للأدمن عند تسجيل تاجر جديد.

    يُنسّق رسالة HTML بتفاصيل التاجر ويُرسلها لمعرّف الأدمن المضبوط.
    في حال الفشل يُسجَّل الخطأ فقط دون إيقاف البوت.

    المعاملات:
        trader_data (dict): قاموس يحتوي على:
            - full_name: الاسم الكامل للتاجر
            - phone: رقم الهاتف
            - country: الدولة
            - product_interest: نوع المنتج المفضل
            - telegram_id: معرّف تليجرام

    المُخرجات:
        bool: True عند نجاح الإرسال، False عند الفشل
    """
    # ===================================================
    # تجهيز الوقت الحالي بصيغة موحدة للتقارير
    # ===================================================
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ===================================================
    # بناء نص الرسالة بصيغة HTML مع إيموجي توضيحية
    # ===================================================
    message_text = (
        "🛒 <b>تاجر جديد تسجّل!</b>\n\n"
        f"👤 <b>الاسم الكامل:</b> {trader_data.get('full_name', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {trader_data.get('phone', 'غير محدد')}\n"
        f"🌍 <b>الدولة:</b> {trader_data.get('country', 'غير محدد')}\n"
        f"🏷 <b>اهتمامات المنتجات:</b> {trader_data.get('product_interest', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {trader_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    # إرسال الرسالة عبر الدالة المساعدة المشتركة
    return _send_admin_message(message_text)
