"""
bot/handlers/product_handler.py — TopKap Bot v6.0
==================================================
Product Management Handler — Add & Publish Products

PROFESSIONAL FLOW (9 steps — matches KAYISOFT API spec exactly):
═══════════════════════════════════════════════════════════════════

  STEP 1 ─ Entry Point
    Supplier presses ➕ Add Product button
    → Bot shows progress bar (Step 1/5)
    → Loads root categories from KAYISOFT API
    → Displays as inline buttons

  STEP 2 ─ Root Category Selection
    Supplier selects root category (e.g. "Giyim / ملابس")
    → Bot loads subcategories from KAYISOFT API
    → Displays as inline buttons
    → Shows progress bar (Step 2/5)

  STEP 3 ─ Subcategory (Leaf) Selection
    Supplier selects leaf category (e.g. "Abaya / عباءات")
    → Bot loads category attributes from KAYISOFT API
    → Separates: required attributes vs optional attributes
    → Separates: selector_attributes (is_variant_selector=True) vs shared_attributes
    → Shows progress bar (Step 3/5)
    → Presents FORM with attribute fields one by one

  STEP 4 ─ Attribute Form (AI-Assisted)
    Supplier sends free-text product description
    → DeepSeek AI extracts:
        • name (product title)
        • description
        • price (TRY amount)
        • min_quantity (minimum order)
        • stock_count
        • shared_attributes: {attr_id: [option_id]} — non-variant attributes
        • selector_attributes: [{attribute_id, option_id}] — variant-defining attributes
    → Bot validates: are all REQUIRED attributes filled?
    → If incomplete → shows missing fields and asks supplier to complete
    → If complete → shows AI extraction summary for verification
    → Shows progress bar (Step 4/5)

  STEP 5 ─ Image Upload
    Supplier uploads product images (1 to max_images per category)
    → Bot shows image count after each upload
    → After first image: shows action buttons
        [✅ Publish Now]  [📸 Add More (X uploaded)]  [❌ Cancel]
    → Shows progress bar (Step 5/5)

  STEP 6 ─ Variants Preview & Confirmation
    Bot builds variants automatically from selector_attributes
    → Shows variant preview table to supplier
    → Supplier confirms or cancels

  STEP 7 ─ Publish Pipeline (automated, no user interaction)
    a. Download images from Telegram
    b. Generate filenames: <ISO-8601>-<SHA-256>
    c. POST api/extensions/signed-urls → get S3 upload URLs
    d. PUT images to S3
    e. Build product payload (with variants, prices, attributes)
    f. POST api/seller/products → product created on TopKap + TopGate
    g. Post professional channel post to supplier's Telegram channel

CHANNEL POST FORMAT:
  ┌─────────────────────────────────────────────────────┐
  │  [Product Images — MediaGroup album if multiple]    │
  │                                                     │
  │  🏷️ <b>Product Name</b>                             │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  📝 Description text                                │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  💰 Price: XXX ₺  |  📦 Min. Order: XX pcs          │
  │  🏭 Supplier: Name                                  │
  │  🌍 Ships Worldwide                                 │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │  [💬 Chat on TopGate]  [🛍️ Supplier Page]          │
  └─────────────────────────────────────────────────────┘

PRODUCT PAYLOAD (matches KAYISOFT API spec exactly):
  {
    "name":        str,
    "product_no":  str,           # auto-generated TK-XXXXXX
    "category_id": str,           # leaf category UUID
    "shared_attributes": {
      "attr_id": ["option_id"]    # non-variant attributes
    },
    "variants": [{
      "stock_id":            str,
      "stock_count":         int,
      "status":              "review",
      "visibility_status":   "public",
      "tax_percentage":      null,
      "cost_price":          null,
      "titles":              [{"language": "tr", "text": "..."}],
      "descriptions":        [{"language": "tr", "text": "..."}],
      "selector_attributes": [{"attribute_id": "uuid", "option_id": "uuid"}],
      "prices":              [{"min_quantity": 1, "price": 1299.99}],
      "images":              ["filename1", "filename2"],
      "videos":              [],
      "currency":            "TRY",
      "dimensions":          null
    }]
  }

KEY FIXES vs v5.0:
  ✅ images field: now list of strings (filenames), not list of dicts
  ✅ prices field: now [{min_quantity, price}], not [{currency, amount}]
  ✅ titles/descriptions: now {"language", "text"} not {"language", "value"}
  ✅ shared_attributes: now {attr_id: [option_id]} not {attr_id: value}
  ✅ selector_attributes: now [{attribute_id, option_id}] not []
  ✅ status field: added "review" (required by API)
  ✅ currency field: moved to variant level, not inside prices
  ✅ Attribute validation: required attributes checked before proceeding
  ✅ Variants: auto-built from selector_attributes (primary variant attribute)
  ✅ Progress bar: shown at each step for better UX
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.constants import ChatAction, ParseMode
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

# ══════════════════════════════════════════════════════════════════════════════
# Conversation States
# Each state represents one step in the product addition flow
# ══════════════════════════════════════════════════════════════════════════════
SELECT_CATEGORY    = 1   # Waiting for root category selection
SELECT_SUBCATEGORY = 2   # Waiting for subcategory selection
FILL_FORM          = 3   # Waiting for free-text product description (AI-assisted)
FIX_MISSING        = 4   # Waiting for supplier to fill missing required attributes
UPLOAD_IMAGES      = 5   # Waiting for image uploads
CONFIRM_VARIANTS   = 6   # Waiting for variant preview confirmation
CONFIRM_PUBLISH    = 7   # Waiting for final publish confirmation


# ══════════════════════════════════════════════════════════════════════════════
# Progress Bar Helper
# Shows the supplier where they are in the 5-step flow
# ══════════════════════════════════════════════════════════════════════════════

def _progress_bar(current: int, total: int = 5) -> str:
    """
    Generates a visual progress bar string.

    Example: _progress_bar(2, 5) → "▓▓░░░  2/5"

    Args:
        current: Current step number (1-based)
        total:   Total number of steps

    Returns:
        str: Progress bar with step counter
    """
    filled = "▓" * current
    empty  = "░" * (total - current)
    return f"{filled}{empty}  {current}/{total}"


# ══════════════════════════════════════════════════════════════════════════════
# TopGate URL Builders
# NOTE: Update base URL when KAYISOFT provides official deep-link format
# ══════════════════════════════════════════════════════════════════════════════

def _product_chat_url(product_id: str, supplier_id: str) -> str:
    """
    Returns the deep-link URL that opens the product page + chat
    inside the TopGate app/web.

    Format: {TOPGATE_WEB_URL}/product/{product_id}?supplier={supplier_id}&action=chat
    """
    base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    return f"{base}/product/{product_id}?supplier={supplier_id}&action=chat"


def _supplier_page_url(supplier_id: str) -> str:
    """
    Returns the URL for the supplier's public profile page on TopGate.

    Format: {TOPGATE_WEB_URL}/supplier/{supplier_id}
    """
    base = os.getenv("TOPGATE_WEB_URL", "https://topgate.app")
    return f"{base}/supplier/{supplier_id}"


# ══════════════════════════════════════════════════════════════════════════════
# Filename Generator
# KAYISOFT API requires: <ISO-8601 timestamp>-<SHA-256 hash>
# Example: 2026-05-09T12:19:58.587Z-136a82a872029fda805f78fa313f8d0c38635887...
# ══════════════════════════════════════════════════════════════════════════════

def _generate_filename(image_bytes: bytes) -> str:
    """
    Generates a unique filename for an image using ISO-8601 timestamp + SHA-256.

    This is the exact format required by KAYISOFT's signed-URL API.

    Args:
        image_bytes: Raw bytes of the image file

    Returns:
        str: Filename in format "<timestamp>-<sha256hash>"
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    sha256    = hashlib.sha256(image_bytes).hexdigest()
    return f"{timestamp}-{sha256}"


