import os
import logging
import requests
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ==============================================================================
# KAYISOFT API Client
# ==============================================================================
# هذا الملف مسؤول عن التواصل مع KAYISOFT Backend بناءً على وثيقة الـ Endpoints
# المعتمدة. جميع الطلبات تتضمن الـ Headers المطلوبة (Token, Telegram-User-Id).
# ==============================================================================

KAYISOFT_API_URL = os.getenv("KAYISOFT_API_URL", "").rstrip("/")
KAYISOFT_API_TOKEN = os.getenv("KAYISOFT_API_TOKEN", "")

def _is_configured() -> bool:
    """يتحقق مما إذا كان KAYISOFT API مضبوطاً في متغيرات البيئة."""
    return bool(KAYISOFT_API_URL and KAYISOFT_API_TOKEN)

def _get_headers(telegram_user_id: str, language_code: str = "ar") -> Dict[str, str]:
    """
    يُنشئ الـ Headers المطلوبة لكل طلب حسب وثيقة KAYISOFT.
    """
    return {
        "Telegram-User-Id": str(telegram_user_id),
        "Authorization": f"Bearer {KAYISOFT_API_TOKEN}",
        "Platform": "telegram",
        "Accept-Language": language_code
    }

def _handle_response(response: requests.Response, endpoint: str) -> Optional[Any]:
    """يُعالج استجابة الطلب ويُسجل الأخطاء إن وجدت."""
    try:
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ KAYISOFT API Error ({endpoint}): {response.status_code} - {response.text}")
        return None
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return None

# ──────────────────────────────────────────────────────────
# Endpoint 1: Connect the seller account with Telegram
# ──────────────────────────────────────────────────────────
def connect_seller(token: str, telegram_user_id: str, telegram_user_name: Optional[str] = None) -> bool:
    """
    يربط حساب البائع في KAYISOFT بحسابه في تليجرام.
    يُستدعى عندما يضغط البائع على رابط /start=TOKEN
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي connect_seller.")
        return False

    endpoint = "/api/seller/telegram-bot/connect"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    payload = {
        "token": token,
        "telegram_user_id": str(telegram_user_id)
    }
    if telegram_user_name:
        payload["telegram_user_name"] = telegram_user_name

    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return False

# ──────────────────────────────────────────────────────────
# Endpoint 2: Create a channel if it does not exist
# ──────────────────────────────────────────────────────────
def register_channel(telegram_user_id: str, channel_id: str, channel_name: str) -> bool:
    """
    يُسجل قناة تليجرام الخاصة بالبائع في نظام KAYISOFT.
    يُستدعى بعد أن يضيف البائع البوت كأدمن في قناته.
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي register_channel.")
        return False

    endpoint = "/api/seller/telegram-bot/create-channel"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    payload = {
        "channel_id": str(channel_id),
        "telegram_user_id": str(telegram_user_id),
        "channel_name": channel_name
    }

    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return False

# ──────────────────────────────────────────────────────────
# Endpoint 3: Get categories
# ──────────────────────────────────────────────────────────
def get_categories(telegram_user_id: str, parent_id: str = "") -> Optional[List[Dict]]:
    """
    يجلب قائمة التصنيفات من KAYISOFT.
    إذا كان parent_id فارغاً ("")، يجلب التصنيفات الرئيسية (Root).
    إذا كان parent_id محدداً، يجلب التصنيفات الفرعية (Leaf).
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي get_categories.")
        return None

    endpoint = "/api/seller/categories"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    params = {"parent": parent_id}
    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return _handle_response(response, endpoint)
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return None

# ──────────────────────────────────────────────────────────
# Endpoint 4: Get attributes with options for a leaf category
# ──────────────────────────────────────────────────────────
def get_category_attributes(telegram_user_id: str, category_id: str) -> Optional[List[Dict]]:
    """
    يجلب الخصائص (Attributes) والخيارات (Options) الخاصة بتصنيف فرعي محدد.
    يُستخدم لبناء الـ Form الذي سيُعرض للبائع.
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي get_category_attributes.")
        return None

    endpoint = f"/api/seller/categories/{category_id}/attributes"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return _handle_response(response, endpoint)
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return None

# ──────────────────────────────────────────────────────────
# Endpoint 5: Get signed URLs to upload the media
# ──────────────────────────────────────────────────────────
def get_signed_urls(telegram_user_id: str, category_id: str, file_names: List[str]) -> Optional[List[Dict]]:
    """
    يطلب روابط رفع مؤمنة (Signed URLs) لرفع صور/فيديوهات المنتج.
    file_names يجب أن تكون بصيغة: <ISO-8601 timestamp>-<SHA-256 hash>
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي get_signed_urls.")
        return None

    endpoint = "/api/extensions/signed-urls"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    payload = {
        "operation": "put_product_variant_media",
        "file_names": file_names,
        "category_id": category_id
    }

    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return _handle_response(response, endpoint)
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return None

# ──────────────────────────────────────────────────────────
# Endpoint 6: Post products
# ──────────────────────────────────────────────────────────
def submit_product(telegram_user_id: str, product_data: Dict) -> Optional[Dict]:
    """
    يُرسل بيانات المنتج الكاملة (مع الـ Variants والصور) إلى KAYISOFT.
    """
    if not _is_configured():
        logger.warning("⚠️ KAYISOFT API غير مضبوط. تم تخطي submit_product.")
        return None

    endpoint = "/api/seller/products"
    url = f"{KAYISOFT_API_URL}{endpoint}"
    
    headers = _get_headers(telegram_user_id)
    
    try:
        response = requests.post(url, json=product_data, headers=headers, timeout=15)
        return _handle_response(response, endpoint)
    except Exception as e:
        logger.error(f"❌ KAYISOFT API Exception ({endpoint}): {str(e)}")
        return None
