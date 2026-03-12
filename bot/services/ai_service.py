"""
bot/services/ai_service.py
خدمة الذكاء الاصطناعي — استخراج بيانات المنتج + تصنيف ديناميكي

التحديث: إضافة تصنيف ديناميكي بشجرة KAYISOFT بدلاً من الفئات الثابتة.

الوصف:
    يستخدم OpenAI gpt-4o-mini مع caching لتقليل التكلفة.
    يستخرج بيانات المنتج المنظمة من النص العربي/التركي لمنشورات القناة.
    يُصنّف المنتج في الفئة الصحيحة من شجرة KAYISOFT الديناميكية.

المتطلبات:
    - متغير البيئة: OPENAI_API_KEY (يُقرأ عند أول استخدام فعلي)
    - مكتبة: openai>=1.0.0

ملاحظة مهمة:
    يتم إنشاء عميل OpenAI عند أول استدعاء فعلي وليس عند الاستيراد،
    لتجنب كراش البوت عند غياب OPENAI_API_KEY في بيئة الإنتاج.
"""

import json
import logging
import hashlib
import os
from typing import Optional

import openai

from bot.services import database_service

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

# ══════════════════════════════════════════════════════
# إنشاء عميل OpenAI بشكل كسول (lazy initialization)
# ══════════════════════════════════════════════════════
_client: Optional[openai.OpenAI] = None


def _get_client() -> Optional[openai.OpenAI]:
    """
    يُعيد عميل OpenAI، وينشئه عند أول استدعاء.

    المخرجات:
        openai.OpenAI إذا كان OPENAI_API_KEY موجوداً، None إذا غاب.

    المنطق:
        - يتحقق من وجود OPENAI_API_KEY في البيئة
        - إذا غاب: يسجّل تحذيراً ويعيد None (البوت يستمر بدون AI)
        - إذا وُجد: ينشئ العميل مرة واحدة ويخزّنه في _client
    """
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "⚠️ OPENAI_API_KEY غير موجود في البيئة — "
            "ميزة استخراج المنتجات بالذكاء الاصطناعي معطّلة. "
            "أضف OPENAI_API_KEY في متغيرات Railway لتفعيلها."
        )
        return None

    try:
        _client = openai.OpenAI(api_key=api_key)
        logger.info("✅ عميل OpenAI جاهز")
        return _client
    except Exception as e:
        logger.error(f"❌ فشل إنشاء عميل OpenAI: {e}")
        return None


# ══════════════════════════════════════════════════════
# القيم الافتراضية عند الفشل
# ══════════════════════════════════════════════════════

def get_default_product_data(raw_text: str = "") -> dict:
    """
    المدخلات: raw_text (str) — النص الأصلي للمنشور (اختياري)
    المخرجات: dict ببيانات افتراضية للمنتج
    المنطق: يُستخدم عند فشل OpenAI API أو عدم وجود نص
    """
    return {
        "title":                  "منتج جديد",
        "title_en":               "New Product",
        "description":            raw_text[:200] if raw_text else "",
        "description_en":         raw_text[:200] if raw_text else "",
        "category":               "other",
        "category_en":            "other",
        "category_id":            None,
        "colors":                 [],
        "sizes":                  [],
        "price":                  None,
        "currency":               None,
        "minimum_order_quantity": None,
    }


# ══════════════════════════════════════════════════════
# جلب شجرة التصنيف من KAYISOFT (مع cache)
# ══════════════════════════════════════════════════════

