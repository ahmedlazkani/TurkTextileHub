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
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id,company_name,contact_name,status"

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

def get_supplier_uuid_by_telegram_id(telegram_id: str) -> Optional[str]:
    """
    يجلب UUID المورد من جدول suppliers باستخدام sales_telegram_id.
    يُستخدم لربط bot_registrations بجدول suppliers عند إضافة المنتجات.
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/suppliers?sales_telegram_id=eq.{telegram_id}&select=id&limit=1"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if results:
                return results[0]["id"]
        logger.warning("⚠️ لم يُوجد سجل في suppliers لـ telegram_id=%s", telegram_id)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في جلب supplier UUID: %s", str(e))
        return None


def add_product(product_data: dict) -> bool:
    """
    يحفظ بيانات المنتج الجديد في جدول products في Supabase.

    المنطق:
    - يحاول أولاً جلب supplier_id من جدول suppliers عبر sales_telegram_id.
    - إذا لم يُوجد سجل في suppliers (مورد البوت فقط)، يحفظ المنتج باستخدام
      bot_supplier_telegram_id مع supplier_id=NULL (مسموح بعد migration).

    المُدخلات:
        product_data (dict): يحتوي على telegram_id, title, category, images, price

    المُخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    import re as _re

    telegram_id = product_data.get("telegram_id")

    # محاولة جلب supplier_id من جدول suppliers
    supplier_id = product_data.get("supplier_id")
    if not supplier_id and telegram_id:
        supplier_id = get_supplier_uuid_by_telegram_id(str(telegram_id))

    url = f"{SUPABASE_URL}/rest/v1/products"
    price_raw = product_data.get("price")
    price_val = None
    if price_raw:
        nums = _re.findall(r"\d+\.?\d*", str(price_raw))
        if nums:
            try:
                price_val = float(nums[0])
            except ValueError:
                pass

    payload = {
        "title": product_data.get("title") or "منتج جديد",
        "category": product_data.get("category") or "other",
        "image_urls": product_data.get("images", []),
        "status": "pending",  # pending حتى يوافق الأدمن
    }

    # إضافة supplier_id إذا وُجد، وإلا استخدام bot_supplier_telegram_id
    if supplier_id:
        payload["supplier_id"] = supplier_id
        logger.info("✅ ربط المنتج بـ suppliers.id: %s", supplier_id)
    elif telegram_id:
        payload["bot_supplier_telegram_id"] = int(telegram_id)
        logger.info("✅ ربط المنتج بـ bot_supplier_telegram_id: %s", telegram_id)
    else:
        logger.error("❌ لا يوجد معرّف مورد صالح لإضافة المنتج")
        return False

    if price_val is not None:
        payload["price"] = price_val

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if response.status_code == 201:
            logger.info("✅ تم حفظ المنتج بنجاح")
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
        f"&select=id,full_name,phone,telegram_id,status"
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

# ===================================================
# دوال ربط القنوات (channel_connections)
# الخطوة 5: /connect_channel
# ===================================================

def save_channel_connection(data: dict) -> bool:
    """
    يحفظ ربط قناة جديدة في جدول channel_connections.

    المعاملات:
        data (dict): يحتوي على:
            - supplier_id (str): UUID المورد
            - channel_id (int): معرّف القناة في تليجرام
            - channel_username (str): اسم القناة بدون @
            - channel_title (str): عنوان القناة

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح، False في أي حالة أخرى
    """
    url = f"{SUPABASE_URL}/rest/v1/channel_connections"
    payload = {
        "supplier_id": data.get("supplier_id"),
        "channel_id": data.get("channel_id"),
        "channel_username": data.get("channel_username"),
        "channel_title": data.get("channel_title"),
        "is_active": True,
        "connection_status": "connected",
    }
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if response.status_code == 201:
            logger.info(
                "✅ تم حفظ ربط القناة: @%s للمورد: %s",
                data.get("channel_username"),
                data.get("supplier_id")
            )
            return True
        logger.error(
            "❌ فشل حفظ ربط القناة: status=%d, body=%s",
            response.status_code, response.text
        )
        return False
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء حفظ ربط القناة: %s", str(e))
        return False


