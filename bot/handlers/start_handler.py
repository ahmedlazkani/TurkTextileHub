"""
start_handler.py — معالج /start ولوحة تحكم المورد/التاجر
TurkTextileHub Bot

يشمل:
- معالجة /start للتمييز بين المورد والتاجر والزائر الجديد
- بناء لوحة تحكم المورد بشكل ديناميكي حسب حالته وعدد قنواته
- عرض قائمة قنوات المورد المربوطة
- تغيير اللغة
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.services.database_service import (
    get_supplier_by_telegram_id,
    get_trader_by_telegram_id,
    get_supplier_channels,
)
from bot.services.language_service import get_string, detect_lang

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ثوابت callback_data
# ─────────────────────────────────────────────
CB_ADD_PRODUCT = "post_reg_add_product"
CB_CONNECT_CHANNEL = "post_reg_connect_channel"
CB_MY_CHANNELS = "my_channels"
CB_CHANGE_LANGUAGE = "change_language"
CB_SET_LANG_AR = "set_lang_ar"
CB_SET_LANG_TR = "set_lang_tr"
CB_SET_LANG_EN = "set_lang_en"


# ─────────────────────────────────────────────
# دوال بناء لوحة التحكم
# ─────────────────────────────────────────────

def _build_supplier_dashboard(
    lang: str,
    status: str,
    channel_count: int = 0,
) -> InlineKeyboardMarkup:
    """
    بناء لوحة تحكم المورد بشكل ديناميكي حسب حالته وعدد قنواته المربوطة.

    Args:
        lang (str): رمز اللغة ("ar" | "tr" | "en")
        status (str): حالة المورد ("pending" | "approved" | "rejected")
        channel_count (int): عدد القنوات المربوطة النشطة للمورد

    Returns:
        InlineKeyboardMarkup: لوحة المفاتيح المناسبة لحالة المورد
    """
    keyboard = []

    # زر إضافة منتج — متاح للجميع
    keyboard.append([
        InlineKeyboardButton(
            get_string(lang, "btn_add_product"),
            callback_data=CB_ADD_PRODUCT,
        )
    ])

    # أزرار حصرية للموردين المعتمدين فقط
    if status == "approved":
        # زر ربط قناة تليجرام
        keyboard.append([
            InlineKeyboardButton(
                get_string(lang, "btn_channel_connect"),
                callback_data=CB_CONNECT_CHANNEL,
            )
        ])

        # زر "قنواتي" — يظهر فقط إذا كان للمورد قنوات مربوطة
        if channel_count > 0:
            keyboard.append([
                InlineKeyboardButton(
                    get_string(lang, "my_channels_btn"),
                    callback_data=CB_MY_CHANNELS,
                )
            ])

    # زر تغيير اللغة — متاح للجميع
    keyboard.append([
        InlineKeyboardButton(
            get_string(lang, "btn_change_language"),
            callback_data=CB_CHANGE_LANGUAGE,
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def _supplier_dashboard_text(
    lang: str,
    contact_name: str,
    status: str,
    channel_count: int = 0,
) -> str:
    """
    بناء نص لوحة تحكم المورد مع عدد القنوات المربوطة للمعتمدين.

    Args:
        lang (str): رمز اللغة
        contact_name (str): اسم جهة الاتصال (المورد)
        status (str): حالة المورد
        channel_count (int): عدد القنوات المربوطة النشطة

    Returns:
        str: نص الرسالة المنسّق بـ HTML
    """
    status_map = {
        "approved": get_string(lang, "status_approved"),
        "pending":  get_string(lang, "status_pending"),
        "rejected": get_string(lang, "status_rejected"),
    }
    status_text = status_map.get(status, status)

    lines = [
        get_string(lang, "supplier_welcome").format(name=contact_name),
        "",
        get_string(lang, "supplier_account_label"),
        get_string(lang, "status_label").format(status=status_text),
    ]

    # إضافة سطر عدد القنوات للموردين المعتمدين فقط
    if status == "approved" and channel_count > 0:
        lines.append(
            get_string(lang, "channels_count_label") + f": {channel_count} 📢"
        )

    lines.append("")
    lines.append(get_string(lang, "dashboard_prompt"))

    return "\n".join(lines)


def _build_language_keyboard() -> InlineKeyboardMarkup:
    """
    بناء لوحة مفاتيح اختيار اللغة.

    Returns:
        InlineKeyboardMarkup: لوحة الاختيار الثلاثي للغات
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇸🇦 العربية", callback_data=CB_SET_LANG_AR),
            InlineKeyboardButton("🇹🇷 Türkçe",  callback_data=CB_SET_LANG_TR),
            InlineKeyboardButton("🇬🇧 English", callback_data=CB_SET_LANG_EN),
        ]
    ])


