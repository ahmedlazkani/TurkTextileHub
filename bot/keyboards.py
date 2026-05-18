"""
bot/keyboards.py
================
Centralized Keyboard Definitions
==================================
Purpose:
    Single source of truth for all Reply Keyboards and Inline Keyboards
    used throughout the bot. Separating keyboard definitions from handler
    logic keeps handlers clean and makes UI changes easy to apply globally.

Layout (Supplier):
    Row 1: [➕ Add Product]                    ← primary action, full width
    Row 2: [📦 My Products]  [📊 Statistics]
    Row 3: [🔗 Channel Management]             ← full width
    Row 4: [⚙️ Settings]    [💎 Subscription]
    Row 5: [💡 Why TopKap?]  [❓ Help]
    Row 6: [📱 TopKap App]                     ← WebApp button (opens in Telegram)

NOTE: "Share TopGate Profile" button removed — redundant with the blue WebApp
      button and the TopKap App row button. Buyers can be reached via product posts.
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
TOPKAP_APP_URL = os.getenv(
    "TOPKAP_APP_URL",
    "https://app-wholesale.dev.kayisoft.net"
)

# TopGate Buyer/Trader App URL — used for product post buttons
TOPGATE_WEB_URL = os.getenv(
    "TOPGATE_WEB_URL",
    "https://topgate.app"
)


def supplier_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for verified suppliers.

    Layout:
        Row 1: [➕ Add Product]                    ← primary action, full width
        Row 2: [📦 My Products]  [📊 Statistics]
        Row 3: [🔗 Channel Management]             ← full width
        Row 4: [⚙️ Settings]    [💎 Subscription]
        Row 5: [💡 Why TopKap?]  [❓ Help]
        Row 6: [📱 TopKap App]                     ← WebApp button (opens in Telegram)

    The WebApp button opens the TopKap supplier app directly inside Telegram
    using Telegram's built-in WebApp feature — no external browser needed.
    """
    keyboard = [
        # Row 1: Primary action — full width
        [KeyboardButton(get_string(lang, "btn_add_product"))],
        # Row 2: Products & Stats
        [
            KeyboardButton(get_string(lang, "btn_my_products")),
            KeyboardButton(get_string(lang, "btn_statistics")),
        ],
        # Row 3: Channel Management — full width
        [KeyboardButton(get_string(lang, "btn_manage_channel"))],
        # Row 4: Settings & Subscription
        [
            KeyboardButton(get_string(lang, "btn_settings")),
            KeyboardButton(get_string(lang, "btn_subscription")),
        ],
        # Row 5: Why TopKap + Help
        [
            KeyboardButton(get_string(lang, "btn_why_topkap")),
            KeyboardButton(get_string(lang, "btn_help")),
        ],
        # Row 6: TopKap App — WebApp button (opens supplier app inside Telegram)
        [
            KeyboardButton(
                "📱 TopKap App",
                web_app=WebAppInfo(url=TOPKAP_APP_URL),
            )
        ],
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