def get_supplier_channels(supplier_id: str) -> list:
    """
    يجلب قائمة القنوات المربوطة بمورد معين.

    المعاملات:
        supplier_id (str): UUID المورد

    المُخرجات:
        list: قائمة القنوات، أو قائمة فارغة عند الفشل
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/channel_connections"
        f"?supplier_id=eq.{supplier_id}"
        f"&is_active=eq.true"
        f"&select=id,channel_id,channel_username,channel_title,connection_status,created_at"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.error("❌ خطأ في جلب قنوات المورد: status=%d", response.status_code)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في الاتصال أثناء جلب قنوات المورد: %s", str(e))
        return []


def get_channel_by_id(channel_id: int) -> Optional[dict]:
    """
    يتحقق من وجود ربط لقناة معينة (لمنع الربط المزدوج).

    المعاملات:
        channel_id (int): معرّف القناة في تليجرام

    المُخرجات:
        dict | None: بيانات الربط الموجود، أو None إذا لم يوجد
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/channel_connections"
        f"?channel_id=eq.{channel_id}"
        f"&is_active=eq.true"
        f"&select=id,supplier_id,channel_username"
        f"&limit=1"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            results = response.json()
            return results[0] if results else None
        return None
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في التحقق من ربط القناة: %s", str(e))
        return None


