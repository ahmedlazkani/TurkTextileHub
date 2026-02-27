# ===================================================
# bot/handlers/browse_handler.py
# معالج تصفح المنتجات للتجار مع Pagination + تدفق RFQ الكامل
# المرحلة السابعة: إضافة تدفق طلب عرض السعر (RFQ)
# التدفق: /browse ← اختيار الفئة ← تصفح المنتجات ← طلب عرض سعر
# KAYISOFT - إسطنبول، تركيا
# ===================================================
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot import states
from bot.services import database_service
from bot.services.language_service import get_string
from bot.services.database_service import (
    get_product_by_id,
    get_trader_by_telegram_id,
    add_quote_request,
)
from bot.services.notification_service import notify_quote_request_to_supplier

logger = logging.getLogger(__name__)

RFQ_DATA_KEY = "rfq_data"


def _build_categories_keyboard(lang: str, categories: list) -> InlineKeyboardMarkup:
    keyboard = []
    for category in categories:
        keyboard.append([
            InlineKeyboardButton(text=f"📁 {category}", callback_data=f"browse_cat_{category}")
        ])
    keyboard.append([
        InlineKeyboardButton(text=get_string(lang, "show_all_btn"), callback_data="browse_cat_all")
    ])
    return InlineKeyboardMarkup(keyboard)


def _build_product_navigation_keyboard(lang: str, current_idx: int, total: int) -> InlineKeyboardMarkup:
    nav_buttons = []
    if current_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text=get_string(lang, "prev_btn"), callback_data="browse_prev"))
    if current_idx < total - 1:
        nav_buttons.append(InlineKeyboardButton(text=get_string(lang, "next_btn"), callback_data="browse_next"))
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text=get_string(lang, "request_quote_btn"), callback_data="browse_request_quote")])
    keyboard.append([InlineKeyboardButton(text=get_string(lang, "back_to_categories_btn"), callback_data="browse_back")])
    return InlineKeyboardMarkup(keyboard)


def _skip_button(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_string(lang, "skip_button"), callback_data="rfq_skip")]])


def _confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_string(lang, "confirm_send_button"), callback_data="rfq_confirm"),
        InlineKeyboardButton(get_string(lang, "cancel_button"), callback_data="rfq_cancel"),
    ]])


def _format_product_caption(lang: str, product: dict, current_idx: int, total: int) -> str:
    supplier_name = "—"
    if product.get("suppliers") and isinstance(product["suppliers"], dict):
        supplier_name = product["suppliers"].get("company_name", "—")
    category = product.get("category", "—")
    price = product.get("price") or "—"
    caption = get_string(lang, "browse_product_caption").format(
        category=category, price=price, supplier_name=supplier_name
    )
    counter = get_string(lang, "product_counter").format(current=current_idx + 1, total=total)
    return f"{caption}\n\n📊 {counter}"


async def start_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ar")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    categories = database_service.get_all_categories()
    if not categories:
        keyboard = [[InlineKeyboardButton(text=get_string(lang, "show_all_btn"), callback_data="browse_cat_all")]]
        await update.message.reply_text(text=get_string(lang, "browse_start"), reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text=get_string(lang, "browse_start"), reply_markup=_build_categories_keyboard(lang, categories))
    return states.BROWSING_CATEGORY


async def start_browse_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق التصفح عند الضغط على زر 'تصفح المنتجات' من لوحة التحكم.
    يتعامل مع callback_query بدلاً من رسالة نصية.
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
    categories = database_service.get_all_categories()
    if not categories:
        keyboard = [[InlineKeyboardButton(text=get_string(lang, "show_all_btn"), callback_data="browse_cat_all")]]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_string(lang, "browse_start"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_string(lang, "browse_start"),
            reply_markup=_build_categories_keyboard(lang, categories)
        )
    return states.BROWSING_CATEGORY