# ─────────────────────────────────────────────
# معالج /start
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start — نقطة الدخول الرئيسية للبوت.

    السلوك:
    - إذا كان المستخدم مورداً مسجلاً → يعرض لوحة تحكم المورد
    - إذا كان المستخدم تاجراً مسجلاً → يعرض لوحة تحكم التاجر
    - غير ذلك → يعرض رسالة الترحيب وخيارات التسجيل

    Args:
        update (Update): تحديث تيليغرام
        context (ContextTypes.DEFAULT_TYPE): سياق المحادثة
    """
    user = update.effective_user
    telegram_id = str(user.id)

    # كشف اللغة أو استخدام المحفوظة
    lang = context.user_data.get("lang") or detect_lang(user.language_code)
    context.user_data["lang"] = lang

    try:
        # التحقق إذا كان مورداً
        supplier = get_supplier_by_telegram_id(telegram_id)
        if supplier:
            supplier_id = supplier["id"]
            status = supplier.get("status", "pending")

            # جلب عدد القنوات للمعتمدين فقط (تحسين الأداء)
            channel_count = 0
            if status == "approved":
                channels = get_supplier_channels(supplier_id)
                channel_count = len(channels)

            context.user_data["supplier_id"] = supplier_id
            context.user_data["role"] = "supplier"

            text = _supplier_dashboard_text(
                lang=lang,
                contact_name=supplier.get("contact_name", user.first_name),
                status=status,
                channel_count=channel_count,
            )
            keyboard = _build_supplier_dashboard(
                lang=lang,
                status=status,
                channel_count=channel_count,
            )
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
            return

        # التحقق إذا كان تاجراً
        trader = get_trader_by_telegram_id(telegram_id)
        if trader:
            context.user_data["trader_id"] = trader["id"]
            context.user_data["role"] = "trader"
            await update.message.reply_text(
                get_string(lang, "trader_welcome").format(
                    name=trader.get("contact_name", user.first_name)
                ),
                parse_mode="HTML",
            )
            return

        # زائر جديد غير مسجل
        await update.message.reply_text(
            get_string(lang, "welcome_new_user"),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"خطأ في معالج /start للمستخدم {telegram_id}: {e}", exc_info=True)
        await update.message.reply_text(get_string(lang, "error_generic"))


# ─────────────────────────────────────────────
# معالج تغيير اللغة
# ─────────────────────────────────────────────

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    عرض لوحة اختيار اللغة عند الضغط على زر "تغيير اللغة".

    Args:
        update (Update): تحديث تيليغرام
        context (ContextTypes.DEFAULT_TYPE): سياق المحادثة
    """
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ar")
    await query.message.reply_text(
        get_string(lang, "choose_language_prompt"),
        reply_markup=_build_language_keyboard(),
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    تطبيق اللغة المختارة وإعادة عرض لوحة التحكم المناسبة.

    callback_data المتوقعة: "set_lang_ar" | "set_lang_tr" | "set_lang_en"

    Args:
        update (Update): تحديث تيليغرام
        context (ContextTypes.DEFAULT_TYPE): سياق المحادثة
    """
    query = update.callback_query
    await query.answer()

    # استخراج اللغة من callback_data
    lang_map = {
        CB_SET_LANG_AR: "ar",
        CB_SET_LANG_TR: "tr",
        CB_SET_LANG_EN: "en",
    }
    new_lang = lang_map.get(query.data, "ar")
    context.user_data["lang"] = new_lang

    telegram_id = str(update.effective_user.id)

    try:
        supplier = get_supplier_by_telegram_id(telegram_id)
        if supplier:
            status = supplier.get("status", "pending")
            channel_count = 0
            if status == "approved":
                channels = get_supplier_channels(supplier["id"])
                channel_count = len(channels)

            text = _supplier_dashboard_text(
                lang=new_lang,
                contact_name=supplier.get("contact_name", ""),
                status=status,
                channel_count=channel_count,
            )
            keyboard = _build_supplier_dashboard(
                lang=new_lang,
                status=status,
                channel_count=channel_count,
            )
            await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
            return

        # رد افتراضي إذا لم يكن مورداً
        await query.message.reply_text(
            get_string(new_lang, "language_changed_success"),
        )

    except Exception as e:
        logger.error(f"خطأ في تغيير اللغة للمستخدم {telegram_id}: {e}", exc_info=True)
        await query.message.reply_text(get_string(new_lang, "error_generic"))


# ─────────────────────────────────────────────
# معالج "قنواتي"
# ─────────────────────────────────────────────

async def show_my_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    عرض قائمة القنوات المربوطة بالمورد عند الضغط على زر "📢 قنواتي".

    السلوك:
    - يجلب قنوات المورد من قاعدة البيانات
    - يعرضها بشكل مرتّب مع اسم كل قناة وتاريخ الربط
    - يضيف زر "➕ ربط قناة أخرى" في الأسفل للعودة لتدفق الربط

    callback_data المتوقعة: "my_channels"

    Args:
        update (Update): تحديث تيليغرام
        context (ContextTypes.DEFAULT_TYPE): سياق المحادثة
    """
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ar")
    telegram_id = str(update.effective_user.id)

    try:
        supplier = get_supplier_by_telegram_id(telegram_id)
        if not supplier:
            await query.message.reply_text(get_string(lang, "error_not_supplier"))
            return

        channels = get_supplier_channels(supplier["id"])

        if not channels:
            # لا توجد قنوات مربوطة
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        get_string(lang, "btn_channel_connect"),
                        callback_data=CB_CONNECT_CHANNEL,
                    )
                ],
                [
                    InlineKeyboardButton(
                        get_string(lang, "back_to_dashboard_btn"),
                        callback_data="back_to_dashboard",
                    )
                ],
            ])
            await query.message.reply_text(
                get_string(lang, "my_channels_empty"),
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        # بناء قائمة القنوات
        lines = [get_string(lang, "my_channels_title"), ""]

        for ch in channels:
            title = ch.get("channel_title", "—")
            username = ch.get("channel_username", "")
            created_at = ch.get("created_at", "")

            # تنسيق التاريخ
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = created_at[:10] if created_at else "—"

            item = get_string(lang, "my_channels_item").format(
                title=title,
                username=username,
                date=date_str,
            )
            lines.append(item)
            lines.append("")  # سطر فاصل

        # أزرار الإجراءات
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    get_string(lang, "add_another_channel_btn"),
                    callback_data=CB_CONNECT_CHANNEL,
                )
            ],
            [
                InlineKeyboardButton(
                    get_string(lang, "back_to_dashboard_btn"),
                    callback_data="back_to_dashboard",
                )
            ],
        ])

        await query.message.reply_text(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(
            f"خطأ في عرض قنوات المورد {telegram_id}: {e}", exc_info=True
        )
        await query.message.reply_text(get_string(lang, "error_generic"))


async def back_to_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    العودة إلى لوحة تحكم المورد.

    Args:
        update (Update): تحديث تيليغرام
        context (ContextTypes.DEFAULT_TYPE): سياق المحادثة
    """
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ar")
    telegram_id = str(update.effective_user.id)

    try:
        supplier = get_supplier_by_telegram_id(telegram_id)
        if not supplier:
            await query.message.reply_text(get_string(lang, "error_generic"))
            return

        status = supplier.get("status", "pending")
        channel_count = 0
        if status == "approved":
            channels = get_supplier_channels(supplier["id"])
            channel_count = len(channels)

        text = _supplier_dashboard_text(
            lang=lang,
            contact_name=supplier.get("contact_name", ""),
            status=status,
            channel_count=channel_count,
        )
        keyboard = _build_supplier_dashboard(
            lang=lang,
            status=status,
            channel_count=channel_count,
        )
        await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"خطأ في العودة للوحة التحكم {telegram_id}: {e}", exc_info=True)
        await query.message.reply_text(get_string(lang, "error_generic"))


# ─────────────────────────────────────────────
# تسجيل المعالجات — يُستدعى من main.py
# ─────────────────────────────────────────────

def register_start_handlers(application) -> None:
    """
    تسجيل جميع معالجات start_handler في الـ Application.

    Args:
        application: كائن Application من python-telegram-bot
    """
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CallbackQueryHandler(change_language, pattern=f"^{CB_CHANGE_LANGUAGE}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            set_language,
            pattern=f"^({CB_SET_LANG_AR}|{CB_SET_LANG_TR}|{CB_SET_LANG_EN})$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(show_my_channels, pattern=f"^{CB_MY_CHANNELS}$")
    )
    application.add_handler(
        CallbackQueryHandler(back_to_dashboard, pattern="^back_to_dashboard$")
    )