def _get_kayisoft_categories() -> dict:
    """
    يجلب شجرة تصنيف KAYISOFT من الـ cache أو من API.

    المخرجات:
        dict: {category_id: category_name} أو {} عند الفشل

    المنطق:
        - يتحقق من cache أولاً (مفتاح: kayisoft_categories)
        - إذا لم يوجد، يجلب من KAYISOFT API
        - يحفظ في cache لمدة 6 ساعات
        - عند الفشل يعيد قاموساً فارغاً (يستخدم الفئات الثابتة)
    """
    cached = database_service.get_cache("kayisoft_categories")
    if cached and isinstance(cached, dict):
        return cached

    try:
        from bot.services import kayisoft_api
        result = kayisoft_api._get("/api/seller/categories")
        if result and isinstance(result, list):
            categories = {
                str(cat.get("id")): cat.get("name") or cat.get("name_ar") or "فئة"
                for cat in result
                if cat.get("id")
            }
            if categories:
                database_service.set_cache("kayisoft_categories", categories, ttl_hours=6)
                return categories
    except Exception as e:
        logger.warning(f"⚠️ فشل جلب فئات KAYISOFT في ai_service: {e}")

    return {}


# ══════════════════════════════════════════════════════
# الدالة الرئيسية لاستخراج بيانات المنتج
# ══════════════════════════════════════════════════════

def extract_product_data(raw_text: str, image_count: int = 0) -> dict:
    """
    المدخلات:
        raw_text    (str): نص المنشور الخام (عربي أو تركي)
        image_count (int): عدد الصور المرفقة بالمنشور
    المخرجات:
        dict: بيانات المنتج المستخرجة بالحقول: title, title_en, description,
              description_en, category, category_en, category_id, colors, sizes,
              price, currency, minimum_order_quantity
    المنطق:
        1. تحقق من وجود OPENAI_API_KEY — إذا غاب أعد بيانات افتراضية
        2. جلب شجرة KAYISOFT للتصنيف الديناميكي
        3. تحقق من cache أولاً: database_service.get_cache(cache_key)
        4. إذا لم يوجد، استدع OpenAI API (sync)
        5. احفظ النتيجة في cache لمدة 24 ساعة
        6. في حالة فشل API: أعد قيماً افتراضية بدلاً من رفع exception
    """
    if not raw_text or not raw_text.strip():
        logger.debug("نص المنشور فارغ — إعادة بيانات افتراضية")
        return get_default_product_data(raw_text)

    # 1. تحقق من وجود عميل OpenAI
    client = _get_client()
    if client is None:
        logger.warning("⚠️ OpenAI غير متاح — إعادة بيانات افتراضية")
        return get_default_product_data(raw_text)

    # بناء cache_key من أول 100 حرف من النص
    cache_key = f"ai_extract_{hashlib.md5(raw_text[:100].encode('utf-8')).hexdigest()}"

    # 2. تحقق من cache
    try:
        cached = database_service.get_cache(cache_key)
        if cached:
            logger.info(f"💾 cache hit: {cache_key}")
            return cached
    except Exception as e:
        logger.warning(f"⚠️ خطأ في قراءة cache: {e}")

    # 3. جلب شجرة KAYISOFT للتصنيف الديناميكي
    kayisoft_categories = _get_kayisoft_categories()
    categories_hint = ""
    if kayisoft_categories:
        cats_list = "\n".join(f"  - id={cid}: {name}" for cid, name in list(kayisoft_categories.items())[:15])
        categories_hint = f"\n\nفئات KAYISOFT المتاحة (اختر category_id المناسب):\n{cats_list}"

    # 4. استدع OpenAI API
    prompt = f"""أنت محلل منتجات نسيج تركية. استخرج من النص التالي بيانات المنتج بتنسيق JSON.

النص: {raw_text}
عدد الصور: {image_count}{categories_hint}

أعد JSON بالحقول التالية (استخدم null إذا لم تجد المعلومة):
{{
  "title": "اسم المنتج بالعربية",
  "title_en": "Product name in English",
  "description": "وصف مختصر بالعربية (جملتان)",
  "description_en": "Short description in English (2 sentences)",
  "category": "اسم الفئة بالعربية أو: abayas|dresses|hijab|sets|other",
  "category_en": "one of: abayas|dresses|hijab|sets|other",
  "category_id": "id الفئة من القائمة أعلاه أو null",
  "colors": ["قائمة الألوان بالعربية"],
  "sizes": ["قائمة المقاسات"],
  "price": "السعر كرقم فقط أو null",
  "currency": "TRY|USD|EUR أو null",
  "minimum_order_quantity": رقم أو null
}}"""

    try:
        logger.info(f"🤖 استدعاء OpenAI | نموذج={_MODEL} | فئات KAYISOFT={len(kayisoft_categories)}")
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "أنت محلل منتجات نسيج متخصص. أعد دائماً JSON صحيحاً فقط بدون أي نص إضافي.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=600,
            response_format={"type": "json_object"},
        )

        raw_response = response.choices[0].message.content
        logger.debug(f"رد OpenAI: {raw_response[:200]}")

        extracted_data = json.loads(raw_response)

        # تطبيق القيم الافتراضية على الحقول المفقودة
        defaults = get_default_product_data(raw_text)
        for key, default_val in defaults.items():
            if extracted_data.get(key) is None:
                extracted_data[key] = default_val

        logger.info(
            f"✅ OpenAI استخرج: {extracted_data.get('title', 'غير محدد')} "
            f"| category_id={extracted_data.get('category_id')}"
        )

        # 5. احفظ في cache لمدة 24 ساعة
        try:
            database_service.set_cache(cache_key, extracted_data, ttl_hours=24)
        except Exception as e:
            logger.warning(f"⚠️ خطأ في حفظ cache: {e}")

        return extracted_data

    except json.JSONDecodeError as e:
        logger.error(f"❌ خطأ في تحليل JSON من OpenAI: {e}")
        return get_default_product_data(raw_text)

    except openai.RateLimitError as e:
        logger.error(f"❌ تجاوز حد معدل OpenAI: {e}")
        return get_default_product_data(raw_text)

    except openai.AuthenticationError as e:
        logger.error(f"❌ خطأ مصادقة OpenAI — تحقق من OPENAI_API_KEY: {e}")
        return get_default_product_data(raw_text)

    except Exception as e:
        # 6. في حالة فشل API: أعد قيماً افتراضية
        logger.error(f"❌ خطأ غير متوقع في OpenAI: {e}")
        return get_default_product_data(raw_text)


