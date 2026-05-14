"""
bot/keyboards.py
================
Centralized Keyboard Definitions
==================================
Purpose:
    Single source of truth for all Reply Keyboards and Inline Keyboards
    used throughout the bot. Separating keyboard definitions from handler
    logic keeps handlers clean and makes UI changes easy to apply globally.
"""
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from bot.services.language_service import get_string

def supplier_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    Main navigation keyboard for verified suppliers.
    """
    keyboard = [
        [KeyboardButton(get_string(lang, "btn_add_product"))],
        [KeyboardButton(get_string(lang, "btn_my_products")), KeyboardButton(get_string(lang, "btn_statistics"))],
        [KeyboardButton(get_string(lang, "btn_manage_channel"))],
        [KeyboardButton(get_string(lang, "btn_settings")), KeyboardButton(get_string(lang, "btn_subscription"))],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder=get_string(lang, "main_menu_supplier"),
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
