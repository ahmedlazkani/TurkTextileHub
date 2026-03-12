# ===================================================
# bot/services/image_service.py
# خدمة الصور — رفع صور تليجرام إلى MinIO عبر KAYISOFT API
#
# الوصف:
#   تحوّل file_ids من تليجرام إلى روابط دائمة في MinIO.
#   تُستخدم من product_handler قبل إرسال المنتج لـ KAYISOFT.
#
# المنطق الكامل:
#   1. جلب file_path من تليجرام باستخدام file_id
#   2. تحميل بايتات الصورة من تليجرام
#   3. حساب SHA256 للملف + توليد اسم الملف بالصيغة المطلوبة
#   4. طلب Signed URL من KAYISOFT API (POST /api/extensions/signed-urls)
#   5. رفع الصورة مباشرة إلى MinIO باستخدام Signed URL
#   6. إعادة الرابط الدائم للصورة
#
# تنسيق اسم الملف (إلزامي):
#   {ISO-8601-timestamp}-{SHA256-hash}.{ext}
#   مثال: 2024-01-15T10-30-00-000Z-a1b2c3d4e5f6....jpg
#
# ملاحظة مهمة:
#   إذا فشل الرفع، تُعاد قائمة فارغة (لا crash).
#   المنتج يمكن حفظه بدون صور وإضافتها لاحقاً من KAYISOFT.
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

from bot.config import BOT_TOKEN

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# إعداد الثوابت
# ──────────────────────────────────────────────────────────

# رابط Telegram Bot API لجلب معلومات الملف
_TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_TELEGRAM_FILES = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

# رابط KAYISOFT API لطلب Signed URLs
_KAYISOFT_URL: str = os.getenv("KAYISOFT_API_URL", "").rstrip("/")
_KAYISOFT_KEY: str = os.getenv("KAYISOFT_API_KEY", "")

# مهلة الطلبات بالثواني
_TIMEOUT = 20

# الامتدادات المدعومة
_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
_DEFAULT_EXT = "jpg"


# ──────────────────────────────────────────────────────────
# دوال مساعدة
# ──────────────────────────────────────────────────────────

def _build_filename(file_bytes: bytes, ext: str) -> str:
    """
    يبني اسم الملف بالصيغة المطلوبة من KAYISOFT API.

    الصيغة: {ISO-8601-timestamp}-{SHA256-hash}.{ext}
    مثال:   2024-01-15T10-30-00-000Z-a1b2c3d4.jpg

    المدخلات:
        file_bytes (bytes): بايتات الصورة لحساب الـ hash
        ext        (str)  : امتداد الملف بدون نقطة

    المخرجات:
        str: اسم الملف بالصيغة المطلوبة
    """
    # توليد timestamp بصيغة ISO-8601 (استبدال : بـ - لتوافق أسماء الملفات)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"

    # حساب SHA256 للملف
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    ext_clean = ext.lower() if ext.lower() in _ALLOWED_EXTENSIONS else _DEFAULT_EXT
    return f"{timestamp}-{sha256_hash}.{ext_clean}"


