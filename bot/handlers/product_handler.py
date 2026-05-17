"""
bot/handlers/product_handler.py
================================
Product management handler — Add, publish, and manage products.

FLOW:
  1. Supplier presses ➕ Add Product
  2. Bot loads categories from KAYISOFT API
  3. Supplier selects category → subcategory
  4. Supplier fills product details (free text)
  5. DeepSeek AI extracts structured data (name, price, description, attributes)
  6. Supplier uploads product images (up to 10)
  7. Supplier confirms → Bot executes full publish pipeline:
     a. Downloads images from Telegram
     b. Gets signed S3 URLs from KAYISOFT
     c. Uploads images to S3
     d. Creates product via KAYISOFT API
        → Auto-published on TopKap app + TopGate marketplace
     e. Posts PROFESSIONAL channel post with 2 inline buttons:
        ┌─────────────────────────────────────────────────────┐
        │  💬 Chat on TopGate  → product page + chat          │
        │  🛍️ Supplier Page    → supplier's TopGate profile   │
        └─────────────────────────────────────────────────────┘

CHANNEL POST FORMAT:
  ┌─────────────────────────────────────────────────────┐
  │  [Product Images — MediaGroup album if multiple]    │
  │                                                     │
  │  🏷️ <b>Product Name</b>                             │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  📝 Description text                                │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  💰 Price: XXX ₺                                    │
  │  📦 Min. Order: XX pcs                              │
  │  🏭 Supplier: Name                                  │
  │  🌍 Ships Worldwide                                 │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  [💬 Chat on TopGate]  [🛍️ Supplier Page]          │
  └─────────────────────────────────────────────────────┘
"""

import logging
import os
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.services.language_service import get_string, get_user_lang
from bot.services.kayisoft_api import KayisoftAPI
from bot.services.deepseek_service import deepseek_service

logger = logging.getLogger(__name__)

# ── Conversation States ────────────────────────────────────────────────────────
SELECT_CATEGORY    = 1
SELECT_SUBCATEGORY = 2
FILL_FORM          = 3
UPLOAD_IMAGES      = 4
CONFIRM            = 5


# ── TopGate URL Builders ───────────────────────────────────────────────────────
def _product_chat_url(product_id: str, supplier_id: str) -> str:
    """
    Returns the deep-link URL that opens the product page + chat
    inside the TopGate app/web.

    NOTE: Update this function when KAYISOFT provides the official URL format.
    Current format: {TOPGATE_WEB_URL}/product/{product_id}?supplier={supplier_id}&action=chat
    """
    base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    return f"{base}/product/{product_id}?supplier={supplier_id}&action=chat"


def _supplier_page_url(supplier_id: str) -> str:
    """
    Returns the URL for the supplier's public profile page on TopGate.

    NOTE: Update this function when KAYISOFT provides the official URL format.
    Current format: {TOPGATE_WEB_URL}/supplier/{supplier_id}
    """
    base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    return f"{base}/supplier/{supplier_id}"


# ── Channel Post Builder ───────────────────────────────────────────────────────
def _build_channel_post(
    lang: str,
    product_name: str,
    description: str,
    price: str,
    min_order: str,
    supplier_name: str,
    product_id: str,
    supplier_id: str,
) -> tuple:
    """
    Builds the professional channel post caption (HTML) and inline keyboard.

    Returns:
        (caption: str, reply_markup: InlineKeyboardMarkup)

    The post uses Telegram HTML parse_mode for bold/italic formatting.
    Two inline URL buttons are included:
      1. 💬 Chat on TopGate  → opens product page with chat in TopGate
      2. 🛍️ Supplier Page    → opens supplier's full profile on TopGate
    """
    sep = "━━━━━━━━━━━━━━━━━━━━━━━━"

    # Localized labels per language
    labels = {
        "tr": {
            "price":     "💰 Fiyat",
            "min_order": "📦 Min. Sipariş",
            "supplier":  "🏭 Tedarikçi",
            "ships":     "🌍 Dünya Geneli Kargo Mevcut",
            "btn_chat":  "💬 TopGate'de Sohbet Et",
            "btn_page":  "🛍️ Tedarikçi Sayfası",
        },
        "ar": {
            "price":     "💰 السعر",
            "min_order": "📦 الحد الأدنى للطلب",
            "supplier":  "🏭 المورد",
            "ships":     "🌍 شحن لجميع دول العالم",
            "btn_chat":  "💬 تواصل عبر TopGate",
            "btn_page":  "🛍️ صفحة المورد على TopGate",
        },
        "en": {
            "price":     "💰 Price",
            "min_order": "📦 Min. Order",
            "supplier":  "🏭 Supplier",
            "ships":     "🌍 Ships Worldwide",
            "btn_chat":  "💬 Chat on TopGate",
            "btn_page":  "🛍️ Supplier Page on TopGate",
        },
    }
    L = labels.get(lang, labels["en"])

    caption = (
        f"🏷️ <b>{product_name}</b>\n"
        f"{sep}\n"
        f"📝 {description}\n"
        f"{sep}\n"
        f"{L['price']}: <b>{price} ₺</b>\n"
        f"{L['min_order']}: {min_order}\n"
        f"{L['supplier']}: {supplier_name}\n"
        f"{L['ships']}\n"
        f"{sep}\n"
        f"<i>TopKap × TopGate</i>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                L["btn_chat"],
                url=_product_chat_url(product_id, supplier_id),
            ),
        ],
        [
            InlineKeyboardButton(
                L["btn_page"],
                url=_supplier_page_url(supplier_id),
            ),
        ],
    ])

    return caption, keyboard


