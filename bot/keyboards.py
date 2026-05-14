"""
bot/keyboards.py
================
Centralized Keyboard Definitions
==================================

Purpose:
    Single source of truth for all Reply Keyboards and Inline Keyboards
    used throughout the bot. Separating keyboard definitions from handler
    logic keeps handlers clean and makes UI changes easy to apply globally.

Design Principles:
    - Reply Keyboards  : persistent bottom-bar menus for main navigation.
    - Inline Keyboards : contextual action buttons attached to messages.
    - All text labels use emoji + text for visual clarity on mobile.
    - resize_keyboard=True ensures compact display on all screen sizes.

Apps:
    - TopKap  : Supplier-facing mobile app (iOS & Android)
    - TopGate : Buyer-facing mobile app (iOS & Android)

Author:
    TurkTextileHub Engineering Team
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)

# ══════════════════════════════════════════════════════════════
# REPLY KEYBOARDS  (persistent bottom-bar navigation)
# ══════════════════════════════════════════════════════════════

def supplier_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for verified suppliers.

    Layout:
        [ ➕ Add Product ]
        [ 📦 My Products ]  [ 📊 Statistics ]
        [ 🔗 Manage Channel ]
        [ ⚙️ Settings ]     [ 💎 Subscription ]
    """
    keyboard = [
        [KeyboardButton("➕ Add Product")],
        [KeyboardButton("📦 My Products"), KeyboardButton("📊 Statistics")],
        [KeyboardButton("🔗 Manage Channel")],
        [KeyboardButton("⚙️ Settings"), KeyboardButton("💎 Subscription")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Choose an option…",
    )


def supplier_main_keyboard_ar() -> ReplyKeyboardMarkup:
    """Arabic variant of the supplier main keyboard."""
    keyboard = [
        [KeyboardButton("➕ إضافة منتج")],
        [KeyboardButton("📦 منتجاتي"), KeyboardButton("📊 إحصائياتي")],
        [KeyboardButton("🔗 إدارة القناة")],
        [KeyboardButton("⚙️ الإعدادات"), KeyboardButton("💎 اشتراكي")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="اختر خياراً…",
    )


def supplier_main_keyboard_tr() -> ReplyKeyboardMarkup:
    """Turkish variant of the supplier main keyboard."""
    keyboard = [
        [KeyboardButton("➕ Ürün Ekle")],
        [KeyboardButton("📦 Ürünlerim"), KeyboardButton("📊 İstatistikler")],
        [KeyboardButton("🔗 Kanal Yönetimi")],
        [KeyboardButton("⚙️ Ayarlar"), KeyboardButton("💎 Aboneliğim")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Bir seçenek seçin…",
    )


def trader_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for registered traders / buyers.

    Layout:
        [ 🔍 Browse Products ]
        [ 📋 My Orders ]  [ ❤️ Saved ]
        [ 📲 Open TopGate App ]
        [ ⚙️ Settings ]
    """
    keyboard = [
        [KeyboardButton("🔍 Browse Products")],
        [KeyboardButton("📋 My Orders"), KeyboardButton("❤️ Saved")],
        [KeyboardButton("📲 Open TopGate App")],
        [KeyboardButton("⚙️ Settings")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Choose an option…",
    )


def trader_main_keyboard_ar() -> ReplyKeyboardMarkup:
    """Arabic variant of the trader main keyboard."""
    keyboard = [
        [KeyboardButton("🔍 تصفح المنتجات")],
        [KeyboardButton("📋 طلباتي"), KeyboardButton("❤️ المحفوظة")],
        [KeyboardButton("📲 فتح تطبيق TopGate")],
        [KeyboardButton("⚙️ الإعدادات")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="اختر خياراً…",
    )


def trader_main_keyboard_tr() -> ReplyKeyboardMarkup:
    """Turkish variant of the trader main keyboard."""
    keyboard = [
        [KeyboardButton("🔍 Ürünlere Göz At")],
        [KeyboardButton("📋 Siparişlerim"), KeyboardButton("❤️ Kaydedilenler")],
        [KeyboardButton("📲 TopGate Uygulamasını Aç")],
        [KeyboardButton("⚙️ Ayarlar")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Bir seçenek seçin…",
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Remove the persistent Reply Keyboard (used during multi-step flows)."""
    return ReplyKeyboardRemove()


# ══════════════════════════════════════════════════════════════
# INLINE KEYBOARDS  (contextual action buttons)
# ══════════════════════════════════════════════════════════════

def role_selection_keyboard() -> InlineKeyboardMarkup:
    """
    Role selection shown on /start for unregistered users.
    Allows choosing between Supplier or Trader registration.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏭 Supplier / مورد", callback_data="supplier"),
            InlineKeyboardButton("🛒 Trader / تاجر",   callback_data="trader"),
        ]
    ])


def language_selection_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard shown during onboarding."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar"),
            InlineKeyboardButton("🇹🇷 Türkçe",  callback_data="set_lang_tr"),
            InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
        ]
    ])


def product_published_keyboard(
    product_id: str,
    seller_id: str,
    lang: str = "tr",
) -> InlineKeyboardMarkup:
    """
    Inline keyboard attached to every published product post on the channel.

    Buttons:
        - View on TopKap  : Deep link to supplier app (TopKap)
        - View on TopGate : Deep link to buyer app (TopGate)
        - Request Quote   : Opens RFQ flow in bot

    Args:
        product_id : KAYISOFT product ID (e.g. "608")
        seller_id  : KAYISOFT seller/supplier ID
        lang       : UI language ("ar", "tr", "en")
    """
    topkap_url  = f"https://topkap.app/product/{product_id}"
    topgate_url = f"https://topgate.app/product/{product_id}"
    rfq_data    = f"rfq_{product_id}"

    labels = {
        "ar": {
            "topkap":  "📲 عرض في TopKap",
            "topgate": "🛒 عرض في TopGate",
            "rfq":     "💬 طلب عرض سعر",
        },
        "tr": {
            "topkap":  "📲 TopKap'ta Görüntüle",
            "topgate": "🛒 TopGate'te Görüntüle",
            "rfq":     "💬 Fiyat Teklifi İste",
        },
        "en": {
            "topkap":  "📲 View on TopKap",
            "topgate": "🛒 View on TopGate",
            "rfq":     "💬 Request a Quote",
        },
    }.get(lang, {
        "topkap":  "📲 View on TopKap",
        "topgate": "🛒 View on TopGate",
        "rfq":     "💬 Request a Quote",
    })

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(labels["topkap"],  url=topkap_url),
            InlineKeyboardButton(labels["topgate"], url=topgate_url),
        ],
        [
            InlineKeyboardButton(labels["rfq"], callback_data=rfq_data),
        ],
    ])


def supplier_store_keyboard(seller_id: str, lang: str = "tr") -> InlineKeyboardMarkup:
    """
    Keyboard attached to the supplier's store announcement post.
    Directs existing Telegram followers to the TopKap app.

    Args:
        seller_id : KAYISOFT seller ID
        lang      : UI language
    """
    topkap_store_url = f"https://topkap.app/seller/{seller_id}"

    labels = {
        "ar": "📲 تابع متجري في TopKap",
        "tr": "📲 TopKap'ta Mağazamı Takip Et",
        "en": "📲 Follow My Store on TopKap",
    }.get(lang, "📲 Follow My Store on TopKap")

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(labels, url=topkap_store_url)]
    ])


def product_confirmation_keyboard(lang: str = "tr") -> InlineKeyboardMarkup:
    """
    Confirm / Edit / Cancel keyboard shown before final product submission.

    Args:
        lang : UI language
    """
    labels = {
        "ar": {"confirm": "✅ نشر المنتج", "edit": "✏️ تعديل", "cancel": "❌ إلغاء"},
        "tr": {"confirm": "✅ Ürünü Yayınla", "edit": "✏️ Düzenle", "cancel": "❌ İptal"},
        "en": {"confirm": "✅ Publish Product", "edit": "✏️ Edit", "cancel": "❌ Cancel"},
    }.get(lang, {"confirm": "✅ Publish", "edit": "✏️ Edit", "cancel": "❌ Cancel"})

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(labels["confirm"], callback_data="product_confirm_yes"),
            InlineKeyboardButton(labels["edit"],    callback_data="product_edit"),
        ],
        [
            InlineKeyboardButton(labels["cancel"], callback_data="product_confirm_no"),
        ],
    ])


def category_keyboard(categories: list[dict], lang: str = "tr") -> InlineKeyboardMarkup:
    """
    Dynamically build a category selection keyboard from KAYISOFT tree data.

    Args:
        categories : List of category dicts with keys: id, name_ar, name_tr, name_en
        lang       : UI language to pick the display name

    Returns:
        InlineKeyboardMarkup with 2 categories per row.
    """
    name_key = {"ar": "name_ar", "tr": "name_tr", "en": "name_en"}.get(lang, "name_en")

    buttons = []
    row = []
    for i, cat in enumerate(categories):
        label = cat.get(name_key) or cat.get("name_en") or cat.get("id", "?")
        row.append(InlineKeyboardButton(label, callback_data=f"kcat_{cat['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


def back_keyboard(callback_data: str = "back", lang: str = "tr") -> InlineKeyboardMarkup:
    """Generic single back-button keyboard."""
    label = {"ar": "◀️ رجوع", "tr": "◀️ Geri", "en": "◀️ Back"}.get(lang, "◀️ Back")
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=callback_data)]])


def skip_keyboard(callback_data: str = "skip", lang: str = "tr") -> InlineKeyboardMarkup:
    """Generic single skip-button keyboard for optional fields."""
    label = {"ar": "تخطي ←", "tr": "Atla →", "en": "Skip →"}.get(lang, "Skip →")
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=callback_data)]])