async def browse_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()
    category = query.data.replace("browse_cat_", "")
    context.user_data["browse_category"] = category
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
    products = database_service.get_products_by_category(category)
    if not products:
        keyboard = [[InlineKeyboardButton(text=get_string(lang, "back_to_categories_btn"), callback_data="browse_back")]]
        await query.edit_message_text(text=get_string(lang, "no_products_found"), reply_markup=InlineKeyboardMarkup(keyboard))
        return states.BROWSING_CATEGORY
    context.user_data["browse_products"] = products
    context.user_data["browse_index"] = 0
    await query.delete_message()
    await _send_product(query.message.chat_id, context, lang, 0)
    return states.BROWSING_PRODUCTS


async def _send_product(chat_id: int, context: ContextTypes.DEFAULT_TYPE, lang: str, idx: int) -> None:
    products = context.user_data.get("browse_products", [])
    product = products[idx]
    total = len(products)
    caption = _format_product_caption(lang, product, idx, total)
    keyboard = _build_product_navigation_keyboard(lang, idx, total)
    images = product.get("images", [])
    if images:
        await context.bot.send_photo(chat_id=chat_id, photo=images[0], caption=caption, reply_markup=keyboard)
    else:
        await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=keyboard)
    context.user_data["browse_index"] = idx


async def next_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
                from telegram import InputMediaPhoto
                await query.edit_message_media(media=InputMediaPhoto(media=images[0], caption=caption), reply_markup=keyboard)
            except Exception:
                await query.delete_message()
                await _send_product(query.message.chat_id, context, lang, new_idx)
                return states.BROWSING_PRODUCTS
        else:
            await query.edit_message_text(text=caption, reply_markup=keyboard)
        context.user_data["browse_index"] = new_idx
    return states.BROWSING_PRODUCTS


async def prev_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
                await query.edit_message_media(media=InputMediaPhoto(media=images[0], caption=caption), reply_markup=keyboard)
            except Exception:
                await query.delete_message()
                await _send_product(query.message.chat_id, context, lang, new_idx)
                return states.BROWSING_PRODUCTS
        else:
            await query.edit_message_text(text=caption, reply_markup=keyboard)
        context.user_data["browse_index"] = new_idx
    return states.BROWSING_PRODUCTS


# ─────────────────────────────────────────────
# تدفق RFQ - طلب عرض السعر
# ─────────────────────────────────────────────

async def request_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نقطة دخول تدفق RFQ - يبدأ عند ضغط التاجر على زر طلب عرض سعر."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ar")
    telegram_id = update.effective_user.id

    current_idx = context.user_data.get("browse_index", 0)
    products = context.user_data.get("browse_products", [])

    if not products or current_idx >= len(products):
        await query.message.reply_text(get_string(lang, "error_invalid_product"))
        return states.BROWSING_PRODUCTS

    current_product = products[current_idx]
    product_id = current_product.get("id")

    product = get_product_by_id(product_id)
    if not product:
        await query.message.reply_text(get_string(lang, "error_product_not_found"))
        return states.BROWSING_PRODUCTS

    trader = get_trader_by_telegram_id(telegram_id)
    if not trader:
        await query.message.reply_text(get_string(lang, "error_trader_not_found"))
        return states.BROWSING_PRODUCTS

    context.user_data[RFQ_DATA_KEY] = {
        "product_id": product_id,
        "product": product,
        "trader": trader,
        "quantity": None,
        "color": None,
        "size": None,
        "delivery_date": None,
    }

    await query.message.reply_text(
        get_string(lang, "rfq_ask_quantity").format(
            product_name=product.get("name") or product.get("category", "")
        ),
        reply_markup=_skip_button(lang),
    )
    return states.GETTING_QUOTE_QUANTITY


async def get_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الكمية والانتقال لسؤال اللون."""
    lang = context.user_data.get("lang", "ar")
    if update.message:
        context.user_data[RFQ_DATA_KEY]["quantity"] = update.message.text.strip()
    await update.effective_message.reply_text(get_string(lang, "rfq_ask_color"), reply_markup=_skip_button(lang))
    return states.GETTING_QUOTE_COLOR


async def get_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اللون والانتقال لسؤال المقاس."""
    lang = context.user_data.get("lang", "ar")
    if update.message:
        context.user_data[RFQ_DATA_KEY]["color"] = update.message.text.strip()
    await update.effective_message.reply_text(get_string(lang, "rfq_ask_size"), reply_markup=_skip_button(lang))
    return states.GETTING_QUOTE_SIZE