# ── Channel Publisher ──────────────────────────────────────────────────────────
async def _publish_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: str,
    lang: str,
    image_file_ids: list,
    product_name: str,
    description: str,
    price: str,
    min_order: str,
    supplier_name: str,
    product_id: str,
    supplier_id: str,
) -> bool:
    """
    Publishes a professional product post to the supplier's Telegram channel.

    Publishing strategy:
    - Multiple images → MediaGroup album (caption on first image) + inline buttons as follow-up
    - Single image    → Photo with caption + inline buttons
    - No images       → Text message with caption + inline buttons

    Returns True on success, False on failure.
    """
    caption, keyboard = _build_channel_post(
        lang=lang,
        product_name=product_name,
        description=description,
        price=price,
        min_order=min_order,
        supplier_name=supplier_name,
        product_id=product_id,
        supplier_id=supplier_id,
    )

    try:
        if len(image_file_ids) > 1:
            # Build MediaGroup — Telegram supports max 10 items per album
            media_group = []
            for i, file_id in enumerate(image_file_ids[:10]):
                if i == 0:
                    media_group.append(
                        InputMediaPhoto(
                            media=file_id,
                            caption=caption,
                            parse_mode="HTML",
                        )
                    )
                else:
                    media_group.append(InputMediaPhoto(media=file_id))

            await context.bot.send_media_group(
                chat_id=channel_id,
                media=media_group,
            )
            # Send inline buttons as a separate follow-up message
            await context.bot.send_message(
                chat_id=channel_id,
                text="⬆️",
                reply_markup=keyboard,
            )

        elif len(image_file_ids) == 1:
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=image_file_ids[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        else:
            await context.bot.send_message(
                chat_id=channel_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        logger.info("✅ Product post published to channel %s (product_id=%s)", channel_id, product_id)
        return True

    except Exception as exc:
        logger.error("❌ Failed to publish to channel %s: %s", channel_id, exc)
        return False


# ── Conversation Handlers ──────────────────────────────────────────────────────

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for the product addition flow.
    Loads top-level categories from KAYISOFT API and presents them as inline buttons.
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    loading_msg = await update.message.reply_text(
        get_string(lang, "add_product_loading_categories"),
        parse_mode="HTML",
    )

    api        = KayisoftAPI(telegram_user_id=user_id, language=lang)
    categories = await api.get_categories()

    await loading_msg.delete()

    if not categories:
        await update.message.reply_text(
            get_string(lang, "add_product_categories_error"),
            parse_mode="HTML",
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(cat.get("name", "—"), callback_data=f"cat_{cat.get('id')}")]
        for cat in categories
    ]
    await update.message.reply_text(
        get_string(lang, "add_product_select_category"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return SELECT_CATEGORY


async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles category button press.
    Loads subcategories — if none exist, skips directly to form input.
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    cat_id  = query.data.split("_", 1)[1]
    context.user_data["selected_category"] = cat_id

    api           = KayisoftAPI(telegram_user_id=user_id, language=lang)
    subcategories = await api.get_categories(parent_id=cat_id)

    if not subcategories:
        # No subcategories — go directly to form
        context.user_data["selected_subcategory"] = cat_id
        await query.edit_message_text(
            get_string(lang, "add_product_fill_form"),
            parse_mode="HTML",
        )
        return FILL_FORM

    keyboard = [
        [InlineKeyboardButton(sub.get("name", "—"), callback_data=f"sub_{sub.get('id')}")]
        for sub in subcategories
    ]
    await query.edit_message_text(
        get_string(lang, "add_product_select_subcategory"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return SELECT_SUBCATEGORY


async def handle_subcategory_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles subcategory button press.
    Loads category attributes to guide AI extraction, then asks for product details.
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    sub_id  = query.data.split("_", 1)[1]
    context.user_data["selected_subcategory"] = sub_id

    api        = KayisoftAPI(telegram_user_id=user_id, language=lang)
    attributes = await api.get_attributes(category_id=sub_id)

    # Store expected attributes to guide DeepSeek extraction
    context.user_data["expected_attributes"] = (
        [attr.get("name") for attr in attributes]
        if attributes
        else ["Renk", "Beden", "Kumaş"]  # Sensible Turkish textile fallback
    )

    await query.edit_message_text(
        get_string(lang, "add_product_fill_form"),
        parse_mode="HTML",
    )
    return FILL_FORM


async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receives free-text product description from supplier.
    DeepSeek AI extracts: name, price, description, min_order, attributes.
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"
    text    = update.message.text

    expected_attrs = context.user_data.get("expected_attributes", [])

    processing_msg = await update.message.reply_text(
        get_string(lang, "add_product_ai_processing"),
        parse_mode="HTML",
    )

    extracted_data = await deepseek_service.analyze_product_text(text, expected_attrs)
    context.user_data["product_details"] = extracted_data or {"raw_text": text}

    await processing_msg.delete()
    await update.message.reply_text(
        get_string(lang, "add_product_upload_images"),
        parse_mode="HTML",
    )
    return UPLOAD_IMAGES


async def handle_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receives product images (up to 10).
    After each image, shows:
      - ✅ Publish Now
      - ➕ Add More Images (X uploaded so far)
      - ❌ Cancel
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    if "images" not in context.user_data:
        context.user_data["images"] = []

    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        context.user_data["images"].append(photo_file_id)

    image_count = len(context.user_data["images"])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            get_string(lang, "btn_confirm_publish"),
            callback_data="confirm_yes",
        )],
        [InlineKeyboardButton(
            get_string(lang, "btn_add_more_images").format(count=image_count),
            callback_data="add_more",
        )],
        [InlineKeyboardButton(
            get_string(lang, "btn_cancel"),
            callback_data="confirm_no",
        )],
    ])

    await update.message.reply_text(
        get_string(lang, "add_product_confirm").format(count=image_count),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return CONFIRM


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the final confirmation step.

    On 'add_more'   → returns to UPLOAD_IMAGES state
    On 'confirm_no' → cancels and clears user data
    On 'confirm_yes' → executes full publish pipeline:
        1. Download images from Telegram
        2. Get signed S3 URLs from KAYISOFT
        3. Upload images to S3
        4. Create product via KAYISOFT API (auto-publishes to TopKap + TopGate)
        5. Post professional channel post with TopGate buttons
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # ── Add more images ────────────────────────────────────────────────────────
    if query.data == "add_more":
        await query.edit_message_text(
            get_string(lang, "add_product_upload_more"),
            parse_mode="HTML",
        )
        return UPLOAD_IMAGES

    # ── Cancel ─────────────────────────────────────────────────────────────────
    if query.data == "confirm_no":
        await query.edit_message_text(
            get_string(lang, "add_product_cancelled"),
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ── CONFIRM YES — Full Publish Pipeline ───────────────────────────────────
    await query.edit_message_text(
        get_string(lang, "add_product_publishing"),
        parse_mode="HTML",
    )

    product_details = context.user_data.get("product_details", {})
    image_file_ids  = context.user_data.get("images", [])
    category_id     = (
        context.user_data.get("selected_subcategory")
        or context.user_data.get("selected_category", "")
    )

    api = KayisoftAPI(telegram_user_id=user_id, language=lang)

    # ── Step 1: Download images from Telegram ─────────────────────────────────
    image_bytes_list = []
    for file_id in image_file_ids:
        try:
            tg_file    = await query.get_bot().get_file(file_id)
            file_bytes = await tg_file.download_as_bytearray()
            image_bytes_list.append(bytes(file_bytes))
        except Exception as exc:
            logger.warning("Could not download image %s: %s", file_id, exc)

    # ── Step 2 & 3: Get signed S3 URLs → Upload images ────────────────────────
    uploaded_file_names = []
    if image_bytes_list:
        file_names  = [api.generate_filename(img) for img in image_bytes_list]
        signed_urls = await api.get_signed_urls(
            file_names=file_names,
            category_id=category_id,
        )
        if signed_urls:
            for i, signed in enumerate(signed_urls):
                if i < len(image_bytes_list):
                    success = await api.upload_media_to_s3(
                        signed_url=signed.get("url", ""),
                        file_bytes=image_bytes_list[i],
                    )
                    if success:
                        uploaded_file_names.append(signed.get("fileName", ""))

    # ── Step 4: Build product payload & create via KAYISOFT API ───────────────
    product_name  = product_details.get("name", product_details.get("raw_text", "")[:50])
    description   = product_details.get("description", "")
    price         = str(product_details.get("price", "0"))
    min_order     = str(product_details.get("min_order", "1"))
    supplier_name = product_details.get("supplier_name", "TopKap Supplier")

    product_payload = {
        "name":        product_name,
        "product_no":  f"TK-{user_id[-6:]}",
        "category_id": category_id,
        "shared_attributes": product_details.get("attributes", {}),
        "variants": [
            {
                "stock_id":            f"VAR-{user_id[-4:]}",
                "stock_count":         int(product_details.get("stock", 100)),
                "visibility_status":   "public",
                "titles":              [{"language": lang, "value": product_name}],
                "descriptions":        [{"language": lang, "value": description}],
                "prices":              [{"currency": "TRY", "amount": float(price)}],
                "images":              [{"fileName": fn} for fn in uploaded_file_names],
                "videos":              [],
                "selector_attributes": [],
                "dimensions":          {},
            }
        ],
    }

    created_product = await api.create_product(product_payload)

    if not created_product:
        await query.edit_message_text(
            get_string(lang, "add_product_api_error"),
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Extract IDs returned by KAYISOFT API
    product_id  = str(created_product.get("id", "0"))
    supplier_id = str(created_product.get("seller_id", user_id))

    # ── Step 5: Publish professional post to Telegram Channel ─────────────────
    # Channel ID is stored when supplier connects their channel via channel_handler
    channel_id = context.user_data.get("channel_id")

    channel_published = False
    if channel_id:
        channel_published = await _publish_to_channel(
            context=context,
            channel_id=channel_id,
            lang=lang,
            image_file_ids=image_file_ids,
            product_name=product_name,
            description=description,
            price=price,
            min_order=min_order,
            supplier_name=supplier_name,
            product_id=product_id,
            supplier_id=supplier_id,
        )

    # ── Success message ────────────────────────────────────────────────────────
    success_text = get_string(lang, "add_product_success")
    if channel_published:
        success_text += "\n\n" + get_string(lang, "add_product_channel_published")
    else:
        success_text += "\n\n" + get_string(lang, "add_product_no_channel")

    await query.edit_message_text(success_text, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


# ── ConversationHandler Factory ────────────────────────────────────────────────

def get_product_conv_handler() -> ConversationHandler:
    """
    Factory function — returns the fully configured ConversationHandler.
    Registered in bot/main.py via application.add_handler().
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^(➕ Ürün Ekle|➕ Add Product|➕ إضافة منتج)$"),
                start_add_product,
            ),
            CommandHandler("add_product", start_add_product),
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern=r"^cat_"),
            ],
            SELECT_SUBCATEGORY: [
                CallbackQueryHandler(handle_subcategory_selection, pattern=r"^sub_"),
            ],
            FILL_FORM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_form_input),
            ],
            UPLOAD_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_upload),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    handle_confirmation,
                    pattern=r"^(confirm_yes|confirm_no|add_more)$",
                ),
                MessageHandler(filters.PHOTO, handle_image_upload),  # Allow more images
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                lambda u, c: (
                    u.message.reply_text("❌ İptal / Cancelled / تم الإلغاء"),
                    ConversationHandler.END,
                )[1],
            )
        ],
        allow_reentry=True,
    )
