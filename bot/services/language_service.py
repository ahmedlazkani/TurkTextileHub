# ===================================================
# bot/services/language_service.py
# خدمة اللغات - تحميل ملفات الترجمة وإرجاع النصوص المترجمة
# تدعم: العربية (ar)، التركية (tr)، الإنجليزية (en)
# ===================================================

import json
import os

# المسار الكامل لمجلد الترجمات
_TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "translations")

# قاموس يخزن جميع الترجمات بعد التحميل
# الشكل: {"ar": {...}, "tr": {...}, "en": {...}}
_translations: dict = {}


def load_translations() -> dict:
    """
    تقرأ ملفات الترجمة الثلاثة وتخزنها في قاموس.
    يتم استدعاء هذه الدالة مرة واحدة عند استيراد الوحدة.
    
    المُخرجات:
        dict: قاموس يحتوي على جميع الترجمات مقسمة حسب اللغة
    """
    translations = {}
    
    # قائمة اللغات المدعومة مع أسماء ملفاتها
    supported_languages = ["ar", "tr", "en"]
    
    for lang in supported_languages:
        # بناء مسار ملف الترجمة
        file_path = os.path.join(_TRANSLATIONS_DIR, f"{lang}.json")
        
        try:
            # قراءة ملف JSON بترميز UTF-8 لدعم الأحرف العربية والتركية
            with open(file_path, "r", encoding="utf-8") as f:
                translations[lang] = json.load(f)
        except FileNotFoundError:
            # في حال عدم وجود الملف نسجل تحذيراً ونضع قاموساً فارغاً
            print(f"⚠️ تحذير: ملف الترجمة غير موجود: {file_path}")
            translations[lang] = {}
        except json.JSONDecodeError as e:
            # في حال وجود خطأ في صياغة JSON
            print(f"⚠️ تحذير: خطأ في قراءة ملف الترجمة {file_path}: {e}")
            translations[lang] = {}
    
    return translations


def get_string(lang: str, key: str) -> str:
    """
    ترجع النص المترجم للمفتاح المحدد باللغة المحددة.
    
    المعاملات:
        lang (str): رمز اللغة المطلوبة (ar, tr, en)
        key (str): مفتاح النص في ملف الترجمة
    
    المُخرجات:
        str: النص المترجم، أو النص العربي كاحتياطي، أو المفتاح نفسه
    
    منطق الاحتياطي:
        1. إذا وُجدت اللغة والمفتاح → يُرجع الترجمة المطلوبة
        2. إذا لم توجد اللغة أو المفتاح → يُرجع النص العربي
        3. إذا لم يوجد المفتاح في العربية أيضاً → يُرجع المفتاح نفسه
    """
    # البحث في اللغة المطلوبة أولاً
    if lang in _translations and key in _translations[lang]:
        return _translations[lang][key]
    
    # الاحتياطي: البحث في العربية
    if "ar" in _translations and key in _translations["ar"]:
        return _translations["ar"][key]
    
    # آخر احتياطي: إرجاع المفتاح نفسه إذا لم يوجد في أي لغة
    return key


# ===================================================
# تحميل الترجمات مرة واحدة عند استيراد الوحدة
# هذا يضمن عدم تكرار قراءة الملفات في كل طلب
# ===================================================
_translations = load_translations()
