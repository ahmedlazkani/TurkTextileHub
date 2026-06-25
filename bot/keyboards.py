"""
bot/keyboards.py
================
Centralized Keyboard Definitions
==================================
Purpose:
    Single source of truth for all Reply Keyboards and Inline Keyboards
    used throughout the bot. Separating keyboard definitions from handler
    logic keeps handlers clean and makes UI changes easy to apply globally.

Layout (Supplier) — Simplified:
    Row 1: [➕ Add Product]           ← primary action — bot's core function
    Row 2: [🔗 Channel Management]   ← Telegram-specific — must stay in bot
    Row 3: [💡 Why TopKap?]  [❓ Help]
    Row 4: [🌐 Change Language]
    Row 5: [📦 Siparişlerim]          ← BLUE WebApp button → opens Orders page in app

Philosophy:
    The bot's single job is adding products & publishing to Telegram channels.
    Everything else (my products, statistics, settings, subscription) lives in
    the TopKap app, accessible via the blue Orders button.
"""
import os
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from bot.services.language_service import get_string

# TopKap Supplier Web App URL — opens inside Telegram WebApp (no external browser)
# KAYISOFT should provide the production URL + deep link to orders page
TOPKAP_APP_URL = os.getenv(
    "TOPKAP_APP_URL",
    "https://app-wholesale.dev.kayisoft.net"
)

# Orders deep-link — KAYISOFT to provide production URL pointing directly to orders page
# e.g. https://app-wholesale.kayisoft.net/orders  or  topkap://supplier/orders
TOPKAP_ORDERS_URL = os.getenv(
    "TOPKAP_ORDERS_URL",
    TOPKAP_APP_URL  # fallback to main app until KAYISOFT provides orders deep-link
)

# TopKap App download / smart link — takes user to app store or supplier page
# Uses KAYISOFT dynalink that detects platform and redirects accordingly
TOPKAP_DOWNLOAD_URL = os.getenv(
    "TOPKAP_DOWNLOAD_URL",
    "https://kayisoft.dynalinks.app/topkap/downloadApp"
)

def _get_miniapp_url() -> str | None:
    """
    Build the /webapp/download-app Mini App URL dynamically at call time.
    Reading env vars inside the function (not at module level) ensures we
    always get the latest value even if Railway injects them after import.
    """
    _raw_static = os.getenv("RAILWAY_STATIC_URL", "")
    _static_domain = _raw_static.replace("https://", "").replace("http://", "").rstrip("/")
    domain = (
        os.getenv("RAILWAY_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or _static_domain
        or ""
    )
    return f"https://{domain}/webapp/download-app" if domain else None

# TopGate Buyer/Trader App URL — used for product post buttons
TOPGATE_WEB_URL = os.getenv(
    "TOPGATE_WEB_URL",
    "https://topgate.app"
)

# ─── Orders button label per language ───────────────────────────────────────
_ORDERS_BTN = {
    "tr": "📦 Siparişlerim",
    "ar": "📦 طلبياتي",
    "en": "📦 My Orders",
}

# ─── TopKap App button label per language ────────────────────────────────────
_APP_BTN = {
    "tr": "📲 TopKap Uygulaması",
    "ar": "📲 تطبيق TopKap",
    "en": "📲 TopKap App",
}


def supplier_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for verified suppliers — simplified.

    Layout:
        Row 1: [➕ Add Product]           ← only action that needs the bot
        Row 2: [🔗 Channel Management]   ← Telegram-specific
        Row 3: [💡 Why TopKap?]  [❓ Help]
        Row 4: [🌐 Change Language]
        Row 5: [📦 Siparişlerim]          ← BLUE WebApp → orders page in app

    Removed: My Products, Statistics, Settings, Subscription
    All of those are accessible inside the app after tapping the blue button.
    """
    orders_label = _ORDERS_BTN.get(lang, _ORDERS_BTN["tr"])
    app_label    = _APP_BTN.get(lang, _APP_BTN["en"])

    # Row 5: TopKap App button
    # Strategy: open /webapp/download-app as a Mini App — that page immediately
    # redirects to the Universal Link (App Store / installed app) via JS.
    # This is the ONLY reliable way to trigger Universal Links from Telegram on iOS.
    # Fallback: plain KeyboardButton (handled in start_handler.py as inline URL button).
    miniapp_url = _get_miniapp_url()
    if miniapp_url:
        app_row = [KeyboardButton(app_label, web_app=WebAppInfo(url=miniapp_url))]
    else:
        app_row = [KeyboardButton(app_label)]

    keyboard = [
        # Row 1: Primary action — full width
        [KeyboardButton(get_string(lang, "btn_add_product"))],
        # Row 2: Channel Management — full width (Telegram-specific)
        [KeyboardButton(get_string(lang, "btn_manage_channel"))],
        # Row 3: Why TopKap + Help
        [
            KeyboardButton(get_string(lang, "btn_why_topkap")),
            KeyboardButton(get_string(lang, "btn_help")),
        ],
        # Row 4: Change Language — full width
        [KeyboardButton(get_string(lang, "btn_language"))],
        # Row 5: TopKap App — Mini App redirect or plain button
        app_row,
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder=(
            "🛍️ Tedarikçi Paneli" if lang == "tr"
            else ("🛍️ لوحة المورد" if lang == "ar"
            else "🛍️ Supplier Dashboard")
        ),
    )


def trader_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for registered traders / buyers.
    """
    keyboard = [
        [KeyboardButton(get_string(lang, "btn_browse_products"))],
        [KeyboardButton(get_string(lang, "btn_my_orders")), KeyboardButton(get_string(lang, "btn_saved"))],
        [KeyboardButton(get_string(lang, "btn_settings")), KeyboardButton(get_string(lang, "btn_help"))],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder=get_string(lang, "main_menu_trader"),
    )


def language_keyboard() -> InlineKeyboardMarkup:
    """
    Inline keyboard for language selection.
    """
    keyboard = [
        [InlineKeyboardButton("🇹🇷 Türkçe", callback_data="set_lang_tr")],
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
    ]
    return InlineKeyboardMarkup(keyboard)
