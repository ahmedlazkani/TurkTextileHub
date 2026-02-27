# ===================================================
# bot/handlers/product_handler.py
# معالج إضافة المنتجات للموردين
# المرحلة السادسة: ميزة جديدة بالكامل
# التدفق: /add_product ← الصور ← الفئة ← السعر ← معاينة ← نشر
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service, notification_service
from bot.services.language_service import get_string

logger = logging.getLogger(__name__)


def _build_category_keyboard(lang: str) -> InlineKeyboardMarkup:
    """يبني لوحة مفاتيح اختيار فئة المنتج."""
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "category_abayas"), callback_data="cat_abayas")],
        [InlineKeyboardButton(text=get_string(lang, "category_dresses"), callback_data="cat_dresses")],
        [InlineKeyboardButton(text=get_string(lang, "category_hijab"), callback_data="cat_hijab")],
        [InlineKeyboardButton(text=get_string(lang, "category_sets"), callback_data="cat_sets")],
        [InlineKeyboardButton(text=get_string(lang, "category_other"), callback_data="cat_other")],
    ]
    return InlineKeyboardMarkup(keyboard)


# خريطة callback_data إلى اسم الفئة للتخزين
CATEGORY_MAP = {
    "cat_abayas": "Abayas",
    "cat_dresses": "Dresses",
    "cat_hijab": "Hijab Clothing",
    "cat_sets": "Sets",
    "cat_other": "Other",
}


async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق إضافة منتج عند كتابة /add_product.

    يتحقق من أن المستخدم مورد مسجل قبل السماح بالإضافة.

    المُخرجات:
        int: states.GETTING_IMAGES إذا مورد مسجل، ConversationHandler.END إذا لم يكن
    """
    lang = context.user_data.get("lang", "ar")
    telegram_id = str(update.effective_user.id)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # التحقق من أن المستخدم مورد مسجل في جدول suppliers
    supplier = database_service.get_supplier_by_telegram_id(telegram_id)

    if not supplier:
        await update.message.reply_text(text=get_string(lang, "not_registered_supplier"))
        return ConversationHandler.END

    # حفظ بيانات المورد للاستخدام لاحقاً
    context.user_data["supplier_id"] = supplier.get("id")
    context.user_data["supplier_name"] = supplier.get("company_name", "")
    context.user_data["images"] = []  # تهيئة قائمة الصور

    await update.message.reply_text(text=get_string(lang, "add_product_start"))

    return states.GETTING_IMAGES


async def start_add_product_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق إضافة منتج عند الضغط على زر 'إضافة منتج جديد' من لوحة التحكم.
    يتعامل مع callback_query بدلاً من رسالة نصية.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    telegram_id = str(query.from_user.id)

    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if not supplier:
        await query.answer(text=get_string(lang, "not_registered_supplier"), show_alert=True)
        return ConversationHandler.END

    context.user_data["supplier_id"] = supplier.get("id")
    context.user_data["supplier_name"] = supplier.get("company_name", "")
    context.user_data["images"] = []

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=get_string(lang, "add_product_start")
    )
    return states.GETTING_IMAGES


async def get_images(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل صور المنتج (1-5 صور) ويحفظ file_id لكل صورة.

    يدعم استقبال صورة مفردة أو مجموعة صور (media group).

    المُخرجات:
        int: states.GETTING_CATEGORY بعد استقبال الصور
    """
    lang = context.user_data.get("lang", "ar")

    # التحقق من وجود صورة في الرسالة
    if not update.message.photo:
        await update.message.reply_text(text=get_string(lang, "add_product_no_images"))
        return states.GETTING_IMAGES

    # جلب أعلى جودة للصورة (آخر عنصر في القائمة)
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # إضافة file_id للقائمة (بحد أقصى 5 صور)
    images = context.user_data.get("images", [])
    if len(images) < 5:
        images.append(file_id)
        context.user_data["images"] = images

    logger.info("📸 تم استقبال صورة رقم %d للمورد: %s", len(images), context.user_data.get("supplier_id"))

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # عرض قائمة اختيار الفئة
    await update.message.reply_text(
        text=get_string(lang, "add_product_get_category"),
        reply_markup=_build_category_keyboard(lang)
    )

    return states.GETTING_CATEGORY