# ══════════════════════════════════════════════════════════════════════════════
# Attribute Processor
# Separates API attributes into shared vs selector, required vs optional
# ══════════════════════════════════════════════════════════════════════════════

def _process_attributes(raw_attributes: list) -> dict:
    """
    Processes the raw attribute list from KAYISOFT API into structured groups.

    KAYISOFT attribute types:
      - shared_attributes:   is_variant_selector=False → apply to whole product
      - selector_attributes: is_variant_selector=True  → define product variants

    Each group is further split into required and optional.

    Args:
        raw_attributes: List of attribute dicts from GET /categories/{id}/attributes

    Returns:
        dict with keys:
            "shared_required":   list of required non-variant attributes
            "shared_optional":   list of optional non-variant attributes
            "selector_required": list of required variant-defining attributes
            "selector_optional": list of optional variant-defining attributes
            "all_by_id":         dict mapping attr_id → attr dict (for fast lookup)
    """
    shared_required   = []
    shared_optional   = []
    selector_required = []
    selector_optional = []
    all_by_id         = {}

    for attr in raw_attributes:
        attr_id = attr.get("id")
        if not attr_id:
            continue

        all_by_id[attr_id] = attr
        is_selector = attr.get("is_variant_selector", False)
        is_required = attr.get("required", False)

        if is_selector:
            if is_required:
                selector_required.append(attr)
            else:
                selector_optional.append(attr)
        else:
            if is_required:
                shared_required.append(attr)
            else:
                shared_optional.append(attr)

    return {
        "shared_required":   shared_required,
        "shared_optional":   shared_optional,
        "selector_required": selector_required,
        "selector_optional": selector_optional,
        "all_by_id":         all_by_id,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Variant Builder
# Auto-builds variants from the primary variant selector attribute
# ══════════════════════════════════════════════════════════════════════════════

def _build_variants(
    product_name: str,
    description: str,
    price_float: float,
    stock_count: int,
    min_quantity: int,
    lang: str,
    uploaded_file_names: list,
    ai_selector_attrs: list,
    raw_attributes: list,
) -> list:
    """
    Builds the variants list for the KAYISOFT product payload.

    Strategy:
    - If AI extracted selector_attributes → create one variant per combination
    - If no selector_attributes → create a single default variant

    Each variant gets:
      - stock_id: auto-generated unique ID
      - All images distributed to first variant (or split if multiple variants)
      - Prices with min_quantity
      - Titles and descriptions in supplier's language (backend translates)

    Args:
        product_name:         Product title from AI extraction
        description:          Product description from AI extraction
        price_float:          Price as float (TRY)
        stock_count:          Available stock count
        min_quantity:         Minimum order quantity
        lang:                 Supplier's language code (tr/ar/en)
        uploaded_file_names:  List of S3 filenames for images
        ai_selector_attrs:    List of {attribute_id, option_id} from AI extraction
        raw_attributes:       Full attribute list from API (for validation)

    Returns:
        list: List of variant dicts matching KAYISOFT API spec
    """
    # If no selector attributes → single variant
    if not ai_selector_attrs:
        return [{
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "status":              "review",
            "visibility_status":   "public",
            "tax_percentage":      None,
            "cost_price":          None,
            "titles":              [{"language": lang, "text": product_name}],
            "descriptions":        [{"language": lang, "text": description}],
            "selector_attributes": [],
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              uploaded_file_names,
            "videos":              [],
            "currency":            "TRY",
            "dimensions":          None,
        }]

    # Group selector attributes by attribute_id to find the primary variant axis
    # Primary variant attribute: is_primary_variant_attribute=True
    primary_attr_id = None
    for attr in raw_attributes:
        if attr.get("is_primary_variant_attribute") and attr.get("is_variant_selector"):
            primary_attr_id = attr.get("id")
            break

    # If no primary found, use the first selector attribute
    if not primary_attr_id and ai_selector_attrs:
        primary_attr_id = ai_selector_attrs[0].get("attribute_id")

    # Build one variant per option of the primary attribute
    primary_options = [
        sa for sa in ai_selector_attrs
        if sa.get("attribute_id") == primary_attr_id
    ]

    # Non-primary selector attributes (shared across all variants)
    other_selectors = [
        sa for sa in ai_selector_attrs
        if sa.get("attribute_id") != primary_attr_id
    ]

    if not primary_options:
        # Fallback: single variant with all selector attributes
        return [{
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "status":              "review",
            "visibility_status":   "public",
            "tax_percentage":      None,
            "cost_price":          None,
            "titles":              [{"language": lang, "text": product_name}],
            "descriptions":        [{"language": lang, "text": description}],
            "selector_attributes": ai_selector_attrs,
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              uploaded_file_names,
            "videos":              [],
            "currency":            "TRY",
            "dimensions":          None,
        }]

    # Distribute images across variants (first variant gets all if only one)
    images_per_variant = []
    if len(primary_options) == 1:
        images_per_variant = [uploaded_file_names]
    else:
        # Distribute images evenly; first variant gets any remainder
        chunk = max(1, len(uploaded_file_names) // len(primary_options))
        for i, _ in enumerate(primary_options):
            start = i * chunk
            end   = start + chunk if i < len(primary_options) - 1 else len(uploaded_file_names)
            images_per_variant.append(uploaded_file_names[start:end])

    variants = []
    for i, primary_opt in enumerate(primary_options):
        variant_selectors = [primary_opt] + other_selectors
        variant_images    = images_per_variant[i] if i < len(images_per_variant) else []

        variants.append({
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "status":              "review",
            "visibility_status":   "public",
            "tax_percentage":      None,
            "cost_price":          None,
            "titles":              [{"language": lang, "text": product_name}],
            "descriptions":        [{"language": lang, "text": description}],
            "selector_attributes": variant_selectors,
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              variant_images,
            "videos":              [],
            "currency":            "TRY",
            "dimensions":          None,
        })

    return variants


# ══════════════════════════════════════════════════════════════════════════════
# Variant Preview Builder
# Shows supplier a human-readable summary of the variants before publishing
# ══════════════════════════════════════════════════════════════════════════════

def _build_variants_preview(lang: str, variants: list, attr_map: dict) -> str:
    """
    Builds a human-readable preview of the auto-generated variants.

    Shows each variant's selector attributes and price so the supplier
    can verify before publishing.

    Args:
        lang:     Supplier's language code
        variants: List of variant dicts (from _build_variants)
        attr_map: Dict mapping attr_id → attr dict (from _process_attributes)

    Returns:
        str: HTML-formatted preview text
    """
    headers = {
        "tr": "🔄 <b>Ürün Varyantları</b>",
        "ar": "🔄 <b>متغيرات المنتج</b>",
        "en": "🔄 <b>Product Variants</b>",
    }
    header = headers.get(lang, headers["en"])

    lines = [header, ""]

    for i, variant in enumerate(variants, 1):
        selectors = variant.get("selector_attributes", [])
        price     = variant.get("prices", [{}])[0].get("price", 0)
        stock     = variant.get("stock_count", 0)

        # Build selector label (e.g. "Renk: Kırmızı | Beden: M")
        selector_labels = []
        for sel in selectors:
            attr_id   = sel.get("attribute_id", "")
            option_id = sel.get("option_id", "")
            attr      = attr_map.get(attr_id, {})
            attr_name = attr.get("name", attr_id)

            # Find option value
            option_value = option_id
            for opt in attr.get("options", []):
                if opt.get("id") == option_id:
                    option_value = opt.get("value", option_id)
                    break

            selector_labels.append(f"{attr_name}: {option_value}")

        selector_str = " | ".join(selector_labels) if selector_labels else "—"
        lines.append(f"<b>#{i}</b> {selector_str}")
        lines.append(f"    💰 {price} ₺  |  📦 {stock} pcs")
        lines.append("")

    confirm_prompts = {
        "tr": "✅ Doğru görünüyor mu? Yayınlamak için onaylayın.",
        "ar": "✅ هل تبدو صحيحة؟ أكّد للنشر.",
        "en": "✅ Does this look correct? Confirm to publish.",
    }
    lines.append(confirm_prompts.get(lang, confirm_prompts["en"]))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Channel Post Builder
# Builds the professional Telegram channel post with TopGate buttons
# ══════════════════════════════════════════════════════════════════════════════

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

    The post uses Telegram HTML parse_mode for bold/italic formatting.
    Two inline URL buttons open the product in TopGate:
      1. 💬 Chat on TopGate  → product page + chat
      2. 🛍️ Supplier Page    → supplier's full profile

    Args:
        lang:          Language code for localized labels
        product_name:  Product title
        description:   Product description
        price:         Price string (e.g. "299.99")
        min_order:     Minimum order quantity string
        supplier_name: Supplier's display name
        product_id:    KAYISOFT product UUID
        supplier_id:   KAYISOFT supplier UUID

    Returns:
        tuple: (caption: str, reply_markup: InlineKeyboardMarkup)
    """
    sep = "━━━━━━━━━━━━━━━━━━━━━━━━"

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


# ══════════════════════════════════════════════════════════════════════════════
# Channel Publisher
# Publishes the professional product post to the supplier's Telegram channel
# ══════════════════════════════════════════════════════════════════════════════

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
    - Multiple images → MediaGroup album (caption on first) + buttons as follow-up
    - Single image    → Photo with caption + inline buttons
    - No images       → Text message with inline buttons

    Args:
        context:       Bot context for API calls
        channel_id:    Telegram channel ID (e.g. "@mychannel" or "-100...")
        lang:          Language code for localized labels
        image_file_ids: List of Telegram file_ids for product images
        product_name:  Product title
        description:   Product description
        price:         Price string
        min_order:     Minimum order quantity
        supplier_name: Supplier's display name
        product_id:    KAYISOFT product UUID
        supplier_id:   KAYISOFT supplier UUID

    Returns:
        bool: True on success, False on any failure
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
            # Inline buttons must be sent as a separate message after MediaGroup
            # (Telegram does not support reply_markup on MediaGroup)
            # We send a minimal separator line so the buttons appear directly below the album
            # without any distracting text — the caption on the first image carries all info.
            sep = "─" * 24
            await context.bot.send_message(
                chat_id=channel_id,
                text=sep,
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
            "✅ Channel post published: channel=%s, product_id=%s",
            channel_id,
            product_id,
        )
        return True

    except Exception as exc:
        logger.error("❌ Failed to publish to channel %s: %s", channel_id, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# AI Extraction Summary Builder
# Shows supplier a clean summary of what the AI understood
# ══════════════════════════════════════════════════════════════════════════════

def _build_extraction_summary(lang: str, data: dict, attr_map: dict) -> str:
    """
    Builds a human-readable summary of the AI-extracted product data.

    Shown to the supplier after AI extraction so they can verify the data
    before uploading images. Includes attribute values for transparency.

    Args:
        lang:     Supplier's language code
        data:     AI extraction result dict
        attr_map: Dict mapping attr_id → attr dict (for attribute name lookup)

    Returns:
        str: HTML-formatted summary text
    """
    name        = data.get("name", "—")
    description = data.get("description", "—")
    price       = data.get("price", "—")
    min_qty     = data.get("min_quantity", data.get("min_order", "1"))

    headers = {
        "tr": "🤖 <b>Yapay Zeka Özeti</b>",
        "ar": "🤖 <b>ملخص الذكاء الاصطناعي</b>",
        "en": "🤖 <b>AI Extraction Summary</b>",
    }
    field_labels = {
        "tr": {"name": "🏷️ Ürün Adı", "desc": "📝 Açıklama", "price": "💰 Fiyat", "min": "📦 Min. Sipariş"},
        "ar": {"name": "🏷️ اسم المنتج", "desc": "📝 الوصف", "price": "💰 السعر", "min": "📦 الحد الأدنى"},
        "en": {"name": "🏷️ Product Name", "desc": "📝 Description", "price": "💰 Price", "min": "📦 Min. Order"},
    }
    confirm_prompts = {
        "tr": "✅ <i>Bilgiler doğruysa fotoğrafları gönderin.</i>",
        "ar": "✅ <i>إذا كانت البيانات صحيحة، أرسل الصور الآن.</i>",
        "en": "✅ <i>If the details look correct, send your product images.</i>",
    }

    L = field_labels.get(lang, field_labels["en"])
    header  = headers.get(lang, headers["en"])
    confirm = confirm_prompts.get(lang, confirm_prompts["en"])

    lines = [
        header, "",
        f"{L['name']}: <b>{name}</b>",
        f"{L['desc']}: {description}",
        f"{L['price']}: <b>{price} ₺</b>",
        f"{L['min']}: {min_qty}",
    ]

    # Show extracted attributes if any
    shared_attrs   = data.get("shared_attributes", {})
    selector_attrs = data.get("selector_attributes", [])

    if shared_attrs or selector_attrs:
        attr_header = {"tr": "\n📋 <b>Özellikler:</b>", "ar": "\n📋 <b>الخصائص:</b>", "en": "\n📋 <b>Attributes:</b>"}
        lines.append(attr_header.get(lang, attr_header["en"]))

        for attr_id, option_ids in shared_attrs.items():
            attr = attr_map.get(attr_id, {})
            attr_name = attr.get("name", attr_id)
            option_values = []
            for opt_id in (option_ids if isinstance(option_ids, list) else [option_ids]):
                for opt in attr.get("options", []):
                    if opt.get("id") == opt_id:
                        option_values.append(opt.get("value", opt_id))
                        break
                else:
                    option_values.append(str(opt_id))
            lines.append(f"  • {attr_name}: {', '.join(option_values)}")

        for sel in selector_attrs:
            attr_id   = sel.get("attribute_id", "")
            option_id = sel.get("option_id", "")
            attr      = attr_map.get(attr_id, {})
            attr_name = attr.get("name", attr_id)
            option_value = option_id
            for opt in attr.get("options", []):
                if opt.get("id") == option_id:
                    option_value = opt.get("value", option_id)
                    break
            lines.append(f"  • {attr_name}: {option_value} 🔄")

    lines.extend(["", confirm])
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Missing Attributes Checker
# Validates that all required attributes are filled before proceeding
# ══════════════════════════════════════════════════════════════════════════════

def _check_missing_required(
    ai_data: dict,
    processed_attrs: dict,
) -> list:
    """
    Checks whether all required attributes were extracted by the AI.

    Compares the AI-extracted attributes against the required attribute list
    from the KAYISOFT API. Returns a list of missing attribute names.

    Args:
        ai_data:          AI extraction result dict
        processed_attrs:  Output of _process_attributes()

    Returns:
        list: Names of required attributes that are missing from AI extraction
    """
    missing = []

    shared_required   = processed_attrs.get("shared_required", [])
    selector_required = processed_attrs.get("selector_required", [])

    ai_shared   = ai_data.get("shared_attributes", {})
    ai_selector = ai_data.get("selector_attributes", [])
    ai_selector_attr_ids = {s.get("attribute_id") for s in ai_selector}

    for attr in shared_required:
        attr_id = attr.get("id")
        if attr_id not in ai_shared or not ai_shared[attr_id]:
            missing.append(attr.get("name", attr_id))

    for attr in selector_required:
        attr_id = attr.get("id")
        if attr_id not in ai_selector_attr_ids:
            missing.append(attr.get("name", attr_id))

    return missing


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Entry Point
# Triggered by "➕ Add Product" button or /add_product command
# ══════════════════════════════════════════════════════════════════════════════

async def start_add_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: Entry → SELECT_CATEGORY

    Entry point for the product addition flow.
    Loads root categories from KAYISOFT API and presents them as inline buttons.

    Progress: Step 1/5 — Category Selection

    On success  → returns SELECT_CATEGORY state
    On API fail → shows error message and ends conversation
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # Clear any previous product data to start fresh
    context.user_data.pop("product_data", None)

    # Show typing indicator for better UX
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    # Show loading message with progress bar
    progress = _progress_bar(1)
    loading_msg = await update.message.reply_text(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_categories')}",
        parse_mode=ParseMode.HTML,
    )

    # Fetch root categories from KAYISOFT API (parent="" → root level)
    api        = KayisoftAPI(telegram_user_id=user_id, language=lang)
    categories = await api.get_categories()

    await loading_msg.delete()

    if not categories:
        await update.message.reply_text(
            get_string(lang, "add_product_categories_error"),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Build inline keyboard — one button per visible root category
    # is_visible_for_creating=True means this category accepts new products
    keyboard = [
        [InlineKeyboardButton(
            cat.get("name", "—"),
            callback_data=f"cat_{cat.get('id')}",
        )]
        for cat in categories
        if cat.get("is_visible_for_creating", True)
    ]

    if not keyboard:
        await update.message.reply_text(
            get_string(lang, "add_product_categories_error"),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"{progress}\n\n{get_string(lang, 'add_product_select_category')}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_CATEGORY


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Root Category Selection
# ══════════════════════════════════════════════════════════════════════════════

async def handle_category_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: SELECT_CATEGORY → SELECT_SUBCATEGORY or FILL_FORM

    Handles root category button press.
    Loads subcategories from KAYISOFT API.

    - If subcategories exist → shows subcategory keyboard → SELECT_SUBCATEGORY
    - If no subcategories    → this IS the leaf category → loads attributes → FILL_FORM

    Progress: Step 2/5 — Subcategory Selection
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    cat_id  = query.data.split("_", 1)[1]

    # Store selected root category
    context.user_data["selected_category"] = cat_id

    progress = _progress_bar(2)

    # Show loading indicator
    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_subcategories')}",
        parse_mode=ParseMode.HTML,
    )

    api           = KayisoftAPI(telegram_user_id=user_id, language=lang)
    subcategories = await api.get_categories(parent_id=cat_id)

    if not subcategories:
        # No subcategories → this root category IS the leaf category
        # Load its attributes to guide AI extraction
        await _load_attributes_and_ask_form(query, context, api, cat_id, lang, progress)
        return FILL_FORM

    # Build subcategory keyboard — one button per visible subcategory
    keyboard = [
        [InlineKeyboardButton(
            sub.get("name", "—"),
            callback_data=f"sub_{sub.get('id')}",
        )]
        for sub in subcategories
        if sub.get("is_visible_for_creating", True)
    ]

    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_select_subcategory')}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_SUBCATEGORY


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Subcategory (Leaf) Selection
# ══════════════════════════════════════════════════════════════════════════════

async def handle_subcategory_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: SELECT_SUBCATEGORY → FILL_FORM

    Handles subcategory (leaf category) button press.
    Loads category attributes from KAYISOFT API.
    Presents the form prompt to the supplier.

    Progress: Step 3/5 — Product Description
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"
    sub_id  = query.data.split("_", 1)[1]

    progress = _progress_bar(3)

    # Show loading indicator
    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_attributes')}",
        parse_mode=ParseMode.HTML,
    )

    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    await _load_attributes_and_ask_form(query, context, api, sub_id, lang, progress)
    return FILL_FORM


async def _load_attributes_and_ask_form(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    api: "KayisoftAPI",
    category_id: str,
    lang: str,
    progress: str,
) -> None:
    """
    Helper: Loads attributes for a leaf category and shows the form prompt.

    Stores in context.user_data:
      - selected_subcategory: leaf category UUID
      - raw_attributes:       full attribute list from API
      - processed_attributes: structured groups (shared/selector, required/optional)
      - max_images:           maximum images allowed for this category

    Args:
        query:       Telegram callback query object
        context:     Bot context
        api:         KayisoftAPI instance
        category_id: Leaf category UUID
        lang:        Supplier's language code
        progress:    Progress bar string for display
    """
    # Store leaf category
    context.user_data["selected_subcategory"] = category_id

    # Fetch attributes for this leaf category
    raw_attributes = await api.get_attributes(category_id=category_id)
    raw_attributes = raw_attributes or []

    # Process and group attributes
    processed = _process_attributes(raw_attributes)

    context.user_data["raw_attributes"]       = raw_attributes
    context.user_data["processed_attributes"] = processed

    # Also store max_images from category metadata (fetched earlier)
    # Default to 10 if not available
    context.user_data.setdefault("max_images", 10)

    # Build the form prompt showing required attributes
    required_names = (
        [a.get("name") for a in processed["shared_required"]]
        + [a.get("name") for a in processed["selector_required"]]
    )

    form_prompt = get_string(lang, "add_product_fill_form")
    if required_names:
        required_label = {
            "tr": "Zorunlu alanlar",
            "ar": "الحقول المطلوبة",
            "en": "Required fields",
        }.get(lang, "Required fields")
        form_prompt += f"\n\n📋 <b>{required_label}:</b>\n" + "\n".join(
            f"  • {name}" for name in required_names if name
        )

    await query.edit_message_text(
        f"{progress}\n\n{form_prompt}",
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — AI-Assisted Form Input
# ══════════════════════════════════════════════════════════════════════════════

async def handle_form_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: FILL_FORM → UPLOAD_IMAGES (or FIX_MISSING if required attrs missing)

    Receives free-text product description from supplier.
    DeepSeek AI extracts structured product data including attributes.

    Validation:
    - If all required attributes found → shows summary → UPLOAD_IMAGES
    - If missing required attributes   → shows missing list → FIX_MISSING

    Progress: Step 3/5 → Step 4/5
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"
    text    = update.message.text

    raw_attributes  = context.user_data.get("raw_attributes", [])
    processed_attrs = context.user_data.get("processed_attributes", {})

    # Show AI processing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )
    processing_msg = await update.message.reply_text(
        get_string(lang, "add_product_ai_processing"),
        parse_mode=ParseMode.HTML,
    )

    # DeepSeek AI extraction
    # Passes raw_attributes so AI knows which options are valid for each attribute
    extracted_data = await deepseek_service.analyze_product_text(
        text=text,
        expected_attributes=raw_attributes,
    )

    # Fallback: use raw text if AI fails completely
    if not extracted_data:
        extracted_data = {
            "name":               text[:80],
            "description":        text,
            "price":              "0",
            "min_quantity":       1,
            "stock_count":        100,
            "shared_attributes":  {},
            "selector_attributes": [],
        }
        logger.warning(
            "DeepSeek extraction failed for user %s — using raw text fallback",
            user_id,
        )

    context.user_data["product_details"] = extracted_data

    await processing_msg.delete()

    # Validate: check for missing required attributes
    missing = _check_missing_required(extracted_data, processed_attrs)

    if missing:
        # Show missing attributes and ask supplier to provide them
        missing_labels = {
            "tr": "Eksik zorunlu alanlar",
            "ar": "الحقول المطلوبة الناقصة",
            "en": "Missing required fields",
        }
        missing_prompt = {
            "tr": "Lütfen aşağıdaki bilgileri ekleyin ve tekrar gönderin:",
            "ar": "يرجى إضافة المعلومات التالية وإعادة الإرسال:",
            "en": "Please add the following information and send again:",
        }

        missing_text = (
            f"⚠️ <b>{missing_labels.get(lang, missing_labels['en'])}:</b>\n"
            + "\n".join(f"  • {m}" for m in missing)
            + f"\n\n{missing_prompt.get(lang, missing_prompt['en'])}"
        )
        await update.message.reply_text(missing_text, parse_mode=ParseMode.HTML)
        return FIX_MISSING

    # All required attributes present → show summary and ask for images
    attr_map = processed_attrs.get("all_by_id", {})
    summary  = _build_extraction_summary(lang, extracted_data, attr_map)
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

    # Ask for images with progress bar
    progress = _progress_bar(4)
    await update.message.reply_text(
        f"{progress}\n\n{get_string(lang, 'add_product_upload_images')}",
        parse_mode=ParseMode.HTML,
    )
    return UPLOAD_IMAGES


async def handle_fix_missing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: FIX_MISSING → UPLOAD_IMAGES (or stays in FIX_MISSING)

    Receives the supplier's correction/addition for missing required attributes.
    Re-runs AI extraction on the combined original text + new input.

    This allows the supplier to just add the missing info without retyping everything.
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"
    new_text = update.message.text

    raw_attributes  = context.user_data.get("raw_attributes", [])
    processed_attrs = context.user_data.get("processed_attributes", {})

    # Combine original description with new input for re-extraction
    original_details = context.user_data.get("product_details", {})
    original_text    = original_details.get("description", "")
    combined_text    = f"{original_text}\n{new_text}"

    # Show AI processing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )
    processing_msg = await update.message.reply_text(
        get_string(lang, "add_product_ai_processing"),
        parse_mode=ParseMode.HTML,
    )

    # Re-run AI extraction with combined text
    extracted_data = await deepseek_service.analyze_product_text(
        text=combined_text,
        expected_attributes=raw_attributes,
    )

    if not extracted_data:
        extracted_data = original_details  # Keep previous data if re-extraction fails

    context.user_data["product_details"] = extracted_data

    await processing_msg.delete()

    # Re-validate
    missing = _check_missing_required(extracted_data, processed_attrs)

    if missing:
        # Still missing — ask again
        missing_labels = {
            "tr": "Hâlâ eksik alanlar var",
            "ar": "لا تزال هناك حقول ناقصة",
            "en": "Still missing required fields",
        }
        missing_text = (
            f"⚠️ <b>{missing_labels.get(lang, missing_labels['en'])}:</b>\n"
            + "\n".join(f"  • {m}" for m in missing)
        )
        await update.message.reply_text(missing_text, parse_mode=ParseMode.HTML)
        return FIX_MISSING

    # All good now — show summary and proceed to images
    attr_map = processed_attrs.get("all_by_id", {})
    summary  = _build_extraction_summary(lang, extracted_data, attr_map)
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

    progress = _progress_bar(4)
    await update.message.reply_text(
        f"{progress}\n\n{get_string(lang, 'add_product_upload_images')}",
        parse_mode=ParseMode.HTML,
    )
    return UPLOAD_IMAGES


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Image Upload
# ══════════════════════════════════════════════════════════════════════════════

async def handle_image_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: UPLOAD_IMAGES → CONFIRM_VARIANTS (or stays in UPLOAD_IMAGES)

    Receives product images (up to max_images per category).
    After each image, shows 3 action buttons:
      - ✅ Publish Now
      - 📸 Add More Images (X uploaded so far)
      - ❌ Cancel

    Progress: Step 5/5
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
    max_images  = context.user_data.get("max_images", 10)

    progress = _progress_bar(5)

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
        f"{progress}\n\n"
        + get_string(lang, "add_product_confirm").format(
            count=image_count,
            max=max_images,
        ),
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM_VARIANTS


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Variants Preview & Confirmation
# ══════════════════════════════════════════════════════════════════════════════

async def handle_variants_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: CONFIRM_VARIANTS → CONFIRM_PUBLISH (or back to UPLOAD_IMAGES / END)

    Callbacks:
      - "add_more"    → returns to UPLOAD_IMAGES
      - "confirm_no"  → cancels and clears user data → END
      - "confirm_yes" → builds variant preview → shows to supplier → CONFIRM_PUBLISH
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

    # ── Confirm Yes → Build and show variant preview ───────────────────────────
    product_details = context.user_data.get("product_details", {})
    processed_attrs = context.user_data.get("processed_attributes", {})
    raw_attributes  = context.user_data.get("raw_attributes", [])
    attr_map        = processed_attrs.get("all_by_id", {})

    # Parse price safely
    price_raw = product_details.get("price", "0")
    try:
        price_float = float(str(price_raw).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        price_float = 0.0

    min_quantity = int(product_details.get("min_quantity", product_details.get("min_order", 1)))
    stock_count  = int(product_details.get("stock_count", product_details.get("stock", 100)))

    # Build variants (using placeholder filenames for preview — real filenames come after upload)
    ai_selector_attrs = product_details.get("selector_attributes", [])
    preview_variants  = _build_variants(
        product_name        = product_details.get("name", ""),
        description         = product_details.get("description", ""),
        price_float         = price_float,
        stock_count         = stock_count,
        min_quantity        = min_quantity,
        lang                = lang,
        uploaded_file_names = [],  # Empty for preview — real files uploaded in next step
        ai_selector_attrs   = ai_selector_attrs,
        raw_attributes      = raw_attributes,
    )

    # Store preview variants for use in publish step
    context.user_data["preview_variants"] = preview_variants

    # Build and show variant preview
    preview_text = _build_variants_preview(lang, preview_variants, attr_map)

    confirm_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            get_string(lang, "btn_confirm_publish"),
            callback_data="publish_yes",
        )],
        [InlineKeyboardButton(
            get_string(lang, "btn_cancel"),
            callback_data="publish_no",
        )],
    ])

    await query.edit_message_text(
        preview_text,
        reply_markup=confirm_keyboard,
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM_PUBLISH


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Final Publish Pipeline
# ══════════════════════════════════════════════════════════════════════════════

async def handle_final_publish(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: CONFIRM_PUBLISH → END

    Executes the full publish pipeline:
      1. Download images from Telegram
      2. Generate filenames: <ISO-8601>-<SHA-256>
      3. POST api/extensions/signed-urls → get S3 upload URLs
      4. PUT images to S3
      5. Build product payload (with correct variants and attributes)
      6. POST api/seller/products → product created on TopKap + TopGate
      7. Post professional channel post to supplier's Telegram channel

    Callbacks:
      - "publish_no"  → cancel → END
      - "publish_yes" → execute pipeline → END
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = get_user_lang(user_id) or "tr"

    # ── Cancel ─────────────────────────────────────────────────────────────────
    if query.data == "publish_no":
        await query.edit_message_text(
            get_string(lang, "add_product_cancelled"),
            parse_mode=ParseMode.HTML,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ── PUBLISH YES — Full Pipeline ────────────────────────────────────────────
    await query.edit_message_text(
        get_string(lang, "add_product_publishing"),
        parse_mode=ParseMode.HTML,
    )

    product_details = context.user_data.get("product_details", {})
    image_file_ids  = context.user_data.get("images", [])
    raw_attributes  = context.user_data.get("raw_attributes", [])
    processed_attrs = context.user_data.get("processed_attributes", {})
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

    # ── Step 2: Generate filenames (ISO-8601 timestamp + SHA-256) ─────────────
    uploaded_file_names = []
    if image_bytes_list:
        file_names = [_generate_filename(img) for img in image_bytes_list]

        # ── Step 3: Get signed S3 URLs from KAYISOFT API ───────────────────────
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
    product_name = product_details.get("name", product_details.get("raw_text", "")[:80])
    description  = product_details.get("description", "")
    price_raw    = product_details.get("price", "0")
    min_quantity = int(product_details.get("min_quantity", product_details.get("min_order", 1)))
    stock_count  = int(product_details.get("stock_count", product_details.get("stock", 100)))
    supplier_name = product_details.get("supplier_name", "TopKap Supplier")

    # Parse price safely
    try:
        price_float = float(str(price_raw).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        price_float = 0.0
    price_str = str(price_raw)

    # Build shared_attributes: {attr_id: [option_id]} — NON-variant attributes
    # This is the correct format for KAYISOFT API (list of option IDs, not raw values)
    ai_shared_attrs = product_details.get("shared_attributes", {})
    shared_attributes = {}
    for attr_id, option_ids in ai_shared_attrs.items():
        if isinstance(option_ids, list):
            shared_attributes[attr_id] = option_ids
        else:
            shared_attributes[attr_id] = [option_ids]

    # Build selector_attributes: [{attribute_id, option_id}] — variant-defining
    ai_selector_attrs = product_details.get("selector_attributes", [])

    # Build variants with real uploaded filenames
    variants = _build_variants(
        product_name        = product_name,
        description         = description,
        price_float         = price_float,
        stock_count         = stock_count,
        min_quantity        = min_quantity,
        lang                = lang,
        uploaded_file_names = uploaded_file_names,
        ai_selector_attrs   = ai_selector_attrs,
        raw_attributes      = raw_attributes,
    )

    # Build the complete product payload matching KAYISOFT API spec exactly
    product_payload = {
        "name":               product_name,
        "product_no":         f"TK-{user_id[-6:]}-{uuid.uuid4().hex[:4].upper()}",
        "category_id":        category_id,
        "shared_attributes":  shared_attributes,
        "variants":           variants,
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
        "✅ Product created: id=%s, seller=%s, category=%s, variants=%d",
        product_id,
        supplier_id,
        category_id,
        len(variants),
    )

    # ── Step 7: Publish professional post to Telegram Channel ─────────────────
    # channel_id is stored in bot_data["user_channels"][user_id] by channel_handler
    # when the supplier adds the bot as admin to their channel.
    # bot_data is shared across all users, keyed by user_id for per-supplier lookup.
    user_channels = context.bot_data.get("user_channels", {})
    channel_id = user_channels.get(user_id) or context.user_data.get("channel_id")

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
            min_order=str(min_quantity),
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


# ══════════════════════════════════════════════════════════════════════════════
# Cancel Handler
# ══════════════════════════════════════════════════════════════════════════════

async def cancel_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Cancels the product addition flow at any step.
    Clears all stored product data from context.

    Triggered by /cancel command.
    """
    user_id = str(update.effective_user.id)
    lang    = get_user_lang(user_id) or "tr"

    context.user_data.clear()

    await update.message.reply_text(
        get_string(lang, "add_product_cancelled"),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# ConversationHandler Factory
# Registers all states and entry points for the product addition flow
# ══════════════════════════════════════════════════════════════════════════════

def get_product_conv_handler() -> ConversationHandler:
    """
    Factory function — returns the fully configured ConversationHandler.

    Registered in bot/main.py via:
        application.add_handler(get_product_conv_handler())

    Entry points:
      - ReplyKeyboard button press (all 3 languages)
      - /add_product command

    States:
      SELECT_CATEGORY    → root category inline button (cat_<id>)
      SELECT_SUBCATEGORY → subcategory inline button (sub_<id>)
      FILL_FORM          → free text message (AI extraction)
      FIX_MISSING        → free text message (missing attributes correction)
      UPLOAD_IMAGES      → photo message
      CONFIRM_VARIANTS   → inline button (confirm_yes / add_more / confirm_no)
      CONFIRM_PUBLISH    → inline button (publish_yes / publish_no)

    Fallback:
      /cancel command → cancels at any step and ends conversation
    """
    return ConversationHandler(
        entry_points=[
            # ReplyKeyboard button (all 3 languages)
            MessageHandler(
                filters.Regex(
                    r"^(➕ Ürün Ekle|➕ Add Product|➕ إضافة منتج)$"
                ),
                start_add_product,
            ),
            # Slash command alternative
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
            FIX_MISSING: [
                # Supplier provides missing attribute information
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_fix_missing,
                ),
            ],
            UPLOAD_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_upload),
            ],
            CONFIRM_VARIANTS: [
                CallbackQueryHandler(
                    handle_variants_confirmation,
                    pattern=r"^(confirm_yes|confirm_no|add_more)$",
                ),
                # Allow more images even in CONFIRM_VARIANTS state
                MessageHandler(filters.PHOTO, handle_image_upload),
            ],
            CONFIRM_PUBLISH: [
                CallbackQueryHandler(
                    handle_final_publish,
                    pattern=r"^(publish_yes|publish_no)$",
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_product),
        ],
        allow_reentry=True,
        name="add_product_conversation",
        persistent=False,
    )
