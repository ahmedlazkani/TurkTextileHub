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
_translations: dict = {}


def load_translations() -> dict:
    """
    تقرأ ملفات الترجمة الثلاثة وتخزنها في قاموس.
    يتم استدعاء هذه الدالة مرة واحدة عند استيراد الوحدة.

    المُخرجات:
        dict: قاموس يحتوي على جميع الترجمات مقسمة حسب اللغة
    """
    translations = {}
    supported_languages = ["ar", "tr", "en"]

    for lang in supported_languages:
        file_path = os.path.join(_TRANSLATIONS_DIR, f"{lang}.json")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                translations[lang] = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ تحذير: ملف الترجمة غير موجود: {file_path}")
            translations[lang] = {}
        except json.JSONDecodeError as e:
            print(f"⚠️ تحذير: خطأ في قراءة ملف الترجمة {file_path}: {e}")
            translations[lang] = {}

    return translations


def get_string(lang: str, key: str) -> str:
    """
    ترجع النص المترجم للمفتاح المحدد باللغة المحددة.

    المعاملات:
        lang (str): رمز اللغة (ar, tr, en)
        key (str): مفتاح النص في ملف الترجمة

    المُخرجات:
        str: النص المترجم، أو النص العربي كاحتياطي، أو المفتاح نفسه
    """
    if lang in _translations and key in _translations[lang]:
        return _translations[lang][key]

    if "ar" in _translations and key in _translations["ar"]:
        return _translations["ar"][key]

    return key


def detect_lang(language_code: str) -> str:
    """
    يحدد اللغة المناسبة من كود لغة تليجرام.

    المعاملات:
        language_code (str): كود اللغة من تليجرام (مثل "ar", "tr-TR", "en-US")

    المُخرجات:
        str: "ar" أو "tr" أو "en"
    """
    if not language_code:
        return "ar"

    if language_code.startswith("tr"):
        return "tr"
    elif language_code.startswith("en"):
        return "en"
    else:
        return "ar"


# تحميل الترجمات مرة واحدة عند استيراد الوحدة
_translations = load_translations()