def _get_telegram_file_info(file_id: str) -> Optional[dict]:
    """
    يجلب معلومات الملف من تليجرام (file_path).

    المدخلات:
        file_id (str): معرّف الملف في تليجرام

    المخرجات:
        dict: معلومات الملف مع file_path، أو None عند الفشل
    """
    try:
        response = requests.get(
            f"{_TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return data.get("result")
        logger.error(f"❌ فشل جلب معلومات الملف {file_id}: status={response.status_code}")
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في جلب معلومات الملف {file_id}: {e}")
        return None


def _download_telegram_file(file_path: str) -> Optional[bytes]:
    """
    يحمّل بايتات الصورة من تليجرام.

    المدخلات:
        file_path (str): مسار الملف من getFile API

    المخرجات:
        bytes: بايتات الصورة، أو None عند الفشل
    """
    try:
        url = f"{_TELEGRAM_FILES}/{file_path}"
        response = requests.get(url, timeout=_TIMEOUT)
        if response.status_code == 200:
            return response.content
        logger.error(f"❌ فشل تحميل الصورة من تليجرام: status={response.status_code}")
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الصورة: {e}")
        return None


def _request_signed_url(filename: str, content_type: str = "image/jpeg") -> Optional[str]:
    """
    يطلب Signed URL من KAYISOFT API لرفع الصورة.

    المدخلات:
        filename     (str): اسم الملف بالصيغة المطلوبة
        content_type (str): نوع المحتوى (افتراضي: image/jpeg)

    المخرجات:
        str: رابط Signed URL لرفع الصورة، أو None عند الفشل
    """
    if not _KAYISOFT_URL or not _KAYISOFT_KEY:
        logger.warning("⚠️ KAYISOFT API غير مضبوط — لا يمكن رفع الصور")
        return None

    try:
        response = requests.post(
            f"{_KAYISOFT_URL}/api/extensions/signed-urls",
            json={"filename": filename, "content_type": content_type},
            headers={
                "Authorization": f"Bearer {_KAYISOFT_KEY}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if response.status_code in (200, 201):
            data = response.json()
            signed_url = data.get("signed_url") or data.get("url")
            if signed_url:
                logger.debug(f"✅ تم الحصول على Signed URL للملف: {filename}")
                return signed_url
            logger.error(f"❌ الاستجابة لا تحتوي على signed_url: {data}")
            return None
        logger.error(
            f"❌ فشل طلب Signed URL: status={response.status_code}, body={response.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في طلب Signed URL: {e}")
        return None


def _upload_to_minio(signed_url: str, file_bytes: bytes, content_type: str = "image/jpeg") -> bool:
    """
    يرفع الصورة مباشرة إلى MinIO باستخدام Signed URL (PUT).

    المدخلات:
        signed_url   (str)  : رابط الرفع المؤقت
        file_bytes   (bytes): بايتات الصورة
        content_type (str)  : نوع المحتوى

    المخرجات:
        bool: True عند النجاح، False عند الفشل
    """
    try:
        response = requests.put(
            signed_url,
            data=file_bytes,
            headers={"Content-Type": content_type},
            timeout=_TIMEOUT,
        )
        if response.status_code in (200, 201, 204):
            logger.debug("✅ تم رفع الصورة إلى MinIO بنجاح")
            return True
        logger.error(f"❌ فشل رفع الصورة إلى MinIO: status={response.status_code}")
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في رفع الصورة إلى MinIO: {e}")
        return False


def _extract_public_url(signed_url: str) -> str:
    """
    يستخرج الرابط الدائم من Signed URL بحذف query parameters.

    المدخلات:
        signed_url (str): رابط الرفع المؤقت مع query params

    المخرجات:
        str: الرابط الدائم بدون query params
    """
    # الرابط الدائم = كل شيء قبل "?"
    return signed_url.split("?")[0]


# ──────────────────────────────────────────────────────────
# الدالة الرئيسية
# ──────────────────────────────────────────────────────────

def upload_telegram_photo(file_id: str) -> Optional[str]:
    """
    يحوّل file_id من تليجرام إلى رابط دائم في MinIO.

    المنطق الكامل:
        1. جلب file_path من تليجرام
        2. تحميل بايتات الصورة
        3. بناء اسم الملف: {timestamp}-{SHA256}.{ext}
        4. طلب Signed URL من KAYISOFT
        5. رفع الصورة إلى MinIO
        6. إعادة الرابط الدائم

    المدخلات:
        file_id (str): معرّف الصورة في تليجرام

    المخرجات:
        str: الرابط الدائم للصورة في MinIO، أو None عند الفشل
    """
    logger.info(f"🖼 بدء رفع صورة: file_id={file_id[:20]}...")

    # 1. جلب معلومات الملف من تليجرام
    file_info = _get_telegram_file_info(file_id)
    if not file_info:
        return None

    file_path = file_info.get("file_path", "")
    ext = file_path.rsplit(".", 1)[-1] if "." in file_path else _DEFAULT_EXT

    # 2. تحميل بايتات الصورة
    file_bytes = _download_telegram_file(file_path)
    if not file_bytes:
        return None

    # 3. بناء اسم الملف
    filename = _build_filename(file_bytes, ext)
    content_type = f"image/{ext}" if ext in _ALLOWED_EXTENSIONS else "image/jpeg"

    # 4. طلب Signed URL
    signed_url = _request_signed_url(filename, content_type)
    if not signed_url:
        return None

    # 5. رفع الصورة
    success = _upload_to_minio(signed_url, file_bytes, content_type)
    if not success:
        return None

    # 6. إعادة الرابط الدائم
    public_url = _extract_public_url(signed_url)
    logger.info(f"✅ تم رفع الصورة: {public_url}")
    return public_url


def upload_multiple_photos(file_ids: list) -> list:
    """
    يحوّل قائمة file_ids إلى روابط دائمة في MinIO.

    المنطق:
        يرفع كل صورة على حدة ويتجاهل الفاشلة منها.
        لا يوقف العملية إذا فشلت صورة واحدة.

    المدخلات:
        file_ids (list): قائمة file_ids من تليجرام

    المخرجات:
        list: قائمة الروابط الدائمة (قد تكون أقل من المدخلات عند فشل بعضها)
    """
    if not file_ids:
        return []

    urls = []
    for idx, file_id in enumerate(file_ids):
        url = upload_telegram_photo(file_id)
        if url:
            urls.append(url)
            logger.info(f"✅ صورة {idx + 1}/{len(file_ids)} مرفوعة")
        else:
            logger.warning(f"⚠️ فشل رفع الصورة {idx + 1}/{len(file_ids)} — تم التخطي")

    logger.info(f"📸 تم رفع {len(urls)}/{len(file_ids)} صورة بنجاح")
    return urls
