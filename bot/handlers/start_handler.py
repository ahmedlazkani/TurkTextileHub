"""
bot/handlers/start_handler.py — TopKap Bot v3.0
Professional Onboarding Experience
- Welcome banner image
- Random motivational messages
- Language confirmation
- Guided dashboard with descriptions
- Full help center
- Teaser messages for coming-soon features
"""
import re
import os
import random
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from bot.services.language_service import get_string, detect_lang, get_user_lang, set_user_lang
from bot.keyboards import language_keyboard, supplier_main_keyboard
from bot.services.kayisoft_api import KayisoftAPI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ASSET PATH
# ─────────────────────────────────────────────
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
WELCOME_BANNER = os.path.join(ASSETS_DIR, "welcome_banner.jpg")
# ───────────────────────────────────────────────
# MOTIVATIONAL MESSAGES — loaded from translation files
# ───────────────────────────────────────────────
MOTIVATIONAL_KEYS = [
    "motivational_1", "motivational_2", "motivational_3",
    "motivational_4", "motivational_5",
]

def _get_motivational(lang: str) -> str:
    """Pick a random motivational message from translation files."""
    msgs = [get_string(lang, k) for k in MOTIVATIONAL_KEYS]
    # Filter out any keys that weren't found (returned as-is)
    msgs = [m for m in msgs if not m.startswith("motivational_")]
    return random.choice(msgs) if msgs else "🌟 <b>TopKap'a Hoş Geldiniz!</b>"

# ───────────────────────────────────────────────
# LANGUAGE CONFIRMED MESSAGES
# ───────────────────────────────────────────────────
LANG_CONFIRMED = {
    "tr": "🇹🇷 <b>Türkçe seçildi!</b>\n\nLütfen aşağıdaki paneli kullanın 👇",
    "ar": "🇸🇦 <b>تم اختيار العربية!</b>\n\nيرجى استخدام اللوحة أدناه 👇",
    "en": "🇬🇧 <b>English selected!</b>\n\nPlease use the panel below 👇",
}

# ─────────────────────────────────────────────
# SETTINGS MESSAGES
# ─────────────────────────────────────────────
SETTINGS_MSG = {
    "tr": "⚙️ <b>Ayarlar</b>\n\nDil değiştirmek için aşağıdan seçin:",
    "ar": "⚙️ <b>الإعدادات</b>\n\nاختر اللغة من الأزرار أدناه:",
    "en": "⚙️ <b>Settings</b>\n\nSelect your language from below:",
}

