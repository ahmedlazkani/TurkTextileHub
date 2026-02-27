# ===================================================
# bot/handlers/start_handler.py
# معالج أمر /start - يعرض لوحة تحكم شخصية للمستخدمين المسجلين
# ===================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.language_service import get_string, detect_lang
from bot.services import database_service


def _build_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح الترحيب للمستخدم الجديد."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "register_supplier_btn"), callback_data="supplier")],
        [InlineKeyboardButton(text=get_string(lang, "register_trader_btn"), callback_data="trader")],
        [InlineKeyboardButton(text=get_string(lang, "change_language"), callback_data="change_language")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_supplier_dashboard(lang: str) -> InlineKeyboardMarkup:
    """لوحة تحكم المورد."""
    if lang == "tr":
        keyboard = [
            [InlineKeyboardButton("➕ Ürün Ekle", callback_data="post_reg_add_product")],
            [InlineKeyboardButton("🌐 Dili Değiştir", callback_data="change_language")],
        ]
    elif lang == "en":
        keyboard = [
            [InlineKeyboardButton("➕ Add Product", callback_data="post_reg_add_product")],
            [InlineKeyboardButton("🌐 Change Language", callback_data="change_language")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="post_reg_add_product")],
            [InlineKeyboardButton("🌐 تغيير اللغة", callback_data="change_language")],
        ]
    return InlineKeyboardMarkup(keyboard)


