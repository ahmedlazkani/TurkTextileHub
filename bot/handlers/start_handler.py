"""
bot/handlers/start_handler.py — TopKap Bot v5.0
================================================
Professional Onboarding + Account Connection + Dashboard

FEATURES:
- Welcome banner image with random motivational messages
- Language auto-detection + manual selection
- Deep link account connection with motivational success/error messages
- Guided supplier dashboard with all 7 action buttons
- Full help center (step-by-step guide)
- Why TopKap infographic
- TopGate profile sharing
- Settings (language change)
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
# ASSET PATHS
# ─────────────────────────────────────────────
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
WELCOME_BANNER = os.path.join(ASSETS_DIR, "welcome_banner.jpg")
WHY_TOPKAP_IMAGE = os.path.join(ASSETS_DIR, "why_topkap.jpg")

# ─────────────────────────────────────────────
# MOTIVATIONAL MESSAGES (random on each /start)
# ─────────────────────────────────────────────
MOTIVATIONAL_KEYS = [
    "motivational_1", "motivational_2", "motivational_3",
    "motivational_4", "motivational_5",
]

def _get_motivational(lang: str) -> str:
    """Pick a random motivational message from translation files."""
    msgs = [get_string(lang, k) for k in MOTIVATIONAL_KEYS]
    msgs = [m for m in msgs if not m.startswith("motivational_")]
    return random.choice(msgs) if msgs else "🌟 <b>TopKap'a Hoş Geldiniz!</b>"

# ─────────────────────────────────────────────
# LANGUAGE CONFIRMED MESSAGES
# ─────────────────────────────────────────────
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
# CONNECTION SUCCESS — Motivational (3 languages)
# ─────────────────────────────────────────────
CONNECTION_SUCCESS = {
    "tr": (
        "🎉 <b>Hesabınız Başarıyla Bağlandı!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ TopKap hesabınız Telegram'a bağlı\n"
        "🌍 180+ ülkeden alıcılara ulaşmaya hazırsınız\n"
        "📢 Ürünlerinizi kanalınıza otomatik yayınlayın\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Başlamak için aşağıdaki paneli kullanın!</b>"
    ),
    "ar": (
        "🎉 <b>تم ربط حسابك بنجاح!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ حسابك على TopKap مرتبط بتيليغرام\n"
        "🌍 أنت الآن جاهز للوصول لمشترين من 180+ دولة\n"
        "📢 انشر منتجاتك تلقائياً على قناتك\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>استخدم اللوحة أدناه للبدء الآن!</b>"
    ),
    "en": (
        "🎉 <b>Account Connected Successfully!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Your TopKap account is linked to Telegram\n"
        "🌍 Ready to reach buyers from 180+ countries\n"
        "📢 Auto-publish products to your channel\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Use the panel below to get started!</b>"
    ),
}

# ─────────────────────────────────────────────
# CONNECTION ERROR — Clear instructions (3 languages)
# ─────────────────────────────────────────────
CONNECTION_ERROR = {
    "tr": (
        "❌ <b>Hesap Bağlama Başarısız</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Bu hata genellikle şu sebeplerden kaynaklanır:\n\n"
        "1️⃣ <b>Bağlantı süresi dolmuş</b>\n"
        "   → TopKap uygulamasından yeni bir bağlantı oluşturun\n\n"
        "2️⃣ <b>Bağlantı daha önce kullanılmış</b>\n"
        "   → Her bağlantı yalnızca bir kez kullanılabilir\n\n"
        "3️⃣ <b>Hesap henüz onaylanmamış</b>\n"
        "   → Hesabınızın onaylandığından emin olun\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>Çözüm:</b> TopKap uygulamasını açın\n"
        "   Ayarlar → Telegram Botu → Yeniden Bağla\n\n"
        "📞 Sorun devam ederse: @TopKapSupport"
    ),
    "ar": (
        "❌ <b>فشل ربط الحساب</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "يحدث هذا الخطأ عادةً بسبب:\n\n"
        "1️⃣ <b>انتهت صلاحية رابط الربط</b>\n"
        "   → أنشئ رابطاً جديداً من تطبيق TopKap\n\n"
        "2️⃣ <b>تم استخدام الرابط مسبقاً</b>\n"
        "   → كل رابط يُستخدم مرة واحدة فقط\n\n"
        "3️⃣ <b>الحساب لم يُفعَّل بعد</b>\n"
        "   → تأكد من اعتماد حسابك\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>الحل:</b> افتح تطبيق TopKap\n"
        "   الإعدادات ← بوت تيليغرام ← إعادة الربط\n\n"
        "📞 إذا استمرت المشكلة: @TopKapSupport"
    ),
    "en": (
        "❌ <b>Account Connection Failed</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "This error usually occurs because:\n\n"
        "1️⃣ <b>Connection link has expired</b>\n"
        "   → Generate a new link from the TopKap app\n\n"
        "2️⃣ <b>Link was already used</b>\n"
        "   → Each link can only be used once\n\n"
        "3️⃣ <b>Account not yet approved</b>\n"
        "   → Make sure your account is verified\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>Solution:</b> Open the TopKap app\n"
        "   Settings → Telegram Bot → Reconnect\n\n"
        "📞 If the issue persists: @TopKapSupport"
    ),
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
        "4️⃣ Kanal otomatik olarak kaydedilir ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>Ürün Nasıl Eklerim?</b>\n"
        "1️⃣ Ürün Ekle butonuna basın\n"
        "2️⃣ Ana kategori → Alt kategori seçin\n"
        "3️⃣ Ürün bilgilerini girin (AI analiz eder)\n"
        "4️⃣ Ürün fotoğraflarını yükleyin\n"
        "5️⃣ Onayla → TopKap + TopGate + Kanalınıza otomatik gönderilir ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>TopGate Profilimi Nasıl Paylaşırım?</b>\n"
        "TopGate Profilimi Paylaş butonuna basın.\n"
        "Hazır mesajı kanalınıza kopyalayın.\n\n"
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
        "3️⃣ ستُسجَّل القناة تلقائياً ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>كيف أضيف منتجاً؟</b>\n"
        "1️⃣ اضغط إضافة منتج\n"
        "2️⃣ اختر الفئة الرئيسية ← الفئة الفرعية\n"
        "3️⃣ أدخل بيانات المنتج (الذكاء الاصطناعي يحللها)\n"
        "4️⃣ ارفع صور المنتج\n"
        "5️⃣ أكّد ← يُنشر تلقائياً على TopKap + TopGate + قناتك ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>كيف أشارك ملفي على TopGate؟</b>\n"
        "اضغط زر 'شارك ملفي على TopGate'.\n"
        "انسخ الرسالة الجاهزة وانشرها على قناتك.\n\n"
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
        "3️⃣ Channel is registered automatically ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ <b>How do I add a product?</b>\n"
        "1️⃣ Press Add Product button\n"
        "2️⃣ Select main category → subcategory\n"
        "3️⃣ Enter product details (AI analyzes them)\n"
        "4️⃣ Upload product photos\n"
        "5️⃣ Confirm → Auto-published to TopKap + TopGate + your channel ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>How do I share my TopGate profile?</b>\n"
        "Press 'Share My TopGate Profile' button.\n"
        "Copy the ready message and post it to your channel.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📞 <b>Support:</b> @TopKapSupport"
    ),
}


# ─────────────────────────────────────────────
# /start COMMAND
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Entry point for the bot.
    - If deep link token present → handle account connection
    - Otherwise → show welcome banner + language selection
    """
    user = update.effective_user
    telegram_id = str(user.id)

    # ── DIAGNOSTIC: log exactly what /start received ────────────────────────
    msg_text = update.message.text if update.message else 'NO_MESSAGE'
    logger.info(
        "START received | telegram_id=%s | args=%s | message_text=%s",
        telegram_id, context.args, msg_text,
    )

    # ── Deep link token (from TopKap app) ─────────────────────────────────────
    if context.args:
        token = context.args[0]
        logger.info("Deep link token detected: %s...", token[:8] if len(token) >= 8 else token)
        await handle_account_connection(update, context, telegram_id, token)
        return
    logger.info("No deep link args — showing normal onboarding for telegram_id=%s", telegram_id)

    # ── Normal /start — show onboarding ───────────────────────────────────────
    lang = get_user_lang(telegram_id) or detect_lang(user.language_code)
    set_user_lang(telegram_id, lang)

    motivation = _get_motivational(lang)
    caption = f"{motivation}\n\n{get_string(lang, 'welcome_message')}"

    try:
        with open(WELCOME_BANNER, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=language_keyboard(),
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        await update.message.reply_text(
            caption,
            reply_markup=language_keyboard(),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────
# ACCOUNT CONNECTION (deep link from TopKap app)
# ─────────────────────────────────────────────
async def handle_account_connection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: str,
    token: str,
) -> None:
    """
    Called when the supplier opens the deep link from the TopKap app.
    Flow:
      1. Show "connecting..." message
      2. Call KAYISOFT API: POST api/seller/telegram-bot/connect
      3. On success → motivational success message + dashboard
      4. On failure → clear error message with instructions
    """
    lang = get_user_lang(telegram_id) or "tr"
    user = update.effective_user
    user_name = user.username or user.first_name or ""

    # Show connecting indicator
    connecting_msgs = {
        "tr": "🔄 <b>Hesap bağlanıyor...</b>",
        "ar": "🔄 <b>جاري ربط الحساب...</b>",
        "en": "🔄 <b>Connecting account...</b>",
    }
    connecting_msg = await update.message.reply_text(
        connecting_msgs.get(lang, connecting_msgs["tr"]),
        parse_mode=ParseMode.HTML,
    )

    # Call KAYISOFT API
    api = KayisoftAPI(telegram_user_id=telegram_id, language=lang)
    response = await api.connect_account(
        deep_link_token=token,
        telegram_user_name=user_name,
    )

    # Delete the "connecting..." message
    try:
        await connecting_msg.delete()
    except Exception:
        pass

    if response is not None:
        # ── SUCCESS ────────────────────────────────────────────────────────────
        logger.info("Account connected successfully: telegram_id=%s", telegram_id)

        await update.message.reply_text(
            CONNECTION_SUCCESS.get(lang, CONNECTION_SUCCESS["tr"]),
            parse_mode=ParseMode.HTML,
        )
        await update.message.reply_text(
            get_string(lang, "main_menu_supplier"),
            reply_markup=supplier_main_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
    else:
        # ── FAILURE ────────────────────────────────────────────────────────────
        logger.warning("Account connection failed: telegram_id=%s, token=%s", telegram_id, token[:8] + "...")

        await update.message.reply_text(
            CONNECTION_ERROR.get(lang, CONNECTION_ERROR["tr"]),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────
# LANGUAGE SELECTION (callback)
# ─────────────────────────────────────────────
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles language selection button press."""
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

    await query.message.reply_text(
        LANG_CONFIRMED[lang],
        parse_mode=ParseMode.HTML,
    )
    await query.message.reply_text(
        get_string(lang, "main_menu_supplier"),
        reply_markup=supplier_main_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────
# MENU BUTTON HANDLER (ReplyKeyboard)
# ─────────────────────────────────────────────
async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes all supplier dashboard button presses to the correct handler."""
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
        # NOTE: This branch should NEVER be reached in normal operation.
        # ConversationHandler is registered BEFORE this handler in main.py,
        # so it intercepts "➕ إضافة منتج" / "➕ Ürün Ekle" directly.
        # This fallback is kept only as a safety net in case of handler ordering issues.
        pass

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

    elif action == "share_topgate":
        await handle_share_topgate(update, context, lang)

    elif action == "why_topkap":
        try:
            with open(WHY_TOPKAP_IMAGE, "rb") as photo:
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
# TOPGATE PROFILE SHARING
# ─────────────────────────────────────────────
async def handle_share_topgate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    lang: str,
) -> None:
    """
    Generates a ready-to-share message for the supplier to post on their
    Telegram channel, inviting buyers to follow them on TopGate.
    """
    telegram_id = str(update.effective_user.id)

    # Fallback to config URL (Universal Link will come from KAYISOFT)
    topgate_base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    topgate_url = topgate_base

    # Format the share message
    share_msg = get_string(lang, "topgate_share_message").format(
        supplier_url=topgate_url
    )

    header = {
        "tr": (
            "📲 <b>TopGate Profil Linkiniz Hazır!</b>\n\n"
            "Aşağıdaki mesajı kanalınıza kopyalayıp yapıştırın.\n"
            "Alıcılar sizi TopGate'de takip edebilecek."
        ),
        "ar": (
            "📲 <b>رابط ملفك على TopGate جاهز!</b>\n\n"
            "انسخ الرسالة أدناه وانشرها على قناتك.\n"
            "سيتمكن المشترون من متابعتك على TopGate."
        ),
        "en": (
            "📲 <b>Your TopGate Profile Link is Ready!</b>\n\n"
            "Copy the message below and post it to your channel.\n"
            "Buyers will be able to follow you on TopGate."
        ),
    }

    await update.message.reply_text(
        header.get(lang, header["tr"]),
        parse_mode="HTML",
    )
    await update.message.reply_text(
        share_msg,
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# REGISTER HANDLERS
# ─────────────────────────────────────────────
def register_start_handlers(application) -> None:
    """Register all start/menu handlers with the application."""
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
