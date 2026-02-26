# ===================================================
# bot/services/database_service.py
# خدمة قاعدة البيانات - التواصل مع Supabase عبر REST API HTTP
# تستخدم مكتبة requests فقط بدون أي مكتبة خارجية إضافية
# يستخدم جدول bot_registrations المخصص للبوت
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

import requests

from bot.config import SUPABASE_KEY, SUPABASE_URL

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# ===================================================
# رأس الطلبات المشتركة لجميع الاتصالات بـ Supabase
# يتضمن مفتاح API والتفويض ونوع المحتوى
# ===================================================
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def save_supplier(supplier_data: dict) -> bool:
    """
    يحفظ بيانات المورد الجديد في جدول bot_registrations في Supabase.

    يُرسل طلب POST إلى REST API ويتحقق من نجاح العملية.
    يستخدم جدول bot_registrations المخصص للبوت والمستقل عن نظام المستخدمين.

    المعاملات:
        supplier_data (dict): قاموس يحتوي على بيانات المورد بالمفاتيح:
            - telegram_id: معرّف المستخدم في تليجرام
            - company_name: اسم الشركة أو المتجر
            - contact_name: اسم جهة الاتصال
            - phone: رقم الهاتف مع رمز الدولة

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح (رمز 201)، False في أي حالة أخرى
    """
    # ===================================================
    # بناء رابط نقطة النهاية لجدول bot_registrations
    # ===================================================
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations"

    # ===================================================
    # تجهيز البيانات المراد إرسالها إلى Supabase
    # ===================================================
    payload = {
        "telegram_id": str(supplier_data.get("telegram_id")),
        "company_name": supplier_data.get("company_name"),
        "contact_name": supplier_data.get("contact_name"),
        "phone": supplier_data.get("phone"),
        "status": "pending",
    }

    try:
        # إرسال طلب POST لحفظ بيانات المورد
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        # التحقق من نجاح العملية - Supabase يُرجع 201 عند الإنشاء الناجح
        if response.status_code == 201:
            logger.info(
                "✅ تم حفظ المورد في Supabase بنجاح: telegram_id=%s",
                supplier_data.get("telegram_id")
            )
            return True

        # تسجيل تفاصيل الخطأ في حال فشل الطلب
        logger.error(
            "❌ فشل حفظ المورد في Supabase: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء حفظ المورد: %s", str(e)
        )
        return False


def check_supplier_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود مورد مسجل مسبقاً باستخدام معرّف تليجرام.

    يُرسل طلب GET للبحث عن سجل يطابق telegram_id في جدول bot_registrations.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام

    المُخرجات:
        bool: True إذا كان المورد مسجلاً بالفعل، False إذا لم يكن أو حدث خطأ
    """
    # ===================================================
    # بناء رابط الاستعلام مع فلتر telegram_id
    # نستخدم eq. لمطابقة القيمة الدقيقة وselect=id لتحميل أقل قدر من البيانات
    # ===================================================
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        # إرسال طلب GET للبحث عن المورد
        response = requests.get(url, headers=HEADERS, timeout=10)

        # التحقق من نجاح الطلب
        if response.status_code == 200:
            results = response.json()

            # إذا كانت القائمة غير فارغة فالمورد مسجل مسبقاً
            if results:
                logger.info(
                    "⚠️ المورد مسجل مسبقاً في Supabase: telegram_id=%s",
                    telegram_id
                )
                return True

            # القائمة فارغة - المورد غير مسجل
            return False

        # تسجيل خطأ في حال فشل الطلب والرجوع بـ False
        logger.error(
            "❌ خطأ في التحقق من وجود المورد: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء التحقق من المورد: %s", str(e)
        )
        return False
