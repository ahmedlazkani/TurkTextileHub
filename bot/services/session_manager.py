# ===================================================
# bot/services/session_manager.py
# إدارة جلسات المستخدمين — تخزين مؤقت في الذاكرة مع Supabase cache كطبقة ثانية
#
# الوصف:
#   يوفر واجهة موحدة لقراءة وكتابة بيانات الجلسة لكل مستخدم.
#   الطبقة الأولى: dict في الذاكرة (سريع، يُمسح عند إعادة تشغيل البوت).
#   الطبقة الثانية: Supabase cache (دائم، يبقى بعد إعادة التشغيل).
#
# الاستخدام:
#   from bot.services.session_manager import SessionManager
#   session = SessionManager(user_id=123456)
#   session.set("lang", "ar")
#   lang = session.get("lang", default="ar")
#   session.clear()
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from typing import Any, Optional

from bot.services import database_service

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# الذاكرة المشتركة بين جميع كائنات SessionManager
# مفتاحها: user_id (int) ← dict بيانات الجلسة
# ──────────────────────────────────────────────────────────
_MEMORY_STORE: dict[int, dict] = {}

# مدة صلاحية الجلسة في Supabase cache (بالساعات)
_SESSION_TTL_HOURS = 48


class SessionManager:
    """
    مدير جلسة لمستخدم واحد.

    يدمج طبقتين من التخزين:
    - الذاكرة (in-process dict): سريعة، تُفقد عند إعادة التشغيل.
    - Supabase cache: دائمة، تُحمَّل تلقائياً عند بداية جلسة جديدة.

    المعاملات:
        user_id (int): معرّف المستخدم في تليجرام.
    """

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self._cache_key = f"session_{user_id}"

        # تهيئة الذاكرة المحلية إذا لم تكن موجودة
        if user_id not in _MEMORY_STORE:
            _MEMORY_STORE[user_id] = {}
            # محاولة تحميل الجلسة من Supabase cache عند أول استخدام
            self._load_from_cache()

    # ──────────────────────────────────────────────────────────
    # واجهة القراءة والكتابة
    # ──────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        يقرأ قيمة من جلسة المستخدم.

        المعاملات:
            key     (str): مفتاح البيانات المطلوبة.
            default (Any): القيمة الافتراضية إذا لم يوجد المفتاح.

        المُخرجات:
            Any: القيمة المخزّنة، أو default إذا لم توجد.
        """
        return _MEMORY_STORE.get(self.user_id, {}).get(key, default)

    def set(self, key: str, value: Any, persist: bool = False) -> None:
        """
        يكتب قيمة في جلسة المستخدم.

        المعاملات:
            key     (str) : مفتاح البيانات.
            value   (Any) : القيمة المراد تخزينها.
            persist (bool): إذا True، يحفظ الجلسة كاملة في Supabase cache فوراً.
        """
        if self.user_id not in _MEMORY_STORE:
            _MEMORY_STORE[self.user_id] = {}

        _MEMORY_STORE[self.user_id][key] = value
        logger.debug(f"📝 session[{self.user_id}][{key}] = {value!r}")

        if persist:
            self._save_to_cache()

    def set_many(self, data: dict, persist: bool = False) -> None:
        """
        يكتب عدة قيم دفعةً واحدة.

        المعاملات:
            data    (dict): قاموس بالمفاتيح والقيم المراد تخزينها.
            persist (bool): إذا True، يحفظ في Supabase cache بعد الكتابة.
        """
        if self.user_id not in _MEMORY_STORE:
            _MEMORY_STORE[self.user_id] = {}

        _MEMORY_STORE[self.user_id].update(data)
        logger.debug(f"📝 session[{self.user_id}] bulk update: {list(data.keys())}")

        if persist:
            self._save_to_cache()

    def delete(self, key: str) -> None:
        """
        يحذف مفتاحاً واحداً من الجلسة.

        المعاملات:
            key (str): المفتاح المراد حذفه.
        """
        _MEMORY_STORE.get(self.user_id, {}).pop(key, None)
        logger.debug(f"🗑 session[{self.user_id}] deleted key: {key}")

    def clear(self) -> None:
        """
        يمسح جلسة المستخدم بالكامل من الذاكرة.
        لا يحذف من Supabase cache (تنتهي صلاحيتها تلقائياً).
        """
        _MEMORY_STORE.pop(self.user_id, None)
        logger.info(f"🧹 session[{self.user_id}] cleared")

    def all(self) -> dict:
        """
        يُعيد نسخة من بيانات الجلسة الكاملة.

        المُخرجات:
            dict: قاموس بجميع بيانات الجلسة الحالية.
        """
        return dict(_MEMORY_STORE.get(self.user_id, {}))

    # ──────────────────────────────────────────────────────────
    # دوال مساعدة للتخزين الدائم
    # ──────────────────────────────────────────────────────────

    def save(self) -> bool:
        """
        يحفظ الجلسة الكاملة في Supabase cache.

        المُخرجات:
            bool: True عند النجاح، False عند الفشل.
        """
        return self._save_to_cache()

    def _save_to_cache(self) -> bool:
        """
        دالة داخلية: تحفظ بيانات الجلسة الحالية في Supabase cache.

        المُخرجات:
            bool: True عند النجاح، False عند الفشل.
        """
        data = _MEMORY_STORE.get(self.user_id, {})
        try:
            result = database_service.set_cache(
                cache_key=self._cache_key,
                value=data,
                ttl_hours=_SESSION_TTL_HOURS,
            )
            if result:
                logger.debug(f"💾 session[{self.user_id}] persisted to cache")
            return result
        except Exception as e:
            logger.error(f"❌ فشل حفظ session[{self.user_id}] في cache: {e}")
            return False

    def _load_from_cache(self) -> None:
        """
        دالة داخلية: تحمّل بيانات الجلسة من Supabase cache إلى الذاكرة.
        تُستدعى مرة واحدة عند إنشاء الكائن لأول مرة.
        """
        try:
            cached = database_service.get_cache(self._cache_key)
            if cached and isinstance(cached, dict):
                _MEMORY_STORE[self.user_id] = cached
                logger.debug(f"📂 session[{self.user_id}] loaded from cache ({len(cached)} keys)")
        except Exception as e:
            logger.warning(f"⚠️ فشل تحميل session[{self.user_id}] من cache: {e}")


# ──────────────────────────────────────────────────────────
# دوال مساعدة على مستوى الوحدة (لا تحتاج كائن SessionManager)
# ──────────────────────────────────────────────────────────

def get_user_lang(user_id: int, default: str = "ar") -> str:
    """
    يُعيد لغة المستخدم المحفوظة في الجلسة.

    المعاملات:
        user_id (int): معرّف المستخدم.
        default (str): اللغة الافتراضية إذا لم تُحفظ لغة مسبقاً (ar).

    المُخرجات:
        str: رمز اللغة — "ar" أو "tr" أو "en".
    """
    session = SessionManager(user_id)
    return session.get("lang", default)


def set_user_lang(user_id: int, lang: str, persist: bool = True) -> None:
    """
    يضبط لغة المستخدم ويحفظها في الجلسة.

    المعاملات:
        user_id (int) : معرّف المستخدم.
        lang    (str) : رمز اللغة — "ar" أو "tr" أو "en".
        persist (bool): إذا True، يحفظ في Supabase cache (افتراضي: True).
    """
    session = SessionManager(user_id)
    session.set("lang", lang, persist=persist)
    logger.info(f"🌐 user[{user_id}] language → {lang}")


def clear_all_sessions() -> int:
    """
    يمسح جميع الجلسات من الذاكرة.
    يُستخدم في الاختبارات أو عند الحاجة لإعادة تهيئة الذاكرة.

    المُخرجات:
        int: عدد الجلسات التي تم مسحها.
    """
    count = len(_MEMORY_STORE)
    _MEMORY_STORE.clear()
    logger.info(f"🧹 تم مسح {count} جلسة من الذاكرة")
    return count


def get_active_session_count() -> int:
    """
    يُعيد عدد الجلسات النشطة حالياً في الذاكرة.

    المُخرجات:
        int: عدد الجلسات في _MEMORY_STORE.
    """
    return len(_MEMORY_STORE)
