# ===================================================
# bot/handlers/channel_handler.py
# معالج ربط قناة تليجرام بالبوت للموردين
#
# التدفق الكامل:
#   /connect_channel
#     ← التحقق من تسجيل المورد
#     ← رسالة تعليمية تفاعلية (خطوة 1: إضافة البوت)
#     ← استقبال اسم القناة
#     ← التحقق الثلاثي (وجود القناة + إشراف + قراءة)
#     ← حفظ الربط في قاعدة البيانات
#     ← رسالة نجاح + إشعار للأدمن
#
# حلول المخاطر المطبّقة:
#   - رسائل خطأ تفاعلية واضحة لكل حالة فشل
#   - زر "❓ أحتاج مساعدة" في كل خطوة
#   - زر "🔄 إعادة المحاولة" عند الفشل
#   - منع ربط نفس القناة مرتين
#   - فحص القنوات المربوطة مسبقاً
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ChatType
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot import states
from bot.config import ADMIN_TELEGRAM_ID
from bot.services import database_service
from bot.services.language_service import get_string

logger = logging.getLogger(__name__)

# ===================================================
# ثوابت رسائل الخطأ التفصيلية
# ===================================================

# أنماط اسم القناة المقبولة
CHANNEL_USERNAME_PATTERN = re.compile(r'^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$')


# ===================================================
# دوال مساعدة لبناء لوحات المفاتيح
# ===================================================

def _help_keyboard(lang: str) -> InlineKeyboardMarkup:
    """زر 'أحتاج مساعدة' يظهر في كل خطوة."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text=get_string(lang, "channel_need_help_btn"),
            callback_data="channel_need_help"
        )
    ]])


def _retry_keyboard(lang: str) -> InlineKeyboardMarkup:
    """أزرار 'إعادة المحاولة' و'أحتاج مساعدة' عند الفشل."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text=get_string(lang, "channel_retry_btn"),
            callback_data="channel_retry"
        )],
        [InlineKeyboardButton(
            text=get_string(lang, "channel_need_help_btn"),
            callback_data="channel_need_help"
        )],
    ])


def _cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """زر 'إلغاء' للخروج من التدفق."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text=get_string(lang, "cancel_btn"),
            callback_data="channel_cancel"
        )
    ]])


def _start_keyboard(lang: str) -> InlineKeyboardMarkup:
    """أزرار البداية: 'جاهز' + 'أحتاج مساعدة'."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text=get_string(lang, "channel_ready_btn"),
            callback_data="channel_ready"
        )],
        [InlineKeyboardButton(
            text=get_string(lang, "channel_need_help_btn"),
            callback_data="channel_need_help"
        )],
        [InlineKeyboardButton(
            text=get_string(lang, "cancel_btn"),
            callback_data="channel_cancel"
        )],
    ])


# ===================================================
# نقطة الدخول: /connect_channel
# ===================================================

