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

import asyncio
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
CONFIRM_DETAILS    = 8   # Waiting for supplier to confirm or edit AI summary
UPLOAD_IMAGES      = 5   # Waiting for image uploads
CONFIRM_VARIANTS   = 6   # Waiting for variant preview confirmation
CONFIRM_PUBLISH    = 7   # Waiting for final publish confirmation


# ══════════════════════════════════════════════════════════════════════════════
# Progress Bar Helper
# Shows the supplier where they are in the 5-step flow
# ══════════════════════════════════════════════════════════════════════════════

def _progress_bar(current: int, total: int = 5) -> str:
    """
    Generates a visual progress bar string compatible with all platforms
    including iOS (which renders ▓/░ as empty boxes).

    Uses standard Unicode bullet symbols that render correctly everywhere:
      ● = filled step (U+25CF BLACK CIRCLE)
      ○ = empty step  (U+25CB WHITE CIRCLE)

    Example: _progress_bar(2, 5) → "●●○○○  2/5"

    Args:
        current: Current step number (1-based)
        total:   Total number of steps

    Returns:
        str: Progress bar with step counter
    """
    filled = "●" * current
    empty  = "○" * (total - current)
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
# Price Parser Helper
# ══════════════════════════════════════════════════════════════════════════════

def _parse_price(raw) -> float:
    """
    Robustly parse a price value from various formats:
    - Arabic-Indic numerals: ٢٠٠ → 200
    - Strings with units:    "200 ليرة" → 200.0
    - Comma decimals:        "1.299,99" → 1299.99  (Turkish format)
    - Period decimals:       "1,299.99" → 1299.99  (English format)
    - Already a float/int:   200 → 200.0
    Returns 0.0 if parsing fails (caller must validate > 0).
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)

    # Convert Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) to ASCII digits
    arabic_to_ascii = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    s = str(raw).translate(arabic_to_ascii).strip()

    # Extract the first numeric token (handles "200 ليرة", "200 lira", "TL 200")
    import re
    # Match: optional sign, digits, optional decimal separator, optional decimals
    match = re.search(r'[\d]+(?:[.,][\d]+)?', s)
    if not match:
        logger.warning("_parse_price: no numeric token found in %r → returning 0.0", raw)
        return 0.0

    token = match.group(0)
    # Normalize decimal separator:
    # Turkish format: 1.299,99 → 1299.99
    # English format: 1,299.99 → 1299.99
    if ',' in token and '.' in token:
        # Both present: remove thousands separator, keep decimal
        if token.rfind(',') > token.rfind('.'):
            # Comma is decimal: "1.299,99"
            token = token.replace('.', '').replace(',', '.')
        else:
            # Period is decimal: "1,299.99"
            token = token.replace(',', '')
    elif ',' in token:
        # Could be thousands ("1,299") or decimal ("1,5")
        parts = token.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            token = token.replace(',', '.')  # treat as decimal
        else:
            token = token.replace(',', '')   # treat as thousands separator

    try:
        result = float(token)
        logger.debug("_parse_price: %r → %s", raw, result)
        return result
    except ValueError:
        logger.warning("_parse_price: float conversion failed for token %r (raw=%r)", token, raw)
        return 0.0


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
    id_to_key: dict = None,
    product_name_en: str = "",
    description_en: str = "",
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
    # ── Helper: convert [{attribute_id, option_id}] → {attr_key: [option_uuid]} ───────────
    # KAYISOFT API PDF spec: selector_attributes in each variant must be a dict
    # where key = attribute.key (e.g. "color", "size") and value = [option_uuid]
    # NOT a list of {attribute_id, option_id} objects.
    # id_to_key maps UUID → key string; if not provided, UUID is used as fallback.
    _key_map = id_to_key or {}

    def _to_selector_dict(selectors: list) -> dict:
        """Convert [{attribute_id, option_id}] → {attr_key: [option_id]}"""
        result = {}
        for sel in selectors:
            attr_id   = sel.get("attribute_id", "")
            option_id = sel.get("option_id", "")
            attr_key  = _key_map.get(attr_id, attr_id)  # fallback to UUID if key missing
            if option_id:  # Only add if option_id is not empty
                if attr_key not in result:
                    result[attr_key] = []
                result[attr_key].append(option_id)
        return result

    # Build titles list — always include English entry (API requirement)
    # API requires titles/descriptions in ALL supported languages: ar, en, tr
    # We use the local text as fallback for missing languages
    SUPPORTED_LANGS = ["ar", "en", "tr"]

    def _build_titles(name_local: str, name_en: str, lang_code: str) -> list:
        titles = []
        for lng in SUPPORTED_LANGS:
            if lng == lang_code:
                text = name_local
            elif lng == "en":
                text = name_en or name_local
            else:
                text = name_local  # fallback: use local text for missing languages
            titles.append({"language": lng, "text": text})
        return titles

    def _build_descriptions(desc_local: str, desc_en: str, lang_code: str) -> list:
        descs = []
        for lng in SUPPORTED_LANGS:
            if lng == lang_code:
                text = desc_local
            elif lng == "en":
                text = desc_en or desc_local
            else:
                text = desc_local  # fallback: use local text for missing languages
            descs.append({"language": lng, "text": text})
        return descs

    # If no selector attributes → single variant
    if not ai_selector_attrs:
        return [{
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "visibility_status":   "public",
            # tax_percentage & cost_price omitted entirely:
            # API requires positive number or absence; null causes HTTP 422
            "titles":              _build_titles(product_name, product_name_en, lang),
            "descriptions":        _build_descriptions(description, description_en, lang),
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              uploaded_file_names,
            "videos":              [],
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
        # Convert list → dict format: {attr_key: [option_uuid]}
        return [{
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "visibility_status":   "public",
            # tax_percentage & cost_price omitted entirely:
            # API requires positive number or absence; null causes HTTP 422
            "titles":              _build_titles(product_name, product_name_en, lang),
            "descriptions":        _build_descriptions(description, description_en, lang),
            "selector_attributes": _to_selector_dict(ai_selector_attrs),
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              uploaded_file_names,
            "videos":              [],
            "dimensions":          None,
        }]

    # ── Distribute images across variants ───────────────────────────────────────
    # Strategy:
    #   - 1 variant  → all images go to that variant
    #   - N variants, images >= N → distribute evenly (first variant gets remainder)
    #   - N variants, images < N  → all images go to EVERY variant (same photos for all colors)
    #     This handles the case where supplier uploads photos for a single color sample
    #     and wants all colors to show those photos.
    images_per_variant = []
    n_variants = len(primary_options)
    n_images   = len(uploaded_file_names)

    if n_variants <= 1 or n_images == 0:
        # Single variant or no images → all images to first (only) variant
        images_per_variant = [uploaded_file_names] * max(1, n_variants)
    elif n_images < n_variants:
        # Fewer images than variants → duplicate all images across every variant
        # (supplier uploaded sample photos; all colors share the same images)
        images_per_variant = [uploaded_file_names] * n_variants
    else:
        # Enough images to distribute — split evenly; last variant gets remainder
        chunk = n_images // n_variants
        for i in range(n_variants):
            start = i * chunk
            end   = start + chunk if i < n_variants - 1 else n_images
            images_per_variant.append(uploaded_file_names[start:end])

    variants = []
    for i, primary_opt in enumerate(primary_options):
        # Each variant's selector_attributes = primary option + shared non-primary selectors
        # Convert from list format [{attribute_id, option_id}] → dict {attr_key: [option_uuid]}
        variant_selectors_list = [primary_opt] + other_selectors
        variant_selectors_dict = _to_selector_dict(variant_selectors_list)
        variant_images         = images_per_variant[i] if i < len(images_per_variant) else []

        variants.append({
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "visibility_status":   "public",
            # tax_percentage & cost_price omitted entirely:
            # API requires positive number or absence; null causes HTTP 422
            "titles":              _build_titles(product_name, product_name_en, lang),
            "descriptions":        _build_descriptions(description, description_en, lang),
            "selector_attributes": variant_selectors_dict,
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              variant_images,
            "videos":              [],
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
        # selector_attributes can be:
        #   - dict: {attr_key: [option_uuid, ...]}  ← new API format
        #   - list: [{attribute_id, option_id}, ...]  ← legacy format
        selector_labels = []
        if isinstance(selectors, dict):
            # New format: {attr_key: [option_uuid, ...]}
            # Find attr by key in attr_map values, then resolve option label/value
            for attr_key, option_ids in selectors.items():
                # Try to find attr by key in attr_map
                attr_name    = attr_key  # fallback to key itself
                option_uuid  = option_ids[0] if option_ids else ""
                option_value = option_uuid  # fallback
                for attr_id_candidate, attr_obj in attr_map.items():
                    if attr_obj.get("key") == attr_key:
                        attr_name = attr_obj.get("name", attr_key)
                        # Resolve option UUID → human label (prefer label > name > value)
                        for opt in attr_obj.get("options", []):
                            if opt.get("id") == option_uuid:
                                raw_val      = opt.get("value", "")
                                label_val    = opt.get("label") or opt.get("name") or ""
                                import re as _re

                                # Handle pipe-separated format: "#FF000000|أسود" → hex + label
                                if "|" in raw_val:
                                    hex_part, label_part = raw_val.split("|", 1)
                                    raw_val   = hex_part.strip()
                                    if not label_val:
                                        label_val = label_part.strip()
                                elif "|" in label_val:
                                    hex_part, label_part = label_val.split("|", 1)
                                    raw_val   = hex_part.strip()
                                    label_val = label_part.strip()

                                # Determine display value: prefer human label over hex
                                if label_val:
                                    option_value = label_val
                                elif raw_val:
                                    option_value = raw_val
                                else:
                                    option_value = option_uuid

                                # Add color emoji if we have a hex value
                                if raw_val and _re.match(r'^#?[0-9A-Fa-f]{6,8}$', raw_val.strip()):
                                    emoji = _render_color_value(raw_val)
                                    # Show emoji + human label (never raw hex)
                                    is_still_hex = _re.match(r'^#?[0-9A-Fa-f]{6,8}$', option_value.strip())
                                    if is_still_hex:
                                        option_value = emoji  # Only emoji if no human label
                                    else:
                                        option_value = f"{emoji} {option_value}"
                                break
                        break
                selector_labels.append(f"{attr_name}: {option_value}")
        else:
            # Legacy list format: [{attribute_id, option_id}, ...]
            for sel in selectors:
                if not isinstance(sel, dict):
                    selector_labels.append(str(sel))
                    continue
                attr_id   = sel.get("attribute_id", "")
                option_id = sel.get("option_id", "")
                attr      = attr_map.get(attr_id, {})
                attr_name = attr.get("name", attr_id)

                # Find option label (prefer label > name > value)
                option_value = option_id
                for opt in attr.get("options", []):
                    if opt.get("id") == option_id:
                        raw_val   = opt.get("value", "")
                        label_val = opt.get("label") or opt.get("name") or ""
                        import re as _re2

                        # Handle pipe-separated format: "#FF000000|أسود" → hex + label
                        if "|" in raw_val:
                            hex_part, label_part = raw_val.split("|", 1)
                            raw_val   = hex_part.strip()
                            if not label_val:
                                label_val = label_part.strip()
                        elif "|" in label_val:
                            hex_part, label_part = label_val.split("|", 1)
                            raw_val   = hex_part.strip()
                            label_val = label_part.strip()

                        # Determine display value: prefer human label over hex
                        if label_val:
                            option_value = label_val
                        elif raw_val:
                            option_value = raw_val
                        else:
                            option_value = option_id

                        # Add color emoji if we have a hex value
                        if raw_val and _re2.match(r'^#?[0-9A-Fa-f]{6,8}$', raw_val.strip()):
                            emoji = _render_color_value(raw_val)
                            is_still_hex = _re2.match(r'^#?[0-9A-Fa-f]{6,8}$', option_value.strip())
                            if is_still_hex:
                                option_value = emoji
                            else:
                                option_value = f"{emoji} {option_value}"
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
# Color Value Renderer
# Converts hex color codes to human-friendly colored emoji squares
# ══════════════════════════════════════════════════════════════════════════════

def _render_color_value(value: str) -> str:
    """
    Converts a hex color code (e.g. "#FFFFDD0" or "#FFC0CB") into a
    human-readable label with a colored square emoji.

    Telegram does not support HTML color spans in bot messages, so we use
    a lookup table of common color hues mapped to Unicode colored squares.

    If the value is not a hex color, it is returned unchanged.

    Examples:
        "#FF0000"  → "🟥 #FF0000"   (red)
        "#FFFFDD0" → "🟨 #FFFFDD0"  (yellow-ish, strip leading zeros)
        "Pamuk"    → "Pamuk"         (not a color, unchanged)
    """
    import re
    v = value.strip() if value else ""

    # Match hex color: optional # followed by 6 or 8 hex digits
    hex_match = re.match(r'^#?([0-9A-Fa-f]{6,8})$', v)
    if not hex_match:
        return value  # Not a hex color — return as-is

    hex_digits = hex_match.group(1)[:6]  # Take first 6 digits (ignore alpha)
    try:
        r = int(hex_digits[0:2], 16)
        g = int(hex_digits[2:4], 16)
        b = int(hex_digits[4:6], 16)
    except (ValueError, IndexError):
        return value

    # Map RGB to the nearest color emoji using simple hue/saturation rules
    # This gives a visual hint without requiring image rendering
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    delta = max_c - min_c

    if delta < 30:  # Low saturation → grayscale
        if max_c > 200:
            emoji = "⬜"  # white
        elif max_c > 100:
            emoji = "🏦"  # light gray (building)
        else:
            emoji = "⬛"  # black
    elif r > g and r > b:  # Red dominant
        if g > 100:
            emoji = "🟧"  # orange
        else:
            emoji = "🟥"  # red
    elif g > r and g > b:  # Green dominant
        emoji = "🟩"  # green
    elif b > r and b > g:  # Blue dominant
        emoji = "🟦"  # blue
    elif r > 180 and g > 180 and b < 100:  # Yellow
        emoji = "🟨"  # yellow
    elif r > 150 and b > 150 and g < 100:  # Purple/Magenta
        emoji = "🟣"  # purple
    elif r > 150 and g > 100 and b < 80:  # Brown/Beige
        emoji = "🟤"  # brown
    elif r > 180 and g > 150 and b > 150:  # Pink
        emoji = "💗"  # pink heart (closest)
    else:
        emoji = "🔵"  # default blue circle

    # Show only the emoji — no raw hex code in user-facing messages
    # The hex is resolved to a visual color indicator; showing #RRGGBB is confusing
    return emoji


# ══════════════════════════════════════════════════════════════════════════════
# AI Extraction Summary Builder
# Shows supplier a clean summary of what the AI understood
# ══════════════════════════════════════════════════════════════════════════════

def _build_extraction_summary(
    lang: str,
    data: dict,
    attr_map: dict,
    cat_name: str = "",
    sub_name: str = "",
) -> str:
    """
    Builds a human-readable summary of the AI-extracted product data.

    Shown to the supplier after AI extraction so they can verify the data
    before uploading images. Includes:
      - Category breadcrumb at the top (cat_name ← sub_name)
      - Product name, professional description, price, min order
      - All extracted attributes with human-readable option values

    Args:
        lang:     Supplier's language code ('ar', 'tr', 'en')
        data:     AI extraction result dict
        attr_map: Dict mapping attr_id → attr dict (for attribute name lookup)
        cat_name: Root category name (e.g. "Giyim / ملابس")
        sub_name: Subcategory name (e.g. "Şallar / شالات")

    Returns:
        str: HTML-formatted summary text ready to send via Telegram
    """
    name        = data.get("name", "—")
    description = data.get("description", "—")
    price       = data.get("price", "—")
    min_qty     = data.get("min_quantity", data.get("min_order", "1"))

    # Build reverse lookup: attr_key → attr dict (for cases where attr_id is UUID but attr_map uses UUID too)
    attr_key_map = {v.get("key", ""): v for v in attr_map.values() if v.get("key")}

    # ── Breadcrumb labels ───────────────────────────────────────────────────────────────────────────────────
    cat_label = {"tr": "Kategori", "ar": "الفئة", "en": "Category"}.get(lang, "Category")
    sub_label = {"tr": "Alt Kategori", "ar": "الفئة الفرعية", "en": "Subcategory"}.get(lang, "Subcategory")

    breadcrumb_parts = []
    if cat_name:
        breadcrumb_parts.append(f"✅ <b>{cat_label}:</b> {cat_name}")
    if sub_name and sub_name != cat_name:
        breadcrumb_parts.append(f"📌 <b>{sub_label}:</b> {sub_name}")
    breadcrumb = "\n".join(breadcrumb_parts)

    # ── Summary header ─────────────────────────────────────────────────────────────────────────────────────
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

    L      = field_labels.get(lang, field_labels["en"])
    header = headers.get(lang, headers["en"])

    # ── Build message lines ────────────────────────────────────────────────────────────────────────────────────
    lines = []

    # Breadcrumb at the very top (above AI header)
    if breadcrumb:
        lines.append(breadcrumb)
        lines.append("")

    lines += [
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
                        # Prefer label/name over value (which may be a raw hex code)
                        # label = human-readable color name (e.g. "Bej", "بيج")
                        # value = raw hex code (e.g. "#FFF5F5DC") — used for API, not display
                        display = (
                            opt.get("label")
                            or opt.get("name")
                            or opt.get("value", opt_id)
                        )
                        option_values.append((display, opt.get("value", "")))
                        break
                else:
                    option_values.append((str(opt_id), ""))
            # ── Color rendering: show emoji + human label (never raw hex) ──────────────
            # Handle "#RRGGBBAA|label" format from API (pipe-separated hex|name)
            rendered_values = []
            import re as _re
            for display, raw_val in option_values:
                # Parse pipe-separated format: "#FFFFFFFF|أبيض" → hex="#FFFFFFFF", label="أبيض"
                if "|" in display:
                    hex_part, label_part = display.split("|", 1)
                    raw_val = hex_part.strip()
                    display = label_part.strip()
                elif "|" in raw_val:
                    hex_part, label_part = raw_val.split("|", 1)
                    raw_val = hex_part.strip()
                    if not display or _re.match(r'^#?[0-9A-Fa-f]{6,8}$', display.strip()):
                        display = label_part.strip()
                emoji = _render_color_value(raw_val if raw_val else display)
                is_hex = bool(_re.match(r'^#?[0-9A-Fa-f]{6,8}$', display.strip()))
                if is_hex:
                    # Only hex available — show emoji only
                    rendered_values.append(emoji)
                else:
                    # Human label available — show emoji + label
                    rendered_values.append(f"{emoji} {display}" if emoji != display else display)
            lines.append(f"  • {attr_name}: {', '.join(rendered_values)}")

        for sel in selector_attrs:
            attr_id   = sel.get("attribute_id", "")
            option_id = sel.get("option_id", "")
            # Try attr_map by UUID first, then by key as fallback
            attr      = attr_map.get(attr_id) or attr_key_map.get(attr_id, {})
            attr_name = attr.get("name") or attr.get("key") or attr_id
            display_val = option_id
            raw_val     = ""
            for opt in attr.get("options", []):
                if opt.get("id") == option_id:
                    # Prefer human label over raw hex value
                    display_val = (
                        opt.get("label")
                        or opt.get("name")
                        or opt.get("value", option_id)
                    )
                    raw_val = opt.get("value", "")
                    break
            # Apply color rendering: emoji + human label (never raw hex)
            # Handle "#RRGGBBAA|label" format from API (pipe-separated hex|name)
            import re as _re
            if "|" in display_val:
                hex_part, label_part = display_val.split("|", 1)
                raw_val  = hex_part.strip()
                display_val = label_part.strip()
            elif "|" in raw_val:
                hex_part, label_part = raw_val.split("|", 1)
                raw_val = hex_part.strip()
                if not display_val or _re.match(r'^#?[0-9A-Fa-f]{6,8}$', display_val.strip()):
                    display_val = label_part.strip()
            emoji = _render_color_value(raw_val if raw_val else display_val)
            is_hex = bool(_re.match(r'^#?[0-9A-Fa-f]{6,8}$', display_val.strip()))
            if is_hex:
                option_value = emoji
            else:
                option_value = f"{emoji} {display_val}" if emoji != display_val else display_val
            lines.append(f"  • {attr_name}: {option_value}")

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

    The AI output is expected to have:
        shared_attributes:    { attr_uuid: value }   for non-variant attrs
        selector_attributes:  [ { attribute_id, option_id } ]  for variant attrs

    Args:
        ai_data:          AI extraction result dict
        processed_attrs:  Output of _process_attributes()

    Returns:
        list: Names of required attributes that are missing from AI extraction
    """
    missing = []

    shared_required   = processed_attrs.get("shared_required", [])
    selector_required = processed_attrs.get("selector_required", [])

    ai_shared   = ai_data.get("shared_attributes", {}) or {}
    ai_selector = ai_data.get("selector_attributes", []) or []

    # Build set of attribute_ids present in selector_attributes
    ai_selector_attr_ids = {s.get("attribute_id") for s in ai_selector if s.get("attribute_id")}

    # ── Log for debugging ─────────────────────────────────────────────────────
    logger.info(
        "_check_missing_required: shared_required=%d, selector_required=%d, "
        "ai_shared_keys=%s, ai_selector_attr_ids=%s",
        len(shared_required), len(selector_required),
        list(ai_shared.keys())[:10],
        list(ai_selector_attr_ids)[:10],
    )

    for attr in shared_required:
        attr_id          = attr.get("id")
        attr_name        = attr.get("name", attr_id)
        default_opt_id   = attr.get("default_option_id")
        options          = attr.get("options", [])
        value            = ai_shared.get(attr_id)

        # Consider the attribute present if it has any non-empty value
        if value is None or value == "" or value == []:
            # ── Fallback: use default_option_id or first option if available ─────────────────────
            fallback_opt = None
            if default_opt_id:
                fallback_opt = default_opt_id
            elif options:
                fallback_opt = options[0].get("id")

            if fallback_opt:
                # Auto-inject the fallback option into ai_data shared_attributes
                if "shared_attributes" not in ai_data:
                    ai_data["shared_attributes"] = {}
                ai_data["shared_attributes"][attr_id] = [fallback_opt]
                fallback_val = next(
                    (o.get("value", "") for o in options if o.get("id") == fallback_opt),
                    fallback_opt[:8]
                )
                logger.info(
                    "  AUTO-FILLED shared required: %s = %s (fallback)",
                    attr_name, fallback_val
                )
            else:
                logger.info("  MISSING shared required: %s (id=%s)", attr_name, attr_id)
                missing.append(attr_name)
        else:
            logger.info("  OK shared required: %s = %s", attr_name, str(value)[:50])

    for attr in selector_required:
        attr_id          = attr.get("id")
        attr_name        = attr.get("name", attr_id)
        default_opt_id   = attr.get("default_option_id")
        options          = attr.get("options", [])

        if attr_id not in ai_selector_attr_ids:
            # ── Fallback: use default_option_id or first option if available ─────────────────────
            fallback_opt = None
            if default_opt_id:
                fallback_opt = default_opt_id
            elif options:
                fallback_opt = options[0].get("id")

            if fallback_opt:
                # Auto-inject the fallback option into ai_data
                if "selector_attributes" not in ai_data:
                    ai_data["selector_attributes"] = []
                ai_data["selector_attributes"].append({
                    "attribute_id": attr_id,
                    "option_id":    fallback_opt,
                })
                ai_selector_attr_ids.add(attr_id)
                fallback_val = next(
                    (o.get("value","") for o in options if o.get("id") == fallback_opt),
                    fallback_opt[:8]
                )
                logger.info(
                    "  AUTO-FILLED selector required: %s = %s (fallback)",
                    attr_name, fallback_val
                )
            else:
                logger.info("  MISSING selector required: %s (id=%s)", attr_name, attr_id)
                missing.append(attr_name)
        else:
            logger.info("  OK selector required: %s", attr_name)

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
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")

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

    # ── Error handling: API returned None or empty list ───────────────────────
    # FIX: Previously the loading message was deleted BEFORE checking for errors,
    # causing the message to vanish with no feedback to the supplier.
    # Now we EDIT the loading message in-place instead of deleting it,
    # so the supplier always sees a clear result (categories or error).
    if not categories:
        error_texts = {
            "tr": (
                "❌ <b>Kategoriler yüklenemedi.</b>\n\n"
                "Sunucuya bağlanırken bir sorun oluştu. "
                "Lütfen birkaç saniye bekleyip tekrar deneyin.\n\n"
                "<i>Sorun devam ederse destek ekibiyle iletişime geçin.</i>"
            ),
            "ar": (
                "❌ <b>تعذّر تحميل الفئات.</b>\n\n"
                "حدثت مشكلة في الاتصال بالخادم. "
                "يرجى الانتظار لحظة والمحاولة مجدداً.\n\n"
                "<i>إذا استمرت المشكلة، تواصل مع فريق الدعم.</i>"
            ),
            "en": (
                "❌ <b>Could not load categories.</b>\n\n"
                "A connection error occurred. "
                "Please wait a moment and try again.\n\n"
                "<i>If the issue persists, contact support.</i>"
            ),
        }
        retry_labels = {"tr": "🔄 Tekrar Dene", "ar": "🔄 أعد المحاولة", "en": "🔄 Try Again"}
        retry_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                retry_labels.get(lang, retry_labels["en"]),
                callback_data="retry_add_product",
            )
        ]])
        await loading_msg.edit_text(
            error_texts.get(lang, error_texts["en"]),
            parse_mode=ParseMode.HTML,
            reply_markup=retry_keyboard,
        )
        return ConversationHandler.END

    # Build inline keyboard — two buttons per row for compact display
    # is_visible_for_creating=True means this category accepts new products
    # Also build a name lookup map so later steps can show the selected category name
    categories_map = {}
    buttons_flat = []
    for cat in categories:
        if cat.get("is_visible_for_creating", True):
            cid   = cat.get("id")
            cname = cat.get("name", "—")
            categories_map[cid] = cname
            buttons_flat.append(InlineKeyboardButton(cname, callback_data=f"cat_{cid}"))
    # Arrange into rows of 2 buttons each
    keyboard = [buttons_flat[i:i+2] for i in range(0, len(buttons_flat), 2)]

    # Store the map so handle_category_selection can look up the selected name
    context.user_data["categories_map"] = categories_map

    if not keyboard:
        no_cat_texts = {
            "tr": "⚠️ Şu an aktif kategori bulunmuyor. Lütfen daha sonra tekrar deneyin.",
            "ar": "⚠️ لا توجد فئات نشطة حالياً. يرجى المحاولة لاحقاً.",
            "en": "⚠️ No active categories available right now. Please try again later.",
        }
        await loading_msg.edit_text(
            no_cat_texts.get(lang, no_cat_texts["en"]),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # ── Success: edit loading message to show category selection ─────────────
    # FIX: Use edit_text instead of delete + reply_text.
    # This avoids the "message disappears" UX issue and is more professional.
    await loading_msg.edit_text(
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
    lang    = get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")
    cat_id  = query.data.split("_", 1)[1]

    # Store selected root category ID and resolve its name from the map
    context.user_data["selected_category"] = cat_id
    categories_map = context.user_data.get("categories_map", {})
    cat_name = categories_map.get(cat_id, "")
    context.user_data["selected_category_name"] = cat_name

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

    # Build subcategory keyboard — two buttons per row for compact display
    # Also build a name map for later steps
    subcategories_map = {}
    sub_buttons_flat = []
    for sub in subcategories:
        if sub.get("is_visible_for_creating", True):
            sid   = sub.get("id")
            sname = sub.get("name", "—")
            subcategories_map[sid] = sname
            sub_buttons_flat.append(InlineKeyboardButton(sname, callback_data=f"sub_{sid}"))
    # Arrange into rows of 2 buttons each
    keyboard = [sub_buttons_flat[i:i+2] for i in range(0, len(sub_buttons_flat), 2)]
    context.user_data["subcategories_map"] = subcategories_map

    # Build breadcrumb label: "✅ الفئة: Giyim"
    breadcrumb_label = {
        "tr": "Kategori",
        "ar": "الفئة",
        "en": "Category",
    }.get(lang, "Category")
    breadcrumb = f"✅ <b>{breadcrumb_label}:</b> {cat_name}" if cat_name else ""

    subcategory_prompt = get_string(lang, "add_product_select_subcategory")
    body = f"{breadcrumb}\n\n{subcategory_prompt}" if breadcrumb else subcategory_prompt

    await query.edit_message_text(
        f"{progress}\n\n{body}",
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
    lang    = get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")
    sub_id  = query.data.split("_", 1)[1]

    # Resolve subcategory name from the map saved in handle_category_selection
    subcategories_map = context.user_data.get("subcategories_map", {})
    sub_name = subcategories_map.get(sub_id, "")
    context.user_data["selected_subcategory_name"] = sub_name

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

    # ── Build breadcrumb: shows selected category path above the form ────────────────
    # Example (AR): "✅ الفئة: Giyim ← الفئة الفرعية: Şallar"
    cat_name = context.user_data.get("selected_category_name", "")
    sub_name = context.user_data.get("selected_subcategory_name", "")

    cat_label = {"tr": "Kategori", "ar": "الفئة", "en": "Category"}.get(lang, "Category")
    sub_label = {"tr": "Alt Kategori", "ar": "الفئة الفرعية", "en": "Subcategory"}.get(lang, "Subcategory")

    breadcrumb_parts = []
    if cat_name:
        breadcrumb_parts.append(f"✅ <b>{cat_label}:</b> {cat_name}")
    if sub_name and sub_name != cat_name:
        breadcrumb_parts.append(f"📌 <b>{sub_label}:</b> {sub_name}")
    breadcrumb = "\n".join(breadcrumb_parts)

    # ── Build the form prompt showing required attributes ────────────────────────
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

    # Compose final message: progress bar + breadcrumb + form prompt
    body_parts = [progress]
    if breadcrumb:
        body_parts.append(breadcrumb)
    body_parts.append(form_prompt)
    full_body = "\n\n".join(body_parts)

    await query.edit_message_text(
        full_body,
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
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")
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
    # Save the original raw text so handle_fix_missing can combine it with corrections
    context.user_data["original_text"] = text

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

        # Build breadcrumb to remind supplier of their selected category
        cat_name = context.user_data.get("selected_category_name", "")
        sub_name = context.user_data.get("selected_subcategory_name", "")
        cat_label = {"tr": "Kategori", "ar": "الفئة", "en": "Category"}.get(lang, "Category")
        sub_label = {"tr": "Alt Kategori", "ar": "الفئة الفرعية", "en": "Subcategory"}.get(lang, "Subcategory")
        breadcrumb_parts = []
        if cat_name:
            breadcrumb_parts.append(f"✅ <b>{cat_label}:</b> {cat_name}")
        if sub_name and sub_name != cat_name:
            breadcrumb_parts.append(f"📌 <b>{sub_label}:</b> {sub_name}")
        breadcrumb = "\n".join(breadcrumb_parts)

        missing_text = (
            (f"{breadcrumb}\n\n" if breadcrumb else "")
            + f"⚠️ <b>{missing_labels.get(lang, missing_labels['en'])}:</b>\n"
            + "\n".join(f"  • {m}" for m in missing)
            + f"\n\n{missing_prompt.get(lang, missing_prompt['en'])}"
        )
        await update.message.reply_text(missing_text, parse_mode=ParseMode.HTML)
        return FIX_MISSING

    # All required attributes present → show summary with confirm/edit buttons
    cat_name = context.user_data.get("selected_category_name", "")
    sub_name = context.user_data.get("selected_subcategory_name", "")
    attr_map = processed_attrs.get("all_by_id", {})
    summary  = _build_extraction_summary(lang, extracted_data, attr_map, cat_name, sub_name)

    # Build confirm/edit inline keyboard
    confirm_labels = {
        "tr": ("✅ Onayla", "✏️ Düzenle"),
        "ar": ("✅ موافق", "✏️ تعديل"),
        "en": ("✅ Confirm", "✏️ Edit"),
    }
    ok_label, edit_label = confirm_labels.get(lang, confirm_labels["en"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(ok_label,   callback_data="details_confirm"),
        InlineKeyboardButton(edit_label, callback_data="details_edit"),
    ]])

    await update.message.reply_text(
        summary,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    return CONFIRM_DETAILS


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
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")
    new_text = update.message.text

    raw_attributes  = context.user_data.get("raw_attributes", [])
    processed_attrs = context.user_data.get("processed_attributes", {})

    # Combine original raw text with new correction for re-extraction
    # Use original_text (full raw input) not description (AI-extracted) for better context
    original_text = context.user_data.get("original_text", "")
    combined_text = f"{original_text}\n{new_text}" if original_text else new_text

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
        # Fallback: keep previous AI-extracted data if re-extraction fails
        # original_details was the old name — fixed to use user_data directly
        extracted_data = context.user_data.get("product_details", {})

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
        missing_prompt = {
            "tr": "Lütfen eksik bilgileri ekleyin ve tekrar gönderin:",
            "ar": "يرجى إضافة المعلومات الناقصة وإعادة الإرسال:",
            "en": "Please add the missing information and send again:",
        }

        # Breadcrumb reminder
        cat_name = context.user_data.get("selected_category_name", "")
        sub_name = context.user_data.get("selected_subcategory_name", "")
        cat_label = {"tr": "Kategori", "ar": "الفئة", "en": "Category"}.get(lang, "Category")
        sub_label = {"tr": "Alt Kategori", "ar": "الفئة الفرعية", "en": "Subcategory"}.get(lang, "Subcategory")
        breadcrumb_parts = []
        if cat_name:
            breadcrumb_parts.append(f"✅ <b>{cat_label}:</b> {cat_name}")
        if sub_name and sub_name != cat_name:
            breadcrumb_parts.append(f"📌 <b>{sub_label}:</b> {sub_name}")
        breadcrumb = "\n".join(breadcrumb_parts)

        missing_text = (
            (f"{breadcrumb}\n\n" if breadcrumb else "")
            + f"⚠️ <b>{missing_labels.get(lang, missing_labels['en'])}:</b>\n"
            + "\n".join(f"  • {m}" for m in missing)
            + f"\n\n{missing_prompt.get(lang, missing_prompt['en'])}"
        )
        await update.message.reply_text(missing_text, parse_mode=ParseMode.HTML)
        return FIX_MISSING

    # All good now — show summary with confirm/edit buttons
    cat_name = context.user_data.get("selected_category_name", "")
    sub_name = context.user_data.get("selected_subcategory_name", "")
    attr_map = processed_attrs.get("all_by_id", {})
    summary  = _build_extraction_summary(lang, extracted_data, attr_map, cat_name, sub_name)

    confirm_labels = {
        "tr": ("✅ Onayla", "✏️ Düzenle"),
        "ar": ("✅ موافق", "✏️ تعديل"),
        "en": ("✅ Confirm", "✏️ Edit"),
    }
    ok_label, edit_label = confirm_labels.get(lang, confirm_labels["en"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(ok_label,   callback_data="details_confirm"),
        InlineKeyboardButton(edit_label, callback_data="details_edit"),
    ]])

    await update.message.reply_text(
        summary,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    return CONFIRM_DETAILS


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4b — Confirm or Edit AI Summary
# Supplier presses ✅ Confirm → proceeds to image upload
# Supplier presses ✏️ Edit → goes back to FILL_FORM to re-enter description
# ══════════════════════════════════════════════════════════════════════════════

async def handle_confirm_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: CONFIRM_DETAILS → UPLOAD_IMAGES (confirm) or FILL_FORM (edit)

    Handles the two inline buttons shown below the AI summary:
      - ✅ موافق / Confirm → proceeds to image upload step
      - ✏️ تعديل / Edit     → returns to FILL_FORM so supplier can re-enter description

    Design note:
      We answer the callback query immediately to remove the loading spinner,
      then send the appropriate follow-up message.
    """
    query   = update.callback_query
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")

    await query.answer()  # Remove Telegram's loading spinner

    if query.data == "details_confirm":
        # ── Supplier confirmed → proceed to image upload ──────────────────────────────────────
        progress = _progress_bar(4)
        upload_prompts = {
            "tr": f"{progress}\n\n📸 <b>Adım 4 — Ürün Fotoğrafları</b>\n\n"
                  f"Ürün fotoğraflarınızı gönderin.\n"
                  f"Kameradan çekebilir veya galerinizden seçebilirsiniz.",
            "ar": f"{progress}\n\n📸 <b>الخطوة 4 — صور المنتج</b>\n\n"
                  f"أرسل صور منتجك الآن.\n"
                  f"يمكنك التصوير مباشرةً من الكاميرا أو الاختيار من المعرض.",
            "en": f"{progress}\n\n📸 <b>Step 4 — Product Images</b>\n\n"
                  f"Send your product photos now.\n"
                  f"You can take a photo directly from your camera or choose from your gallery.",
        }
        await query.message.reply_text(
            upload_prompts.get(lang, upload_prompts["en"]),
            parse_mode=ParseMode.HTML,
        )
        return UPLOAD_IMAGES

    else:  # details_edit
        # ── Supplier wants to edit → return to FILL_FORM ──────────────────────────────────────
        edit_prompts = {
            "tr": "✏️ Ürün bilgilerini yeniden girin:",
            "ar": "✏️ أعد كتابة تفاصيل المنتج:",
            "en": "✏️ Please re-enter your product details:",
        }
        await query.message.reply_text(
            edit_prompts.get(lang, edit_prompts["en"]),
            parse_mode=ParseMode.HTML,
        )
        return FILL_FORM


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
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")

    # Initialize image list on first upload
    if "images" not in context.user_data:
        context.user_data["images"] = []
    if "image_hashes" not in context.user_data:
        context.user_data["image_hashes"] = set()

    # Accept photo from two sources:
    # 1. update.message.photo  → standard compressed photo (gallery or camera)
    # 2. update.message.document → high-res image sent as file (some camera apps)
    # Both are valid; we store the file_id for later download and S3 upload.
    photo_file_id = None
    if update.message.photo:
        # Standard photo: use the highest-resolution variant (last in the list)
        photo_file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type and \
            update.message.document.mime_type.startswith("image/"):
        # Document-as-image: high-res camera shot sent without compression
        photo_file_id = update.message.document.file_id

    if photo_file_id:
        # v6.2: Deduplicate images using SHA-256 of file_id (unique_id is stable per file)
        # Telegram's file_id can differ per bot but unique_id is stable across bots.
        # We use file_id as the dedup key since unique_id requires an extra API call.
        img_hash = hashlib.sha256(photo_file_id.encode()).hexdigest()[:16]
        if img_hash in context.user_data["image_hashes"]:
            # Duplicate detected — notify user and ignore
            dup_msg = {
                "ar": "⚠️ هذه الصورة مضافة مسبقاً.",
                "tr": "⚠️ Bu fotoğraf zaten eklendi.",
                "en": "⚠️ This image was already added.",
            }
            await update.message.reply_text(dup_msg.get(lang, dup_msg["en"]))
            return UPLOAD_IMAGES
        context.user_data["image_hashes"].add(img_hash)
        context.user_data["images"].append(photo_file_id)

    image_count = len(context.user_data["images"])
    max_images  = context.user_data.get("max_images", 10)

    progress = _progress_bar(5)

    # ── Color Analysis via AI Vision ───────────────────────────────────────────
    # After each uploaded image, analyze the primary color using GPT-4o mini
    # vision and display the international color name + circle emoji to the
    # supplier. This replaces raw HEX codes with a human-friendly indicator.
    #
    # DESIGN NOTE: We get the Telegram file URL (public CDN link) and pass it
    # directly to the vision API. Falls back silently if analysis fails.
    color_line = ""
    try:
        tg_file = await update.message.photo[-1].get_file() if update.message.photo \
            else await update.message.document.get_file()
        image_url = tg_file.file_path  # Telegram CDN URL (valid for ~1 hour)

        # v6.2: Only analyze color for the FIRST image — avoid redundant API calls
        # for multi-image uploads. Color is stored in detected_colors list.
        if not context.user_data.get("detected_colors"):
            color_result = await deepseek_service.analyze_image_color(image_url)
        else:
            color_result = None
        if color_result:
            color_name  = color_result.get("color_name", "")
            color_emoji = color_result.get("color_emoji", "🔵")
            # Store detected color in user_data for use in product description
            if "detected_colors" not in context.user_data:
                context.user_data["detected_colors"] = []
            context.user_data["detected_colors"].append(
                {"name": color_name, "emoji": color_emoji}
            )
            color_line = f"\n\n🎨 <b>{color_emoji} {color_name}</b>"
    except Exception as _color_err:
        # Non-critical: color analysis failure must never block the upload flow
        logger.warning("Color analysis skipped: %s", _color_err)

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
        )
        + color_line,
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
    lang    = get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

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

    # ── Guard: require at least one image before publishing ─────────────────────
    # v6.2: Prevent publishing products with no images (dead catalog listings)
    if query.data == "confirm_yes":
        image_count = len(context.user_data.get("images", []))
        if image_count == 0:
            no_photo_msg = {
                "ar": "⚠️ يجب إضافة صورة واحدة على الأقل قبل النشر.",
                "tr": "⚠️ Yayınlamadan önce en az bir fotoğraf ekleyin.",
                "en": "⚠️ Please add at least one photo before publishing.",
            }
            await query.answer(
                no_photo_msg.get(lang, no_photo_msg["en"]),
                show_alert=True,
            )
            return UPLOAD_IMAGES

    # ── Confirm Yes → Build and show variant preview ───────────────────────────
    product_details = context.user_data.get("product_details", {})
    processed_attrs = context.user_data.get("processed_attributes", {})
    raw_attributes  = context.user_data.get("raw_attributes", [])
    attr_map        = processed_attrs.get("all_by_id", {})

    # Parse price safely (handles Arabic numerals, units like "ليرة", Turkish decimals)
    price_raw   = product_details.get("price", "0")
    price_float = _parse_price(price_raw)
    if price_float <= 0:
        logger.warning(
            "handle_variants_preview: price_float=%s (raw=%r) — "
            "will show 0 in preview but user can still proceed",
            price_float, price_raw
        )

    min_quantity = int(product_details.get("min_quantity", product_details.get("min_order", 1)))
    stock_count  = int(product_details.get("stock_count", product_details.get("stock", 100)))

    # Build id_to_key map for preview (attr_uuid → attr_key string)
    id_to_key_preview = {}
    for attr in raw_attributes:
        attr_id_raw  = attr.get("id", "")
        attr_key_raw = attr.get("key", "")
        if attr_id_raw and attr_key_raw:
            id_to_key_preview[attr_id_raw] = attr_key_raw

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
        id_to_key           = id_to_key_preview,
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
    lang    = get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

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

    # ── DEBUG: log user_data keys and image count ────────────────────────────────────────────────────
    logger.info(
        "🔑 handle_final_publish: user_data keys=%s",
        list(context.user_data.keys())
    )
    logger.info(
        "🖼️ image_file_ids count=%d, category_id=%s",
        len(image_file_ids), category_id[:8] if category_id else 'EMPTY'
    )
    logger.info(
        "📦 product_details keys=%s, shared_attrs=%s, selector_attrs=%d",
        list(product_details.keys())[:10],
        str(product_details.get('shared_attributes', {}))[:200],
        len(product_details.get('selector_attributes', []))
    )

    api = KayisoftAPI(telegram_user_id=user_id, language=lang)

    # ── Step 1: Download images from Telegram (parallel) ───────────────────────
    # v6.2: Use asyncio.gather for concurrent downloads instead of sequential loop.
    # Result: 5 images download in ~1s (slowest) instead of 5× sequential waits.
    logger.info("🖼️ Starting parallel image download: %d images", len(image_file_ids))

    async def _download_one(bot, file_id: str) -> Optional[bytes]:
        try:
            tg_file = await bot.get_file(file_id)
            data    = bytes(await tg_file.download_as_bytearray())
            logger.info("✅ Downloaded image %s (%d bytes)", file_id[:8], len(data))
            return data
        except Exception as exc:
            logger.warning("❌ Could not download image %s: %s", file_id[:8], exc)
            return None

    results = await asyncio.gather(
        *[_download_one(query.get_bot(), fid) for fid in image_file_ids]
    )
    image_bytes_list = [r for r in results if isinstance(r, bytes) and r]

    # ── Step 2: Generate filenames (ISO-8601 timestamp + SHA-256) ─────────────
    uploaded_file_names = []
    if image_bytes_list:
        file_names = [_generate_filename(img) for img in image_bytes_list]

        # ── Step 3: Get signed S3 URLs from KAYISOFT API ─────────────────────
        logger.info("🔗 Requesting signed URLs for %d files, category=%s", len(file_names), category_id)
        signed_urls = await api.get_signed_urls(
            file_names=file_names,
            category_id=category_id,
        )
        logger.info("🔗 get_signed_urls response: %s", str(signed_urls)[:500] if signed_urls else "None/Empty")

        # ── Step 4: Upload images to S3 ────────────────────────────────────────────────────
        if signed_urls:
            for i, signed in enumerate(signed_urls):
                if i < len(image_bytes_list):
                    s3_url = signed.get("url", "")
                    file_name = signed.get("fileName", "")
                    logger.info("☁️ Uploading image %d/%d to S3: fileName=%s", i + 1, len(image_bytes_list), file_name)
                    success = await api.upload_media_to_s3(
                        signed_url=s3_url,
                        file_bytes=image_bytes_list[i],
                    )
                    if success:
                        uploaded_file_names.append(file_name)
                        logger.info("✅ S3 upload success %d/%d: %s", i + 1, len(image_bytes_list), file_name)
                    else:
                        logger.warning("❌ S3 upload FAILED for image %d/%d (url=%s)", i + 1, len(image_bytes_list), s3_url[:80])
        else:
            logger.warning("❌ Could not get signed URLs for user %s — signed_urls=%s", user_id, signed_urls)

    logger.info("📊 Image upload summary: %d/%d uploaded successfully", len(uploaded_file_names), len(image_file_ids))

    # ── Step 5: Build product payload ─────────────────────────────────────────
    product_name = product_details.get("name", product_details.get("raw_text", "")[:80])
    description  = product_details.get("description", "")
    price_raw    = product_details.get("price", "0")
    min_quantity = int(product_details.get("min_quantity", product_details.get("min_order", 1)))
    stock_count  = int(product_details.get("stock_count", product_details.get("stock", 100)))

    # v6.2: supplier_name from Telegram user (first_name + last_name)
    # More reliable than product_details since it comes directly from Telegram API.
    # Falls back to username, then to a generic label.
    tg_user = query.from_user
    if tg_user:
        _first = (tg_user.first_name or "").strip()
        _last  = (tg_user.last_name  or "").strip()
        supplier_name = f"{_first} {_last}".strip() or tg_user.username or "TopKap Supplier"
    else:
        supplier_name = product_details.get("supplier_name", "TopKap Supplier")
    logger.info("🏭 supplier_name resolved: %s", supplier_name)

    # Parse price safely (handles Arabic numerals, units, Turkish decimal format)
    price_float = _parse_price(price_raw)
    price_str   = str(price_raw)

    # CRITICAL: KAYISOFT API rejects variants with price <= 0
    # If price is still 0 after parsing, abort with a clear user-facing error
    if price_float <= 0:
        logger.error(
            "❌ handle_final_publish: price_float=%s (raw=%r) — "
            "aborting product creation to avoid HTTP 422 from KAYISOFT API",
            price_float, price_raw
        )
        price_error = {
            "tr": "❌ <b>Geçersiz fiyat.</b>\nLütfen geçerli bir fiyat girin (0'dan büyük olmalıdır).",
            "ar": "❌ <b>سعر غير صالح.</b>\nيرجى إدخال سعر صحيح (يجب أن يكون أكبر من صفر).",
            "en": "❌ <b>Invalid price.</b>\nPlease enter a valid price (must be greater than zero).",
        }
        await query.edit_message_text(
            price_error.get(lang, price_error["en"]),
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    logger.info(
        "💰 Price parsed successfully: raw=%r → float=%s",
        price_raw, price_float
    )

    # ── Build id→key map from raw_attributes ─────────────────────────────────
    # KAYISOFT API requires attribute KEY (e.g. "condition", "brand") as the dict key
    # for BOTH shared_attributes and selector_attributes — NOT the UUID.
    # raw_attributes is the full list from GET /categories/{id}/attributes.
    # We build a lookup: {attr_id (UUID) → attr_key (string)} for fast conversion.
    id_to_key = {}
    for attr in raw_attributes:
        attr_id_raw  = attr.get("id", "")
        attr_key_raw = attr.get("key", "")
        if attr_id_raw and attr_key_raw:
            id_to_key[attr_id_raw] = attr_key_raw
    logger.info("🔑 id_to_key map: %s", str(id_to_key)[:500])

    # Build shared_attributes: {attr_key: [option_id]} — NON-variant attributes
    # PDF spec: key = attribute.key (e.g. "condition"), value = [option_uuid, ...]
    # WRONG (old): {attr_uuid: [option_uuid]}  ← caused HTTP 422 Missing required attribute
    # RIGHT (new): {attr_key: [option_uuid]}   ← matches KAYISOFT API spec exactly
    ai_shared_attrs = product_details.get("shared_attributes", {})
    shared_attributes = {}
    for attr_id, option_ids in ai_shared_attrs.items():
        # Convert UUID key → string key using id_to_key map
        attr_key = id_to_key.get(attr_id, attr_id)  # fallback to UUID if key not found
        if isinstance(option_ids, list):
            if option_ids:  # Only add if not empty
                shared_attributes[attr_key] = option_ids
        else:
            if option_ids:  # Only add if not empty
                shared_attributes[attr_key] = [option_ids]
    logger.info("📋 shared_attributes (key-based): %s", str(shared_attributes)[:500])

    # Build selector_attributes: [{attribute_id, option_id}] — variant-defining
    # NOTE: selector_attributes in variants also need key-based format per PDF spec
    # The conversion is done inside _build_variants using id_to_key map
    ai_selector_attrs = product_details.get("selector_attributes", [])

    # Build variants with real uploaded filenames
    # id_to_key is passed so _build_variants can convert selector_attributes
    # from {attribute_id: uuid, option_id: uuid} to {attr_key: [option_uuid]}
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
        id_to_key           = id_to_key,
    )

    # v6.2: product_no format: TK-YYYYMMDD-XXXX (date-based, globally unique)
    _today = datetime.now(timezone.utc).strftime("%Y%m%d")
    _rand  = uuid.uuid4().hex[:6].upper()
    product_no = f"TK-{_today}-{_rand}"

    # Build the complete product payload matching KAYISOFT API spec exactly
    product_payload = {
        "name":               product_name,
        "product_no":         product_no,
        "category_id":        category_id,
        "shared_attributes":  shared_attributes,
        "variants":           variants,
    }

    # ── Step 6: Create product via KAYISOFT API ────────────────────────────────
    # ── DEBUG: log full payload to Railway logs for inspection ────────────────────
    import json as _json
    logger.info(
        "📦 PRODUCT PAYLOAD SENT TO API:\n%s",
        _json.dumps(product_payload, ensure_ascii=False, indent=2)[:4000],
    )

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
    # channel_id is retrieved via get_channel_id_for_user which checks:
    #   1. bot_data["user_channels"] (in-memory, fast)
    #   2. /data/user_channels.json  (persistent, survives Railway restarts)
    from bot.handlers.channel_handler import get_channel_id_for_user
    channel_id = get_channel_id_for_user(user_id, context) or context.user_data.get("channel_id")

    channel_published = False
    if channel_id:
        logger.info(
            "📢 Attempting channel publish: channel_id=%s, user_id=%s, images=%d",
            channel_id, user_id, len(image_file_ids)
        )
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
    else:
        logger.warning(
            "⚠️ No channel_id found for user_id=%s — product NOT published to channel. "
            "User must link a channel via /channel command.",
            user_id
        )

    # ── Success message ────────────────────────────────────────────────────────
    success_text = get_string(lang, "add_product_success")
    if channel_published:
        success_text += "\n\n" + get_string(lang, "add_product_channel_published")
    elif channel_id:
        # channel_id exists but publish failed (bot not admin or API error)
        channel_fail_texts = {
            "tr": (
                "⚠️ <b>Kanala yayınlanamadı.</b>\n"
                "Botun kanalda yönetici olduğundan emin olun, "
                "ardından 'Kanal Yönetimi' bölümünden kanalı yeniden bağlayın."
            ),
            "ar": (
                "⚠️ <b>فشل النشر على القناة.</b>\n"
                "تأكد أن البوت مشرف على قناتك، "
                "ثم أعد ربط القناة من قسم 'إدارة القناة'."
            ),
            "en": (
                "⚠️ <b>Failed to publish to channel.</b>\n"
                "Make sure the bot is an admin in your channel, "
                "then re-link it from 'Channel Management'."
            ),
        }
        success_text += "\n\n" + channel_fail_texts.get(lang, channel_fail_texts["en"])
        logger.error(
            "❌ Channel publish failed for user_id=%s channel_id=%s — "
            "bot may not be admin or channel_id is invalid",
            user_id, channel_id
        )
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
    user    = update.effective_user
    user_id = str(user.id)
    lang    = get_user_lang(user_id, telegram_language_code=user.language_code or "")

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
            CONFIRM_DETAILS: [
                # Supplier presses ✅ Confirm or ✏️ Edit below the AI summary
                CallbackQueryHandler(
                    handle_confirm_details,
                    pattern=r"^(details_confirm|details_edit)$",
                ),
            ],
            UPLOAD_IMAGES: [
                # Accept photos from camera or gallery
                MessageHandler(filters.PHOTO, handle_image_upload),
                # Accept photos sent as documents (high-res camera shots on some devices)
                MessageHandler(
                    filters.Document.IMAGE,
                    handle_image_upload,
                ),
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
