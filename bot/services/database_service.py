# ===================================================
# bot/services/database_service.py
# خدمة قاعدة البيانات - التواصل مع Supabase عبر REST API HTTP
# المرحلة السادسة: إضافة دوال المنتجات (إضافة، تصفح)
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from typing import Optional

import requests

from bot.config import SUPABASE_KEY, SUPABASE_URL

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# ===================================================
# رأس الطلبات المشتركة لجميع الاتصالات بـ Supabase
# ===================================================
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

HEADERS_RETURN = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ===================================================
# دوال الموردين
# ===================================================

def save_supplier(supplier_data: dict) -> bool:
    """
    يحفظ بيانات المورد الجديد في جدول bot_registrations في Supabase.

    المعاملات:
        supplier_data (dict): يحتوي على:
            - telegram_id, company_name, contact_name, city, phone
            - sales_telegram_id (اختياري)

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح، False في أي حالة أخرى
    """
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations"

    payload = {
        "telegram_id": supplier_data.get("telegram_id"),
        "company_name": supplier_data.get("company_name"),
        "contact_name": supplier_data.get("contact_name"),
        "city": supplier_data.get("city"),
        "phone": supplier_data.get("phone"),
        "sales_telegram_id": supplier_data.get("sales_telegram_id"),
        "status": "pending",
    }

    # إزالة المفاتيح الفارغة
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        if response.status_code == 201:
            logger.info("✅ تم حفظ المورد بنجاح: telegram_id=%s", supplier_data.get("telegram_id"))
            return True

        logger.error("❌ فشل حفظ المورد: status=%d, response=%s", response.status_code, response.text)
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال بـ Supabase أثناء حفظ المورد: %s", str(e))
        return False


def check_supplier_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود مورد مسجل مسبقاً.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام

    المُخرجات:
        bool: True إذا كان مسجلاً، False إذا لم يكن
    """
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            results = response.json()
            if results:
                logger.info("⚠️ المورد مسجل مسبقاً: telegram_id=%s", telegram_id)
                return True
            return False

        logger.error("❌ خطأ في التحقق من المورد: status=%d", response.status_code)
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء التحقق من المورد: %s", str(e))
        return False


def get_supplier_by_telegram_id(telegram_id: str) -> Optional[dict]:
    """
    يجلب بيانات المورد من جدول suppliers باستخدام telegram_id.

    يُستخدم لجلب supplier_id اللازم لإضافة المنتجات.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام

    المُخرجات:
        dict | None: بيانات المورد أو None إذا لم يُوجد
    """
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id,company_name"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            results = response.json()
            if results:
                return results[0]
            return None

        logger.error("❌ خطأ في جلب بيانات المورد: status=%d", response.status_code)
        return None

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب المورد: %s", str(e))
        return None


# ===================================================
# دوال التجار
# ===================================================

def save_trader(trader_data: dict) -> bool:
    """
    يحفظ بيانات التاجر الجديد في جدول bot_trader_registrations.

    المعاملات:
        trader_data (dict): يحتوي على:
            - telegram_id, full_name, phone, country, business_type

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح، False في أي حالة أخرى
    """
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations"

    payload = {
        "telegram_id": trader_data.get("telegram_id"),
        "full_name": trader_data.get("full_name"),
        "phone": trader_data.get("phone"),
        "country": trader_data.get("country"),
        "business_type": trader_data.get("business_type"),
        "status": "pending",
    }

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        if response.status_code == 201:
            logger.info("✅ تم حفظ التاجر بنجاح: telegram_id=%s", trader_data.get("telegram_id"))
            return True

        logger.error("❌ فشل حفظ التاجر: status=%d, response=%s", response.status_code, response.text)
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء حفظ التاجر: %s", str(e))
        return False


def check_trader_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود تاجر مسجل مسبقاً.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام

    المُخرجات:
        bool: True إذا كان مسجلاً، False إذا لم يكن
    """
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            results = response.json()
            if results:
                logger.info("⚠️ التاجر مسجل مسبقاً: telegram_id=%s", telegram_id)
                return True
            return False

        logger.error("❌ خطأ في التحقق من التاجر: status=%d", response.status_code)
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء التحقق من التاجر: %s", str(e))
        return False


# ===================================================
# دوال المنتجات (جديد - المرحلة السادسة)
# ===================================================

def add_product(product_data: dict) -> bool:
    """
    يحفظ بيانات المنتج الجديد في جدول products في Supabase.

    المعاملات:
        product_data (dict): يحتوي على:
            - supplier_id (UUID): معرّف المورد في جدول suppliers
            - category (str): فئة المنتج
            - price (str): السعر (اختياري)
            - images (list): مصفوفة file_id للصور

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح، False في أي حالة أخرى
    """
    url = f"{SUPABASE_URL}/rest/v1/products"

    payload = {
        "supplier_id": product_data.get("supplier_id"),
        "category": product_data.get("category"),
        "price": product_data.get("price"),
        "images": product_data.get("images", []),
        "is_active": True,
    }

    # إزالة price إذا كانت None
    if payload["price"] is None:
        payload.pop("price")

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        if response.status_code == 201:
            logger.info("✅ تم حفظ المنتج بنجاح للمورد: %s", product_data.get("supplier_id"))
            return True

        logger.error("❌ فشل حفظ المنتج: status=%d, response=%s", response.status_code, response.text)
        return False

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء حفظ المنتج: %s", str(e))
        return False


