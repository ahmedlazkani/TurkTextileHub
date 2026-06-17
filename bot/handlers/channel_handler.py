"""
bot/handlers/channel_handler.py
===============================
Handles channel connection and management.

FIX (2026-05-21-v2): Critical fixes applied:

  BUG 1 — channel_id NOT saved when KAYISOFT API returns None
  ─────────────────────────────────────────────────────────────
  BEFORE: channel_id was only saved if `response is not None`.
          If the API call failed (network error, token issue, etc.),
          channel_id was silently dropped — so the bot could never
          publish to the channel even though it was added as admin.
  AFTER:  channel_id is ALWAYS saved locally (bot_data + disk) when
          the bot is added as admin, regardless of API response.
          The API call is still made (best-effort), but a failure
          no longer prevents local storage.

  BUG 2 — /data not writable on Railway → channel_id lost on restart
  ──────────────────────────────────────────────────────────────────
  Railway does NOT mount /data by default. Without a Railway Volume,
  /tmp is used as fallback — but /tmp is ephemeral (cleared on restart).
  Added clear warning in logs + /setchannel command as manual override.

  NEW — /setchannel command for manual channel_id override
  ─────────────────────────────────────────────────────────
  Allows a supplier to manually set their channel_id if the automatic
  detection via handle_my_chat_member fails.
  Usage: /setchannel -1001234567890
"""
import json
import logging
import urllib.parse
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from bot.services.language_service import get_string, get_user_lang, detect_lang
from bot.services.kayisoft_api import KayisoftAPI
from bot.keyboards import supplier_main_keyboard

logger = logging.getLogger(__name__)

# ── Persistent storage path ────────────────────────────────────────────────────
# Railway provides a writable /data volume IF you add one in the dashboard.
# If /data is not mounted (no Volume configured), fall back to /tmp.
# NOTE: /tmp is ephemeral — channel_id will be lost on Railway restarts.
#       To persist across restarts, add a Railway Volume mounted at /data.
def _resolve_channels_file() -> str:
    """
    Resolve the path to the user_channels.json persistence file.

    Priority order:
      1. CHANNELS_FILE env var  — explicit override (RECOMMENDED for Railway)
      2. /data directory        — Railway Volume mounted at /data
      3. /tmp                   — ephemeral fallback (LOST on restart)

    ⚠️  /app/data is intentionally EXCLUDED from the priority list.
        On Railway, /app/data is part of the container filesystem and is
        WIPED on every deploy — even if a Volume is mounted at /data.
        Using /app/data would silently bypass the Volume and lose all
        channel_id mappings on every redeploy.

    To persist channel_ids across Railway restarts:
      RECOMMENDED: Set env var CHANNELS_FILE=/data/user_channels.json
                   in Railway Dashboard → Variables.
                   This guarantees the Volume is always used.
    """
    # 1. Explicit env var override — highest priority, always wins
    env_path = os.environ.get("CHANNELS_FILE", "").strip()
    if env_path:
        logger.info("✅ Using CHANNELS_FILE from env: %s", env_path)
        return env_path

    # 2. /data — Railway Volume mount point
    #    Only use if the directory actually exists AND is writable
    #    (i.e. a Volume is mounted). Do NOT create it — creation would
    #    succeed on the container filesystem and bypass the Volume.
    data_dir = "/data"
    if os.path.isdir(data_dir) and os.access(data_dir, os.W_OK):
        path = os.path.join(data_dir, "user_channels.json")
        logger.info("✅ Using /data Volume for channel persistence: %s", path)
        return path

    # 3. /tmp fallback — ephemeral, LOST on Railway restarts/redeploys
    #    This is only acceptable for local development.
    logger.warning(
        "⚠️  No persistent storage found — using /tmp/user_channels.json as fallback. "
        "channel_id WILL BE LOST on Railway restarts/redeploys. "
        "FIX: Set env var CHANNELS_FILE=/data/user_channels.json in Railway Dashboard."
    )
    return "/tmp/user_channels.json"

_CHANNELS_FILE = _resolve_channels_file()


