# ===================================================
# bot/services/language_service.py
# خدمة اللغات - تحميل ملفات الترجمة وإرجاع النصوص المترجمة
# تدعم: العربية (ar)، التركية (tr)، الإنجليزية (en)
# ===================================================

import json
import os

# المسار الكامل لمجلد الترجمات
_TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "locales")

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

    if "tr" in _translations and key in _translations["tr"]:
        return _translations["tr"][key]

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
        return "tr"

    if language_code.startswith("ar"):
        return "ar"
    elif language_code.startswith("tr"):
        return "tr"
    elif language_code.startswith("en"):
        return "en"
    else:
        return "tr"


# تحميل الترجمات مرة واحدة عند استيراد الوحدة
_translations = load_translations()

# ── In-memory language store ──────────────────────────────────────────────────
# NOTE: This dict lives in RAM and is cleared on every Railway restart.
# Until a persistent DB is added, we use telegram_language_code as a fallback
# so users don't revert to Turkish after every deployment.
_user_langs: dict = {}


def get_user_lang(telegram_id: str, telegram_language_code: str = "") -> str:
    """
    Return the stored language for this user, or detect it from Telegram's
    language_code if not yet set.

    Priority:
      1. Explicitly set by user via language button  → stored in _user_langs
      2. Detected from Telegram account language     → detect_lang(language_code)
      3. Default fallback                            → "tr"

    Args:
        telegram_id:           Telegram user ID as string
        telegram_language_code: user.language_code from the Update object
                                (e.g. "ar", "tr-TR", "en-US").  Optional.
    """
    stored = _user_langs.get(str(telegram_id))
    if stored:
        return stored
    if telegram_language_code:
        detected = detect_lang(telegram_language_code)
        # Cache it so subsequent calls in the same session are consistent
        _user_langs[str(telegram_id)] = detected
        return detected
    return "tr"


def set_user_lang(telegram_id: str, lang: str) -> None:
    """Explicitly set the language for a user (called from language selection button)."""
    _user_langs[str(telegram_id)] = lang