def get_all_categories() -> list:
    """
    يجلب قائمة بجميع الفئات المتاحة من المنتجات النشطة.

    المُخرجات:
        list: قائمة الفئات الفريدة، أو قائمة فارغة في حال الخطأ
    """
    url = f"{SUPABASE_URL}/rest/v1/products?is_active=eq.true&select=category"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            results = response.json()
            # استخراج الفئات الفريدة
            categories = list({item["category"] for item in results if item.get("category")})
            return sorted(categories)

        logger.error("❌ خطأ في جلب الفئات: status=%d", response.status_code)
        return []

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب الفئات: %s", str(e))
        return []


def get_products_by_category(category: str) -> list:
    """
    يجلب المنتجات النشطة حسب الفئة مع بيانات المورد.

    المعاملات:
        category (str): اسم الفئة، أو "all" لجلب جميع المنتجات

    المُخرجات:
        list: قائمة المنتجات مع بياناتها، أو قائمة فارغة في حال الخطأ
    """
    if category == "all":
        url = f"{SUPABASE_URL}/rest/v1/products?is_active=eq.true&select=*,suppliers(company_name)"
    else:
        # ترميز المسافات في اسم الفئة
        encoded_category = category.replace(" ", "%20")
        url = (
            f"{SUPABASE_URL}/rest/v1/products"
            f"?is_active=eq.true&category=eq.{encoded_category}"
            f"&select=*,suppliers(company_name)"
        )

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            products = response.json()
            logger.info("✅ تم جلب %d منتج من فئة: %s", len(products), category)
            return products

        logger.error("❌ خطأ في جلب المنتجات: status=%d", response.status_code)
        return []

    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب المنتجات: %s", str(e))
        return []

# ===================================================
# دوال طلبات عروض الأسعار - RFQ
# المرحلة السابعة: إضافة دوال RFQ
# ==================================================


def get_product_by_id(product_id: str) -> Optional[dict]:
    """
    يجلب بيانات منتج واحد بمعرّفه مع بيانات المورد الكاملة (بما فيها telegram_id).
    المعاملات:
        product_id (str): معرّف المنتج (UUID)
    المُخرجات:
        dict: بيانات المنتج مع بيانات المورد، أو None
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/products"
        f"?id=eq.{product_id}"
        f"&is_active=eq.true"
        f"&select=*,suppliers(id,company_name,telegram_id,phone)"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                logger.info("✅ تم جلب المنتج: id=%s", product_id)
                return data[0]
        logger.error("❌ خطأ في جلب المنتج %s: status=%d", product_id, response.status_code)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب المنتج: %s", str(e))
        return None


def get_trader_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """
    يجلب بيانات التاجر باستخدام Telegram ID من جدول bot_trader_registrations.
    المعاملات:
        telegram_id (int): معرّف تيليجرام للتاجر
    المُخرجات:
        dict: بيانات التاجر (id, full_name, phone, telegram_id)، أو None
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/bot_trader_registrations"
        f"?telegram_id=eq.{telegram_id}"
        f"&select=id,full_name,phone,telegram_id"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                trader = data[0]
                trader["name"] = trader.get("full_name", "غير معروف")
                logger.info("✅ تم جلب بيانات التاجر: telegram_id=%s", telegram_id)
                return trader
        logger.error("❌ خطأ في جلب التاجر %s: status=%d", telegram_id, response.status_code)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب التاجر: %s", str(e))
        return None


def add_quote_request(
    product_id: str,
    supplier_id: str,
    trader_id: int,
    quantity: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    delivery_date: Optional[str] = None,
) -> Optional[dict]:
    """
    يحفظ طلب عرض سعر جديد في جدول quote_requests في Supabase.
    المعاملات:
        product_id (str): معرّف المنتج (UUID)
        supplier_id (str): معرّف المورد (UUID)
        trader_id (int): Telegram ID للتاجر (BIGINT)
        quantity (str): الكمية المطلوبة (اختياري)
        color (str): اللون المطلوب (اختياري)
        size (str): المقاس المطلوب (اختياري)
        delivery_date (str): تاريخ التسليم المطلوب (اختياري)
    المُخرجات:
        dict: بيانات الطلب المحفوظ، أو None عند الفشل
    """
    data = {
        "product_id": product_id,
        "supplier_id": supplier_id,
        "trader_id": trader_id,
        "status": "pending",
    }
    if quantity:
        data["quantity"] = quantity
    if color:
        data["color"] = color
    if size:
        data["size"] = size
    if delivery_date:
        data["delivery_date"] = delivery_date

    url = f"{SUPABASE_URL}/rest/v1/quote_requests"
    try:
        response = requests.post(url, headers=HEADERS_RETURN, json=data, timeout=10)
        if response.status_code in (200, 201):
            result = response.json()
            saved = result[0] if result else data
            logger.info(
                "✅ تم حفظ طلب عرض السعر: product_id=%s, trader_id=%s",
                product_id, trader_id
            )
            return saved
        logger.error(
            "❌ خطأ في حفظ طلب عرض السعر: status=%d, body=%s",
            response.status_code, response.text
        )
        return None
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء حفظ طلب عرض السعر: %s", str(e))
        return None
