# ===================================================
# bot/handlers/browse_handler.py
# معالج تصفح المنتجات للتجار مع Pagination
# المرحلة السادسة: ميزة جديدة بالكامل
# التدفق: /browse ← اختيار الفئة ← تصفح المنتجات ← التنقل بينها
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service
from bot.services.language_service import get_string

logger = logging.getLogger(__name__)


def _build_categories_keyboard(lang: str, categories: list) -> InlineKeyboardMarkup:
    """
    يبني لوحة مفاتيح ديناميكية بالفئات المتاحة + زر 'عرض الكل'.

    المعاملات:
        lang (str): كود اللغة
        categories (list): قائمة الفئات المتاحة

    المُخرجات:
        InlineKeyboardMarkup: لوحة المفاتيح الجاهزة
    """
    keyboard = []

    for category in categories:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📁 {category}",
                callback_data=f"browse_cat_{category}"
            )
        ])

    # زر عرض الكل
    keyboard.append([
        InlineKeyboardButton(
            text=get_string(lang, "show_all_btn"),
            callback_data="browse_cat_all"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def _build_product_navigation_keyboard(lang: str, current_idx: int, total: int) -> InlineKeyboardMarkup:
    """
    يبني لوحة مفاتيح التنقل بين المنتجات.

    يعرض أزرار التالي/السابق حسب الموضع الحالي.

    المعاملات:
        lang (str): كود اللغة
        current_idx (int): فهرس المنتج الحالي (0-based)
        total (int): العدد الإجمالي للمنتجات

    المُخرجات:
        InlineKeyboardMarkup: لوحة مفاتيح التنقل
    """
    nav_buttons = []

    # زر السابق (إذا لم يكن في البداية)
    if current_idx > 0:
        nav_buttons.append(
            InlineKeyboardButton(text=get_string(lang, "prev_btn"), callback_data="browse_prev")
        )

    # زر التالي (إذا لم يكن في النهاية)
    if current_idx < total - 1:
        nav_buttons.append(
            InlineKeyboardButton(text=get_string(lang, "next_btn"), callback_data="browse_next")
        )

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)

    # زر طلب عرض السعر
    keyboard.append([
        InlineKeyboardButton(text=get_string(lang, "request_quote_btn"), callback_data="browse_request_quote")
    ])

    # زر العودة للفئات
    keyboard.append([
        InlineKeyboardButton(text=get_string(lang, "back_to_categories_btn"), callback_data="browse_back")
    ])

    return InlineKeyboardMarkup(keyboard)


def _format_product_caption(lang: str, product: dict, current_idx: int, total: int) -> str:
    """
    يبني نص تسمية المنتج مع معلومات التنقل.

    المعاملات:
        lang (str): كود اللغة
        product (dict): بيانات المنتج
        current_idx (int): الفهرس الحالي (0-based)
        total (int): العدد الإجمالي

    المُخرجات:
        str: نص التسمية المنسق
    """
    # استخراج اسم المورد من العلاقة
    supplier_name = "—"
    if product.get("suppliers") and isinstance(product["suppliers"], dict):
        supplier_name = product["suppliers"].get("company_name", "—")

    category = product.get("category", "—")
    price = product.get("price") or "—"

    caption = get_string(lang, "browse_product_caption").format(
        category=category,
        price=price,
        supplier_name=supplier_name
    )

    counter = get_string(lang, "product_counter").format(
        current=current_idx + 1,
        total=total
    )

    return f"{caption}\n\n📊 {counter}"


async def start_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق التصفح عند كتابة /browse.

    يجلب الفئات المتاحة ويعرضها كأزرار.

    المُخرجات:
        int: states.BROWSING_CATEGORY أو ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # جلب الفئات المتاحة من قاعدة البيانات
    categories = database_service.get_all_categories()

    if not categories:
        # لا توجد فئات - عرض كل المنتجات أو إشعار بعدم التوفر
        keyboard = [
            [InlineKeyboardButton(text=get_string(lang, "show_all_btn"), callback_data="browse_cat_all")]
        ]
        await update.message.reply_text(
            text=get_string(lang, "browse_start"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text=get_string(lang, "browse_start"),
            reply_markup=_build_categories_keyboard(lang, categories)
        )

    return states.BROWSING_CATEGORY


async def browse_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اختيار الفئة ويعرض أول منتج فيها.

    المُخرجات:
        int: states.BROWSING_PRODUCTS أو نفس الحالة إذا لم توجد منتجات
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    # استخراج الفئة من callback_data (browse_cat_XXX)
    category = query.data.replace("browse_cat_", "")
    context.user_data["browse_category"] = category

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    # جلب المنتجات من قاعدة البيانات
    products = database_service.get_products_by_category(category)

    if not products:
        keyboard = [
            [InlineKeyboardButton(text=get_string(lang, "back_to_categories_btn"), callback_data="browse_back")]
        ]
        await query.edit_message_text(
            text=get_string(lang, "no_products_found"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return states.BROWSING_CATEGORY

    # حفظ قائمة المنتجات والفهرس الحالي
    context.user_data["browse_products"] = products
    context.user_data["browse_index"] = 0

    # عرض أول منتج
    await query.delete_message()
    await _send_product(query.message.chat_id, context, lang, 0)

    return states.BROWSING_PRODUCTS


async def _send_product(chat_id: int, context: ContextTypes.DEFAULT_TYPE, lang: str, idx: int) -> None:
    """
    دالة داخلية: ترسل رسالة منتج جديدة (ليست تعديلاً).

    تُستخدم عند الانتقال لصفحة جديدة.

    المعاملات:
        chat_id (int): معرف المحادثة
        context: سياق البوت
        lang (str): كود اللغة
        idx (int): فهرس المنتج
    """
    products = context.user_data.get("browse_products", [])
    product = products[idx]
    total = len(products)

    caption = _format_product_caption(lang, product, idx, total)
    keyboard = _build_product_navigation_keyboard(lang, idx, total)
    images = product.get("images", [])

    if images:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=images[0],
            caption=caption,
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=keyboard
        )

    context.user_data["browse_index"] = idx


async def next_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يتنقل للمنتج التالي عند الضغط على زر 'التالي'.

    المُخرجات:
        int: states.BROWSING_PRODUCTS
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    current_idx = context.user_data.get("browse_index", 0)
    products = context.user_data.get("browse_products", [])

    new_idx = min(current_idx + 1, len(products) - 1)

    if new_idx != current_idx:
        product = products[new_idx]
        total = len(products)
        caption = _format_product_caption(lang, product, new_idx, total)
        keyboard = _build_product_navigation_keyboard(lang, new_idx, total)
        images = product.get("images", [])

        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

        if images:
            try:
                # محاولة تعديل الصورة الحالية
                from telegram import InputMediaPhoto
                await query.edit_message_media(
                    media=InputMediaPhoto(media=images[0], caption=caption),
                    reply_markup=keyboard
                )
            except Exception:
                # إذا فشل التعديل، أرسل رسالة جديدة
                await query.delete_message()
                await _send_product(query.message.chat_id, context, lang, new_idx)
                return states.BROWSING_PRODUCTS
        else:
            await query.edit_message_text(text=caption, reply_markup=keyboard)

        context.user_data["browse_index"] = new_idx

    return states.BROWSING_PRODUCTS


async def prev_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يتنقل للمنتج السابق عند الضغط على زر 'السابق'.

    المُخرجات:
        int: states.BROWSING_PRODUCTS
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    current_idx = context.user_data.get("browse_index", 0)
    products = context.user_data.get("browse_products", [])

    new_idx = max(current_idx - 1, 0)

    if new_idx != current_idx:
        product = products[new_idx]
        total = len(products)
        caption = _format_product_caption(lang, product, new_idx, total)
        keyboard = _build_product_navigation_keyboard(lang, new_idx, total)
        images = product.get("images", [])

        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

        if images:
            try:
                from telegram import InputMediaPhoto
                await query.edit_message_media(
                    media=InputMediaPhoto(media=images[0], caption=caption),
                    reply_markup=keyboard
                )
            except Exception:
                await query.delete_message()
                await _send_product(query.message.chat_id, context, lang, new_idx)
                return states.BROWSING_PRODUCTS
        else:
            await query.edit_message_text(text=caption, reply_markup=keyboard)

        context.user_data["browse_index"] = new_idx

    return states.BROWSING_PRODUCTS


async def request_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل طلب عرض السعر ويُرسل إشعاراً للمورد.

    المُخرجات:
        int: states.BROWSING_PRODUCTS
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    current_idx = context.user_data.get("browse_index", 0)
    products = context.user_data.get("browse_products", [])

    if products and current_idx < len(products):
        product = products[current_idx]
        logger.info(
            "📋 طلب عرض سعر للمنتج: id=%s من المستخدم: %s",
            product.get("id"),
            query.from_user.id
        )

    # إرسال رسالة تأكيد للتاجر
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=get_string(lang, "quote_request_sent")
    )

    return states.BROWSING_PRODUCTS


async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يعود لقائمة الفئات عند الضغط على 'العودة للفئات'.

    المُخرجات:
        int: states.BROWSING_CATEGORY
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    # مسح بيانات التصفح الحالي
    context.user_data.pop("browse_products", None)
    context.user_data.pop("browse_index", None)
    context.user_data.pop("browse_category", None)

    # جلب الفئات من جديد
    categories = database_service.get_all_categories()

    try:
        await query.edit_message_text(
            text=get_string(lang, "browse_start"),
            reply_markup=_build_categories_keyboard(lang, categories)
        )
    except Exception:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_string(lang, "browse_start"),
            reply_markup=_build_categories_keyboard(lang, categories)
        )

    return states.BROWSING_CATEGORY


async def cancel_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي تدفق التصفح عند كتابة /cancel.

    المُخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")

    # مسح بيانات التصفح
    for key in ["browse_products", "browse_index", "browse_category"]:
        context.user_data.pop(key, None)

    await update.message.reply_text(text=get_string(lang, "cancel"))
    return ConversationHandler.END