async def start_connect_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    نقطة دخول أمر /connect_channel.

    يتحقق من:
    1. أن المستخدم مورد مسجل
    2. أن حسابه معتمد (approved)

    ثم يعرض الخطوة التعليمية الأولى.
    """
    lang = context.user_data.get("lang", "ar")
    telegram_id = str(update.effective_user.id)

    # تحديد ما إذا كان الطلب من زر (callback) أم من أمر نصي
    is_callback = update.callback_query is not None
    if is_callback:
        # إظهار رد فعل فوري للمستخدم عند ضغط الزر
        await update.callback_query.answer("🔗 جاري تحميل إعداد القناة...")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # دالة مساعدة لإرسال الرد بغض النظر عن نوع التحديث
    async def reply(text, reply_markup=None, parse_mode=None):
        target = update.callback_query.message if is_callback else update.message
        await target.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    # التحقق من أن المستخدم مورد مسجل
    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if not supplier:
        await reply(text=get_string(lang, "not_registered_supplier"))
        return ConversationHandler.END

    # التحقق من حالة الحساب
    supplier_status = supplier.get("status", "pending")
    if supplier_status == "pending":
        await reply(text=get_string(lang, "channel_supplier_pending"))
        return ConversationHandler.END

    if supplier_status == "rejected":
        await reply(text=get_string(lang, "channel_supplier_rejected"))
        return ConversationHandler.END

    # حفظ بيانات المورد في السياق
    context.user_data["supplier_id"] = supplier.get("id")
    context.user_data["supplier_name"] = supplier.get("company_name", "")

    # فحص القنوات المربوطة مسبقاً
    existing = database_service.get_supplier_channels(supplier.get("id"))
    if existing:
        channel_list = "\n".join([
            f"  • {ch.get('channel_title', '')} (@{ch.get('channel_username', '')})"
            for ch in existing
        ])
        await reply(
            text=get_string(lang, "channel_already_connected").format(channels=channel_list),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    text=get_string(lang, "channel_add_another_btn"),
                    callback_data="channel_add_another"
                )],
                [InlineKeyboardButton(
                    text=get_string(lang, "channel_cancel_btn"),
                    callback_data="channel_cancel"
                )],
            ])
        )
        return states.CHANNEL_CONFIRM_ADD_ANOTHER

    # عرض الخطوة التعليمية الأولى
    msg = update.callback_query.message if is_callback else update.message
    return await _show_step_one(msg, context, lang)


async def _show_step_one(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    """
    الخطوة 1: تعليم المورد كيفية إضافة البوت كمشرف في قناته.
    """
    bot_username = context.bot.username
    await message.reply_text(
        text=get_string(lang, "channel_step1_instructions").format(
            bot_username=f"@{bot_username}"
        ),
        reply_markup=_start_keyboard(lang),
        parse_mode="HTML"
    )
    return states.CHANNEL_WAITING_READY


# ===================================================
# الخطوة 2: المورد يضغط "جاهز" ← طلب اسم القناة
# ===================================================

async def channel_ready(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المورد أكد أنه أضاف البوت كمشرف.
    نطلب منه الآن إرسال اسم القناة.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    await query.edit_message_text(
        text=get_string(lang, "channel_step2_ask_username"),
        reply_markup=_cancel_keyboard(lang),
        parse_mode="HTML"
    )
    return states.CHANNEL_WAITING_USERNAME


# ===================================================
# الخطوة 3: استقبال اسم القناة والتحقق الثلاثي
# ===================================================

async def channel_received_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم القناة ويُجري التحقق الثلاثي:
    1. هل القناة موجودة؟
    2. هل البوت مشرف فيها؟
    3. هل لديه صلاحية قراءة الرسائل؟
    """
    lang = context.user_data.get("lang", "ar")
    raw_input = update.message.text.strip()

    # تنظيف الإدخال
    channel_username = raw_input.lstrip("@").strip()

    # التحقق من صحة الصيغة
    if not CHANNEL_USERNAME_PATTERN.match(f"@{channel_username}"):
        await update.message.reply_text(
            text=get_string(lang, "channel_invalid_username"),
            reply_markup=_retry_keyboard(lang)
        )
        return states.CHANNEL_WAITING_USERNAME

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # رسالة "جاري التحقق..."
    checking_msg = await update.message.reply_text(
        text=get_string(lang, "channel_checking"),
    )

    # ===================================================
    # التحقق الأول: هل القناة موجودة؟
    # ===================================================
    try:
        chat = await context.bot.get_chat(f"@{channel_username}")
    except BadRequest as e:
        logger.warning("❌ القناة غير موجودة: @%s — %s", channel_username, e)
        await checking_msg.delete()
        await update.message.reply_text(
            text=get_string(lang, "channel_not_found").format(
                channel=f"@{channel_username}"
            ),
            reply_markup=_retry_keyboard(lang),
            parse_mode="HTML"
        )
        return states.CHANNEL_WAITING_USERNAME
    except Exception as e:
        logger.error("❌ خطأ غير متوقع في get_chat: %s", e)
        await checking_msg.delete()
        await update.message.reply_text(
            text=get_string(lang, "error_general"),
            reply_markup=_retry_keyboard(lang)
        )
        return states.CHANNEL_WAITING_USERNAME

    # التحقق من أنها قناة وليس مجموعة
    if chat.type not in [ChatType.CHANNEL]:
        await checking_msg.delete()
        await update.message.reply_text(
            text=get_string(lang, "channel_not_a_channel").format(
                channel=f"@{channel_username}"
            ),
            reply_markup=_retry_keyboard(lang),
            parse_mode="HTML"
        )
        return states.CHANNEL_WAITING_USERNAME

    # ===================================================
    # التحقق الثاني: هل البوت مشرف في القناة؟
    # ===================================================
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_admin = bot_member.status in ["administrator", "creator"]
    except Forbidden:
        is_admin = False
    except Exception as e:
        logger.error("❌ خطأ في get_chat_member: %s", e)
        is_admin = False

    if not is_admin:
        await checking_msg.delete()
        bot_username = context.bot.username
        await update.message.reply_text(
            text=get_string(lang, "channel_bot_not_admin").format(
                channel=f"@{channel_username}",
                bot_username=f"@{bot_username}"
            ),
            reply_markup=_retry_keyboard(lang),
            parse_mode="HTML"
        )
        return states.CHANNEL_WAITING_USERNAME

    # ===================================================
    # التحقق الثالث: هل للبوت صلاحية قراءة الرسائل؟
    # ===================================================
    can_read = getattr(bot_member, "can_read_all_group_messages", None)
    # في القنوات، المشرف يستطيع القراءة تلقائياً إذا كان مشرفاً
    # لكن نتحقق من صلاحية post_messages كمؤشر
    can_post = getattr(bot_member, "can_post_messages", None)

    # إذا كان مشرفاً بدون أي صلاحيات (مشرف مجهول)
    if can_post is False and can_read is False:
        await checking_msg.delete()
        await update.message.reply_text(
            text=get_string(lang, "channel_bot_no_read_permission").format(
                channel=f"@{channel_username}"
            ),
            reply_markup=_retry_keyboard(lang),
            parse_mode="HTML"
        )
        return states.CHANNEL_WAITING_USERNAME

    # ===================================================
    # التحقق من عدم ربط هذه القناة مسبقاً بمورد آخر
    # ===================================================
    existing_connection = database_service.get_channel_by_id(chat.id)
    if existing_connection:
        await checking_msg.delete()
        await update.message.reply_text(
            text=get_string(lang, "channel_already_taken").format(
                channel=f"@{channel_username}"
            ),
            reply_markup=_help_keyboard(lang),
            parse_mode="HTML"
        )
        return states.CHANNEL_WAITING_USERNAME

    # ===================================================
    # كل التحققات نجحت — حفظ البيانات مؤقتاً وطلب التأكيد
    # ===================================================
    await checking_msg.delete()

    context.user_data["pending_channel"] = {
        "channel_id": chat.id,
        "channel_username": channel_username,
        "channel_title": chat.title or channel_username,
    }

    await update.message.reply_text(
        text=get_string(lang, "channel_verification_success").format(
            channel_title=chat.title or channel_username,
            channel_username=f"@{channel_username}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                text=get_string(lang, "channel_confirm_connect_btn"),
                callback_data="channel_confirm_connect"
            )],
            [InlineKeyboardButton(
                text=get_string(lang, "cancel_btn"),
                callback_data="channel_cancel"
            )],
        ]),
        parse_mode="HTML"
    )
    return states.CHANNEL_CONFIRM_CONNECT