async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اختيار الفئة ويطلب السعر.

    المُخرجات:
        int: states.GETTING_PRICE
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    # تخزين الفئة بالاسم الإنجليزي للتخزين الموحد
    category = CATEGORY_MAP.get(query.data, "Other")
    context.user_data["category"] = category

    # بناء قائمة السعر مع زر التخطي
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "skip_btn"), callback_data="price_skip")]
    ]

    await query.edit_message_text(
        text=get_string(lang, "add_product_get_price"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return states.GETTING_PRICE


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نص السعر من المستخدم ويعرض معاينة المنتج.

    المُخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    lang = context.user_data.get("lang", "ar")

    price = update.message.text.strip()
    context.user_data["price"] = price

    return await _show_product_preview(update.message, context, lang)


async def skip_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يتجاهل إدخال السعر ويعرض معاينة المنتج.

    المُخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    context.user_data["price"] = None

    return await _show_product_preview(query.message, context, lang)


async def _show_product_preview(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    """
    دالة داخلية: تعرض معاينة المنتج قبل النشر.

    ترسل أول صورة مع نص المعاينة وأزرار التأكيد.

    المعاملات:
        message: كائن الرسالة
        context: سياق البوت
        lang: كود اللغة

    المُخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    category = context.user_data.get("category", "Other")
    price = context.user_data.get("price") or "—"
    images = context.user_data.get("images", [])

    # نص المعاينة من قالب الترجمة
    preview_text = get_string(lang, "add_product_confirm").format(
        category=category,
        price=price
    )

    # أزرار التأكيد والإلغاء
    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "publish_btn"), callback_data="product_confirm_yes")],
        [InlineKeyboardButton(text=get_string(lang, "cancel_btn"), callback_data="product_confirm_no")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    if images:
        # إرسال الصورة الأولى مع نص المعاينة
        await context.bot.send_photo(
            chat_id=message.chat_id,
            photo=images[0],
            caption=preview_text,
            reply_markup=reply_markup
        )
    else:
        # بدون صور
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=preview_text,
            reply_markup=reply_markup
        )

    return states.CONFIRM_ADD_PRODUCT


async def finish_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل تأكيد النشر ويحفظ المنتج في قاعدة البيانات.

    يُرسل إشعاراً للأدمن عند نجاح النشر.

    المُخرجات:
        int: ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    product_data = {
        "supplier_id": context.user_data.get("supplier_id"),
        "category": context.user_data.get("category"),
        "price": context.user_data.get("price"),
        "images": context.user_data.get("images", []),
    }

    success = database_service.add_product(product_data)

    if success:
        logger.info("✅ تم نشر منتج جديد للمورد: %s", product_data["supplier_id"])

        # إشعار الأدمن
        supplier_info = {
            "company_name": context.user_data.get("supplier_name", "غير محدد")
        }
        notification_service.notify_new_product(supplier_info, product_data)

        await query.edit_message_caption(
            caption=get_string(lang, "add_product_success")
        )
    else:
        logger.error("❌ فشل نشر المنتج للمورد: %s", product_data["supplier_id"])
        await query.edit_message_caption(
            caption=get_string(lang, "error_general")
        )

    return ConversationHandler.END


async def cancel_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية إلغاء المنتج من زر الإلغاء أو أمر /cancel.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_caption(
            caption=get_string(lang, "cancel")
        )
    else:
        await update.message.reply_text(text=get_string(lang, "cancel"))

    # مسح بيانات المنتج من الذاكرة
    for key in ["images", "category", "price", "supplier_id"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END