async def get_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المقاس والانتقال لسؤال تاريخ التسليم."""
    lang = context.user_data.get("lang", "ar")
    if update.message:
        context.user_data[RFQ_DATA_KEY]["size"] = update.message.text.strip()
    await update.effective_message.reply_text(get_string(lang, "rfq_ask_delivery_date"), reply_markup=_skip_button(lang))
    return states.GETTING_QUOTE_DELIVERY_DATE


async def get_delivery_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال تاريخ التسليم وعرض ملخص التأكيد."""
    lang = context.user_data.get("lang", "ar")
    if update.message:
        context.user_data[RFQ_DATA_KEY]["delivery_date"] = update.message.text.strip()
    return await _show_confirmation(update, context)


async def _show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض ملخص طلب عرض السعر وطلب التأكيد."""
    lang = context.user_data.get("lang", "ar")
    rfq = context.user_data[RFQ_DATA_KEY]
    product = rfq["product"]

    def val(v: Optional[str]) -> str:
        return v if v else get_string(lang, "not_specified")

    summary = get_string(lang, "rfq_summary").format(
        product_name=product.get("name") or product.get("category", ""),
        quantity=val(rfq.get("quantity")),
        color=val(rfq.get("color")),
        size=val(rfq.get("size")),
        delivery_date=val(rfq.get("delivery_date")),
    )
    await update.effective_message.reply_text(summary, reply_markup=_confirm_keyboard(lang), parse_mode="HTML")
    return states.CONFIRM_QUOTE_REQUEST


async def skip_rfq_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالج زر تخطي - يحدد الحالة الحالية ويتجاوز السؤال."""
    query = update.callback_query
    await query.answer()
    current_state = context.user_data.get("current_rfq_state", states.GETTING_QUOTE_QUANTITY)
    if current_state == states.GETTING_QUOTE_QUANTITY:
        return await get_quantity(update, context)
    elif current_state == states.GETTING_QUOTE_COLOR:
        return await get_color(update, context)
    elif current_state == states.GETTING_QUOTE_SIZE:
        return await get_size(update, context)
    elif current_state == states.GETTING_QUOTE_DELIVERY_DATE:
        return await _show_confirmation(update, context)
    return ConversationHandler.END


async def confirm_quote_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد الطلب: الحفظ في قاعدة البيانات وإرسال الإشعار للمورد."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ar")
    rfq = context.user_data.get(RFQ_DATA_KEY, {})
    product = rfq.get("product", {})
    trader = rfq.get("trader", {})
    supplier = product.get("suppliers", {})

    saved = add_quote_request(
        product_id=rfq.get("product_id"),
        supplier_id=supplier.get("id"),
        trader_id=trader.get("id"),
        quantity=rfq.get("quantity"),
        color=rfq.get("color"),
        size=rfq.get("size"),
        delivery_date=rfq.get("delivery_date"),
    )

    if not saved:
        await query.message.reply_text(get_string(lang, "rfq_save_error"))
        return ConversationHandler.END

    supplier_telegram_id = supplier.get("telegram_id")
    notified = False
    if supplier_telegram_id:
        notified = notify_quote_request_to_supplier(
            supplier_telegram_id=supplier_telegram_id,
            trader_name=trader.get("name", "غير معروف"),
            trader_phone=trader.get("phone", "غير متوفر"),
            trader_telegram_id=trader.get("telegram_id"),
            product_id=rfq.get("product_id"),
            product_name=product.get("name") or product.get("category", ""),
            product_url=product.get("image_url"),
            supplier_id=supplier.get("id"),
            quantity=rfq.get("quantity"),
            color=rfq.get("color"),
            size=rfq.get("size"),
            delivery_date=rfq.get("delivery_date"),
        )

    if notified:
        await query.message.reply_text(get_string(lang, "rfq_sent_success"))
    else:
        await query.message.reply_text(get_string(lang, "rfq_notification_failed"))

    context.user_data.pop(RFQ_DATA_KEY, None)
    context.user_data.pop("current_rfq_state", None)
    return ConversationHandler.END


