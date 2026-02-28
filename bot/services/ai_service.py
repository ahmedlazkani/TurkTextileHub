"""
bot/services/ai_service.py
خدمة الذكاء الاصطناعي — استخراج بيانات المنتج من نص المنشور

الوصف:
    يستخدم OpenAI gpt-4o-mini مع caching لتقليل التكلفة.
    يستخرج بيانات المنتج المنظمة من النص العربي/التركي لمنشورات القناة.

المتطلبات:
    - متغير البيئة: OPENAI_API_KEY (يُقرأ تلقائياً بـ openai.OpenAI())
    - مكتبة: openai>=1.0.0
"""

import json
import logging
import hashlib
from typing import Optional

import openai

from bot.services import database_service

logger = logging.getLogger(__name__)

# عميل OpenAI — يقرأ OPENAI_API_KEY تلقائياً من البيئة
client = openai.OpenAI()

_MODEL = "gpt-4o-mini"


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
        "colors":                 [],
        "sizes":                  [],
        "price":                  None,
        "currency":               None,
        "minimum_order_quantity": None,
    }


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
              description_en, category, category_en, colors, sizes,
              price, currency, minimum_order_quantity
    المنطق:
        1. تحقق من cache أولاً: database_service.get_cache(cache_key)
        2. إذا لم يوجد، استدع OpenAI API (sync)
        3. احفظ النتيجة في cache لمدة 24 ساعة
        4. في حالة فشل API: أعد قيماً افتراضية بدلاً من رفع exception
    """
    if not raw_text or not raw_text.strip():
        logger.debug("نص المنشور فارغ — إعادة بيانات افتراضية")
        return get_default_product_data(raw_text)

    # بناء cache_key من أول 100 حرف من النص
    cache_key = f"ai_extract_{hashlib.md5(raw_text[:100].encode('utf-8')).hexdigest()}"

    # 1. تحقق من cache أولاً
    try:
        cached = database_service.get_cache(cache_key)
        if cached:
            logger.info(f"💾 cache hit: {cache_key}")
            return cached
    except Exception as e:
        logger.warning(f"⚠️ خطأ في قراءة cache: {e}")

    # 2. استدع OpenAI API (sync)
    prompt = f"""أنت محلل منتجات نسيج تركية. استخرج من النص التالي بيانات المنتج بتنسيق JSON.

النص: {raw_text}
عدد الصور: {image_count}

أعد JSON بالحقول التالية (استخدم null إذا لم تجد المعلومة):
{{
  "title": "اسم المنتج بالعربية",
  "title_en": "Product name in English",
  "description": "وصف مختصر بالعربية (جملتان)",
  "description_en": "Short description in English (2 sentences)",
  "category": "إحدى الفئات: abayas|dresses|hijab|sets|other",
  "category_en": "one of: abayas|dresses|hijab|sets|other",
  "colors": ["قائمة الألوان بالعربية"],
  "sizes": ["قائمة المقاسات"],
  "price": "السعر كرقم فقط أو null",
  "currency": "TRY|USD|EUR أو null",
  "minimum_order_quantity": رقم أو null
}}"""

    try:
        logger.info(f"🤖 استدعاء OpenAI | نموذج={_MODEL}")
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

        logger.info(f"✅ OpenAI استخرج: {extracted_data.get('title', 'غير محدد')}")

        # 3. احفظ في cache لمدة 24 ساعة
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
        # 4. في حالة فشل API: أعد قيماً افتراضية بدلاً من رفع exception
        logger.error(f"❌ خطأ غير متوقع في OpenAI: {e}")
        return get_default_product_data(raw_text)