# ─────────────────────────────────────────────
# COMING SOON — teaser messages per feature
# ─────────────────────────────────────────────
COMING_SOON = {
    "tr": {
        "my_products": (
            "📦 <b>Ürünlerim</b>\n\n"
            "🔜 <i>Bu özellik çok yakında aktif olacak!</i>\n\n"
            "Tüm ürünlerinizi tek ekranda yönetebilecek,\n"
            "stok durumunu takip edebilecek ve\n"
            "fiyatları anında güncelleyebileceksiniz.\n\n"
            "⏳ <b>Yakında — Stay tuned!</b>"
        ),
        "statistics": (
            "📊 <b>İstatistikler</b>\n\n"
            "🔜 <i>Bu özellik çok yakında aktif olacak!</i>\n\n"
            "Gerçek zamanlı satış raporları,\n"
            "ürün görüntülenme istatistikleri ve\n"
            "kanal performans analizleri görebileceksiniz.\n\n"
            "⏳ <b>Yakında — Stay tuned!</b>"
        ),
        "subscription": (
            "💎 <b>Aboneliğim</b>\n\n"
            "🔜 <i>Bu özellik çok yakında aktif olacak!</i>\n\n"
            "Premium planlar, özel özellikler ve\n"
            "öncelikli destek hizmetine erişebileceksiniz.\n\n"
            "⏳ <b>Yakında — Stay tuned!</b>"
        ),
    },
    "ar": {
        "my_products": (
            "📦 <b>منتجاتي</b>\n\n"
            "🔜 <i>هذه الميزة ستكون متاحة قريباً جداً!</i>\n\n"
            "ستتمكن من إدارة جميع منتجاتك في شاشة واحدة،\n"
            "متابعة حالة المخزون وتحديث الأسعار فوراً.\n\n"
            "⏳ <b>قريباً — ترقّب!</b>"
        ),
        "statistics": (
            "📊 <b>الإحصائيات</b>\n\n"
            "🔜 <i>هذه الميزة ستكون متاحة قريباً جداً!</i>\n\n"
            "تقارير مبيعات فورية،\n"
            "إحصائيات مشاهدات المنتجات\n"
            "وتحليل أداء قناتك.\n\n"
            "⏳ <b>قريباً — ترقّب!</b>"
        ),
        "subscription": (
            "💎 <b>اشتراكي</b>\n\n"
            "🔜 <i>هذه الميزة ستكون متاحة قريباً جداً!</i>\n\n"
            "خطط مميزة، ميزات حصرية\n"
            "وخدمة دعم ذات أولوية.\n\n"
            "⏳ <b>قريباً — ترقّب!</b>"
        ),
    },
    "en": {
        "my_products": (
            "📦 <b>My Products</b>\n\n"
            "🔜 <i>This feature is coming very soon!</i>\n\n"
            "You'll be able to manage all your products in one screen,\n"
            "track stock status and update prices instantly.\n\n"
            "⏳ <b>Coming soon — Stay tuned!</b>"
        ),
        "statistics": (
            "📊 <b>Statistics</b>\n\n"
            "🔜 <i>This feature is coming very soon!</i>\n\n"
            "Real-time sales reports,\n"
            "product view statistics and\n"
            "channel performance analytics.\n\n"
            "⏳ <b>Coming soon — Stay tuned!</b>"
        ),
        "subscription": (
            "💎 <b>My Subscription</b>\n\n"
            "🔜 <i>This feature is coming very soon!</i>\n\n"
            "Premium plans, exclusive features and\n"
            "priority support access.\n\n"
            "⏳ <b>Coming soon — Stay tuned!</b>"
        ),
    },
}

