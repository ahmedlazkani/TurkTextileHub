# ===================================================
# bot/services/kayisoft_api.py
# عميل HTTP لتطبيق KAYISOFT — نقطة التواصل الوحيدة مع لوحة التحكم
#
# الوصف:
#   يوفر 5 endpoints لتمرير البيانات بين البوت وتطبيق KAYISOFT.
#   تيليغرام = إدخال بيانات + إشعارات فقط.
#   تطبيق KAYISOFT = مركز القرار الكامل (قبول/رفض، إحصائيات، إدارة).
#
# Endpoints:
#   1. POST /api/bot/suppliers          — تسجيل مورد جديد
#   2. POST /api/bot/traders            — تسجيل تاجر جديد
#   3. POST /api/bot/products           — إضافة منتج جديد
#   4. POST /api/bot/quote-requests     — إرسال طلب عرض سعر
#   5. GET  /api/bot/supplier/{tg_id}   — جلب بيانات مورد بـ telegram_id
#
# التشغيل بدون KAYISOFT_API_URL:
#   جميع الدوال تُعيد None أو False بدلاً من crash.
#   البوت يستمر في العمل معتمداً على Supabase مباشرة.
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# إعداد العميل — يُقرأ من متغيرات البيئة
# ──────────────────────────────────────────────────────────

_BASE_URL: Optional[str] = os.getenv("KAYISOFT_API_URL", "").rstrip("/")
_API_KEY: Optional[str] = os.getenv("KAYISOFT_API_KEY", "")

# مدة انتظار الطلب بالثواني
_TIMEOUT = 15

# رأس الطلبات المشتركة
_HEADERS: dict = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _is_configured() -> bool:
    """
    يتحقق من اكتمال إعداد KAYISOFT API.

    المُخرجات:
        bool: True إذا كان KAYISOFT_API_URL و KAYISOFT_API_KEY موجودَين.
    """
    if not _BASE_URL or not _API_KEY:
        logger.debug(
            "⚠️ KAYISOFT_API_URL أو KAYISOFT_API_KEY غير مضبوط — "
            "البوت يعمل بدون تطبيق KAYISOFT"
        )
        return False
    return True


def _build_headers() -> dict:
    """
    يبني رأس الطلب مع مفتاح API.

    المُخرجات:
        dict: رأس الطلب الكامل مع Authorization.
    """
    return {
        **_HEADERS,
        "Authorization": f"Bearer {_API_KEY}",
    }


def _post(endpoint: str, payload: dict) -> Optional[dict]:
    """
    دالة داخلية: ترسل POST request لـ KAYISOFT API.

    المعاملات:
        endpoint (str) : المسار النسبي (مثال: "/api/bot/suppliers")
        payload  (dict): جسم الطلب بصيغة JSON

    المُخرجات:
        dict: استجابة JSON عند النجاح، None عند الفشل.
    """
    if not _is_configured():
        return None

    url = f"{_BASE_URL}{endpoint}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_build_headers(),
            timeout=_TIMEOUT,
        )
        if response.status_code in (200, 201):
            logger.info(f"✅ KAYISOFT POST {endpoint} → {response.status_code}")
            return response.json() if response.content else {}
        logger.error(
            f"❌ KAYISOFT POST {endpoint} → {response.status_code}: {response.text[:200]}"
        )
        return None
    except requests.exceptions.Timeout:
        logger.error(f"❌ KAYISOFT timeout: POST {endpoint}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ KAYISOFT connection error: POST {endpoint}")
        return None
    except Exception as e:
        logger.error(f"❌ KAYISOFT خطأ غير متوقع: POST {endpoint}: {e}")
        return None


def _get(endpoint: str, params: Optional[dict] = None) -> Optional[Any]:
    """
    دالة داخلية: ترسل GET request لـ KAYISOFT API.

    المعاملات:
        endpoint (str)          : المسار النسبي
        params   (dict | None)  : معاملات الاستعلام (query params)

    المُخرجات:
        Any: استجابة JSON عند النجاح، None عند الفشل.
    """
    if not _is_configured():
        return None

    url = f"{_BASE_URL}{endpoint}"
    try:
        response = requests.get(
            url,
            headers=_build_headers(),
            params=params or {},
            timeout=_TIMEOUT,
        )
        if response.status_code == 200:
            logger.info(f"✅ KAYISOFT GET {endpoint} → 200")
            return response.json() if response.content else {}
        if response.status_code == 404:
            logger.info(f"ℹ️ KAYISOFT GET {endpoint} → 404 (not found)")
            return None
        logger.error(
            f"❌ KAYISOFT GET {endpoint} → {response.status_code}: {response.text[:200]}"
        )
        return None
    except requests.exceptions.Timeout:
        logger.error(f"❌ KAYISOFT timeout: GET {endpoint}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ KAYISOFT connection error: GET {endpoint}")
        return None
    except Exception as e:
        logger.error(f"❌ KAYISOFT خطأ غير متوقع: GET {endpoint}: {e}")
        return None


# ──────────────────────────────────────────────────────────
# Endpoint 1: تسجيل مورد جديد
# ──────────────────────────────────────────────────────────