def _build_trader_dashboard(lang: str) -> InlineKeyboardMarkup:
    """لوحة تحكم التاجر."""
    if lang == "tr":
        keyboard = [
            [InlineKeyboardButton("🔍 Ürünlere Göz At", callback_data="post_reg_browse_products")],
            [InlineKeyboardButton("🌐 Dili Değiştir", callback_data="change_language")],
        ]
    elif lang == "en":
        keyboard = [
            [InlineKeyboardButton("🔍 Browse Products", callback_data="post_reg_browse_products")],
            [InlineKeyboardButton("🌐 Change Language", callback_data="change_language")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🔍 تصفح المنتجات", callback_data="post_reg_browse_products")],
            [InlineKeyboardButton("🌐 تغيير اللغة", callback_data="change_language")],
        ]
    return InlineKeyboardMarkup(keyboard)


def _supplier_dashboard_text(lang: str, name: str, status: str) -> str:
    """نص لوحة تحكم المورد."""
    status_map = {
        "pending": {"ar": "⏳ قيد المراجعة", "en": "⏳ Pending Review", "tr": "⏳ İnceleniyor"},
        "approved": {"ar": "✅ موافق عليه", "en": "✅ Approved", "tr": "✅ Onaylandı"},
        "rejected": {"ar": "❌ مرفوض", "en": "❌ Rejected", "tr": "❌ Reddedildi"},
    }
    status_text = status_map.get(status, {}).get(lang, status)

    if lang == "tr":
        return (
            f"👋 Tekrar hoş geldiniz, *{name}*!\n\n"
            f"🏭 *Tedarikçi Hesabınız*\n"
            f"📊 Durum: {status_text}\n\n"
            f"Ne yapmak istersiniz?"
        )
    elif lang == "en":
        return (
            f"👋 Welcome back, *{name}*!\n\n"
            f"🏭 *Supplier Account*\n"
            f"📊 Status: {status_text}\n\n"
            f"What would you like to do?"
        )
    else:
        return (
            f"👋 أهلاً بعودتك، *{name}*!\n\n"
            f"🏭 *حساب المورد*\n"
            f"📊 الحالة: {status_text}\n\n"
            f"ماذا تريد أن تفعل؟"
        )


def _trader_dashboard_text(lang: str, name: str, status: str) -> str:
    """نص لوحة تحكم التاجر."""
    status_map = {
        "pending": {"ar": "⏳ قيد المراجعة", "en": "⏳ Pending Review", "tr": "⏳ İnceleniyor"},
        "approved": {"ar": "✅ موافق عليه", "en": "✅ Approved", "tr": "✅ Onaylandı"},
        "rejected": {"ar": "❌ مرفوض", "en": "❌ Rejected", "tr": "❌ Reddedildi"},
    }
    status_text = status_map.get(status, {}).get(lang, status)

    if lang == "tr":
        return (
            f"👋 Tekrar hoş geldiniz, *{name}*!\n\n"
            f"🛒 *Alıcı Hesabınız*\n"
            f"📊 Durum: {status_text}\n\n"
            f"Ne yapmak istersiniz?"
        )
    elif lang == "en":
        return (
            f"👋 Welcome back, *{name}*!\n\n"
            f"🛒 *Trader Account*\n"
            f"📊 Status: {status_text}\n\n"
            f"What would you like to do?"
        )
    else:
        return (
            f"👋 أهلاً بعودتك، *{name}*!\n\n"
            f"🛒 *حساب التاجر*\n"
            f"📊 الحالة: {status_text}\n\n"
            f"ماذا تريد أن تفعل؟"
        )


def _build_welcome_message(lang: str) -> str:
    """نص رسالة الترحيب للمستخدم الجديد."""
    return f"{get_string(lang, 'welcome')}\n\n{get_string(lang, 'role_selection')}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start.
    - إذا كان المستخدم مسجلاً كمورد → يعرض لوحة تحكم المورد
    - إذا كان مسجلاً كتاجر → يعرض لوحة تحكم التاجر
    - إذا كان جديداً → يعرض رسالة الترحيب مع خيارات التسجيل
    """
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    lang = detect_lang(update.effective_user.language_code or "")
    context.user_data["lang"] = lang
    telegram_id = str(update.effective_user.id)

    # التحقق أولاً: هل هو مورد مسجل؟
    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if supplier:
        name = supplier.get("company_name") or supplier.get("contact_name") or "مورد"
        status = supplier.get("status", "pending")
        await update.message.reply_text(
            text=_supplier_dashboard_text(lang, name, status),
            reply_markup=_build_supplier_dashboard(lang),
            parse_mode="Markdown"
        )
        return

    # التحقق ثانياً: هل هو تاجر مسجل؟
    trader = database_service.get_trader_by_telegram_id(int(telegram_id))
    if trader:
        name = trader.get("full_name") or trader.get("name") or "تاجر"
        status = trader.get("status", "pending")
        await update.message.reply_text(
            text=_trader_dashboard_text(lang, name, status),
            reply_markup=_build_trader_dashboard(lang),
            parse_mode="Markdown"
        )
        return

    # مستخدم جديد → رسالة الترحيب العادية
    await update.message.reply_text(
        text=_build_welcome_message(lang),
        reply_markup=_build_main_keyboard(lang)
    )


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض قائمة اختيار اللغة."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ar")

    keyboard = [
        [InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang_ar")],
        [InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    ]

    await query.edit_message_text(
        text=get_string(lang, "select_language"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يضبط لغة المستخدم ويعيد عرض القائمة المناسبة."""
    query = update.callback_query
    await query.answer()

    callback = query.data
    if callback == "lang_tr":
        lang = "tr"
    elif callback == "lang_en":
        lang = "en"
    else:
        lang = "ar"

    context.user_data["lang"] = lang

    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.TYPING
    )

    telegram_id = str(query.from_user.id)

    # إعادة عرض اللوحة المناسبة بعد تغيير اللغة
    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if supplier:
        name = supplier.get("company_name") or supplier.get("contact_name") or "مورد"
        status = supplier.get("status", "pending")
        await query.edit_message_text(
            text=_supplier_dashboard_text(lang, name, status),
            reply_markup=_build_supplier_dashboard(lang),
            parse_mode="Markdown"
        )
        return

    trader = database_service.get_trader_by_telegram_id(int(telegram_id))
    if trader:
        name = trader.get("full_name") or trader.get("name") or "تاجر"
        status = trader.get("status", "pending")
        await query.edit_message_text(
            text=_trader_dashboard_text(lang, name, status),
            reply_markup=_build_trader_dashboard(lang),
            parse_mode="Markdown"
        )
        return

    await query.edit_message_text(
        text=_build_welcome_message(lang),
        reply_markup=_build_main_keyboard(lang)
    )