# ─────────────────────────────────────────────
# HELP GUIDE — full step-by-step guide
# ─────────────────────────────────────────────
HELP_GUIDE = {
    "tr": (
        "❓ <b>TopKap Yardım Merkezi</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>Nasıl Başlarım?</b>\n"
        "1️⃣ TopKap uygulamasını indirin\n"
        "2️⃣ Tedarikçi hesabı oluşturun\n"
        "3️⃣ Ayarlar → Telegram Botu → Bağla\n"
        "4️⃣ Bu botta otomatik giriş yapılır ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>Kanal Nasıl Bağlarım?</b>\n"
        "1️⃣ Telegram'da bir kanal oluşturun\n"
        "2️⃣ @TopKapTR_bot'u kanala <b>Admin</b> olarak ekleyin\n"
        "3️⃣ Kanal Yönetimi → Kanal Bağla\n"
        "4️⃣ Kanal adını girin → Bağlantı tamamlandı ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>Ürün Nasıl Eklerim?</b>\n"
        "1️⃣ Ürün Ekle butonuna basın\n"
        "2️⃣ Kategori seçin\n"
        "3️⃣ Ürün fotoğraflarını yükleyin\n"
        "4️⃣ Fiyat ve açıklama girin\n"
        "5️⃣ Yayınla → Kanalınıza otomatik gönderilir ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📞 <b>Destek için:</b> @TopKapSupport"
    ),
    "ar": (
        "❓ <b>مركز مساعدة TopKap</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>كيف أبدأ؟</b>\n"
        "1️⃣ حمّل تطبيق TopKap\n"
        "2️⃣ أنشئ حساب مورد\n"
        "3️⃣ الإعدادات ← بوت تيليغرام ← ربط\n"
        "4️⃣ سيتم تسجيل الدخول تلقائياً هنا ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>كيف أربط قناتي؟</b>\n"
        "1️⃣ أنشئ قناة على تيليغرام\n"
        "2️⃣ أضف @TopKapTR_bot كـ <b>مشرف</b> في القناة\n"
        "3️⃣ إدارة القناة ← ربط قناة\n"
        "4️⃣ أدخل اسم القناة ← اكتمل الربط ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>كيف أضيف منتجاً؟</b>\n"
        "1️⃣ اضغط إضافة منتج\n"
        "2️⃣ اختر الفئة\n"
        "3️⃣ ارفع صور المنتج\n"
        "4️⃣ أدخل السعر والوصف\n"
        "5️⃣ انشر ← يُرسل تلقائياً لقناتك ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📞 <b>للدعم:</b> @TopKapSupport"
    ),
    "en": (
        "❓ <b>TopKap Help Center</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>How do I get started?</b>\n"
        "1️⃣ Download the TopKap app\n"
        "2️⃣ Create a supplier account\n"
        "3️⃣ Settings → Telegram Bot → Connect\n"
        "4️⃣ You'll be logged in here automatically ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>How do I connect my channel?</b>\n"
        "1️⃣ Create a channel on Telegram\n"
        "2️⃣ Add @TopKapTR_bot as <b>Admin</b> to the channel\n"
        "3️⃣ Channel Management → Connect Channel\n"
        "4️⃣ Enter channel name → Connection complete ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>How do I add a product?</b>\n"
        "1️⃣ Press Add Product button\n"
        "2️⃣ Select a category\n"
        "3️⃣ Upload product photos\n"
        "4️⃣ Enter price and description\n"
        "5️⃣ Publish → Auto-sent to your channel ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📞 <b>Support:</b> @TopKapSupport"
    ),
}

