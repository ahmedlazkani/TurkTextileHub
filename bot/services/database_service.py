# ===================================================
# bot/services/database_service.py
# خدمة قاعدة البيانات - التواصل مع Supabase عبر REST API HTTP
# تستخدم مكتبة requests فقط بدون أي مكتبة خارجية إضافية
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


# ===================================================
# دوال الموردين
# ===================================================

def save_supplier(supplier_data: dict) -> bool:
    """
    يحفظ بيانات المورد الجديد في جدول suppliers في Supabase.

    يُرسل طلب POST إلى REST API ويتحقق من نجاح العملية.
    لا يُنشئ جدولاً جديداً - الجدول موجود بالفعل في Supabase.

    ملاحظة: نحفظ telegram_id في عمود user_id لعدم وجود عمود مستقل له.

    المعاملات:
        supplier_data (dict): قاموس يحتوي على:
            - telegram_id: معرّف المستخدم في تليجرام
            - company_name: اسم الشركة أو المتجر
            - contact_name: اسم جهة الاتصال
            - phone: رقم الهاتف مع رمز الدولة

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح (رمز 201)، False في أي حالة أخرى
    """
    # بناء رابط نقطة النهاية لجدول suppliers
    url = f"{SUPABASE_URL}/rest/v1/suppliers/"

    # ===================================================
    # تجهيز البيانات المراد إرسالها إلى Supabase
    # القيم الثابتة تُضاف هنا لتهيئة السجل الجديد
    # ===================================================
    payload = {
        "user_id": supplier_data.get("telegram_id"),   # نحفظ telegram_id في user_id
        "business_name": supplier_data.get("company_name"),
        "whatsapp": supplier_data.get("phone"),
        "verification_status": "pending",
        "reputation_score": 0,
        "total_products": 0,
        "total_rfqs": 0,
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

    يُرسل طلب GET للبحث عن سجل يطابق telegram_id في عمود user_id.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام (كنص)

    المُخرجات:
        bool: True إذا كان المورد مسجلاً بالفعل، False إذا لم يكن أو حدث خطأ
    """
    # ===================================================
    # بناء رابط الاستعلام مع فلتر user_id
    # نستخدم eq. لمطابقة القيمة الدقيقة وselect=id لتحميل أقل قدر من البيانات
    # ===================================================
    url = f"{SUPABASE_URL}/rest/v1/suppliers?user_id=eq.{telegram_id}&select=id"

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


# ===================================================
# دوال التجار (المرحلة الرابعة)
# ===================================================

def save_trader(trader_data: dict) -> bool:
    """
    يحفظ بيانات التاجر الجديد في جدول bot_trader_registrations في Supabase.

    يُرسل طلب POST إلى REST API ويتحقق من نجاح العملية.
    الجدول bot_trader_registrations يجب أن يكون موجوداً مسبقاً في Supabase.

    المعاملات:
        trader_data (dict): قاموس يحتوي على:
            - telegram_id: معرّف المستخدم في تليجرام (text)
            - full_name: الاسم الكامل للتاجر (text)
            - phone: رقم الهاتف مع رمز الدولة (text)
            - country: دولة التاجر (text)
            - product_interest: نوع المنتج المفضل (text)

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح (رمز 201)، False في أي حالة أخرى
    """
    # بناء رابط نقطة النهاية لجدول التجار
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations"

    # ===================================================
    # تجهيز البيانات المراد إرسالها إلى Supabase
    # status يُضبط على 'pending' تلقائياً للتجار الجدد
    # ===================================================
    payload = {
        "telegram_id": trader_data.get("telegram_id"),
        "full_name": trader_data.get("full_name"),
        "phone": trader_data.get("phone"),
        "country": trader_data.get("country"),
        "product_interest": trader_data.get("product_interest"),
        "status": "pending",
    }

    try:
        # إرسال طلب POST لحفظ بيانات التاجر
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        # التحقق من نجاح العملية - Supabase يُرجع 201 عند الإنشاء الناجح
        if response.status_code == 201:
            logger.info(
                "✅ تم حفظ التاجر في Supabase بنجاح: telegram_id=%s",
                trader_data.get("telegram_id")
            )
            return True

        # تسجيل تفاصيل الخطأ في حال فشل الطلب
        logger.error(
            "❌ فشل حفظ التاجر في Supabase: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء حفظ التاجر: %s", str(e)
        )
        return False


def check_trader_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود تاجر مسجل مسبقاً باستخدام معرّف تليجرام.

    يُرسل طلب GET للبحث عن سجل في جدول bot_trader_registrations.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام (كنص)

    المُخرجات:
        bool: True إذا كان التاجر مسجلاً بالفعل، False إذا لم يكن أو حدث خطأ
    """
    # بناء رابط الاستعلام مع فلتر telegram_id
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        # إرسال طلب GET للبحث عن التاجر
        response = requests.get(url, headers=HEADERS, timeout=10)

        # التحقق من نجاح الطلب
        if response.status_code == 200:
            results = response.json()

            # إذا كانت القائمة غير فارغة فالتاجر مسجل مسبقاً
            if results:
                logger.info(
                    "⚠️ التاجر مسجل مسبقاً في Supabase: telegram_id=%s",
                    telegram_id
                )
                return True

            # القائمة فارغة - التاجر غير مسجل
            return False

        # تسجيل خطأ في حال فشل الطلب
        logger.error(
            "❌ خطأ في التحقق من وجود التاجر: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء التحقق من التاجر: %s", str(e)
        )
        return False