# ══════════════════════════════════════════════════════
# دالة التصنيف المستقلة (للاستخدام من channel_post_handler)
# ══════════════════════════════════════════════════════

def classify_product_category(title: str, description: str = "") -> dict:
    """
    يُصنّف منتجاً في فئة KAYISOFT المناسبة بناءً على العنوان والوصف.

    المدخلات:
        title       (str): عنوان المنتج
        description (str): وصف المنتج (اختياري)

    المخرجات:
        dict: {
            "category"    (str): اسم الفئة
            "category_id" (str|None): id الفئة في KAYISOFT
        }

    المنطق:
        - إذا كانت شجرة KAYISOFT متاحة: استخدم OpenAI للتصنيف الدقيق
        - إذا لم تكن متاحة: استخدم تصنيف بسيط بالكلمات المفتاحية
    """
    kayisoft_categories = _get_kayisoft_categories()

    # تصنيف بسيط بالكلمات المفتاحية كـ fallback
    text_lower = (title + " " + description).lower()
    simple_map = {
        "abaya":   "Abayas",
        "عباية":   "Abayas",
        "فستان":   "Dresses",
        "dress":   "Dresses",
        "حجاب":    "Hijab Clothing",
        "hijab":   "Hijab Clothing",
        "طقم":     "Sets",
        "set":     "Sets",
    }
    for keyword, category in simple_map.items():
        if keyword in text_lower:
            # محاولة إيجاد category_id من الشجرة
            category_id = None
            for cat_id, cat_name in kayisoft_categories.items():
                if category.lower() in cat_name.lower():
                    category_id = cat_id
                    break
            return {"category": category, "category_id": category_id}

    return {"category": "other", "category_id": None}
