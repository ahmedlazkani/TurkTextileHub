"""
bot/handlers/product_handler.py — TopKap Bot v5.0
==================================================
Product Management Handler — Add, Publish, and Manage Products

FLOW (6 steps):
  1. Supplier presses ➕ Add Product
     → Bot loads root categories from KAYISOFT API
  2. Supplier selects root category
     → Bot loads subcategories
  3. Supplier selects subcategory (leaf category)
     → Bot loads category attributes from KAYISOFT API
     → DeepSeek AI will use these to guide extraction
  4. Supplier sends free-text product description
     → DeepSeek AI extracts: name, price, description, min_order, attributes
     → Bot shows a confirmation summary of extracted data
  5. Supplier uploads product images (up to 10)
     → After each image: [✅ Publish Now] [📸 Add More] [❌ Cancel]
  6. Supplier confirms → Full publish pipeline:
     a. Download images from Telegram
     b. Generate filenames (timestamp + SHA-256)
     c. Get signed S3 URLs from KAYISOFT API
     d. Upload images to S3
     e. Build product payload (with variants)
     f. POST to KAYISOFT API → auto-published on TopKap + TopGate
     g. Post PROFESSIONAL channel post with 2 inline buttons:
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

PRODUCT PAYLOAD STRUCTURE (KAYISOFT API):
  {
    "name":        str,
    "product_no":  str,
    "category_id": str (leaf category UUID),
    "shared_attributes": {attr_id: value, ...},
    "variants": [
      {
        "stock_id":            str,
        "stock_count":         int,
        "visibility_status":   "public",
        "titles":              [{"language": "tr", "value": "..."}],
        "descriptions":        [{"language": "tr", "value": "..."}],
        "prices":              [{"currency": "TRY", "amount": float}],
        "images":              [{"fileName": "..."}],
        "videos":              [],
        "selector_attributes": [],
        "dimensions":          {}
      }
    ]
  }
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
from telegram.constants import ParseMode
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
SELECT_CATEGORY    = 1   # Waiting for root category selection
SELECT_SUBCATEGORY = 2   # Waiting for subcategory selection
FILL_FORM          = 3   # Waiting for free-text product description
UPLOAD_IMAGES      = 4   # Waiting for image uploads
CONFIRM            = 5   # Waiting for publish confirmation


# ── TopGate URL Builders ───────────────────────────────────────────────────────

def _product_chat_url(product_id: str, supplier_id: str) -> str:
    """
    Returns the deep-link URL that opens the product page + chat
    inside the TopGate app/web.

    NOTE: Update when KAYISOFT provides the official URL format.
    Current format: {TOPGATE_WEB_URL}/product/{product_id}?supplier={supplier_id}&action=chat
    """
    base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    return f"{base}/product/{product_id}?supplier={supplier_id}&action=chat"


def _supplier_page_url(supplier_id: str) -> str:
    """
    Returns the URL for the supplier's public profile page on TopGate.

    NOTE: Update when KAYISOFT provides the official URL format.
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
                            parse_mode=ParseMode.HTML,
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
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

        else:
            await context.bot.send_message(
                chat_id=channel_id,
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

        logger.info(
            "✅ Product post published to channel %s (product_id=%s)",
            channel_id,
            product_id,
        )
        return True

    except Exception as exc:
        logger.error("❌ Failed to publish to channel %s: %s", channel_id, exc)
        return False


# ── AI Extraction Summary ──────────────────────────────────────────────────────

def _build_extraction_summary(lang: str, data: dict) -> str:
    """
    Builds a human-readable summary of the AI-extracted product data.
    Shown to the supplier before they upload images, so they can verify
    the AI understood their description correctly.
    """
    name        = data.get("name", "—")
    description = data.get("description", "—")
    price       = data.get("price", "—")
    min_order   = data.get("min_order", "—")

    summaries = {
        "tr": (
            f"🤖 <b>Yapay Zeka Özeti</b>\n\n"
            f"🏷️ <b>Ürün Adı:</b> {name}\n"
            f"📝 <b>Açıklama:</b> {description}\n"
            f"💰 <b>Fiyat:</b> {price} ₺\n"
            f"📦 <b>Min. Sipariş:</b> {min_order}\n\n"
            f"✅ <i>Bilgiler doğru görünüyorsa fotoğrafları gönderin.</i>"
        ),
        "ar": (
            f"🤖 <b>ملخص الذكاء الاصطناعي</b>\n\n"
            f"🏷️ <b>اسم المنتج:</b> {name}\n"
            f"📝 <b>الوصف:</b> {description}\n"
            f"💰 <b>السعر:</b> {price} ₺\n"
            f"📦 <b>الحد الأدنى للطلب:</b> {min_order}\n\n"
            f"✅ <i>إذا كانت البيانات صحيحة، أرسل الصور الآن.</i>"
        ),
        "en": (
            f"🤖 <b>AI Summary</b>\n\n"
            f"🏷️ <b>Product Name:</b> {name}\n"
            f"📝 <b>Description:</b> {description}\n"
            f"💰 <b>Price:</b> {price} ₺\n"
            f"📦 <b>Min. Order:</b> {min_order}\n\n"
            f"✅ <i>If the details look correct, send your product images.</i>"
        ),
    }
    return summaries.get(lang, summaries["en"])


# ── Conversation Handlers ──────────────────────────────────────────────────────

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    STATE: Entry point (before SELECT_CATEGORY)

    Entry point for the product addition flow.
    Loads top-level categories from KAYISOFT API and presents them as inline buttons.

    On success → returns SELECT_CATEGORY state
    On API failure → shows error message and ends conversation
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # Show loading indicator while fetching categories
    loading_msg = await update.message.reply_text(
        get_string(lang, "add_product_loading_categories"),
        parse_mode=ParseMode.HTML,
    )

    api        = KayisoftAPI(telegram_user_id=user_id, language=lang)
    categories = await api.get_categories()  # parent="" → root categories

    await loading_msg.delete()

    if not categories:
        await update.message.reply_text(
            get_string(lang, "add_product_categories_error"),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Build inline keyboard — one button per category
    keyboard = [
        [InlineKeyboardButton(
            cat.get("name", "—"),
            callback_data=f"cat_{cat.get('id')}",
        )]
        for cat in categories
        if cat.get("is_visible_for_creating", True)  # Respect API visibility flag
    ]

    await update.message.reply_text(
        get_string(lang, "add_product_select_category"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_CATEGORY


async def handle_category_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: SELECT_CATEGORY → SELECT_SUBCATEGORY or FILL_FORM

    Handles root category button press.
    Loads subcategories from KAYISOFT API.
    - If subcategories exist → shows subcategory keyboard → SELECT_SUBCATEGORY
    - If no subcategories → treats this as leaf category → loads attributes → FILL_FORM
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    cat_id  = query.data.split("_", 1)[1]

    # Store selected category
    context.user_data["selected_category"] = cat_id

    api           = KayisoftAPI(telegram_user_id=user_id, language=lang)
    subcategories = await api.get_categories(parent_id=cat_id)

    if not subcategories:
        # This category has no children → it IS the leaf category
        # Load attributes to guide AI extraction
        context.user_data["selected_subcategory"] = cat_id
        attributes = await api.get_attributes(category_id=cat_id)
        context.user_data["expected_attributes"] = (
            [attr.get("name") for attr in attributes if attr.get("name")]
            if attributes
            else ["Renk", "Beden", "Kumaş"]  # Sensible Turkish textile fallback
        )
        context.user_data["raw_attributes"] = attributes or []

        await query.edit_message_text(
            get_string(lang, "add_product_fill_form"),
            parse_mode=ParseMode.HTML,
        )
        return FILL_FORM

    # Build subcategory keyboard — one button per subcategory
    keyboard = [
        [InlineKeyboardButton(
            sub.get("name", "—"),
            callback_data=f"sub_{sub.get('id')}",
        )]
        for sub in subcategories
        if sub.get("is_visible_for_creating", True)
    ]

    await query.edit_message_text(
        get_string(lang, "add_product_select_subcategory"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_SUBCATEGORY


async def handle_subcategory_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: SELECT_SUBCATEGORY → FILL_FORM

    Handles subcategory (leaf category) button press.
    Loads category attributes from KAYISOFT API to guide AI extraction.
    Then asks the supplier to describe their product in free text.
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    sub_id  = query.data.split("_", 1)[1]

    # Store selected leaf category
    context.user_data["selected_subcategory"] = sub_id

    api        = KayisoftAPI(telegram_user_id=user_id, language=lang)
    attributes = await api.get_attributes(category_id=sub_id)

    # Store expected attribute names to guide DeepSeek extraction
    context.user_data["expected_attributes"] = (
        [attr.get("name") for attr in attributes if attr.get("name")]
        if attributes
        else ["Renk", "Beden", "Kumaş"]
    )
    context.user_data["raw_attributes"] = attributes or []

    await query.edit_message_text(
        get_string(lang, "add_product_fill_form"),
        parse_mode=ParseMode.HTML,
    )
    return FILL_FORM


async def handle_form_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: FILL_FORM → UPLOAD_IMAGES

    Receives free-text product description from supplier.
    DeepSeek AI extracts structured data:
      - name, price, description, min_order, stock
      - attributes (color, size, fabric, etc.)

    Shows AI extraction summary to the supplier, then asks for images.
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"
    text    = update.message.text

    expected_attrs = context.user_data.get("expected_attributes", [])

    # Show AI processing indicator
    processing_msg = await update.message.reply_text(
        get_string(lang, "add_product_ai_processing"),
        parse_mode=ParseMode.HTML,
    )

    # DeepSeek AI extraction
    extracted_data = await deepseek_service.analyze_product_text(
        text=text,
        expected_attributes=expected_attrs,
    )

    # Fallback: store raw text if AI fails
    if not extracted_data:
        extracted_data = {
            "name":        text[:80],
            "description": text,
            "price":       "0",
            "min_order":   "1",
            "stock":       100,
            "attributes":  {},
        }
        logger.warning("DeepSeek extraction failed for user %s — using raw text fallback", user_id)

    context.user_data["product_details"] = extracted_data

    await processing_msg.delete()

    # Show AI extraction summary
    summary = _build_extraction_summary(lang, extracted_data)
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

    # Ask for images
    await update.message.reply_text(
        get_string(lang, "add_product_upload_images"),
        parse_mode=ParseMode.HTML,
    )
    return UPLOAD_IMAGES


async def handle_image_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: UPLOAD_IMAGES → CONFIRM (or stays in UPLOAD_IMAGES)

    Receives product images (up to 10).
    After each image, shows 3 action buttons:
      - ✅ Publish Now
      - 📸 Add More Images (X uploaded so far)
      - ❌ Cancel
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # Initialize image list on first upload
    if "images" not in context.user_data:
        context.user_data["images"] = []

    # Accept the highest-resolution version of the photo
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        context.user_data["images"].append(photo_file_id)

    image_count = len(context.user_data["images"])

    # Build action keyboard
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
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM


async def handle_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: CONFIRM → END (or back to UPLOAD_IMAGES)

    Handles the final confirmation step.

    Callbacks:
      - "add_more"     → returns to UPLOAD_IMAGES state
      - "confirm_no"   → cancels and clears user data → END
      - "confirm_yes"  → executes full publish pipeline → END

    PUBLISH PIPELINE (confirm_yes):
      1. Download images from Telegram
      2. Generate filenames (timestamp + SHA-256)
      3. Get signed S3 URLs from KAYISOFT API
      4. Upload images to S3
      5. Build product payload (with variants)
      6. POST to KAYISOFT API → auto-published on TopKap + TopGate
      7. Post professional channel post with TopGate buttons
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # ── Add more images ────────────────────────────────────────────────────────
    if query.data == "add_more":
        await query.edit_message_text(
            get_string(lang, "add_product_upload_more"),
            parse_mode=ParseMode.HTML,
        )
        return UPLOAD_IMAGES

    # ── Cancel ─────────────────────────────────────────────────────────────────
    if query.data == "confirm_no":
        await query.edit_message_text(
            get_string(lang, "add_product_cancelled"),
            parse_mode=ParseMode.HTML,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ── CONFIRM YES — Full Publish Pipeline ───────────────────────────────────
    await query.edit_message_text(
        get_string(lang, "add_product_publishing"),
        parse_mode=ParseMode.HTML,
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
            logger.debug("Downloaded image %s (%d bytes)", file_id[:8], len(file_bytes))
        except Exception as exc:
            logger.warning("Could not download image %s: %s", file_id[:8], exc)

    # ── Step 2 & 3: Generate filenames → Get signed S3 URLs ──────────────────
    uploaded_file_names = []
    if image_bytes_list:
        # Generate unique filenames: <ISO-8601 timestamp>-<SHA-256 hash>
        file_names = [api.generate_filename(img) for img in image_bytes_list]

        signed_urls = await api.get_signed_urls(
            file_names=file_names,
            category_id=category_id,
        )

        # ── Step 4: Upload images to S3 ───────────────────────────────────────
        if signed_urls:
            for i, signed in enumerate(signed_urls):
                if i < len(image_bytes_list):
                    success = await api.upload_media_to_s3(
                        signed_url=signed.get("url", ""),
                        file_bytes=image_bytes_list[i],
                    )
                    if success:
                        uploaded_file_names.append(signed.get("fileName", ""))
                        logger.debug("Uploaded image %d/%d to S3", i + 1, len(image_bytes_list))
                    else:
                        logger.warning("S3 upload failed for image %d/%d", i + 1, len(image_bytes_list))
        else:
            logger.warning("Could not get signed URLs for user %s", user_id)

    # ── Step 5: Build product payload ─────────────────────────────────────────
    product_name  = product_details.get("name", product_details.get("raw_text", "")[:80])
    description   = product_details.get("description", "")
    price_raw     = product_details.get("price", "0")
    min_order     = str(product_details.get("min_order", "1"))
    supplier_name = product_details.get("supplier_name", "TopKap Supplier")
    stock_count   = int(product_details.get("stock", 100))

    # Parse price safely
    try:
        price_float = float(str(price_raw).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        price_float = 0.0
    price_str = str(price_raw)

    # Build shared_attributes from AI-extracted attributes
    # Format: {attribute_id: value} — IDs come from raw_attributes list
    raw_attributes  = context.user_data.get("raw_attributes", [])
    ai_attributes   = product_details.get("attributes", {})
    shared_attrs    = {}

    for attr in raw_attributes:
        attr_id   = attr.get("id")
        attr_name = attr.get("name", "")
        if attr_id and attr_name in ai_attributes:
            shared_attrs[attr_id] = ai_attributes[attr_name]

    # Build multilingual titles and descriptions
    # Include all 3 languages if AI provided them, otherwise use the supplier's language
    titles = [{"language": lang, "value": product_name}]
    descriptions = [{"language": lang, "value": description}]

    # Add English if available
    if "name_en" in product_details:
        titles.append({"language": "en", "value": product_details["name_en"]})
    if "description_en" in product_details:
        descriptions.append({"language": "en", "value": product_details["description_en"]})

    product_payload = {
        "name":              product_name,
        "product_no":        f"TK-{user_id[-6:]}",
        "category_id":       category_id,
        "shared_attributes": shared_attrs,
        "variants": [
            {
                "stock_id":            f"VAR-{user_id[-4:]}",
                "stock_count":         stock_count,
                "visibility_status":   "public",
                "titles":              titles,
                "descriptions":        descriptions,
                "prices":              [{"currency": "TRY", "amount": price_float}],
                "images":              [{"fileName": fn} for fn in uploaded_file_names],
                "videos":              [],
                "selector_attributes": [],
                "dimensions":          {},
            }
        ],
    }

    # ── Step 6: Create product via KAYISOFT API ────────────────────────────────
    created_product = await api.create_product(product_payload)

    if not created_product:
        await query.edit_message_text(
            get_string(lang, "add_product_api_error"),
            parse_mode=ParseMode.HTML,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Extract IDs returned by KAYISOFT API
    product_id  = str(created_product.get("id", "0"))
    supplier_id = str(created_product.get("seller_id", user_id))

    logger.info(
        "✅ Product created: id=%s, seller=%s, category=%s",
        product_id,
        supplier_id,
        category_id,
    )

    # ── Step 7: Publish professional post to Telegram Channel ─────────────────
    # Channel ID is stored in user_data when supplier connects their channel
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
            price=price_str,
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

    await query.edit_message_text(success_text, parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END


# ── ConversationHandler Factory ────────────────────────────────────────────────

def get_product_conv_handler() -> ConversationHandler:
    """
    Factory function — returns the fully configured ConversationHandler.

    Registered in bot/main.py via:
        application.add_handler(get_product_conv_handler())

    Entry points:
      - ReplyKeyboard button press (all 3 languages)
      - /add_product command

    States:
      SELECT_CATEGORY    → category inline button
      SELECT_SUBCATEGORY → subcategory inline button
      FILL_FORM          → free text message
      UPLOAD_IMAGES      → photo message
      CONFIRM            → inline button (confirm_yes / confirm_no / add_more)

    Fallback:
      /cancel command → cancels and ends conversation
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(
                    r"^(➕ Ürün Ekle|➕ Add Product|➕ إضافة منتج)$"
                ),
                start_add_product,
            ),
            CommandHandler("add_product", start_add_product),
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(
                    handle_category_selection,
                    pattern=r"^cat_",
                ),
            ],
            SELECT_SUBCATEGORY: [
                CallbackQueryHandler(
                    handle_subcategory_selection,
                    pattern=r"^sub_",
                ),
            ],
            FILL_FORM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_form_input,
                ),
            ],
            UPLOAD_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_upload),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    handle_confirmation,
                    pattern=r"^(confirm_yes|confirm_no|add_more)$",
                ),
                # Allow more images even in CONFIRM state
                MessageHandler(filters.PHOTO, handle_image_upload),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                lambda u, c: (
                    u.message.reply_text(
                        "❌ İptal edildi / Cancelled / تم الإلغاء"
                    ),
                    ConversationHandler.END,
                )[1],
            )
        ],
        allow_reentry=True,
        name="add_product_conversation",
        persistent=False,
    )