def get_all_active_channels() -> list:
    """
    يجلب جميع القنوات المربوطة والنشطة (للاستخدام في مستمع المنشورات).

    المُخرجات:
        list: قائمة القنوات مع supplier_id لكل منها
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/channel_connections"
        f"?is_active=eq.true"
        f"&connection_status=eq.connected"
        f"&select=id,channel_id,channel_username,channel_title,supplier_id,last_post_id"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في جلب القنوات النشطة: %s", str(e))
        return []


def disconnect_channel(connection_id: str) -> bool:
    """
    تعطيل ربط قناة معينة (soft delete).

    يضبط is_active=False وconnection_status='disconnected' مع تسجيل وقت التحديث.
    لا يحذف السجل من قاعدة البيانات للحفاظ على سجل التاريخ.

    المعاملات:
        connection_id (str): UUID سجل الربط في جدول channel_connections

    المُخرجات:
        bool: True عند النجاح، False في حالة الفشل
    """
    from datetime import datetime
    url = f"{SUPABASE_URL}/rest/v1/channel_connections?id=eq.{connection_id}"
    payload = {
        "is_active": False,
        "connection_status": "disconnected",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        response = requests.patch(url, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status()
        logger.info("✅ تم فصل القناة بنجاح - connection_id: %s", connection_id)
        return True
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في فصل القناة %s: %s", connection_id, str(e))
        return False


def enable_channel(connection_id: str) -> bool:
    """
    إعادة تفعيل ربط قناة كانت معطّلة.

    يضبط is_active=True وconnection_status='connected'.

    المعاملات:
        connection_id (str): UUID سجل الربط في جدول channel_connections

    المُخرجات:
        bool: True عند النجاح، False في حالة الفشل
    """
    from datetime import datetime
    url = f"{SUPABASE_URL}/rest/v1/channel_connections?id=eq.{connection_id}"
    payload = {
        "is_active": True,
        "connection_status": "connected",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        response = requests.patch(url, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status()
        logger.info("✅ تم تفعيل القناة بنجاح - connection_id: %s", connection_id)
        return True
    except requests.exceptions.RequestException as e:
        logger.error("❌ خطأ في تفعيل القناة %s: %s", connection_id, str(e))
        return False


# ══════════════════════════════════════════════════════
# دوال الخطوة 6 — مستمع القناة
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
# 1. جلب اتصال القناة النشط
# ══════════════════════════════════════════════════════

def get_active_connection_by_channel_id(channel_id: int) -> Optional[dict]:
    """
    المدخلات: channel_id (bigint) — معرف قناة تليجرام
    المخرجات: dict بيانات الاتصال النشط أو None إذا لم يوجد
    المنطق: يبحث في channel_connections عن سجل بـ is_active=true و connection_status=active
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/channel_connections"
        params = {
            "channel_id":         f"eq.{channel_id}",
            "is_active":          "eq.true",
            "connection_status":  "eq.active",
            "select":             "*",
            "limit":              "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            logger.debug(f"✅ اتصال نشط للقناة {channel_id}: {data[0]['id']}")
            return data[0]
        logger.debug(f"لا يوجد اتصال نشط للقناة {channel_id}")
        return None
    except Exception as e:
        logger.error(f"❌ get_active_connection_by_channel_id({channel_id}): {e}")
        raise


# ══════════════════════════════════════════════════════
# 2. التحقق من تكرار المنشور
# ══════════════════════════════════════════════════════

def is_duplicate_post(channel_id: int, message_id: int) -> bool:
    """
    المدخلات:
        channel_id (int): معرف القناة
        message_id (int): معرف الرسالة
    المخرجات: True إذا كان موجوداً بالفعل في pending_posts، False إذا كان جديداً
    المنطق: يتحقق من وجود (channel_id, message_id) في جدول pending_posts
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/pending_posts"
        params = {
            "channel_id":  f"eq.{channel_id}",
            "message_id":  f"eq.{message_id}",
            "select":      "id",
            "limit":       "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        is_dup = len(data) > 0
        if is_dup:
            logger.debug(f"🔁 منشور مكرر: channel_id={channel_id}, message_id={message_id}")
        return is_dup
    except Exception as e:
        logger.error(f"❌ is_duplicate_post({channel_id}, {message_id}): {e}")
        return False


# ══════════════════════════════════════════════════════
# 3. حفظ منشور معلق
# ══════════════════════════════════════════════════════

def save_pending_post(post_data: dict) -> Optional[dict]:
    """
    المدخلات:
        post_data (dict): يحتوي على:
            supplier_id   (str UUID)
            channel_id    (int)
            message_id    (int)
            raw_text      (str)
            image_urls    (list): قائمة file_ids للصور
            video_url     (str|None)
            extracted_data(dict): بيانات المنتج من AI
    المخرجات: dict المنشور المحفوظ مع id أو None عند الفشل
    المنطق: يحفظ في pending_posts مع expires_at = now + 24 ساعة وstatus=pending
    """
    try:
        now        = datetime.utcnow()
        expires_at = now + timedelta(hours=24)

        payload = {
            "supplier_id":    post_data["supplier_id"],
            "channel_id":     post_data["channel_id"],
            "message_id":     post_data["message_id"],
            "raw_text":       post_data.get("raw_text", ""),
            "image_urls":     post_data.get("image_urls", []),
            "video_url":      post_data.get("video_url"),
            "extracted_data": post_data.get("extracted_data", {}),
            "status":         "pending",
            "created_at":     now.isoformat() + "Z",
            "expires_at":     expires_at.isoformat() + "Z",
        }

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/pending_posts",
            headers=HEADERS,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        data   = response.json()
        result = data[0] if isinstance(data, list) and data else data
        logger.info(f"💾 تم حفظ pending_post: {result.get('id')}")
        return result
    except Exception as e:
        logger.error(f"❌ save_pending_post: {e}")
        raise


# ══════════════════════════════════════════════════════
# 4. جلب منشور معلق بـ id
# ══════════════════════════════════════════════════════

def get_pending_post(pending_post_id: str) -> Optional[dict]:
    """
    المدخلات: pending_post_id (str UUID) — معرف المنشور المعلق
    المخرجات: dict بيانات المنشور أو None إذا لم يوجد
    المنطق: يجلب سجلاً واحداً من pending_posts بمعرفه
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/pending_posts"
        params = {
            "id":     f"eq.{pending_post_id}",
            "select": "*",
            "limit":  "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            return data[0]
        logger.warning(f"⚠️ pending_post {pending_post_id} غير موجود")
        return None
    except Exception as e:
        logger.error(f"❌ get_pending_post({pending_post_id}): {e}")
        raise


# ══════════════════════════════════════════════════════
# 5. تحديث حالة منشور معلق
# ══════════════════════════════════════════════════════

def update_pending_post_status(pending_post_id: str, status: str) -> bool:
    """
    المدخلات:
        pending_post_id (str UUID): معرف المنشور
        status          (str)     : الحالة الجديدة — approved|rejected|expired
    المخرجات: True عند النجاح، False عند الفشل
    المنطق: يحدّث حقل status وupdated_at في pending_posts
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/pending_posts"
        params  = {"id": f"eq.{pending_post_id}"}
        payload = {
            "status":     status,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        response = requests.patch(url, headers=HEADERS, params=params, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ تم تحديث حالة المنشور {pending_post_id} → {status}")
        return True
    except Exception as e:
        logger.error(f"❌ update_pending_post_status({pending_post_id}, {status}): {e}")
        return False


# ══════════════════════════════════════════════════════
# 6. نشر منتج من منشور معلق
# ══════════════════════════════════════════════════════

def publish_product_from_pending(pending_post_id: str) -> Optional[dict]:
    """
    المدخلات: pending_post_id (str UUID)
    المخرجات: dict المنتج المنشور مع id أو None عند الفشل
    المنطق:
        1. جلب pending_post من قاعدة البيانات
        2. استخدام extracted_data لملء حقول products
        3. إنشاء سجل في جدول products
        4. إعادة product_id عند النجاح
    """
    try:
        # 1. جلب المنشور المعلق
        post = get_pending_post(pending_post_id)
        if not post:
            logger.error(f"❌ pending_post {pending_post_id} غير موجود للنشر")
            return None

        # 2. استخدام extracted_data لملء حقول products
        extracted = post.get("extracted_data") or {}
        now       = datetime.utcnow()

        product_payload = {
            "supplier_id":            post["supplier_id"],
            "title":                  extracted.get("title")       or "منتج جديد",
            "title_en":               extracted.get("title_en")    or "New Product",
            "description":            extracted.get("description") or "",
            "description_en":         extracted.get("description_en") or "",
            "category":               extracted.get("category")    or "other",
            "category_en":            extracted.get("category_en") or "other",
            "colors":                 extracted.get("colors")      or [],
            "sizes":                  extracted.get("sizes")       or [],
            "price":                  str(extracted["price"]) if extracted.get("price") is not None else None,
            "currency":               extracted.get("currency"),
            "minimum_order_quantity": extracted.get("minimum_order_quantity"),
            "image_urls":             post.get("image_urls")       or [],
            "video_url":              post.get("video_url"),
            "source_message_id":      post.get("message_id"),
            "source_channel_id":      post.get("channel_id"),
            "status":                 "active",
            "created_at":             now.isoformat() + "Z",
            "updated_at":             now.isoformat() + "Z",
        }

        # 3. إنشاء سجل في جدول products
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/products",
            headers=HEADERS,
            json=product_payload,
            timeout=10,
        )
        response.raise_for_status()
        data    = response.json()
        product = data[0] if isinstance(data, list) and data else data
        logger.info(f"🛍 تم نشر المنتج: {product.get('id')} من pending_post {pending_post_id}")
        return product
    except Exception as e:
        logger.error(f"❌ publish_product_from_pending({pending_post_id}): {e}")
        raise


# ══════════════════════════════════════════════════════
# 7. التحقق من حد المعدل اليومي
# ══════════════════════════════════════════════════════

def check_rate_limit(supplier_id: str, max_posts: int = 10) -> bool:
    """
    المدخلات:
        supplier_id (str UUID): معرف المورد
        max_posts   (int)     : الحد الأقصى للمنشورات اليومية (افتراضي: 10)
    المخرجات: True إذا لم يتجاوز الحد، False إذا تجاوزه
    المنطق:
        1. جلب سجل rate_limits لليوم الحالي
        2. إذا وُجد وتجاوز الحد → إعادة False
        3. إذا وُجد ولم يتجاوز → زيادة posts_count تلقائياً → True
        4. إذا لم يوجد → إنشاء سجل جديد بـ posts_count=1 → True
    """
    try:
        today = datetime.utcnow().date().isoformat()
        url   = f"{SUPABASE_URL}/rest/v1/rate_limits"
        params = {
            "supplier_id": f"eq.{supplier_id}",
            "date":        f"eq.{today}",
            "select":      "*",
            "limit":       "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        records = response.json()

        if records:
            record        = records[0]
            current_count = record.get("posts_count", 0)

            if current_count >= max_posts:
                logger.warning(
                    f"⚠️ المورد {supplier_id} تجاوز حد {max_posts} منشورات/يوم "
                    f"(الحالي: {current_count})"
                )
                return False

            # زيادة العداد تلقائياً
            requests.patch(
                url,
                headers=HEADERS,
                params={"id": f"eq.{record['id']}"},
                json={"posts_count": current_count + 1},
                timeout=10,
            )
        else:
            # إنشاء سجل جديد
            requests.post(
                url,
                headers=HEADERS,
                json={
                    "supplier_id":    supplier_id,
                    "date":           today,
                    "posts_count":    1,
                    "api_calls_count": 0,
                },
                timeout=10,
            )

        logger.debug(f"✅ rate limit OK للمورد {supplier_id}")
        return True
    except Exception as e:
        logger.critical(
            f"🚨 check_rate_limit({supplier_id}) فشل بسبب: {e} — "
            f"تم رفض المنشور بشكل احتياطي"
        )
        return False  # رفض آمن عند الشك (بدلاً من السماح بتجاوز الحد عند العطل)


# ══════════════════════════════════════════════════════
# 8. قراءة قيمة من cache
# ══════════════════════════════════════════════════════

def get_cache(cache_key: str) -> Optional[dict]:
    """
    المدخلات: cache_key (str) — مفتاح البحث في جدول cache
    المخرجات: dict القيمة المخزنة أو None إذا انتهت الصلاحية أو لم توجد
    المنطق: يتحقق من expires_at قبل إعادة القيمة
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/cache"
        params = {
            "cache_key": f"eq.{cache_key}",
            "select":    "*",
            "limit":     "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return None

        record     = data[0]
        expires_at = record.get("expires_at", "")

        if expires_at:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=exp.tzinfo)
            if now > exp:
                logger.debug(f"⏰ cache منتهي الصلاحية: {cache_key}")
                return None

        logger.debug(f"💾 cache hit: {cache_key}")
        return record.get("cache_value")
    except Exception as e:
        logger.error(f"❌ get_cache({cache_key}): {e}")
        return None


# ══════════════════════════════════════════════════════
# 9. حفظ قيمة في cache
# ══════════════════════════════════════════════════════

def set_cache(cache_key: str, value: dict, ttl_hours: int = 24) -> bool:
    """
    المدخلات:
        cache_key (str) : مفتاح التخزين
        value     (dict): القيمة المراد تخزينها
        ttl_hours (int) : مدة الصلاحية بالساعات (افتراضي: 24)
    المخرجات: True عند النجاح، False عند الفشل
    المنطق: يحفظ في جدول cache مع expires_at = now + ttl_hours
    """
    try:
        now        = datetime.utcnow()
        expires_at = now + timedelta(hours=ttl_hours)

        payload = {
            "cache_key":   cache_key,
            "cache_value": value,
            "ttl":         ttl_hours * 3600,
            "created_at":  now.isoformat() + "Z",
            "expires_at":  expires_at.isoformat() + "Z",
        }

        # upsert: إنشاء أو تحديث
        upsert_headers = {
            **HEADERS,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/cache",
            headers=upsert_headers,
            json=payload,
            timeout=10,
        )

        if response.status_code in (200, 201):
            logger.debug(f"✅ cache set: {cache_key} (TTL={ttl_hours}h)")
            return True
        logger.warning(f"⚠️ cache set غير ناجح: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"❌ set_cache({cache_key}): {e}")
        return False


# ══════════════════════════════════════════════════════
# 10. جلب بيانات المورد بمعرفه
# ══════════════════════════════════════════════════════

def get_supplier_by_id(supplier_id: str) -> Optional[dict]:
    """
    المدخلات: supplier_id (str UUID)
    المخرجات: dict بيانات المورد من bot_registrations أو None
    المنطق: يجلب سجل المورد من جدول bot_registrations بمعرفه
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/bot_registrations"
        params = {
            "id":     f"eq.{supplier_id}",
            "select": "*",
            "limit":  "1",
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"❌ get_supplier_by_id({supplier_id}): {e}")
        return None


# ══════════════════════════════════════════════════════
# 11. تحديث extracted_data في منشور معلق (للتعديل)
# ══════════════════════════════════════════════════════

def update_pending_post_extracted_data(pending_post_id: str, extracted_data: dict) -> bool:
    """
    المدخلات:
        pending_post_id (str UUID): معرف المنشور
        extracted_data  (dict)    : البيانات المستخرجة المحدّثة
    المخرجات: True عند النجاح، False عند الفشل
    المنطق: يحدّث حقل extracted_data وupdated_at في pending_posts
    """
    try:
        url     = f"{SUPABASE_URL}/rest/v1/pending_posts"
        params  = {"id": f"eq.{pending_post_id}"}
        payload = {
            "extracted_data": extracted_data,
            "updated_at":     datetime.utcnow().isoformat() + "Z",
        }
        response = requests.patch(url, headers=HEADERS, params=params, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ تم تحديث extracted_data للمنشور {pending_post_id}")
        return True
    except Exception as e:
        logger.error(f"❌ update_pending_post_extracted_data({pending_post_id}): {e}")
        return False

# ===================================================
# دوال طلبات عروض الأسعار - RFQ (إضافات)
# ===================================================

def get_all_quote_requests(limit: int = 100, offset: int = 0) -> list:
    """
    يجلب جميع طلبات عروض الأسعار من قاعدة البيانات (للوحة التحكم).
    المعاملات:
        limit  (int): عدد السجلات المطلوبة (افتراضي: 100)
        offset (int): البداية للتصفح الصفحي (افتراضي: 0)
    المُخرجات: قائمة بجميع طلبات عروض الأسعار مرتبة تنازلياً بالتاريخ
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/quote_requests"
        params = {
            "select": "*, products(title, category, image_urls)",
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"✅ جُلب {len(data)} طلب عرض سعر")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"❌ get_all_quote_requests: {e}")
        return []


def update_quote_request_status(quote_id: str, status: str) -> bool:
    """
    يحدّث حالة طلب عرض السعر.
    المعاملات:
        quote_id (str UUID): معرف الطلب
        status   (str)     : الحالة الجديدة — pending|answered|closed
    المُخرجات: True عند النجاح، False عند الفشل
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/quote_requests"
        params = {"id": f"eq.{quote_id}"}
        payload = {"status": status}
        response = requests.patch(
            url, headers=HEADERS_RETURN, params=params, json=payload, timeout=10
        )
        response.raise_for_status()
        logger.info(f"✅ quote_request {quote_id} → {status}")
        return True
    except Exception as e:
        logger.error(f"❌ update_quote_request_status({quote_id}, {status}): {e}")
        return False