# ─────────────────────────────────────────────
# /start COMMAND
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    telegram_id = str(user.id)

    # Deep link token check
    if context.args:
        token = context.args[0]
        await handle_account_connection(update, context, telegram_id, token)
        return

    # Detect language
    lang = get_user_lang(telegram_id) or detect_lang(user.language_code)
    set_user_lang(telegram_id, lang)

    # Random motivational message + welcome
    motivation = _get_motivational(lang)
    caption = f"{motivation}\n\n{get_string(lang, 'welcome_message')}"

    # Send banner image with language keyboard
    try:
        with open(WELCOME_BANNER, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=language_keyboard(),
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        # Fallback to text if image unavailable
        await update.message.reply_text(
            caption,
            reply_markup=language_keyboard(),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────
# ACCOUNT CONNECTION (deep link)
# ─────────────────────────────────────────────
async def handle_account_connection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: str,
    token: str,
) -> None:
    lang = get_user_lang(telegram_id) or "tr"
    user_name = update.effective_user.username or update.effective_user.first_name

    api = KayisoftAPI(telegram_user_id=telegram_id, language=lang)
    response = await api.connect_account(deep_link_token=token, telegram_user_name=user_name)

    if response is not None:
        success_msgs = {
            "tr": "🎉 <b>Hesabınız başarıyla bağlandı!</b>\n\nArtık TopKap'ın tüm özelliklerini kullanabilirsiniz.",
            "ar": "🎉 <b>تم ربط حسابك بنجاح!</b>\n\nيمكنك الآن استخدام جميع ميزات TopKap.",
            "en": "🎉 <b>Your account has been connected successfully!</b>\n\nYou can now use all TopKap features.",
        }
        await update.message.reply_text(
            success_msgs.get(lang, success_msgs["tr"]),
            parse_mode=ParseMode.HTML,
        )
        await update.message.reply_text(
            get_string(lang, "main_menu_supplier"),
            reply_markup=supplier_main_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            get_string(lang, "connect_error"),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────
# LANGUAGE SELECTION (callback)
# ─────────────────────────────────────────────
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    telegram_id = str(query.from_user.id)
    data = query.data

    if data == "set_lang_tr":
        lang = "tr"
    elif data == "set_lang_ar":
        lang = "ar"
    else:
        lang = "en"

    set_user_lang(telegram_id, lang)

    # Confirm language selection
    await query.message.reply_text(
        LANG_CONFIRMED[lang],
        parse_mode=ParseMode.HTML,
    )

    # Show guided dashboard
    await query.message.reply_text(
        get_string(lang, "main_menu_supplier"),
        reply_markup=supplier_main_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────
# MENU BUTTON HANDLER
# ─────────────────────────────────────────────
async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = str(update.effective_user.id)
    lang = get_user_lang(telegram_id) or "tr"
    text = update.message.text

    # Build text → action map for all 3 languages
    btn_map = {}
    for _lang in ["tr", "ar", "en"]:
        btn_map[get_string(_lang, "btn_add_product")]    = "add_product"
        btn_map[get_string(_lang, "btn_my_products")]    = "my_products"
        btn_map[get_string(_lang, "btn_statistics")]     = "statistics"
        btn_map[get_string(_lang, "btn_manage_channel")] = "channel"
        btn_map[get_string(_lang, "btn_settings")]       = "settings"
        btn_map[get_string(_lang, "btn_subscription")]   = "subscription"
        btn_map[get_string(_lang, "btn_help")]           = "help"
        btn_map[get_string(_lang, "btn_why_topkap")]     = "why_topkap"

    action = btn_map.get(text)

    if action == "add_product":
        from bot.handlers.product_handler import start_add_product
        await start_add_product(update, context)

    elif action == "my_products":
        await update.message.reply_text(
            COMING_SOON[lang]["my_products"],
            parse_mode=ParseMode.HTML,
        )

    elif action == "statistics":
        await update.message.reply_text(
            COMING_SOON[lang]["statistics"],
            parse_mode=ParseMode.HTML,
        )

    elif action == "channel":
        from bot.handlers.channel_handler import start_channel_connection
        await start_channel_connection(update, context)

    elif action == "settings":
        await update.message.reply_text(
            SETTINGS_MSG[lang],
            reply_markup=language_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "subscription":
        await update.message.reply_text(
            COMING_SOON[lang]["subscription"],
            parse_mode=ParseMode.HTML,
        )

    elif action == "help":
        await update.message.reply_text(
            HELP_GUIDE[lang],
            parse_mode=ParseMode.HTML,
        )

    elif action == "why_topkap":
        # Show Why TopKap infographic + detailed text
        why_image = os.path.join(ASSETS_DIR, "why_topkap.jpg")
        try:
            with open(why_image, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=get_string(lang, "onboarding_stats"),
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            pass
        await update.message.reply_text(
            get_string(lang, "why_topkap"),
            parse_mode=ParseMode.HTML,
        )

    else:
        # Fallback: show main menu
        await update.message.reply_text(
            get_string(lang, "main_menu_supplier"),
            reply_markup=supplier_main_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────
# REGISTER HANDLERS
# ─────────────────────────────────────────────
def register_start_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_"))

    # Build regex pattern for all menu button texts (all 3 languages)
    menu_buttons = []
    for _lang in ["tr", "ar", "en"]:
        for key in [
            "btn_add_product", "btn_my_products", "btn_statistics",
            "btn_manage_channel", "btn_settings", "btn_subscription",
            "btn_help", "btn_why_topkap",
        ]:
            val = get_string(_lang, key)
            if val and val != key:
                menu_buttons.append(val)

    if menu_buttons:
        pattern = "^(" + "|".join(re.escape(b) for b in menu_buttons) + ")$"
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), handle_menu_button)
        )