def register_supplier(supplier_data: dict) -> Optional[dict]:
    """
    يُرسل بيانات مورد جديد لتطبيق KAYISOFT للمراجعة والتسجيل.

    المعاملات:
        supplier_data (dict): يحتوي على:
            - telegram_id    (str): معرّف المورد في تليجرام
            - company_name   (str): اسم الشركة أو المتجر
            - contact_name   (str): اسم جهة الاتصال
            - city           (str): المدينة
            - phone          (str): رقم الهاتف مع رمز الدولة
            - sales_telegram_id (str | None): يوزرنيم موظف المبيعات

    المُخرجات:
        dict: بيانات المورد المُنشأ في KAYISOFT، أو None عند الفشل أو عدم الإعداد.

    الملاحظة:
        عند إعادة None، يستمر البوت ويحفظ البيانات في Supabase مباشرة.
    """
    logger.info(f"📤 KAYISOFT: تسجيل مورد telegram_id={supplier_data.get('telegram_id')}")
    return _post("/api/bot/suppliers", supplier_data)


# ──────────────────────────────────────────────────────────
# Endpoint 2: تسجيل تاجر جديد
# ──────────────────────────────────────────────────────────

def register_trader(trader_data: dict) -> Optional[dict]:
    """
    يُرسل بيانات تاجر جديد لتطبيق KAYISOFT.

    المعاملات:
        trader_data (dict): يحتوي على:
            - telegram_id   (str): معرّف التاجر في تليجرام
            - full_name     (str): الاسم الكامل
            - phone         (str): رقم الهاتف
            - country       (str): الدولة
            - business_type (str): نوع النشاط التجاري

    المُخرجات:
        dict: بيانات التاجر المُنشأ في KAYISOFT، أو None عند الفشل أو عدم الإعداد.
    """
    logger.info(f"📤 KAYISOFT: تسجيل تاجر telegram_id={trader_data.get('telegram_id')}")
    return _post("/api/bot/traders", trader_data)


# ──────────────────────────────────────────────────────────
# Endpoint 3: إضافة منتج جديد
# ──────────────────────────────────────────────────────────

def submit_product(product_data: dict) -> Optional[dict]:
    """
    يُرسل بيانات منتج جديد لتطبيق KAYISOFT للمراجعة.

    المعاملات:
        product_data (dict): يحتوي على:
            - telegram_id (str)      : معرّف المورد في تليجرام
            - supplier_id (str|None) : UUID المورد في Supabase (اختياري)
            - category    (str)      : فئة المنتج
            - price       (str|None) : السعر (نص حر)
            - images      (list)     : قائمة file_ids للصور

    المُخرجات:
        dict: بيانات المنتج المُنشأ في KAYISOFT، أو None عند الفشل أو عدم الإعداد.
    """
    logger.info(
        f"📤 KAYISOFT: إضافة منتج | supplier={product_data.get('telegram_id')} "
        f"| category={product_data.get('category')}"
    )
    return _post("/api/bot/products", product_data)


# ──────────────────────────────────────────────────────────
# Endpoint 4: إرسال طلب عرض سعر (RFQ)
# ──────────────────────────────────────────────────────────

def submit_quote_request(rfq_data: dict) -> Optional[dict]:
    """
    يُرسل طلب عرض سعر جديد لتطبيق KAYISOFT لتسجيله وإشعار المورد.

    المعاملات:
        rfq_data (dict): يحتوي على:
            - product_id    (str)      : UUID المنتج
            - supplier_id   (str)      : UUID المورد
            - trader_id     (int)      : telegram_id التاجر
            - quantity      (str|None) : الكمية المطلوبة
            - color         (str|None) : اللون المطلوب
            - size          (str|None) : المقاس المطلوب
            - delivery_date (str|None) : تاريخ التسليم المطلوب

    المُخرجات:
        dict: بيانات الطلب المُنشأ في KAYISOFT مع reference_id، أو None.
    """
    logger.info(
        f"📤 KAYISOFT: طلب عرض سعر | product={rfq_data.get('product_id')} "
        f"| trader={rfq_data.get('trader_id')}"
    )
    return _post("/api/bot/quote-requests", rfq_data)


# ──────────────────────────────────────────────────────────
# Endpoint 5: جلب بيانات مورد بـ telegram_id
# ──────────────────────────────────────────────────────────

def get_supplier(telegram_id: str) -> Optional[dict]:
    """
    يجلب بيانات مورد من تطبيق KAYISOFT بـ telegram_id.

    المعاملات:
        telegram_id (str): معرّف المورد في تليجرام.

    المُخرجات:
        dict: بيانات المورد كاملة من KAYISOFT، أو None إذا لم يوجد.

    الاستخدام:
        يُستخدم لجلب حالة المورد (approved/pending/rejected) من KAYISOFT
        بدلاً من قراءتها مباشرة من Supabase — لضمان المصدر الموحد للحقيقة.
    """
    logger.debug(f"📥 KAYISOFT: جلب مورد telegram_id={telegram_id}")
    return _get(f"/api/bot/supplier/{telegram_id}")


# ──────────────────────────────────────────────────────────
# دالة التحقق من صحة الاتصال بـ KAYISOFT (health check)
# ──────────────────────────────────────────────────────────

def health_check() -> bool:
    """
    يتحقق من أن تطبيق KAYISOFT يعمل ومتاح.

    المُخرجات:
        bool: True إذا استجاب التطبيق بـ 200، False في أي حالة أخرى.

    الاستخدام:
        يُستدعى عند بدء تشغيل البوت لتأكيد الاتصال وتسجيل حالته في السجلات.
    """
    if not _is_configured():
        logger.info("ℹ️ KAYISOFT API غير مضبوط — البوت يعمل في وضع Supabase-only")
        return False

    result = _get("/api/health")
    if result is not None:
        logger.info("✅ KAYISOFT API متاح ويعمل")
        return True

    logger.warning("⚠️ KAYISOFT API غير متاح — البوت يستمر بدونه")
    return False