async def cancel_quote_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء طلب عرض السعر."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ar")
    context.user_data.pop(RFQ_DATA_KEY, None)
    context.user_data.pop("current_rfq_state", None)
    await query.message.reply_text(get_string(lang, "rfq_cancelled"))
    return ConversationHandler.END


# ─────────────────────────────────────────────
# State Tracker
# ─────────────────────────────────────────────

def _state_tracker(state):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            context.user_data["current_rfq_state"] = state
            return await func(update, context)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


_tracked_get_quantity = _state_tracker(states.GETTING_QUOTE_QUANTITY)(get_quantity)
_tracked_get_color = _state_tracker(states.GETTING_QUOTE_COLOR)(get_color)
_tracked_get_size = _state_tracker(states.GETTING_QUOTE_SIZE)(get_size)
_tracked_get_delivery_date = _state_tracker(states.GETTING_QUOTE_DELIVERY_DATE)(get_delivery_date)


async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعود لقائمة الفئات."""
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
    context.user_data.pop("browse_products", None)
    context.user_data.pop("browse_index", None)
    context.user_data.pop("browse_category", None)
    categories = database_service.get_all_categories()
    try:
        await query.edit_message_text(text=get_string(lang, "browse_start"), reply_markup=_build_categories_keyboard(lang, categories))
    except Exception:
        await context.bot.send_message(chat_id=query.message.chat_id, text=get_string(lang, "browse_start"), reply_markup=_build_categories_keyboard(lang, categories))
    return states.BROWSING_CATEGORY


async def cancel_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يُلغي تدفق التصفح."""
    lang = context.user_data.get("lang", "ar")
    for key in ["browse_products", "browse_index", "browse_category"]:
        context.user_data.pop(key, None)
    await update.message.reply_text(text=get_string(lang, "cancel"))
    return ConversationHandler.END


# ─────────────────────────────────────────────
# ConversationHandler الموحد
# ─────────────────────────────────────────────

def get_browse_conversation_handler() -> ConversationHandler:
    """يُنشئ ConversationHandler الموحد للتصفح وتدفق RFQ."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("browse", start_browse),
            CallbackQueryHandler(start_browse_from_button, pattern="^post_reg_browse_products$"),
        ],
        states={
            states.BROWSING_CATEGORY: [
                CallbackQueryHandler(browse_by_category, pattern=r"^browse_cat_"),
            ],
            states.BROWSING_PRODUCTS: [
                CallbackQueryHandler(next_product, pattern="^browse_next$"),
                CallbackQueryHandler(prev_product, pattern="^browse_prev$"),
                CallbackQueryHandler(request_quote, pattern="^browse_request_quote$"),
                CallbackQueryHandler(back_to_categories, pattern="^browse_back$"),
            ],
            states.GETTING_QUOTE_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _tracked_get_quantity),
                CallbackQueryHandler(skip_rfq_step, pattern="^rfq_skip$"),
            ],
            states.GETTING_QUOTE_COLOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _tracked_get_color),
                CallbackQueryHandler(skip_rfq_step, pattern="^rfq_skip$"),
            ],
            states.GETTING_QUOTE_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _tracked_get_size),
                CallbackQueryHandler(skip_rfq_step, pattern="^rfq_skip$"),
            ],
            states.GETTING_QUOTE_DELIVERY_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _tracked_get_delivery_date),
                CallbackQueryHandler(skip_rfq_step, pattern="^rfq_skip$"),
            ],
            states.CONFIRM_QUOTE_REQUEST: [
                CallbackQueryHandler(confirm_quote_request, pattern="^rfq_confirm$"),
                CallbackQueryHandler(cancel_quote_request, pattern="^rfq_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_browse)],
        per_user=True,
        per_chat=True,
        name="browse_rfq_conversation",
        persistent=False,
    )