# ===================================================
# الخطوة 4: تأكيد الربط وحفظه في قاعدة البيانات
# ===================================================

async def channel_confirm_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يحفظ ربط القناة في جدول channel_connections
    ويرسل إشعاراً للأدمن.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.TYPING
    )

    supplier_id = context.user_data.get("supplier_id")
    supplier_name = context.user_data.get("supplier_name", "")
    pending = context.user_data.get("pending_channel", {})

    success = database_service.save_channel_connection({
        "supplier_id": supplier_id,
        "channel_id": pending.get("channel_id"),
        "channel_username": pending.get("channel_username"),
        "channel_title": pending.get("channel_title"),
    })

    if not success:
        await query.edit_message_text(
            text=get_string(lang, "error_general"),
            reply_markup=_retry_keyboard(lang)
        )
        return states.CHANNEL_CONFIRM_CONNECT

    # رسالة نجاح للمورد
    await query.edit_message_text(
        text=get_string(lang, "channel_connected_success").format(
            channel_title=pending.get("channel_title", ""),
            channel_username=f"@{pending.get('channel_username', '')}"
        ),
        parse_mode="HTML"
    )

    # إشعار للأدمن
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=get_string("ar", "channel_admin_notification").format(
                supplier_name=supplier_name,
                channel_title=pending.get("channel_title", ""),
                channel_username=f"@{pending.get('channel_username', '')}",
                channel_id=pending.get("channel_id", "")
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("⚠️ فشل إرسال إشعار الأدمن: %s", e)

    # تنظيف بيانات المحادثة
    for key in ["supplier_id", "supplier_name", "pending_channel"]:
        context.user_data.pop(key, None)

    logger.info(
        "✅ تم ربط القناة @%s للمورد: %s",
        pending.get("channel_username"),
        supplier_id
    )
    return ConversationHandler.END


# ===================================================
# معالجات الأزرار المساعدة
# ===================================================

async def channel_need_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يرسل إشعاراً للأدمن بأن المورد يحتاج مساعدة،
    ويعطي المورد رسالة طمأنة.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    supplier_name = context.user_data.get("supplier_name", "غير محدد")
    telegram_id = str(query.from_user.id)
    username = query.from_user.username or "لا يوجد"

    # إشعار فوري للأدمن
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=get_string("ar", "channel_help_request_admin").format(
                supplier_name=supplier_name,
                telegram_id=telegram_id,
                username=f"@{username}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("⚠️ فشل إرسال إشعار طلب المساعدة: %s", e)

    # رسالة طمأنة للمورد
    await query.edit_message_text(
        text=get_string(lang, "channel_help_sent_to_admin"),
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def channel_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يعيد المورد لخطوة إدخال اسم القناة.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    await query.edit_message_text(
        text=get_string(lang, "channel_step2_ask_username"),
        reply_markup=_cancel_keyboard(lang),
        parse_mode="HTML"
    )
    return states.CHANNEL_WAITING_USERNAME


async def channel_add_another(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المورد يريد إضافة قناة إضافية.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()

    await query.edit_message_text(
        text=get_string(lang, "channel_step2_ask_username"),
        reply_markup=_cancel_keyboard(lang),
        parse_mode="HTML"
    )
    return states.CHANNEL_WAITING_USERNAME


async def channel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يلغي عملية ربط القناة.
    """
    lang = context.user_data.get("lang", "ar")

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=get_string(lang, "channel_cancelled")
        )
    else:
        await update.message.reply_text(
            text=get_string(lang, "channel_cancelled")
        )

    # تنظيف
    for key in ["supplier_id", "supplier_name", "pending_channel"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END


# ===================================================
# بناء ConversationHandler
# ===================================================

def get_channel_conversation_handler() -> ConversationHandler:
    """
    يُنشئ ConversationHandler الكامل لتدفق ربط القناة.

    الحالات:
        CHANNEL_WAITING_READY          ← انتظار ضغط "جاهز"
        CHANNEL_WAITING_USERNAME       ← انتظار اسم القناة
        CHANNEL_CONFIRM_CONNECT        ← انتظار تأكيد الربط
        CHANNEL_CONFIRM_ADD_ANOTHER    ← انتظار قرار إضافة قناة أخرى
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("connect_channel", start_connect_channel),
            # زر "ربط قناة" من لوحة تحكم المورد
            CallbackQueryHandler(start_connect_channel, pattern="^post_reg_connect_channel$"),
        ],
        states={
            states.CHANNEL_WAITING_READY: [
                CallbackQueryHandler(channel_ready, pattern="^channel_ready$"),
                CallbackQueryHandler(channel_need_help, pattern="^channel_need_help$"),
                CallbackQueryHandler(channel_cancel, pattern="^channel_cancel$"),
            ],
            states.CHANNEL_WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, channel_received_username),
                CallbackQueryHandler(channel_need_help, pattern="^channel_need_help$"),
                CallbackQueryHandler(channel_retry, pattern="^channel_retry$"),
                CallbackQueryHandler(channel_cancel, pattern="^channel_cancel$"),
            ],
            states.CHANNEL_CONFIRM_CONNECT: [
                CallbackQueryHandler(channel_confirm_connect, pattern="^channel_confirm_connect$"),
                CallbackQueryHandler(channel_need_help, pattern="^channel_need_help$"),
                CallbackQueryHandler(channel_cancel, pattern="^channel_cancel$"),
            ],
            states.CHANNEL_CONFIRM_ADD_ANOTHER: [
                CallbackQueryHandler(channel_add_another, pattern="^channel_add_another$"),
                CallbackQueryHandler(channel_cancel, pattern="^channel_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", channel_cancel),
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
        name="channel_connection_conversation",
        persistent=False,
    )