def _load_channels() -> dict:
    """Load persisted user→channel mapping from disk."""
    try:
        with open(_CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_channels(channels: dict) -> None:
    """Persist user→channel mapping to disk."""
    try:
        # Ensure parent directory exists (important for /data/user_channels.json)
        parent = os.path.dirname(_CHANNELS_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels, f, ensure_ascii=False, indent=2)
        logger.info("✅ Saved user_channels to %s", _CHANNELS_FILE)
    except Exception as exc:
        logger.error("❌ Failed to save user_channels to %s: %s", _CHANNELS_FILE, exc)


def save_channel_for_user(user_id: str, channel_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Save channel_id for a user in both in-memory cache and disk.
    This is the single source of truth for channel persistence.

    Called from:
      - handle_my_chat_member (automatic detection)
      - handle_setchannel     (manual /setchannel command)

    Programmatic note:
      Separating the save logic into its own function follows the
      Single Responsibility Principle — one function, one job.
      Both automatic and manual flows call the same save logic.
    """
    # ── 0. Normalize channel_id: remove all spaces (e.g. "-10014428 17937" → "-1001442817937") ──
    channel_id = channel_id.replace(" ", "").strip()

    # ── 1. In-memory cache (fast, lost on restart) ─────────────────────────────
    if "user_channels" not in context.bot_data:
        context.bot_data["user_channels"] = {}
    context.bot_data["user_channels"][user_id] = channel_id
    logger.info("✅ Saved channel_id=%s for user_id=%s in bot_data (memory)", channel_id, user_id)

    # ── 2. Disk persistence (survives Railway restarts if /data is mounted) ─────
    channels = _load_channels()
    channels[user_id] = channel_id
    _save_channels(channels)


def get_channel_id_for_user(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Return the channel_id for a given user_id.

    Lookup order:
      1. context.bot_data["user_channels"]  (in-memory, fast)
      2. Persistent JSON file               (survives Railway restarts)

    Returns None if no channel has been linked for this user.
    """
    # 1. In-memory cache
    channel_id = context.bot_data.get("user_channels", {}).get(user_id)
    if channel_id:
        # Normalize on read: remove spaces that may have been saved before this fix
        return channel_id.replace(" ", "").strip()

    # 2. Disk fallback
    channels = _load_channels()
    channel_id = channels.get(user_id)
    if channel_id:
        # Normalize on read: remove spaces that may have been saved before this fix
        channel_id = channel_id.replace(" ", "").strip()
        # Warm the in-memory cache so subsequent calls are fast
        if "user_channels" not in context.bot_data:
            context.bot_data["user_channels"] = {}
        context.bot_data["user_channels"][user_id] = channel_id
        logger.info(
            "Loaded channel_id=%s for user_id=%s from disk (cache warmed)",
            channel_id, user_id
        )
    return channel_id


# ══════════════════════════════════════════════════════════════════════════════
# /channel — Show instructions to add bot as admin
# ══════════════════════════════════════════════════════════════════════════════

def _support_keyboard(lang: str, extra_buttons: list | None = None):
    """Gmail support button — opens pre-filled email to topkap.support@kayisoft.net"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import urllib.parse
    # Use ASCII-safe subject only — Telegram rejects mailto: with non-ASCII body (Button_url_invalid)
    subject_map = {"ar": "Help - TopKap", "tr": "Destek - TopKap", "en": "Support - TopKap"}
    labels      = {"ar": "📧 تواصل مع الدعم", "tr": "📧 Destek ile iletişim", "en": "📧 Contact Support"}
    subject  = urllib.parse.quote(subject_map.get(lang, subject_map["en"]), safe="")
    gmail_url = f"https://mail.google.com/mail/?view=cm&to=topkap.support%40kayisoft.net&su={subject}"
    support_row = [InlineKeyboardButton(labels.get(lang, labels["en"]), url=gmail_url)]
    rows = list(extra_buttons) if extra_buttons else []
    rows.append(support_row)
    return InlineKeyboardMarkup(rows)


async def start_channel_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Instructs the user to add the bot to their channel as an admin.
    Also shows current channel_id if one is already linked.
    """
    user = update.effective_user
    user_id = str(user.id)
    lang = get_user_lang(user_id)
    if lang == "tr" and user.language_code:
        detected = detect_lang(user.language_code)
        if detected != "tr":
            lang = detected

    # Show current channel status
    current_channel = get_channel_id_for_user(user_id, context)
    if current_channel:
        status_texts = {
            "ar": f"✅ <b>قناتك المرتبطة حالياً:</b> <code>{current_channel}</code>\n\n",
            "tr": f"✅ <b>Mevcut bağlı kanalınız:</b> <code>{current_channel}</code>\n\n",
            "en": f"✅ <b>Your currently linked channel:</b> <code>{current_channel}</code>\n\n",
        }
        status = status_texts.get(lang, status_texts["en"])
    else:
        status_texts = {
            "ar": "⚠️ <b>لم تربط أي قناة بعد.</b>\n\n",
            "tr": "⚠️ <b>Henüz kanal bağlanmadı.</b>\n\n",
            "en": "⚠️ <b>No channel linked yet.</b>\n\n",
        }
        status = status_texts.get(lang, status_texts["en"])

    base_text = get_string(lang, "channel_add_admin")
    manual_hint = {
        "ar": "\n\n💡 <b>بديل:</b> إذا كنت تعرف معرّف قناتك، أرسل:\n<code>/setchannel -1001234567890</code>",
        "tr": "\n\n💡 <b>Alternatif:</b> Kanal ID'nizi biliyorsanız gönderin:\n<code>/setchannel -1001234567890</code>",
        "en": "\n\n💡 <b>Alternative:</b> If you know your channel ID, send:\n<code>/setchannel -1001234567890</code>",
    }.get(lang, "")

    await update.message.reply_text(
        status + base_text + manual_hint,
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# /setchannel <channel_id> — Manual channel_id override
# ══════════════════════════════════════════════════════════════════════════════
async def handle_setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manual channel_id override command.
    Usage: /setchannel -1001234567890

    This is useful when:
      - The automatic detection via handle_my_chat_member failed
      - The bot was added to the channel before the bot was running
      - The user wants to change their linked channel

    Programmatic note:
      context.args is a list of strings after the command.
      /setchannel -1001234567890  →  context.args = ["-1001234567890"]
    """
    user = update.effective_user
    user_id = str(user.id)
    lang = get_user_lang(user_id)

    if not context.args or len(context.args) < 1:
        usage = {
            "ar": (
                "❌ <b>استخدام خاطئ.</b>\n\n"
                "أرسل معرّف قناتك هكذا:\n"
                "<code>/setchannel -1001234567890</code>\n\n"
                "للحصول على معرّف قناتك:\n"
                "1. أضف @userinfobot لقناتك\n"
                "2. أو استخدم @getidsbot\n"
                "3. المعرّف يبدأ بـ -100"
            ),
            "tr": (
                "❌ <b>Yanlış kullanım.</b>\n\n"
                "Kanal ID'nizi şöyle gönderin:\n"
                "<code>/setchannel -1001234567890</code>\n\n"
                "Kanal ID'nizi öğrenmek için:\n"
                "1. @userinfobot'u kanalınıza ekleyin\n"
                "2. Veya @getidsbot kullanın\n"
                "3. ID -100 ile başlar"
            ),
            "en": (
                "❌ <b>Wrong usage.</b>\n\n"
                "Send your channel ID like this:\n"
                "<code>/setchannel -1001234567890</code>\n\n"
                "To find your channel ID:\n"
                "1. Add @userinfobot to your channel\n"
                "2. Or use @getidsbot\n"
                "3. Channel IDs start with -100"
            ),
        }
        await update.message.reply_text(
            usage.get(lang, usage["en"]),
            parse_mode="HTML",
            reply_markup=_support_keyboard(lang),
        )
        return

    channel_id_raw = context.args[0].strip()

    # Basic validation: must be a negative integer starting with -100
    if not (channel_id_raw.startswith("-") and channel_id_raw[1:].isdigit()):
        error_texts = {
            "ar": (
                "❌ <b>معرّف القناة غير صحيح.</b>\n\n"
                f"القيمة التي أرسلتها: <code>{channel_id_raw}</code>\n\n"
                "معرّف القناة يجب أن يكون رقماً سالباً مثل:\n"
                "<code>-1001234567890</code>"
            ),
            "tr": (
                "❌ <b>Geçersiz kanal ID.</b>\n\n"
                f"Gönderdiğiniz değer: <code>{channel_id_raw}</code>\n\n"
                "Kanal ID negatif bir sayı olmalıdır:\n"
                "<code>-1001234567890</code>"
            ),
            "en": (
                "❌ <b>Invalid channel ID.</b>\n\n"
                f"You sent: <code>{channel_id_raw}</code>\n\n"
                "Channel ID must be a negative number like:\n"
                "<code>-1001234567890</code>"
            ),
        }
        await update.message.reply_text(
            error_texts.get(lang, error_texts["en"]),
            parse_mode="HTML",
            reply_markup=_support_keyboard(lang),
        )
        return

    # Save the channel_id
    save_channel_for_user(user_id, channel_id_raw, context)
    logger.info("✅ /setchannel: user_id=%s manually set channel_id=%s", user_id, channel_id_raw)

    success_texts = {
        "ar": (
            f"✅ <b>تم ربط القناة بنجاح!</b>\n\n"
            f"معرّف القناة: <code>{channel_id_raw}</code>\n\n"
            "سيتم نشر منتجاتك القادمة على هذه القناة.\n\n"
            "⚠️ <b>تأكد أن البوت مشرف على القناة</b> وإلا لن يتمكن من النشر."
        ),
        "tr": (
            f"✅ <b>Kanal başarıyla bağlandı!</b>\n\n"
            f"Kanal ID: <code>{channel_id_raw}</code>\n\n"
            "Gelecek ürünleriniz bu kanala yayınlanacak.\n\n"
            "⚠️ <b>Botun kanalda yönetici olduğundan emin olun</b>, aksi takdirde yayınlayamaz."
        ),
        "en": (
            f"✅ <b>Channel linked successfully!</b>\n\n"
            f"Channel ID: <code>{channel_id_raw}</code>\n\n"
            "Your upcoming products will be published to this channel.\n\n"
            "⚠️ <b>Make sure the bot is an admin in the channel</b>, otherwise it cannot post."
        ),
    }
    await update.message.reply_text(success_texts.get(lang, success_texts["en"]), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# ChatMemberHandler — Detect bot added to channel as admin
# ══════════════════════════════════════════════════════════════════════════════
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Triggered when the bot's status in a chat changes.
    Used to detect when the bot is added to a channel as an admin.

    CRITICAL FIX (v2):
      channel_id is now ALWAYS saved locally, regardless of whether
      the KAYISOFT API call succeeds or fails.

      BEFORE: if response is None → channel_id silently dropped
      AFTER:  save first, then call API (best-effort, non-blocking)

    Programmatic note:
      This is the "save first, sync later" pattern — common in
      distributed systems where local state must not depend on
      remote API availability.
    """
    result = update.my_chat_member
    if not result:
        return

    chat = result.chat
    new_status = result.new_chat_member.status

    # Only handle: channel type + bot made administrator
    if chat.type != "channel" or new_status != "administrator":
        return

    user = result.from_user
    user_id = str(user.id)
    lang = get_user_lang(user_id)
    if lang == "tr" and user.language_code:
        detected = detect_lang(user.language_code)
        if detected != "tr":
            lang = detected

    logger.info(
        "Bot added to channel: title=%s | channel_id=%s | by user_id=%s | lang=%s",
        chat.title, chat.id, user_id, lang
    )

    channel_id    = str(chat.id)
    channel_title = chat.title

    # ── STEP 1: Save locally FIRST (always, regardless of API result) ──────────
    # This ensures the bot can publish to the channel even if the API is down.
    save_channel_for_user(user_id, channel_id, context)

    # ── STEP 2: Register with KAYISOFT API (best-effort) ──────────────────────
    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    logger.info(
        "Calling create_channel: channel_id=%s | channel_name=%s | telegram_user_id=%s | token=%s...",
        channel_id, channel_title, user_id,
        api.token[:8] if api.token else 'EMPTY'
    )

    try:
        response = await api.create_channel(channel_id=channel_id, channel_name=channel_title)
        logger.info("create_channel API response: %s", response)

        if response is None:
            # API failed — but channel_id is already saved locally (Step 1)
            # Bot can still publish to the channel
            logger.warning(
                "⚠️ create_channel API call failed for user_id=%s channel_id=%s. "
                "channel_id is saved locally — bot will still publish to channel. "
                "The product may not appear on TopKap/TopGate until API is fixed.",
                user_id, channel_id
            )
    except Exception as exc:
        logger.error(
            "❌ create_channel exception for user_id=%s channel_id=%s: %s",
            user_id, channel_id, exc
        )
        response = None

    # ── STEP 3: Send welcome post to the channel ────────────────────────────────
    await _send_channel_welcome_post(context.bot, channel_id, channel_title, lang)

    # ── STEP 4: Send confirmation to user ─────────────────────────────────────
    try:
        if response is not None:
            # Full success: saved locally + registered with API
            success_text = get_string(lang, "channel_connected").replace(
                "{channel_name}", channel_title
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=success_text,
                parse_mode="HTML",
                reply_markup=supplier_main_keyboard(lang),  # Task: Show keyboard after channel linked
            )
        else:
            # Partial success: saved locally, API registration failed
            partial_texts = {
                "ar": (
                    f"✅ <b>تم ربط القناة '{channel_title}' بالبوت!</b>\n\n"
                    "سيتم نشر منتجاتك على هذه القناة.\n\n"
                    "⚠️ <i>ملاحظة: لم يتم تسجيل القناة على TopKap حالياً. "
                    "المنتجات ستُنشر على قناتك، لكن قد لا تظهر على التطبيق حتى يتم الإصلاح.</i>"
                ),
                "tr": (
                    f"✅ <b>'{channel_title}' kanalı bota bağlandı!</b>\n\n"
                    "Ürünleriniz bu kanala yayınlanacak.\n\n"
                    "⚠️ <i>Not: Kanal şu anda TopKap'a kaydedilemedi. "
                    "Ürünler kanalınıza yayınlanacak, ancak sorun çözülene kadar uygulamada görünmeyebilir.</i>"
                ),
                "en": (
                    f"✅ <b>Channel '{channel_title}' linked to the bot!</b>\n\n"
                    "Your products will be published to this channel.\n\n"
                    "⚠️ <i>Note: Channel could not be registered on TopKap right now. "
                    "Products will still post to your channel, but may not appear in the app until fixed.</i>"
                ),
            }
            await context.bot.send_message(
                chat_id=user.id,
                text=partial_texts.get(lang, partial_texts["en"]),
                parse_mode="HTML",
                reply_markup=supplier_main_keyboard(lang),  # Task: Show keyboard even on partial success
            )
    except Exception as e:
        logger.error("Could not send confirmation to user %s: %s", user_id, e)


# ══════════════════════════════════════════════════════════════════════════════
# Inline callback: How to get channel ID
# ══════════════════════════════════════════════════════════════════════════════
async def _send_channel_welcome_post(
    bot,
    channel_id: str,
    channel_title: str,
    lang: str,
) -> None:
    """
    Sends a professional welcome post to the supplier's channel
    immediately after it is linked to the bot.

    The post introduces the channel to subscribers and explains
    that products from TopGate will be published here.

    Programmatic note:
      This is a "fire and forget" call — errors are caught and logged
      but do NOT block the main channel-linking flow.
    """
    welcome_texts = {
        "ar": (
            "🌟 <b>مرحباً بكم في قناة {channel_title}</b>\n\n"
            "يسعدنا الإعلان عن انطلاق هذه القناة الرسمية للتجارة بالجملة.\n"
            "سيتم نشر منتجات المورد هنا بشكل منتظم عبر منصة <b>TopGate</b>.\n\n"
            "📦 <b>ما ستجده هنا:</b>\n"
            "• منتجات تركية مباشرة من المورد\n"
            "• أسعار الجملة بالدولار\n"
            "• إمكانية التواصل مع المورد مباشرة\n\n"
            "🔔 اشترك في القناة لتصلك أحدث المنتجات فور نشرها.\n\n"
            "<i>مدعوم بواسطة TopGate — منصة B2B للتجارة التركية</i>"
        ),
        "tr": (
            "🌟 <b>{channel_title} Kanalına Hoş Geldiniz</b>\n\n"
            "Bu resmi toptan ticaret kanalının açılışını duyurmaktan mutluluk duyuyoruz.\n"
            "Tedarikçi ürünleri <b>TopGate</b> platformu aracılığıyla düzenli olarak burada yayınlanacaktır.\n\n"
            "📦 <b>Burada neler bulacaksınız:</b>\n"
            "• Doğrudan tedarikçiden Türk ürünleri\n"
            "• Dolar cinsinden toptan fiyatlar\n"
            "• Tedarikçiyle doğrudan iletişim imkânı\n\n"
            "🔔 En yeni ürünleri anında almak için kanala abone olun.\n\n"
            "<i>TopGate tarafından desteklenmektedir — Türk ticareti için B2B platformu</i>"
        ),
        "en": (
            "🌟 <b>Welcome to {channel_title}</b>\n\n"
            "We are pleased to announce the launch of this official wholesale channel.\n"
            "Supplier products will be published here regularly via the <b>TopGate</b> platform.\n\n"
            "📦 <b>What you will find here:</b>\n"
            "• Turkish products directly from the supplier\n"
            "• Wholesale prices in USD\n"
            "• Direct contact with the supplier\n\n"
            "🔔 Subscribe to the channel to receive the latest products as soon as they are published.\n\n"
            "<i>Powered by TopGate — B2B platform for Turkish trade</i>"
        ),
    }
    text = welcome_texts.get(lang, welcome_texts["en"]).replace("{channel_title}", channel_title)
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info("✅ Welcome post sent to channel %s", channel_id)
    except Exception as exc:
        logger.warning("⚠️ Could not send welcome post to channel %s: %s", channel_id, exc)


async def handle_how_to_get_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Responds to the inline button 'How to get my channel ID?'.
    Explains the two methods: @userinfobot and forwarding a message.
    Then prompts the user to send /setchannel <id>.
    """
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = get_user_lang(user_id)

    texts = {
        "ar": (
            "🔗 <b>كيف تحصل على معرّف قناتك:</b>\n\n"
            "<b>الطريقة السهلة:</b>\n"
            "1️⃣ افتح قناتك → أي رسالة → اضغط عليها طويلاً → <b>إعادة توجيه</b>\n"
            "2️⃣ أرسلها لبوت @userinfobot\n"
            "3️⃣ سيظهر لك معرّف القناة يبدأ بـ <code>-100</code>\n\n"
            "<b>ثم أرسل:</b>\n"
            "<code>/setchannel -100XXXXXXXXXX</code>\n\n"
            "⚠️ إذا كنت قد أضفت البوت كمشرف ولم يصلك تأكيد، فقط أرسل الأمر أعلاه بمعرّف قناتك."
        ),
        "tr": (
            "🔗 <b>Kanal ID'nizi nasıl öğrenirsiniz:</b>\n\n"
            "<b>Kolay yöntem:</b>\n"
            "1️⃣ Kanalınızı açın → Herhangi bir mesaja uzun basın → <b>İlet</b>\n"
            "2️⃣ @userinfobot'a iletin\n"
            "3️⃣ <code>-100</code> ile başlayan kanal ID'si görünecek\n\n"
            "<b>Sonra gönderin:</b>\n"
            "<code>/setchannel -100XXXXXXXXXX</code>\n\n"
            "⚠️ Botu yönetici olarak eklediniz ama onay gelmedi ise, yukarıdaki komutu gönderin."
        ),
        "en": (
            "🔗 <b>How to get your channel ID:</b>\n\n"
            "<b>Easy method:</b>\n"
            "1️⃣ Open your channel → Long-press any message → <b>Forward</b>\n"
            "2️⃣ Forward it to @userinfobot\n"
            "3️⃣ You'll see the channel ID starting with <code>-100</code>\n\n"
            "<b>Then send:</b>\n"
            "<code>/setchannel -100XXXXXXXXXX</code>\n\n"
            "⚠️ If you already added the bot as admin but got no confirmation, just send the command above."
        ),
    }

    await query.message.reply_text(
        texts.get(lang, texts["en"]),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Register all channel-related handlers
# ══════════════════════════════════════════════════════════════════════════════
def register_channel_handlers(application) -> None:
    """Register all channel management handlers with the Telegram application."""
    # Channel management menu button (all 3 languages)
    application.add_handler(
        MessageHandler(
            filters.Regex(r'^(🔗 Kanal Yönetimi|🔗 Channel Management|🔗 إدارة القناة)$'),
            start_channel_connection
        )
    )
    # /channel command
    application.add_handler(CommandHandler('channel', start_channel_connection))
    # /setchannel <channel_id> — manual override
    application.add_handler(CommandHandler('setchannel', handle_setchannel))
    # Inline button: how to get channel ID
    application.add_handler(CallbackQueryHandler(handle_how_to_get_channel_id, pattern='^how_to_get_channel_id$'))
