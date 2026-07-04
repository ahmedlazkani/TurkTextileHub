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
import json          # ← مطلوب لـ json.loads() في handle_webapp_data و handle_form_submitted
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
from bot.services.deepseek_service import deepseek_service, generate_channel_post
from bot.handlers.channel_stats import track_product_published

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
AI_POST_REVIEW     = 9   # Waiting for supplier to approve DeepSeek-generated channel post
UPLOAD_IMAGES      = 5   # Waiting for image uploads
CONFIRM_VARIANTS   = 6   # Waiting for variant preview confirmation
CONFIRM_PUBLISH    = 7   # Waiting for final publish confirmation
COLOR_UPLOAD       = 10  # Waiting for per-color image uploads (color-by-color flow)


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
# Support Button Helper
# Adds a Gmail mailto button below error messages so suppliers can contact us
# ══════════════════════════════════════════════════════════════════════════════

def _support_keyboard(lang: str, extra_buttons: list | None = None) -> InlineKeyboardMarkup:
    """
    Returns an InlineKeyboardMarkup with a Gmail support button.
    The button opens Gmail (or default mail app) with a pre-filled email
    to topkap.support@kayisoft.net in the user's language.

    Args:
        lang:          User language code ("ar", "tr", "en")
        extra_buttons: Optional list of additional InlineKeyboardButton rows
                       to include ABOVE the support button row.

    Returns:
        InlineKeyboardMarkup with support button (and optional extra rows)

    Gmail mailto URL format:
        mailto:EMAIL?subject=SUBJECT&body=BODY
    """
    subjects = {
        "ar": "مساعدة — TopKap",
        "tr": "Destek — TopKap",
        "en": "Support — TopKap",
    }
    bodies = {
        "ar": "مرحباً فريق TopKap،\n\nأحتاج مساعدة بخصوص:\n\n",
        "tr": "Merhaba TopKap ekibi,\n\nŞu konuda yardıma ihtiyacım var:\n\n",
        "en": "Hello TopKap team,\n\nI need help with:\n\n",
    }
    labels = {
        "ar": "📧 تواصل مع الدعم",
        "tr": "📧 Destek ile iletişim",
        "en": "📧 Contact Support",
    }

    # Use simple mailto URL with subject only.
    # Telegram rejects mailto: URLs with non-ASCII body content (Button_url_invalid).
    # Solution: encode subject only using ASCII-safe percent-encoding, omit body.
    import urllib.parse
    # Use only ASCII-safe subject to avoid Telegram's Button_url_invalid error
    subject_map = {
        "ar": "Help - TopKap",
        "tr": "Destek - TopKap",
        "en": "Support - TopKap",
    }
    subject = urllib.parse.quote(subject_map.get(lang, subject_map["en"]), safe="")
    gmail_url = f"https://mail.google.com/mail/?view=cm&to=topkap.support%40kayisoft.net&su={subject}"

    support_row = [InlineKeyboardButton(
        labels.get(lang, labels["en"]),
        url=gmail_url,
    )]

    rows = list(extra_buttons) if extra_buttons else []
    rows.append(support_row)
    return InlineKeyboardMarkup(rows)



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

    import logging as _logging
    _log = _logging.getLogger(__name__)

    for attr in raw_attributes:
        attr_id = attr.get("id")
        if not attr_id:
            continue

        # ── Deduplicate attribute name at the source ─────────────────────────────
        # KAYISOFT API sometimes returns duplicated names like 'نسائي نسائي' or 'XS XS'.
        # We fix this here once so ALL downstream code (summary, post, variants) gets
        # clean names without needing per-call deduplication.
        _log.info(f"[DEDUP_DEBUG] attr raw id={attr.get('id')!r} name={attr.get('name')!r} value={attr.get('value')!r}")
        if attr.get("name"):
            attr["name"] = _deduplicate_name(attr["name"])
        # Also deduplicate every option name/label inside this attribute
        for opt in attr.get("options", []):
            if not isinstance(opt, dict):
                continue
            _log.info(f"[DEDUP_DEBUG]   opt raw id={opt.get('id')!r} name={opt.get('name')!r} label={opt.get('label')!r} value={opt.get('value')!r}")
            if opt.get("name"):
                opt["name"] = _deduplicate_name(opt["name"])
            if opt.get("label"):
                opt["label"] = _deduplicate_name(opt["label"])
            # Handle pipe-separated value like '#FF0000|أحمر أحمر' → '#FF0000|أحمر'
            raw_val = str(opt.get("value", ""))
            if "|" in raw_val:
                hex_part, label_part = raw_val.split("|", 1)
                clean_label = _deduplicate_name(label_part.strip())
                opt["value"] = f"{hex_part.strip()}|{clean_label}"
                if not opt.get("label"):
                    opt["label"] = clean_label

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
    product_name_tr: str = "",
    description_tr: str = "",
    product_name_ar: str = "",
    description_ar: str = "",
    color_uploaded_map: dict = None,  # BUG FIX Band 12: {color_option_id: [s3_filename]}
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
        """
        Build the multilingual titles list required by KAYISOFT API.

        Priority per language slot:
          1. Explicit per-language field (name_ar / name_tr / name_en) — set by AI
             extraction or by Band-6 fix in handle_form_submitted.
          2. name_local — the text the supplier actually typed.  Used only for the
             slot that matches the supplier's own language (lang_code).  For other
             language slots we intentionally leave the text as name_local too
             (KAYISOFT backend will translate), but we mark it clearly in the
             comment so a future translation layer can replace it.

        Band-6 root-cause fix:
          The old code had `(name_local if lang_code == "ar" else name_local)` which
          always resolved to name_local regardless of lang_code, causing every
          language slot to receive the supplier's language text (e.g. Turkish text
          in the Arabic slot).  Now each slot uses its dedicated field first.
        """
        _per_lang = {
            "ar": product_name_ar or (name_local if lang_code == "ar" else ""),
            "tr": product_name_tr or (name_local if lang_code == "tr" else ""),
            "en": name_en or product_name_en or (name_local if lang_code == "en" else ""),
        }
        # Final fallback: if a slot is still empty, use name_local so the API
        # always receives a non-empty string (KAYISOFT rejects blank titles).
        titles = [
            {"language": lng, "text": _per_lang.get(lng) or name_local}
            for lng in SUPPORTED_LANGS
        ]
        return titles

    def _build_descriptions(desc_local: str, desc_en: str, lang_code: str) -> list:
        """
        Build the multilingual descriptions list required by KAYISOFT API.
        Same logic as _build_titles — see its docstring for details.
        """
        _per_lang = {
            "ar": description_ar or (desc_local if lang_code == "ar" else ""),
            "tr": description_tr or (desc_local if lang_code == "tr" else ""),
            "en": desc_en or description_en or (desc_local if lang_code == "en" else ""),
        }
        descs = [
            {"language": lng, "text": _per_lang.get(lng) or desc_local}
            for lng in SUPPORTED_LANGS
        ]
        return descs

    # ── If no selector attributes → single variant ──────────────────────────────────────────────────────────────────────────────────
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

    # ── KAYISOFT API RULE: each variant's selector_attributes must have EXACTLY ONE option
    # per attribute. We must create one variant per combination of (primary_option × other_options).
    #
    # Example: sizes=[S, M, L], colors=[Red, Blue]
    #   → 6 variants: (S,Red), (S,Blue), (M,Red), (M,Blue), (L,Red), (L,Blue)
    #
    # If only one selector attribute (e.g. sizes=[S, M, L]):
    #   → 3 variants: (S,), (M,), (L,)
    #
    # _to_selector_dict MUST receive exactly one {attribute_id, option_id} per attribute
    # so that the resulting dict is {attr_key: [single_option_uuid]}.
    # ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────

    # Step 1: Group all selector entries by attribute_id
    # Each group = one attribute with potentially multiple selected options
    from collections import defaultdict
    attr_groups: dict[str, list[str]] = defaultdict(list)  # {attribute_id: [option_id, ...]}
    for sel in ai_selector_attrs:
        attr_id   = sel.get("attribute_id", "")
        option_id = sel.get("option_id", "")
        if attr_id and option_id:
            attr_groups[attr_id].append(option_id)

    if not attr_groups:
        # All entries were malformed → single fallback variant
        return [{
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "visibility_status":   "public",
            "titles":              _build_titles(product_name, product_name_en, lang),
            "descriptions":        _build_descriptions(description, description_en, lang),
            "prices":              [{"min_quantity": min_quantity, "price": price_float}],
            "images":              uploaded_file_names,
            "videos":              [],
            "dimensions":          None,
        }]

    # Step 2: Identify the PRIMARY variant attribute (is_primary_variant_attribute=True)
    # This is the axis along which images are distributed (e.g. color).
    # All other attributes are secondary (e.g. size, material).
    primary_attr_id = None
    for attr in raw_attributes:
        if attr.get("is_primary_variant_attribute") and attr.get("is_variant_selector"):
            primary_attr_id = attr.get("id")
            break
    # Fallback: use the attribute with the most options as primary
    if not primary_attr_id:
        primary_attr_id = max(attr_groups, key=lambda k: len(attr_groups[k]))

    primary_options  = attr_groups.get(primary_attr_id, [])
    secondary_groups = {k: v for k, v in attr_groups.items() if k != primary_attr_id}

    # Step 3: Cartesian product of primary × secondary options
    # Each combination becomes one variant with EXACTLY ONE option per attribute.
    import itertools

    # Build list of (attr_id, option_id) tuples for secondary attributes
    secondary_axes = [
        [(attr_id, opt_id) for opt_id in opt_ids]
        for attr_id, opt_ids in secondary_groups.items()
    ]

    # Cartesian product: primary_option × secondary_axis_1 × secondary_axis_2 ...
    if secondary_axes:
        combinations = list(itertools.product(primary_options, *secondary_axes))
    else:
        combinations = [(opt,) for opt in primary_options]

    # Step 4: Distribute images across variants
    # BUG FIX (Band 12): If color_uploaded_map is provided, use it to assign
    # each color variant its own images instead of distributing evenly.
    # Strategy:
    #   - color_uploaded_map provided → assign per-color images to matching variants
    #   - 1 variant  → all images
    #   - N variants, images >= N → distribute evenly
    #   - N variants, images < N  → all images duplicated to every variant
    n_variants = len(combinations)
    n_images   = len(uploaded_file_names)
    images_per_variant: list[list] = []

    if color_uploaded_map and n_variants > 1:
        # Per-color image assignment: match primary option_id to color_uploaded_map
        for combo in combinations:
            primary_opt_id = combo[0]
            color_imgs = color_uploaded_map.get(primary_opt_id, [])
            if not color_imgs:
                # Fallback: use all images if this color has no specific images
                color_imgs = uploaded_file_names
            images_per_variant.append(color_imgs)
    elif n_variants <= 1 or n_images == 0:
        images_per_variant = [uploaded_file_names] * max(1, n_variants)
    elif n_images < n_variants:
        images_per_variant = [uploaded_file_names] * n_variants
    else:
        chunk = n_images // n_variants
        for i in range(n_variants):
            start = i * chunk
            end   = start + chunk if i < n_variants - 1 else n_images
            images_per_variant.append(uploaded_file_names[start:end])

    # Step 5: Build one variant dict per combination
    variants = []
    for i, combo in enumerate(combinations):
        # combo[0] = primary option_id (str)
        # combo[1..] = (attr_id, option_id) tuples for secondary attributes
        primary_opt_id = combo[0]

        # Build selector_attributes dict: {attr_key: [single_option_uuid]}
        sel_dict: dict[str, list] = {}

        # Primary attribute → exactly one option
        primary_key = _key_map.get(primary_attr_id, primary_attr_id)
        sel_dict[primary_key] = [primary_opt_id]

        # Secondary attributes → exactly one option each
        for sec_pair in combo[1:]:
            sec_attr_id, sec_opt_id = sec_pair
            sec_key = _key_map.get(sec_attr_id, sec_attr_id)
            sel_dict[sec_key] = [sec_opt_id]

        variant_images = images_per_variant[i] if i < len(images_per_variant) else []

        variants.append({
            "stock_id":            f"VAR-{uuid.uuid4().hex[:8].upper()}",
            "stock_count":         stock_count,
            "visibility_status":   "public",
            # tax_percentage & cost_price omitted entirely:
            # API requires positive number or absence; null causes HTTP 422
            "titles":              _build_titles(product_name, product_name_en, lang),
            "descriptions":        _build_descriptions(description, description_en, lang),
            "selector_attributes": sel_dict,
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
    Builds a human-readable GROUPED preview of the auto-generated variants.

    Instead of listing every variant separately (#1 Siyah|M, #2 Siyah|L...),
    this groups by attribute and shows unique values:
      🎨 Renk: ⬛ Siyah, ⬜ Beyaz
      📏 Beden: M, L, XL
      💰 3.0 ₺ | 📦 500 pcs

    Args:
        lang:     Supplier's language code
        variants: List of variant dicts (from _build_variants)
        attr_map: Dict mapping attr_id → attr dict (from _process_attributes)

    Returns:
        str: HTML-formatted preview text
    """
    import re as _re_prev

    headers = {
        "tr": "🔄 <b>Ürün Varyantları</b>",
        "ar": "🔄 <b>متغيرات المنتج</b>",
        "en": "🔄 <b>Product Variants</b>",
    }
    header = headers.get(lang, headers["en"])

    # ── Helper: resolve a single option UUID → human display value ──────────
    def _resolve_option(attr_obj: dict, option_uuid: str) -> str:
        for opt in attr_obj.get("options", []):
            if opt.get("id") == option_uuid:
                raw_val   = opt.get("value", "")
                label_val = opt.get("label") or opt.get("name") or ""
                # Handle pipe-separated: "#FF000000|Siyah"
                if "|" in raw_val:
                    hex_part, lbl = raw_val.split("|", 1)
                    raw_val = hex_part.strip()
                    if not label_val:
                        label_val = lbl.strip()
                elif "|" in label_val:
                    hex_part, lbl = label_val.split("|", 1)
                    raw_val = hex_part.strip()
                    label_val = lbl.strip()
                # Prefer human label
                display = label_val if label_val else (raw_val if raw_val else option_uuid)
                # Add color emoji
                if raw_val and _re_prev.match(r'^#?[0-9A-Fa-f]{6,8}$', raw_val.strip()):
                    emoji = _render_color_value(raw_val)
                    is_hex = _re_prev.match(r'^#?[0-9A-Fa-f]{6,8}$', display.strip())
                    display = emoji if is_hex else f"{emoji} {display}"
                return display
        return option_uuid

    # ── Collect unique values per attribute across all variants ─────────────
    # attr_key → (attr_name, [unique_display_values], seen_set)
    attr_order: list   = []  # ordered list of attr_keys
    attr_names: dict   = {}  # attr_key → human name
    attr_values: dict  = {}  # attr_key → list of unique display values (ordered)
    attr_seen: dict    = {}  # attr_key → set of seen display values

    for variant in variants:
        selectors = variant.get("selector_attributes", {})
        if isinstance(selectors, dict):
            for attr_key, option_ids in selectors.items():
                option_uuid = option_ids[0] if option_ids else ""
                # Resolve attr name
                if attr_key not in attr_names:
                    attr_order.append(attr_key)
                    attr_names[attr_key] = attr_key  # fallback
                    attr_values[attr_key] = []
                    attr_seen[attr_key]   = set()
                    for _, attr_obj in attr_map.items():
                        if attr_obj.get("key") == attr_key:
                            attr_names[attr_key] = attr_obj.get("name", attr_key)
                            break
                # Resolve option display
                display = option_uuid
                for _, attr_obj in attr_map.items():
                    if attr_obj.get("key") == attr_key:
                        display = _resolve_option(attr_obj, option_uuid)
                        break
                if display not in attr_seen[attr_key]:
                    attr_seen[attr_key].add(display)
                    attr_values[attr_key].append(display)
        else:
            # Legacy list format
            for sel in selectors:
                if not isinstance(sel, dict):
                    continue
                attr_id   = sel.get("attribute_id", "")
                option_id = sel.get("option_id", "")
                attr_obj  = attr_map.get(attr_id, {})
                attr_key  = attr_obj.get("key", attr_id)
                if attr_key not in attr_names:
                    attr_order.append(attr_key)
                    attr_names[attr_key]  = attr_obj.get("name", attr_id)
                    attr_values[attr_key] = []
                    attr_seen[attr_key]   = set()
                display = _resolve_option(attr_obj, option_id)
                if display not in attr_seen[attr_key]:
                    attr_seen[attr_key].add(display)
                    attr_values[attr_key].append(display)

    # ── Get price and stock from first variant ───────────────────────────────
    price = variants[0].get("prices", [{}])[0].get("price", 0) if variants else 0
    stock = variants[0].get("stock_count", 0) if variants else 0
    total = len(variants)

    # ── Build output ─────────────────────────────────────────────────────────
    variant_count_labels = {
        "tr": f"📊 Toplam {total} varyant",
        "ar": f"📊 إجمالي {total} متغير",
        "en": f"📊 Total {total} variants",
    }

    lines = [header, "", variant_count_labels.get(lang, variant_count_labels["en"]), ""]

    for attr_key in attr_order:
        name   = attr_names.get(attr_key, attr_key)
        values = attr_values.get(attr_key, [])
        lines.append(f"🎨 <b>{name}:</b> {', '.join(values)}")

    lines.append("")
    lines.append(f"💰 {price} ₺  |  📦 {stock} pcs")
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
    attributes: list = None,       # list of {"name": str, "value": str} for DeepSeek post
    share_link_chat: str = "",     # KAYISOFT deep link: start-chat-variant
    share_link_details: str = "",  # KAYISOFT deep link: product-variant details
    post_languages: list = None,   # languages for the AI post; defaults to ["ar","tr","en"]
) -> bool:
    """
    Publishes a professional product post to the supplier's Telegram channel.

    Publishing strategy:
    - Multiple images → MediaGroup album (caption on first) + buttons as follow-up
    - Single image    → Photo with caption + inline buttons
    - No images       → Text message with inline buttons

    Button URLs (per TelegramBackendEndpoints spec, orange section):
    - share_link_chat    (KAYISOFT dynalinks) → opens supplier chat for this variant
    - share_link_details (KAYISOFT dynalinks) → opens product variant detail page
    - Falls back to legacy _product_chat_url / _supplier_page_url if not provided.

    Args:
        context:             Bot context for API calls
        channel_id:          Telegram channel ID (e.g. "@mychannel" or "-100...")
        lang:                Language code for localized labels
        image_file_ids:      List of Telegram file_ids for product images
        product_name:        Product title
        description:         Product description
        price:               Price string
        min_order:           Minimum order quantity
        supplier_name:       Supplier's display name
        product_id:          KAYISOFT product UUID
        supplier_id:         KAYISOFT supplier UUID
        share_link_chat:     KAYISOFT deep link for chat (optional, falls back to legacy)
        share_link_details:  KAYISOFT deep link for product details (optional, falls back)

    Returns:
        bool: True on success, False on any failure
    """
    # ── Build keyboard using KAYISOFT share_links (or fallback to legacy URLs) ───
    # Per TelegramBackendEndpoints spec (orange section):
    #   - share_link_chat    → btn_chat button URL
    #   - share_link_details → btn_page button URL
    # If KAYISOFT did not return share_links, fall back to legacy URL builders.
    _btn_chat_url = share_link_chat    or _product_chat_url(product_id, supplier_id)
    _btn_page_url = share_link_details or _supplier_page_url(supplier_id)

    _btn_labels = {
        "ar": {"btn_chat": "💬 تواصل مع المورد",  "btn_page": "🛒 عرض المنتج"},
        "tr": {"btn_chat": "💬 Tedarikçiyle Sohbet", "btn_page": "🛒 Ürünü Görüntüle"},
        "en": {"btn_chat": "💬 Chat with Supplier",  "btn_page": "🛒 View Product"},
    }
    _L_btn = _btn_labels.get(lang, _btn_labels["en"])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_L_btn["btn_chat"], url=_btn_chat_url)],
        [InlineKeyboardButton(_L_btn["btn_page"], url=_btn_page_url)],
    ])

    logger.info(
        "🔗 Channel buttons: chat=%s | details=%s",
        _btn_chat_url[:60] if _btn_chat_url else "(fallback)",
        _btn_page_url[:60] if _btn_page_url else "(fallback)",
    )

    # ── Build post caption via DeepSeek AI (professional copywriting) ─────────
    # DeepSeek generates a polished, multilingual channel post.
    # Falls back to static _build_channel_post caption if AI fails.
    from bot.services.deepseek_service import generate_channel_post as _gen_post
    product_data_for_ai = {
        "name":         product_name,
        "description":  description,
        "price":        price,
        "min_quantity": min_order,
        "product_code": None,
        "notes":        None,
        "attributes":   attributes or [],
    }
    # Use the languages selected by the supplier; fall back to all 3 if not specified
    if not post_languages:
        post_languages = ["ar", "tr", "en"]
    logger.info("🤖 Generating AI channel post via DeepSeek (languages=%s)...", post_languages)
    ai_caption = await _gen_post(product_data_for_ai, post_languages)
    if ai_caption:
        caption = ai_caption
        logger.info("✅ AI channel post generated (%d chars)", len(caption))
    else:
        # Fallback: use static caption from _build_channel_post
        logger.warning("⚠️ AI post generation failed — using static caption fallback")
        caption, _ = _build_channel_post(
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
            # Even if this fails, the album was already published — treat as success
            try:
                sep = "─" * 24
                await context.bot.send_message(
                    chat_id=channel_id,
                    text=sep,
                    reply_markup=keyboard,
                )
            except Exception as btn_exc:
                logger.warning("⚠️ Could not send buttons after album: %s", btn_exc)

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


async def _send_new_product_notification(
    bot,
    channel_id: str,
    product_name: str,
    lang: str,
    share_link_details: str = "",
) -> None:
    """
    Sends a short notification to the channel subscribers immediately
    after a new product is published.

    This is a separate, brief message (not the full product post)
    that acts as a "ping" to attract attention.

    Programmatic note:
      This is a fire-and-forget call. Errors are caught and logged
      but do NOT block the main publish flow.
    """
    notif_texts = {
        "ar": (
            f"🔔 <b>منتج جديد متاح الآن</b>\n\n"
            f"📦 {product_name}\n\n"
            "⬇️ اضغط على زر عرض المنتج أدناه للاطلاع على التفاصيل."
        ),
        "tr": (
            f"🔔 <b>Yeni Ürün Müsait</b>\n\n"
            f"📦 {product_name}\n\n"
            "⬇️ Detaylar için aşağıdaki ürün görüntcalme düğmesine basın."
        ),
        "en": (
            f"🔔 <b>New Product Available</b>\n\n"
            f"📦 {product_name}\n\n"
            "⬇️ Tap the product button below to view the details."
        ),
    }
    text = notif_texts.get(lang, notif_texts["en"])

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    if share_link_details:
        view_labels = {"ar": "🛒 عرض المنتج", "tr": "🛒 Ürünü Gör", "en": "🛒 View Product"}
        buttons.append([InlineKeyboardButton(
            view_labels.get(lang, view_labels["en"]),
            url=share_link_details,
        )])
    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info("🔔 New product notification sent to channel %s", channel_id)
    except Exception as exc:
        logger.warning("⚠️ Could not send new product notification to channel %s: %s", channel_id, exc)


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

    raw_hex = hex_match.group(1)
    # KAYISOFT API uses AARRGGBB format (8 digits) — skip first 2 (alpha) to get RGB
    # Standard 6-digit hex is RRGGBB — use directly
    if len(raw_hex) == 8:
        hex_digits = raw_hex[2:8]  # skip alpha channel (first 2 digits)
    else:
        hex_digits = raw_hex[:6]
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



def _deduplicate_name(name: str) -> str:
    """
    Removes duplicated words from option names returned by KAYISOFT API.
    KAYISOFT sometimes returns names like 'XS XS', 'M M', 'L L', 'XL XL'.
    This function detects and removes the duplication.
    Examples:
        'XS XS'  → 'XS'
        'M M'    → 'M'
        'XL XL'  → 'XL'
        'Satin Satin' → 'Satin'
        'Navy Blue'  → 'Navy Blue'  (not duplicated, unchanged)
    """
    if not name:
        return name
    parts = name.strip().split()
    if len(parts) >= 2:
        half = len(parts) // 2
        if len(parts) % 2 == 0 and parts[:half] == parts[half:]:
            return " ".join(parts[:half])
    return name


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
    ]

    # Show extracted attributes if any
    shared_attrs   = data.get("shared_attributes", {})
    selector_attrs = data.get("selector_attributes", [])

    if shared_attrs or selector_attrs:
        attr_header = {"tr": "\n━━━━━━━━━━━━━━━━━━━━\n📋 <b>Özellikler:</b>", "ar": "\n━━━━━━━━━━━━━━━━━━━━\n📋 <b>الخصائص:</b>", "en": "\n━━━━━━━━━━━━━━━━━━━━\n📋 <b>Attributes:</b>"}
        lines.append(attr_header.get(lang, attr_header["en"]))

        for attr_id, option_ids in shared_attrs.items():
            attr = attr_map.get(attr_id) or attr_key_map.get(attr_id, {})
            attr_name = _deduplicate_name(attr.get("name") or attr.get("key") or attr_id)
            # Deduplicate option_ids to avoid showing same option twice
            seen_opt_ids: list = []
            for oid in (option_ids if isinstance(option_ids, list) else [option_ids]):
                if oid not in seen_opt_ids:
                    seen_opt_ids.append(oid)
            option_values = []
            for opt_id in seen_opt_ids:
                for opt in attr.get("options", []):
                    if opt.get("id") == opt_id:
                        # Prefer label/name over value (which may be a raw hex code)
                        # label = human-readable color name (e.g. "Bej", "بيج")
                        # value = raw hex code (e.g. "#FFF5F5DC") — used for API, not display
                        # Prefer label (already deduped by webapp_routes proxy)
                        # over name (may still contain 'نسائي نسائي' from raw API)
                        raw_display = (
                            opt.get("label")
                            or opt.get("name")
                            or opt.get("value", opt_id)
                        )
                        # Strip pipe-separated hex prefix if present: "#FF0000|أحمر" → "أحمر"
                        if "|" in (raw_display or ""):
                            raw_display = raw_display.split("|", 1)[-1].strip()
                        display = _deduplicate_name(raw_display)
                        option_values.append((display, opt.get("value", "")))
                        break
                else:
                    # opt_id not found in options list — try fuzzy match by UUID prefix
                    # (AI sometimes generates a UUID with a single-char typo)
                    _fuzzy_display = None
                    for opt in attr.get("options", []):
                        real_id = opt.get("id", "")
                        if real_id and opt_id[:20].lower() == real_id[:20].lower():
                            raw_d = opt.get("label") or opt.get("name") or opt.get("value", "")
                            if "|" in (raw_d or ""):
                                raw_d = raw_d.split("|", 1)[-1].strip()
                            _fuzzy_display = _deduplicate_name(raw_d) if raw_d else None
                            break
                    if _fuzzy_display:
                        option_values.append((_fuzzy_display, ""))
                    else:
                        # Last resort: show UUID as-is (shouldn't happen in normal flow)
                        option_values.append((_deduplicate_name(str(opt_id)), ""))
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
             # Each attribute on its own line with separator
            values_str = ' | '.join(rendered_values)
            lines.append(f"  ┣ <b>{attr_name}:</b> {values_str}")
            lines.append("")

        # ── Group selector_attrstor_attrs by attribute_id so each attribute appears on ONE line \u2500\u2500
        # e.g. instead of: \u2022 Size: M / \u2022 Size: L / \u2022 Size: XL
        # we show:         \u2022 Size: M, L, XL
        import re as _re
        from collections import OrderedDict as _OD
        sel_grouped: dict = _OD()  # attr_id → {"name": str, "values": list}
        for sel in selector_attrs:
            attr_id   = sel.get("attribute_id", "")
            option_id = sel.get("option_id", "")
            if not attr_id:
                continue
            if attr_id not in sel_grouped:
                attr      = attr_map.get(attr_id) or attr_key_map.get(attr_id, {})
                attr_name = _deduplicate_name(attr.get("name") or attr.get("key") or attr_id)
                sel_grouped[attr_id] = {"name": attr_name, "attr": attr, "values": [], "seen_opts": set()}
            # Deduplicate option_ids
            if option_id not in sel_grouped[attr_id]["seen_opts"]:
                sel_grouped[attr_id]["seen_opts"].add(option_id)
                sel_grouped[attr_id]["values"].append(option_id)

        for attr_id, grp in sel_grouped.items():
            attr      = grp["attr"]
            attr_name = grp["name"]
            rendered_values = []
            for option_id in grp["values"]:
                display_val = option_id
                raw_val     = ""
                for opt in attr.get("options", []):
                    if opt.get("id") == option_id:
                        # Prefer human label over raw hex value
                        # Prefer label (already deduped) over name (may have 'نسائي نسائي')
                        raw_name = (
                            opt.get("label")
                            or opt.get("name")
                            or opt.get("value", option_id)
                        )
                        raw_val  = opt.get("value", "")
                        # Parse pipe-separated format: "#FFFFFFFF|أبيض" → label="أبيض"
                        if "|" in raw_name:
                            _, display_val = raw_name.split("|", 1)
                            display_val = display_val.strip()
                            raw_val = raw_name.split("|", 1)[0].strip()
                        elif "|" in raw_val:
                            raw_val, lbl = raw_val.split("|", 1)
                            raw_val = raw_val.strip()
                            display_val = lbl.strip() if lbl.strip() else raw_name
                        else:
                            display_val = raw_name
                        display_val = _deduplicate_name(display_val)
                        break
                # Strip any remaining hex from display_val
                if "|" in display_val:
                    _, display_val = display_val.split("|", 1)
                    display_val = display_val.strip()
                if _re.match(r'^#?[0-9A-Fa-f]{6,8}$', display_val.strip()):
                    display_val = ""  # pure hex — use emoji only
                emoji = _render_color_value(raw_val if raw_val else option_id)
                if display_val:
                    rendered_values.append(f"{emoji} {display_val}" if emoji != display_val else display_val)
                else:
                    rendered_values.append(emoji)
            # Each attribute on its own line with separator
            values_str = ' | '.join(rendered_values)
            lines.append(f"  ┣ <b>{attr_name}:</b> {values_str}")
            lines.append("")

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

    # ── حفظ اللغة في user_data لاستخدامها في كل خطوات التدفق ────────────────────────────────
    context.user_data["lang"] = lang

    # ── دعم كلا الحالتين: message (زر ReplyKeyboard) و callback_query (زر inline) ──────────
    # عند الاستدعاء من زر "إضافة منتج جديد" بعد النشر، update.message يكون None
    _query = update.callback_query
    if _query:
        await _query.answer()
        async def _send_msg(text, **kwargs):
            return await context.bot.send_message(
                chat_id=update.effective_chat.id, text=text, **kwargs
            )
    else:
        async def _send_msg(text, **kwargs):
            return await update.message.reply_text(text, **kwargs)

    # ── مهمة 5: فحص وجود channel_id قبل بدء التدفق ─────────────────────────────────────────
    # القناة اختيارية: إذا لم يربط المورد قناته، نُرسل إشعاراً تحفيزياً ونكمل التدفق
    # المنتج يُنشر على KAYISOFT بكل الأحوال، والقناة تُستخدم فقط إذا كانت مربوطة
    from bot.handlers.channel_handler import get_channel_id_for_user
    from bot.keyboards import supplier_main_keyboard
    channel_id = get_channel_id_for_user(user_id, context)
    if not channel_id:  # Channel is REQUIRED — supplier must link before adding products
        setup_msgs = {
            "ar": (
                "📢 <b>خطوة مهمة قبل إضافة المنتجات!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "لنشر منتجاتك تلقائياً على قناتك، يجب أولاً:\n\n"
                "1️⃣ <b>إنشاء قناة تيليجرام</b> (إذا لم تكن موجودة)\n"
                "   → اضغط (+) في تيليجرام ← قناة جديدة\n\n"
                "2️⃣ <b>إضافة البوت كمشرف</b>\n"
                "   → افتح القناة ← المشرفون ← أضف @TopKapTR_bot\n"
                "   → امنحه صلاحية: نشر الرسائل ✅\n\n"
                "3️⃣ <b>انتظر الاكتشاف التلقائي</b>\n"
                "   → سيرسل البوت تأكيداً فور إضافته\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 أو أرسل: /setchannel -1001234567890\n"
                "🚀 بعد الإعداد ستتمكن من النشر لـ 180+ دولة!"
            ),
            "tr": (
                "📢 <b>Ürün eklemeden önce önemli adım!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Ürünlerinizi kanalınıza otomatik yayınlamak için:\n\n"
                "1️⃣ <b>Telegram kanalı oluşturun</b>\n"
                "   → Telegram'da (+) → Yeni Kanal\n\n"
                "2️⃣ <b>Botu kanal yöneticisi yapın</b>\n"
                "   → Kanalı açın → Yöneticiler → @TopKapTR_bot ekleyin\n"
                "   → Mesaj gönderme yetkisi verin ✅\n\n"
                "3️⃣ <b>Otomatik tespiti bekleyin</b>\n"
                "   → Bot eklenince onay mesajı gelecek\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 Veya gönderin: /setchannel -1001234567890\n"
                "🚀 Kurulum sonrası 180+ ülkeye ürün yayınlayın!"
            ),
            "en": (
                "📢 <b>One step before adding products!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "To auto-publish products to your channel:\n\n"
                "1️⃣ <b>Create a Telegram channel</b>\n"
                "   → Tap (+) in Telegram → New Channel\n\n"
                "2️⃣ <b>Add bot as admin</b>\n"
                "   → Open channel → Admins → Add @TopKapTR_bot\n"
                "   → Grant: Post Messages ✅\n\n"
                "3️⃣ <b>Wait for auto-detection</b>\n"
                "   → Bot sends confirmation once added\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 Or send: /setchannel -1001234567890\n"
                "🚀 After setup, reach 180+ countries!"
            ),
        }
        # Inline buttons: channel ID guide + support
        channel_id_rows = {
            "ar": [InlineKeyboardButton("🔗 أعرف كيف أحصل على معرّف قناتي", callback_data="how_to_get_channel_id")],
            "tr": [InlineKeyboardButton("🔗 Kanal ID'mi nasıl öğrenirim?", callback_data="how_to_get_channel_id")],
            "en": [InlineKeyboardButton("🔗 How to get my channel ID?", callback_data="how_to_get_channel_id")],
        }
        await _send_msg(
            setup_msgs.get(lang, setup_msgs["en"]),
            parse_mode="HTML",
            reply_markup=_support_keyboard(lang, extra_buttons=[channel_id_rows.get(lang, channel_id_rows["en"])]),
        )
        return ConversationHandler.END
    # ── نهاية فحص القناة ──────────────────────────────────────────────────────────────────────────────────────

    # Clear any previous product data to start fresh
    context.user_data.pop("product_data", None)

    # Show typing indicator for better UX
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    # Show loading message with progress bar
    progress = _progress_bar(1)
    loading_msg = await _send_msg(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_categories')}",
        parse_mode=ParseMode.HTML,
    )

    # Fetch root categories from KAYISOFT API (parent="" → root level)
    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    try:
        categories = await api.get_categories()
    except Exception as exc:
        logger.error("start_add_product: unexpected exception from get_categories: %s", exc)
        categories = None

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
        retry_row = [InlineKeyboardButton(
            retry_labels.get(lang, retry_labels["en"]),
            callback_data="retry_add_product",
        )]
        await loading_msg.edit_text(
            error_texts.get(lang, error_texts["en"]),
            parse_mode=ParseMode.HTML,
            reply_markup=_support_keyboard(lang, extra_buttons=[retry_row]),
        )
        return ConversationHandler.END

    # Build inline keyboard — ONE button per row for main categories
    # ── Rationale: same as subcategories — full-width rows prevent name truncation
    # is_visible_for_creating=True means this category accepts new products
    # Also build a name lookup map so later steps can show the selected category name
    # ── Band 1 FIX: Sort categories by ui_order (ascending) as provided by the API ──
    # ui_order is the canonical display order defined by the backend.
    # Fallback to 9999 for categories without ui_order so they appear last.
    visible_cats = [c for c in categories if c.get("is_visible_for_creating", True)]
    visible_cats.sort(key=lambda c: (int(c.get("ui_order") or 9999), c.get("name", "").lower()))

    categories_map = {}
    buttons_flat = []
    for cat in visible_cats:
        cid   = cat.get("id")
        cname = cat.get("name", "—")
        categories_map[cid] = cname
        buttons_flat.append(InlineKeyboardButton(cname, callback_data=f"cat_{cid}"))
    # One button per row — full-width, no truncation
    keyboard = [[btn] for btn in buttons_flat]

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
    # Use lang stored in user_data (set at start_add_product) for consistency
    # Fallback to get_user_lang only if user_data was cleared unexpectedly
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")
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

    # Build subcategory keyboard — ONE button per row (sequential layout)
    # ── Rationale: two-per-row causes names to be truncated with "..." in Telegram
    #    (Telegram limits inline button text to ~20 chars per button in 2-col layout).
    #    One-per-row gives each button the full message width, so names like
    #    "Erkek Spor Giyim & Aksesuar" are always fully visible.
    # ── Band 1 FIX: Sort subcategories by ui_order (ascending) as provided by the API ──
    visible_subs = [s for s in subcategories if s.get("is_visible_for_creating", True)]
    visible_subs.sort(key=lambda s: (int(s.get("ui_order") or 9999), s.get("name", "").lower()))

    subcategories_map = {}
    # Each sub-list is a single row → one button per row (full-width, no truncation)
    keyboard = []
    for sub in visible_subs:
        sid   = sub.get("id")
        sname = sub.get("name", "—")
        subcategories_map[sid] = sname
        keyboard.append([InlineKeyboardButton(sname, callback_data=f"sub_{sid}")])
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

    # Add back button to return to root category selection
    _back_labels = {"ar": "⬅️ رجوع للفئات", "tr": "⬅️ Kategorilere Dön", "en": "⬅️ Back to Categories"}
    keyboard.append([InlineKeyboardButton(_back_labels.get(lang, _back_labels["en"]), callback_data="back_to_category")])

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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")
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
    from telegram import WebAppInfo

    # Store leaf category
    context.user_data["selected_subcategory"] = category_id

    # Fetch attributes for this leaf category
    raw_attributes = await api.get_attributes(category_id=category_id)
    raw_attributes = raw_attributes or []

    # Process and group attributes
    processed = _process_attributes(raw_attributes)

    context.user_data["raw_attributes"]       = raw_attributes
    context.user_data["processed_attributes"] = processed
    context.user_data.setdefault("max_images", 10)

    user_id = str(query.from_user.id)

    # ── Build WebApp URL ───────────────────────────────────────────────────────
    # Auto-detect Railway domain from multiple possible env vars:
    #   RAILWAY_DOMAIN          — manually set by user in Railway Variables (highest priority)
    #   RAILWAY_PUBLIC_DOMAIN   — set automatically by Railway for public services
    #   RAILWAY_STATIC_URL      — legacy Railway env var (strip protocol prefix)
    _raw_static = os.getenv("RAILWAY_STATIC_URL", "")
    _static_domain = _raw_static.replace("https://", "").replace("http://", "").rstrip("/")
    RAILWAY_DOMAIN = (
        os.getenv("RAILWAY_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or _static_domain
        or ""
    )
    webapp_url = (
        f"https://{RAILWAY_DOMAIN}/webapp/product-form"
        f"?category_id={category_id}"
        f"&lang={lang}"
        f"&user_id={user_id}"
    ) if RAILWAY_DOMAIN else None

    # ── Build breadcrumb ───────────────────────────────────────────────────────
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

    # ── Build required fields list ─────────────────────────────────────────────
    required_names = (
        [a.get("name") for a in processed["shared_required"]]
        + [a.get("name") for a in processed["selector_required"]]
    )

    # ── Build message text ─────────────────────────────────────────────────────
    SEP = "━━━━━━━━━━━━━━━━━━━━"
    if webapp_url:
        # ── Header ────────────────────────────────────────────────────────────
        step_headers = {
            "ar": "📝 <b>الخطوة 3 — بيانات المنتج</b>",
            "tr": "📝 <b>Adım 3 — Ürün Bilgileri</b>",
            "en": "📝 <b>Step 3 — Product Details</b>",
        }
        # ── Instruction ────────────────────────────────────────────────────────
        instructions = {
            "ar": "اضغط الزر أدناه لفتح نموذج المنتج المنظّم.",
            "tr": "Aşağıdaki butona tıklayarak ürün formunu açın.",
            "en": "Tap the button below to open the structured product form.",
        }
        # ── Required fields block ──────────────────────────────────────────────
        if required_names:
            req_headers = {
                "ar": "🔴 <b>الحقول الإجبارية</b> <i>(يجب تعبئتها)</i>",
                "tr": "🔴 <b>Zorunlu Alanlar</b> <i>(doldurulması gerekir)</i>",
                "en": "🔴 <b>Required Fields</b> <i>(must be filled)</i>",
            }
            fields_lines = "\n".join(
                f"  ❗ {n}" for n in required_names if n
            )
            req_block = (
                req_headers.get(lang, req_headers["en"])
                + "\n"
                + fields_lines
            )
        else:
            req_block = ""

        parts = [step_headers.get(lang, step_headers["en"])]
        parts.append(SEP)
        parts.append(instructions.get(lang, instructions["en"]))
        if req_block:
            parts.append(SEP)
            parts.append(req_block)
        form_prompt = "\n".join(parts)
    else:
        # Fallback: no RAILWAY_DOMAIN set → use old text-based flow
        form_prompt = get_string(lang, "add_product_fill_form")
        if required_names:
            required_label = {
                "tr": "Zorunlu alanlar",
                "ar": "الحقول المطلوبة",
                "en": "Required fields",
            }.get(lang, "Required fields")
            form_prompt += f"\n\n🔴 <b>{required_label}:</b>\n" + "\n".join(
                f"  ❗ {name}" for name in required_names if name
            )

    body_parts = [progress]
    if breadcrumb:
        body_parts.append(breadcrumb)
    body_parts.append(form_prompt)
    full_body = "\n\n".join(body_parts)

    # ── Build keyboard ─────────────────────────────────────────────────────────
    if webapp_url:
        btn_labels = {
            "ar": ("📝 فتح فورم المنتج",   "✏️ الإدخال اليدوي"),
            "tr": ("📝 Ürün Formunu Aç",   "✏️ Manuel Giriş"),
            "en": ("📝 Open Product Form", "✏️ Manual Entry"),
        }
        webapp_label, manual_label = btn_labels.get(lang, btn_labels["en"])
        # Back button — goes back to subcategory list (or category list if no subs)
        _back_labels = {"ar": "⬅️ رجوع للخطوة السابقة", "tr": "⬅️ Önceki Adıma Dön", "en": "⬅️ Back to Previous Step"}
        _back_label = _back_labels.get(lang, _back_labels["en"])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(webapp_label, web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(manual_label, callback_data="form_manual_entry")],
            [InlineKeyboardButton(_back_label, callback_data="back_to_subcategory")],
        ])
        await query.edit_message_text(full_body, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        logger.info(
            "WebApp form button sent: user_id=%s category_id=%s",
            user_id, category_id,
        )
    else:
        await query.edit_message_text(full_body, parse_mode=ParseMode.HTML)
        logger.warning(
            "RAILWAY_DOMAIN not set — falling back to text input. user_id=%s", user_id
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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")
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

    # Preserve the language selection made before entering manual flow
    # (stored earlier as context.user_data["post_languages"] when user chose language)
    _saved_langs = context.user_data.get("post_languages")
    if _saved_langs and "post_languages" not in extracted_data:
        extracted_data["post_languages"] = _saved_langs

    # BUG FIX (Band 15): Merge new extraction with existing product_details instead of
    # replacing it wholesale. This prevents AI from overwriting fields the user didn't touch.
    # Strategy: only overwrite a field if the new extraction actually provided a non-empty value.
    old_details = context.user_data.get("product_details", {})
    if old_details:
        merged = dict(old_details)  # start from old
        for k, v in extracted_data.items():
            # Always overwrite these structural/meta fields
            if k in ("post_languages", "_source", "category_id"):
                merged[k] = v
                continue
            # For dicts (shared_attributes, selector_attributes list): merge if non-empty
            if isinstance(v, dict) and v:
                merged[k] = v
            elif isinstance(v, list) and v:
                merged[k] = v
            elif isinstance(v, str) and v.strip():
                merged[k] = v
            elif isinstance(v, (int, float)) and v not in (0, 0.0, 1, 100):
                # Only overwrite numeric defaults if they look intentional
                merged[k] = v
            # else: keep old value
        extracted_data = merged

    context.user_data["product_details"] = extracted_data
    # Save the original raw text so handle_fix_missing can combine it with corrections
    context.user_data["original_text"] = text

    await processing_msg.delete()

    # Validate: check for missing required attributes
    missing = _check_missing_required(extracted_data, processed_attrs)

    if missing:
        # ── Build clear, prominent missing-fields alert ───────────────────────────────────────
        SEP = "━━━━━━━━━━━━━━━━━━━━"
        alert_headers = {
            "tr": "🚨 <b>Eksik Zorunlu Alanlar!</b>",
            "ar": "🚨 <b>حقول إجبارية ناقصة!</b>",
            "en": "🚨 <b>Missing Required Fields!</b>",
        }
        missing_intros = {
            "tr": "❌ Aşağıdaki zorunlu alanlar doldurulmadı:",
            "ar": "❌ لم يتم تعبئة الحقول الإجبارية التالية:",
            "en": "❌ The following required fields were not filled:",
        }
        missing_prompts = {
            "tr": "📝 Lütfen bu bilgileri mesaj olarak gönderin ve devam edin.",
            "ar": "📝 يرجى إرسال هذه المعلومات كرسالة نصية للمتابعة.",
            "en": "📝 Please send this information as a message to continue.",
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

        # Build numbered missing list for clarity
        numbered_missing = "\n".join(
            f"  {i+1}. ❗ <b>{m}</b>" for i, m in enumerate(missing)
        )

        lines = []
        if breadcrumb:
            lines.append(breadcrumb)
            lines.append(SEP)
        lines.append(alert_headers.get(lang, alert_headers["en"]))
        lines.append(missing_intros.get(lang, missing_intros["en"]))
        lines.append(numbered_missing)
        lines.append(SEP)
        lines.append(missing_prompts.get(lang, missing_prompts["en"]))

        missing_text = "\n".join(lines)
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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")
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

    # Preserve language selection across re-extraction
    _saved_langs2 = context.user_data.get("post_languages")
    if _saved_langs2 and "post_languages" not in extracted_data:
        extracted_data["post_languages"] = _saved_langs2

    # BUG FIX (Band 15): Merge new extraction with existing product_details
    # so that only the fields the user explicitly corrected get updated.
    old_details2 = context.user_data.get("product_details", {})
    if old_details2 and extracted_data is not old_details2:
        merged2 = dict(old_details2)
        for k, v in extracted_data.items():
            if k in ("post_languages", "_source", "category_id"):
                merged2[k] = v
                continue
            if isinstance(v, dict) and v:
                merged2[k] = v
            elif isinstance(v, list) and v:
                merged2[k] = v
            elif isinstance(v, str) and v.strip():
                merged2[k] = v
            elif isinstance(v, (int, float)) and v not in (0, 0.0, 1, 100):
                merged2[k] = v
        extracted_data = merged2

    context.user_data["product_details"] = extracted_data

    await processing_msg.delete()

    # Re-validate
    missing = _check_missing_required(extracted_data, processed_attrs)

    if missing:
        # ── Still missing — show persistent prominent alert ──────────────────────────────────────
        SEP = "━━━━━━━━━━━━━━━━━━━━"
        alert_headers = {
            "tr": "🚨 <b>Hâlâ Eksik Alanlar Var!</b>",
            "ar": "🚨 <b>لا تزال هناك حقول إجبارية ناقصة!</b>",
            "en": "🚨 <b>Still Missing Required Fields!</b>",
        }
        missing_intros = {
            "tr": "❌ Henüz doldurulmayan zorunlu alanlar:",
            "ar": "❌ الحقول الإجبارية التي لم تكتمل بعد:",
            "en": "❌ Required fields still not completed:",
        }
        missing_prompts = {
            "tr": "📝 Sadece eksik bilgileri gönderin, geri kalanı hatırlıyorum.",
            "ar": "📝 أرسل فقط المعلومات الناقصة، الباقي محفوظ لديّ.",
            "en": "📝 Just send the missing info — I remember the rest.",
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

        # Numbered missing list
        numbered_missing = "\n".join(
            f"  {i+1}. ❗ <b>{m}</b>" for i, m in enumerate(missing)
        )

        lines = []
        if breadcrumb:
            lines.append(breadcrumb)
            lines.append(SEP)
        lines.append(alert_headers.get(lang, alert_headers["en"]))
        lines.append(missing_intros.get(lang, missing_intros["en"]))
        lines.append(numbered_missing)
        lines.append(SEP)
        lines.append(missing_prompts.get(lang, missing_prompts["en"]))

        missing_text = "\n".join(lines)
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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    await query.answer()  # Remove Telegram's loading spinner

    if query.data == "details_confirm":
        # ── Supplier confirmed → generate AI channel post ────────────────────────────────────────────
        product_details = context.user_data.get("product_details", {})
        languages = product_details.get("post_languages") or context.user_data.get("post_languages") or ["ar", "tr", "en"]

        # Build attributes list for DeepSeek
        # NOTE: raw_attributes is a LIST; build a dict keyed by id for fast lookup
        attrs_list = []
        # Use processed_attributes (already deduplicated by _process_attributes)
        # instead of raw_attributes (which may still contain 'نسائي نسائي' from API)
        processed_attrs = context.user_data.get("processed_attributes", {})
        all_attrs = processed_attrs.get("all_by_id") or {
            a.get("id"): a for a in context.user_data.get("raw_attributes", []) if a.get("id")
        }
        logger.info("[CONFIRM_DEBUG] all_attrs size=%d raw_attrs size=%d",
                    len(all_attrs), len(context.user_data.get("raw_attributes", [])))
        # If all_attrs is empty (session lost between form and confirm), re-fetch from API
        if not all_attrs:
            category_id = context.user_data.get("selected_subcategory", "")
            logger.info("[CONFIRM_DEBUG] all_attrs empty! Re-fetching attributes for category=%s", category_id)
            if category_id:
                try:
                    _api = KayisoftAPI(telegram_user_id=user_id, language=lang)
                    _raw = await _api.get_attributes(category_id=category_id)
                    _raw = _raw or []
                    _processed = _process_attributes(_raw)
                    context.user_data["raw_attributes"]       = _raw
                    context.user_data["processed_attributes"] = _processed
                    all_attrs = _processed.get("all_by_id") or {
                        a.get("id"): a for a in _raw if a.get("id")
                    }
                    logger.info("[CONFIRM_DEBUG] re-fetched all_attrs size=%d", len(all_attrs))
                except Exception as _e:
                    logger.warning("[CONFIRM_DEBUG] re-fetch failed: %s", _e)
        shared_attrs = product_details.get("shared_attributes", {})
        # ── Helper: resolve option display name from opt_id ──────────────────────────────
        # KAYISOFT options carry an 'id' UUID field.  The WebApp sends back that UUID
        # as the selected option_id.  We look up the human-readable label here.
        # Fallback chain:
        #   1. Match opt.id == opt_id  (normal case)
        #   2. Match opt.value == opt_id  (proxy may set id = value for non-UUID values)
        #   3. opt_id is already human-readable (not a UUID pattern)
        import re as _re_uuid
        _UUID_RE = _re_uuid.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            _re_uuid.I,
        )

        def _resolve_opt_label(attr_info: dict, opt_id: str) -> str:
            """Return human-readable label for opt_id from attr_info.options."""
            options = attr_info.get("options", [])
            # Pass 1: match by id (UUID)
            for opt in options:
                if opt.get("id") == opt_id:
                    raw_n = opt.get("label") or opt.get("name") or str(opt.get("value", ""))
                    if "|" in raw_n:
                        raw_n = raw_n.split("|", 1)[-1].strip()
                    return _deduplicate_name(raw_n) if raw_n else opt_id
            # Pass 2: match by value (proxy sets opt.id = opt.value for non-UUID options)
            for opt in options:
                raw_val = str(opt.get("value", ""))
                cmp_val = raw_val.split("|", 1)[-1].strip() if "|" in raw_val else raw_val
                if cmp_val == opt_id or raw_val == opt_id:
                    raw_n = opt.get("label") or opt.get("name") or cmp_val
                    if "|" in raw_n:
                        raw_n = raw_n.split("|", 1)[-1].strip()
                    return _deduplicate_name(raw_n) if raw_n else opt_id
            # Pass 3: opt_id is already a human-readable string (not a UUID)
            if not _UUID_RE.match(opt_id):
                return _deduplicate_name(opt_id)
            return opt_id  # last resort: return UUID as-is

        # ── Build secondary lookup by key (some attrs use 'key' instead of 'id') ─────
        _all_attrs_by_key = {
            a.get("key", ""): a
            for a in context.user_data.get("raw_attributes", [])
            if a.get("key")
        }

        def _get_attr_info(aid: str) -> dict:
            """Lookup attr by UUID (id) or key, returns {} if not found."""
            result = all_attrs.get(aid) or _all_attrs_by_key.get(aid) or {}
            if not result:
                logger.warning(
                    "[ATTRS_LOOKUP] attr_id=%r not found in all_attrs (keys=%s)",
                    aid,
                    list(all_attrs.keys())[:5],
                )
            return result

        for attr_id, option_ids in shared_attrs.items():
            attr_info = _get_attr_info(attr_id)
            attr_name = _deduplicate_name(attr_info.get("name", "") or attr_id)
            seen_oids: set = set()
            option_names: list = []
            for opt_id in (option_ids if isinstance(option_ids, list) else [option_ids]):
                if opt_id in seen_oids:
                    continue
                seen_oids.add(opt_id)
                label = _resolve_opt_label(attr_info, opt_id)
                logger.info(
                    "[AI_RESOLVE] shared attr_id=%r opt_id=%r → label=%r",
                    attr_id, opt_id, label,
                )
                option_names.append(label)
            if option_names:
                attrs_list.append({"name": attr_name, "value": ", ".join(option_names)})

        selector_attrs = product_details.get("selector_attributes", [])
        # Group selector_attrs by attribute_id to avoid one-line-per-option repetition
        sel_grouped: dict = {}
        for sel in selector_attrs:
            attr_id = sel.get("attribute_id", "")
            opt_id  = sel.get("option_id", "")
            if not attr_id:
                continue
            if attr_id not in sel_grouped:
                sel_grouped[attr_id] = {"attr_info": _get_attr_info(attr_id), "opt_ids": [], "seen": set()}
            if opt_id and opt_id not in sel_grouped[attr_id]["seen"]:
                sel_grouped[attr_id]["seen"].add(opt_id)
                sel_grouped[attr_id]["opt_ids"].append(opt_id)
        for attr_id, grp in sel_grouped.items():
            attr_info = grp["attr_info"]
            attr_name = _deduplicate_name(attr_info.get("name", "") or attr_id)
            opt_names = []
            for oid in grp["opt_ids"]:
                label = _resolve_opt_label(attr_info, oid)
                logger.info(
                    "[AI_RESOLVE] selector attr_id=%r opt_id=%r → label=%r",
                    attr_id, oid, label,
                )
                opt_names.append(label)
            attrs_list.append({"name": attr_name, "value": ", ".join(opt_names)})

        import json as _jdebug
        logger.info("[AI_ATTRS_DEBUG] attrs_list=%s", _jdebug.dumps(attrs_list, ensure_ascii=False))
        logger.info("[AI_ATTRS_DEBUG] languages=%s", languages)

        # Add sizes from form if provided — but only if no size attribute already exists
        # in selector_attributes or shared_attributes to avoid duplication (Band 5 fix)
        _SIZE_KEYWORDS = {"size", "beden", "مقاس", "ebat", "boyut"}
        _has_size_attr = any(
            any(kw in (_get_attr_info(a_id).get("name", "") or "").lower() for kw in _SIZE_KEYWORDS)
            for a_id in list(sel_grouped.keys()) + list(shared_attrs.keys())
        )
        sizes_val = (product_details.get("sizes") or "").strip()
        if sizes_val and not _has_size_attr:
            attrs_list.append({"name": "المقاسات", "value": sizes_val})

        post_data = {
            "name":         product_details.get("name", ""),
            "description":  product_details.get("description", ""),
            "price":        product_details.get("price", ""),
            "min_quantity": product_details.get("min_quantity", 1),
            "product_code": product_details.get("product_code", ""),
            "notes":        product_details.get("notes", ""),
            "attributes":   attrs_list,
        }
        # Show "generating" message
        generating_msgs = {
            "ar": "🤖 <b>AI</b> يُحسّن بوست القناة...",
            "tr": "🤖 <b>AI</b> kanal gönderisi oluşturuluyor...",
            "en": "🤖 <b>AI</b> is crafting your channel post...",
        }
        gen_msg = await query.message.reply_text(
            generating_msgs.get(lang, generating_msgs["en"]),
            parse_mode=ParseMode.HTML,
        )

        # Call DeepSeek
        ai_post = await generate_channel_post(post_data, languages)

        if not ai_post:
            # Fallback: skip AI review and go straight to image upload
            await gen_msg.delete()
            progress = _progress_bar(4)
            upload_prompts = {
                "tr": f"{progress}\n\n📸 <b>Adım 4 — Ürün Fotoğrafları</b>\n\nÜrün fotoğraflarınızı gönderin.",
                "ar": f"{progress}\n\n📸 <b>الخطوة 4 — صور المنتج</b>\n\nأرسل صور منتجك الآن.",
                "en": f"{progress}\n\n📸 <b>Step 4 — Product Images</b>\n\nSend your product photos now.",
            }
            await query.message.reply_text(
                upload_prompts.get(lang, upload_prompts["en"]),
                parse_mode=ParseMode.HTML,
            )
            return UPLOAD_IMAGES

        # Save AI post for later use in channel publishing
        context.user_data["ai_channel_post"] = ai_post

        # Show AI post preview with approve/edit/regenerate buttons
        preview_headers = {
            "ar": "🤖 <b>معاينة بوست القناة</b> (مُحسَّن بالذكاء الاصطناعي)\n\n",
            "tr": "🤖 <b>Kanal Gönderisi Önizlemesi</b> (AI ile iyileştirildi)\n\n",
            "en": "🤖 <b>Channel Post Preview</b> (AI-enhanced)\n\n",
        }
        preview_text = preview_headers.get(lang, preview_headers["en"]) + ai_post

        approve_labels = {
            "ar": ("✅ موافق، ارفع الصور", "🔄 أعد التوليد", "✏️ تعديل يدوي"),
            "tr": ("✅ Onayla, Fotoğraf Ekle", "🔄 Yeniden Oluştur", "✏️ Manuel Düzenle"),
            "en": ("✅ Approve & Upload", "🔄 Regenerate", "✏️ Edit"),
        }
        approve_lbl, regen_lbl, edit_lbl = approve_labels.get(lang, approve_labels["en"])

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(approve_lbl, callback_data="post_approve"),
            InlineKeyboardButton(regen_lbl,   callback_data="post_regenerate"),
        ], [
            InlineKeyboardButton(edit_lbl,    callback_data="post_edit"),
        ]])

        await gen_msg.delete()
        await query.message.reply_text(
            preview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        return AI_POST_REVIEW

    else:  # details_edit
        # ── Supplier wants to edit → re-open form with prefill if source was webapp ────────────────
        from telegram import WebAppInfo
        import json, base64

        product_details = context.user_data.get("product_details", {})
        source = product_details.get("_source", "")

        # Detect Railway domain (same logic as _load_attributes_and_ask_form)
        _raw_static = os.getenv("RAILWAY_STATIC_URL", "")
        _static_domain = _raw_static.replace("https://", "").replace("http://", "").rstrip("/")
        RAILWAY_DOMAIN = (
            os.getenv("RAILWAY_DOMAIN")
            or os.getenv("RAILWAY_PUBLIC_DOMAIN")
            or _static_domain
            or ""
        )

        category_id = context.user_data.get("selected_subcategory", "")
        user_id_str = str(query.from_user.id)

        # If data came from the webapp form AND we have a Railway domain → re-open form with prefill
        if source in ("webapp", "webapp_post") and RAILWAY_DOMAIN and category_id:
            # Build prefill JSON (only the fields the form knows about)
            # Band-15 Fix: always pass the canonical name/description that the
            # supplier originally typed (stored under name_<lang> by Band-6 fix).
            # This prevents the form from opening with an empty or '—' title
            # when the supplier edits and re-submits.
            _edit_lang = lang  # supplier's language at edit time
            _prefill_name = (
                product_details.get(f"name_{_edit_lang}")
                or product_details.get("name", "")
            )
            _prefill_desc = (
                product_details.get(f"description_{_edit_lang}")
                or product_details.get("description", "")
            )
            prefill_data = {
                "name":                _prefill_name,
                "description":         _prefill_desc,
                "price":               str(product_details.get("price", "")),
                "min_quantity":        product_details.get("min_quantity", 1),
                "stock_count":         product_details.get("stock_count", 500),
                "product_code":        product_details.get("product_code", ""),
                "notes":               product_details.get("notes", ""),
                "post_languages":      product_details.get("post_languages", ["ar"]),
                "shared_attributes":   product_details.get("shared_attributes", {}),
                "selector_attributes": product_details.get("selector_attributes", []),
            }
            # Encode as URL-safe base64 to pass in query param
            prefill_b64 = base64.urlsafe_b64encode(
                json.dumps(prefill_data, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")

            webapp_url = (
                f"https://{RAILWAY_DOMAIN}/webapp/product-form"
                f"?category_id={category_id}"
                f"&lang={lang}"
                f"&user_id={user_id_str}"
                f"&prefill={prefill_b64}"
            )

            btn_labels = {
                "ar": ("📝 فتح الفورم للتعديل",   "✏️ الإدخال اليدوي"),
                "tr": ("📝 Formu Düzenle",          "✏️ Manuel Giriş"),
                "en": ("📝 Edit in Form",            "✏️ Manual Entry"),
            }
            webapp_label, manual_label = btn_labels.get(lang, btn_labels["en"])

            edit_headers = {
                "ar": "✏️ <b>تعديل بيانات المنتج</b>\nاضغط الزر لفتح الفورم مع بياناتك السابقة.",
                "tr": "✏️ <b>Ürün Bilgilerini Düzenle</b>\nÖnceki verilerinizle formu açmak için butona basın.",
                "en": "✏️ <b>Edit Product Details</b>\nTap the button to reopen the form with your previous data.",
            }

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(webapp_label, web_app=WebAppInfo(url=webapp_url))],
                [InlineKeyboardButton(manual_label, callback_data="form_manual_entry")],
            ])
            await query.message.reply_text(
                edit_headers.get(lang, edit_headers["en"]),
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        else:
            # Fallback: no Railway domain or data came from manual text entry
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
# AI POST REVIEW — Approve / Regenerate / Edit
# ══════════════════════════════════════════════════════════════════════════════
async def handle_ai_post_review(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: AI_POST_REVIEW
    Handles the three buttons shown below the AI-generated channel post:
      - post_approve     → proceed to image upload
      - post_regenerate  → call DeepSeek again and show new post
      - post_edit        → ask supplier to type their own post text
    """
    query   = update.callback_query
    user    = update.effective_user
    user_id = str(user.id)
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")
    await query.answer()

    if query.data == "post_approve":
        # ── Approved → start color-by-color upload flow ─────────────────────────────────
        return await _start_color_upload(update, context, from_query=True)

    elif query.data == "post_regenerate":
        # ── Regenerate → call DeepSeek again ────────────────────────────────
        product_details = context.user_data.get("product_details", {})
        languages = product_details.get("post_languages") or context.user_data.get("post_languages") or ["ar", "tr", "en"]

        gen_msgs = {
            "ar": "🔄 <b>إعادة توليد البوست...</b>",
            "tr": "🔄 <b>Gönderi yeniden oluşturuluyor...</b>",
            "en": "🔄 <b>Regenerating post...</b>",
        }
        gen_msg = await query.message.reply_text(
            gen_msgs.get(lang, gen_msgs["en"]),
            parse_mode=ParseMode.HTML,
        )

        # Build post_data again
        # NOTE: raw_attributes is a LIST; build a dict keyed by id for fast lookup
        attrs_list = []
        raw_attrs_list = context.user_data.get("raw_attributes", [])
        all_attrs = {a.get("id"): a for a in raw_attrs_list if a.get("id")}

        for attr_id, option_ids in product_details.get("shared_attributes", {}).items():
            attr_info = all_attrs.get(attr_id, {})
            attr_name = _deduplicate_name(attr_info.get("name", "") or attr_id)
            seen_oids = set()
            option_names = []
            for opt_id in (option_ids if isinstance(option_ids, list) else [option_ids]):
                if opt_id in seen_oids:
                    continue
                seen_oids.add(opt_id)
                for opt in attr_info.get("options", []):
                    if opt.get("id") == opt_id:
                        # Prefer label (already deduped by proxy) over name
                        raw_n = opt.get("label") or opt.get("name", "") or opt_id
                        if "|" in (raw_n or ""):
                            raw_n = raw_n.split("|", 1)[-1].strip()
                        option_names.append(_deduplicate_name(raw_n))
                        break
                else:
                    option_names.append(_deduplicate_name(str(opt_id)))
            if option_names:
                attrs_list.append({"name": attr_name, "value": ", ".join(option_names)})

        # Also add selector_attrs grouped by attribute
        sel_grouped_regen: dict = {}
        for sel in product_details.get("selector_attributes", []):
            a_id = sel.get("attribute_id", "")
            o_id = sel.get("option_id", "")
            if not a_id:
                continue
            if a_id not in sel_grouped_regen:
                sel_grouped_regen[a_id] = {"attr_info": all_attrs.get(a_id, {}), "opt_ids": [], "seen": set()}
            if o_id and o_id not in sel_grouped_regen[a_id]["seen"]:
                sel_grouped_regen[a_id]["seen"].add(o_id)
                sel_grouped_regen[a_id]["opt_ids"].append(o_id)
        for a_id, grp in sel_grouped_regen.items():
            a_info = grp["attr_info"]
            a_name = _deduplicate_name(a_info.get("name", "") or a_id)
            o_names = []
            for o_id in grp["opt_ids"]:
                # Band 8 fix: resolve option label properly (not just o_id[:8])
                _found_label = None
                for opt in a_info.get("options", []):
                    if opt.get("id") == o_id:
                        raw_n = opt.get("label") or opt.get("name") or opt.get("value", "")
                        if "|" in (raw_n or ""):
                            raw_n = raw_n.split("|", 1)[-1].strip()
                        _found_label = _deduplicate_name(raw_n) if raw_n else None
                        break
                # Fallback: check by value (proxy sets opt.id = opt.value for non-UUID options)
                if not _found_label:
                    for opt in a_info.get("options", []):
                        raw_val = str(opt.get("value", ""))
                        cmp_val = raw_val.split("|", 1)[-1].strip() if "|" in raw_val else raw_val
                        if cmp_val == o_id or raw_val == o_id:
                            raw_n = opt.get("label") or opt.get("name") or cmp_val
                            if "|" in (raw_n or ""):
                                raw_n = raw_n.split("|", 1)[-1].strip()
                            _found_label = _deduplicate_name(raw_n) if raw_n else None
                            break
                # Last resort: use o_id as-is if it looks human-readable (not a UUID)
                import re as _re_regen
                _UUID_PAT = _re_regen.compile(
                    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                    _re_regen.I,
                )
                if not _found_label:
                    _found_label = o_id if not _UUID_PAT.match(o_id) else f"[{o_id[:8]}]"
                o_names.append(_found_label)
            attrs_list.append({"name": a_name, "value": ", ".join(o_names)})

        # Band 5 fix: add free-text sizes only if no size attribute already in structured attrs
        _SIZE_KWS = {"size", "beden", "مقاس", "ebat", "boyut"}
        _regen_has_size = any(
            any(kw in (all_attrs.get(a_id, {}).get("name", "") or "").lower() for kw in _SIZE_KWS)
            for a_id in list(sel_grouped_regen.keys()) + list(product_details.get("shared_attributes", {}).keys())
        )
        _regen_sizes_val = (product_details.get("sizes") or "").strip()
        if _regen_sizes_val and not _regen_has_size:
            attrs_list.append({"name": "المقاسات", "value": _regen_sizes_val})

        post_data = {
            "name":         product_details.get("name", ""),
            "description":  product_details.get("description", ""),
            "price":        product_details.get("price", ""),
            "min_quantity": product_details.get("min_quantity", 1),
            "product_code": product_details.get("product_code", ""),
            "notes":        product_details.get("notes", ""),
            "attributes":   attrs_list,
        }

        ai_post = await generate_channel_post(post_data, languages)
        await gen_msg.delete()

        if not ai_post:
            err_msgs = {
                "ar": "⚠️ فشل التوليد. سيُستخدم البوست السابق.",
                "tr": "⚠️ Oluşturma başarısız. Önceki gönderi kullanılacak.",
                "en": "⚠️ Generation failed. Previous post will be used.",
            }
            await query.message.reply_text(err_msgs.get(lang, err_msgs["en"]))
            return AI_POST_REVIEW

        context.user_data["ai_channel_post"] = ai_post

        preview_headers = {
            "ar": "🤖 <b>بوست جديد</b> (مُحسَّن بالذكاء الاصطناعي)\n\n",
            "tr": "🤖 <b>Yeni Gönderi</b> (AI ile iyileştirildi)\n\n",
            "en": "🤖 <b>New Post</b> (AI-enhanced)\n\n",
        }
        preview_text = preview_headers.get(lang, preview_headers["en"]) + ai_post

        approve_labels = {
            "ar": ("✅ موافق، ارفع الصور", "🔄 أعد التوليد", "✏️ تعديل يدوي"),
            "tr": ("✅ Onayla, Fotoğraf Ekle", "🔄 Yeniden Oluştur", "✏️ Manuel Düzenle"),
            "en": ("✅ Approve & Upload", "🔄 Regenerate", "✏️ Edit"),
        }
        approve_lbl, regen_lbl, edit_lbl = approve_labels.get(lang, approve_labels["en"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(approve_lbl, callback_data="post_approve"),
            InlineKeyboardButton(regen_lbl,   callback_data="post_regenerate"),
        ], [
            InlineKeyboardButton(edit_lbl,    callback_data="post_edit"),
        ]])
        await query.message.reply_text(
            preview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        return AI_POST_REVIEW

    else:  # post_edit
        # ── Manual edit → ask supplier to type their own post ───────────────
        edit_prompts = {
            "ar": "✏️ اكتب نص البوست الذي تريد نشره على القناة:\n(يمكنك استخدام HTML: <b>عريض</b>، <i>مائل</i>)",
            "tr": "✏️ Kanala göndermek istediğiniz gönderi metnini yazın:\n(HTML kullanabilirsiniz: <b>kalın</b>, <i>italik</i>)",
            "en": "✏️ Type the post text you want to publish to the channel:\n(You can use HTML: <b>bold</b>, <i>italic</i>)",
        }
        await query.message.reply_text(
            edit_prompts.get(lang, edit_prompts["en"]),
            parse_mode=ParseMode.HTML,
        )
        return AI_POST_REVIEW


async def handle_ai_post_manual_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: AI_POST_REVIEW (text message)
    Handles supplier typing their own post text after pressing ✏️ Edit Manually.
    """
    user    = update.effective_user
    user_id = str(user.id)
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")
    text    = update.message.text.strip()

    if not text:
        return AI_POST_REVIEW

    context.user_data["ai_channel_post"] = text

    # Show the edited post with approve button
    approve_labels = {
        "ar": ("✅ موافق، ارفع الصور", "🔄 أعد التوليد بالذكاء الاصطناعي"),
        "tr": ("✅ Onayla, Fotoğraf Ekle", "🔄 AI ile Yeniden Oluştur"),
        "en": ("✅ Approve & Upload", "🔄 Regenerate with AI"),
    }
    approve_lbl, regen_lbl = approve_labels.get(lang, approve_labels["en"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(approve_lbl, callback_data="post_approve"),
        InlineKeyboardButton(regen_lbl,   callback_data="post_regenerate"),
    ]])

    preview_headers = {
        "ar": "📝 <b>معاينة البوست المُعدَّل</b>\n\n",
        "tr": "📝 <b>Düzenlenmiş Gönderi Önizlemesi</b>\n\n",
        "en": "📝 <b>Edited Post Preview</b>\n\n",
    }
    preview_text = preview_headers.get(lang, preview_headers["en"]) + text
    await update.message.reply_text(
        preview_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return AI_POST_REVIEW


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4.5 — Color-by-Color Image Upload
# ══════════════════════════════════════════════════════════════════════════════

MULTI_COLOR_NAMES = {"çok renkli", "multicolor", "multi-color", "multi color", "متعدد الألوان", "çokrenkli"}
MAX_PHOTOS_PER_COLOR = 5


# Keywords that identify a color attribute by name
_COLOR_ATTR_KEYWORDS = {"renk", "color", "colour", "لون", "رنگ"}


def _get_color_options(context) -> list:
    """
    Extracts the list of selected color options from user_data.
    Returns a list of dicts: [{"id": uuid, "name": str, "hex": str, "is_multi": bool}]
    Returns empty list if no color attribute found.

    Detection priority:
      1. is_primary_variant_attribute=True + is_variant_selector=True
      2. Attribute name contains a color keyword (renk / color / لون)
      3. Selector attribute with the most hex-value options (pipe-separated)
    """
    product_details = context.user_data.get("product_details", {})
    raw_attributes  = context.user_data.get("raw_attributes", [])
    selector_attrs  = product_details.get("selector_attributes", [])

    # Build set of attribute_ids actually used in selector_attributes
    used_selector_ids = {sel.get("attribute_id") for sel in selector_attrs if sel.get("attribute_id")}

    def _build_options_map(attr: dict) -> dict:
        """Build {option_id: {name, hex}} for an attribute."""
        omap = {}
        for opt in attr.get("options", []):
            raw_val  = opt.get("value", "")
            parts    = raw_val.split("|") if raw_val else []
            hex_val  = parts[0].strip() if parts else ""
            name_val = parts[1].strip() if len(parts) > 1 else opt.get("name", "")
            name_val = _deduplicate_name(name_val)
            omap[opt.get("id", "")] = {"name": name_val, "hex": hex_val}
        return omap

    color_attr_id    = None
    color_options_map = {}

    # ── Priority 1: explicit primary variant attribute ────────────────────────
    for attr in raw_attributes:
        if attr.get("is_primary_variant_attribute") and attr.get("is_variant_selector"):
            color_attr_id     = attr.get("id")
            color_options_map = _build_options_map(attr)
            break

    # ── Priority 2: selector attribute whose name contains a color keyword ────
    if not color_attr_id:
        for attr in raw_attributes:
            if attr.get("id") not in used_selector_ids:
                continue
            attr_name_lower = (attr.get("name") or "").lower()
            if any(kw in attr_name_lower for kw in _COLOR_ATTR_KEYWORDS):
                color_attr_id     = attr.get("id")
                color_options_map = _build_options_map(attr)
                break

    # ── Priority 3: selector attribute with the most hex-value options ────────
    if not color_attr_id:
        best_attr = None
        best_hex_count = 0
        for attr in raw_attributes:
            if attr.get("id") not in used_selector_ids:
                continue
            hex_count = sum(
                1 for opt in attr.get("options", [])
                if "|" in (opt.get("value") or "")
            )
            if hex_count > best_hex_count:
                best_hex_count = hex_count
                best_attr      = attr
        if best_attr and best_hex_count > 0:
            color_attr_id     = best_attr.get("id")
            color_options_map = _build_options_map(best_attr)

    if not color_attr_id:
        return []

    # Collect selected color option IDs (deduplicated, preserving order)
    seen_ids = set()
    selected_color_ids = []
    for sel in selector_attrs:
        if sel.get("attribute_id") == color_attr_id and sel.get("option_id"):
            oid = sel["option_id"]
            if oid not in seen_ids:
                seen_ids.add(oid)
                selected_color_ids.append(oid)

    result = []
    for oid in selected_color_ids:
        info = color_options_map.get(oid, {})
        name = info.get("name", oid)
        is_multi = name.lower().strip() in MULTI_COLOR_NAMES
        result.append({"id": oid, "name": name, "hex": info.get("hex", ""), "is_multi": is_multi})

    return result


async def _start_color_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    from_query: bool = False,
) -> int:
    """
    Initialises the color-by-color upload flow.
    Called from handle_ai_post_review when supplier presses ✅ Approve.
    Returns COLOR_UPLOAD state (or UPLOAD_IMAGES if no colors found).
    """
    user    = update.effective_user
    user_id = str(user.id)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    colors = _get_color_options(context)

    if not colors:
        # No color attribute → fall back to generic image upload
        progress = _progress_bar(4)
        upload_prompts = {
            "tr": f"{progress}\n\n📸 <b>Adım 4 — Ürün Fotoğrafları</b>\n\nÜrün fotoğraflarınızı gönderin.",
            "ar": f"{progress}\n\n📸 <b>الخطوة 4 — صور المنتج</b>\n\nأرسل صور منتجك الآن.",
            "en": f"{progress}\n\n📸 <b>Step 4 — Product Images</b>\n\nSend your product photos now.",
        }
        msg = update.callback_query.message if from_query else update.message
        await msg.reply_text(
            upload_prompts.get(lang, upload_prompts["en"]),
            parse_mode=ParseMode.HTML,
        )
        return UPLOAD_IMAGES

    # Initialise color upload state
    context.user_data["color_upload_list"]  = colors
    context.user_data["color_upload_index"] = 0
    context.user_data["color_images_map"]   = {}   # {color_option_id: [file_id, ...]}

    msg = update.callback_query.message if from_query else update.message
    await _ask_color_photos(msg, context, lang, colors, 0)
    return COLOR_UPLOAD


async def _ask_color_photos(
    message,
    context,
    lang: str,
    colors: list,
    index: int,
) -> None:
    """
    Sends the prompt asking for photos of the current color.
    Photos are MANDATORY — no skip option is presented.
    Keyboard layout: [📸 Add Another Photo] / [✅ Done — Next Color]
    """
    color   = colors[index]
    current = index + 1
    total   = len(colors)

    # ── Hardcoded fallbacks (used if translation file not yet loaded) ──
    _FALLBACK_ASK = {
        "ar": "🎨 اللون {current}/{total}: <b>{color_name}</b>\n━━━━━━━━━━━━━━━━━━━━\n📸 أرسل صور هذا اللون.\n<i>من 1 إلى 5 صور لكل لون.</i>",
        "tr": "🎨 Renk {current}/{total}: <b>{color_name}</b>\n━━━━━━━━━━━━━━━━━━━━\n📸 Bu renk için fotoğraf gönderin.\n<i>En az 1, en fazla 5 fotoğraf yükleyebilirsiniz.</i>",
        "en": "🎨 Color {current}/{total}: <b>{color_name}</b>\n━━━━━━━━━━━━━━━━━━━━\n📸 Send photos for this color.\n<i>1 to 5 photos per color.</i>",
    }
    _FALLBACK_MULTI = {
        "ar": "🌈 <b>متعدد الألوان</b> — أرسل جميع صور المنتج\n━━━━━━━━━━━━━━━━━━━━\n📸 من 1 إلى 5 صور.",
        "tr": "🌈 <b>Çok Renkli</b> ürün için tüm fotoğrafları gönderin\n━━━━━━━━━━━━━━━━━━━━\n📸 En fazla 5 fotoğraf yükleyebilirsiniz.",
        "en": "🌈 <b>Multi-Color</b> product — send all product photos\n━━━━━━━━━━━━━━━━━━━━\n📸 1 to 5 photos.",
    }
    # Build done button text with next color name if available
    next_index = index + 1
    _next_color_name = colors[next_index]["name"] if next_index < len(colors) else None
    _FALLBACK_DONE = {
        "ar": f"✅ تم — انتقل لـ {_next_color_name}" if _next_color_name else "✅ تم — نشر المنتج",
        "tr": f"✅ Tamam — {_next_color_name} Rengine Geç" if _next_color_name else "✅ Tamam — Ürünü Yayınla",
        "en": f"✅ Done — Next: {_next_color_name}" if _next_color_name else "✅ Done — Publish",
    }
    def _gs(key: str, fallback_dict: dict) -> str:
        """get_string with hardcoded fallback."""
        val = get_string(lang, key)
        # If get_string returned the key itself (not found), use hardcoded fallback
        if val == key:
            return fallback_dict.get(lang, fallback_dict["en"])
        return val

    if color["is_multi"]:
        # Multi-color: ask for all photos at once
        text = _gs("color_upload_multicolor_ask", _FALLBACK_MULTI)
    else:
        text = _gs("color_upload_ask", _FALLBACK_ASK).format(
            current=current,
            total=total,
            color_name=color["name"],
        )

    # 2-button layout — photos are MANDATORY, no skip option:
    # Row 1: 📸 Add Another Photo
    # Row 2: ✅ Done — Next Color  (only enabled after at least 1 photo is sent)
    _ADD_PHOTO_FALLBACK = {
        "ar": f"📸 إضافة صورة لـ {color['name']}",
        "tr": f"📸 {color['name']} için Fotoğraf Ekle",
        "en": f"📸 Add Photo for {color['name']}",
    }
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            _ADD_PHOTO_FALLBACK.get(lang, _ADD_PHOTO_FALLBACK["en"]),
            callback_data="color_add_more",
        )],
        [
            InlineKeyboardButton(
                _gs("color_upload_done_btn", _FALLBACK_DONE),
                callback_data="color_done",
            ),
        ],
    ])

    sent = await message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    context.user_data["last_color_msg_id"]  = sent.message_id
    context.user_data["last_color_chat_id"] = sent.chat_id


async def handle_color_image_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: COLOR_UPLOAD
    Receives photos for the current color.
    """
    user    = update.effective_user
    user_id = str(user.id)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    colors = context.user_data.get("color_upload_list", [])
    index  = context.user_data.get("color_upload_index", 0)
    if not colors or index >= len(colors):
        return COLOR_UPLOAD

    color = colors[index]
    color_id = color["id"]

    # Accept photo or document-as-image
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type and \
            update.message.document.mime_type.startswith("image/"):
        photo_file_id = update.message.document.file_id

    if not photo_file_id:
        return COLOR_UPLOAD

    # Initialise map entry
    if color_id not in context.user_data["color_images_map"]:
        context.user_data["color_images_map"][color_id] = []

    current_count = len(context.user_data["color_images_map"][color_id])

    # Enforce max 5 photos per color
    if current_count >= MAX_PHOTOS_PER_COLOR:
        await update.message.reply_text(
            get_string(lang, "color_upload_max").format(color_name=color["name"]),
            parse_mode=ParseMode.HTML,
        )
        return COLOR_UPLOAD

    # Deduplicate
    img_hash = hashlib.sha256(photo_file_id.encode()).hexdigest()[:16]
    if "image_hashes" not in context.user_data:
        context.user_data["image_hashes"] = set()
    if img_hash in context.user_data["image_hashes"]:
        dup_msg = {"ar": "⚠️ هذه الصورة مضافة مسبقاً.", "tr": "⚠️ Bu fotoğraf zaten eklendi.", "en": "⚠️ Already added."}
        await update.message.reply_text(dup_msg.get(lang, dup_msg["en"]))
        return COLOR_UPLOAD
    context.user_data["image_hashes"].add(img_hash)
    context.user_data["color_images_map"][color_id].append(photo_file_id)

    new_count = len(context.user_data["color_images_map"][color_id])

    # Update the keyboard message to reflect new count
    prev_msg_id  = context.user_data.get("last_color_msg_id")
    prev_chat_id = context.user_data.get("last_color_chat_id")

    # Hardcoded fallbacks for color_upload messages
    _ADDED_FALLBACK = {
        "ar": "✅ <b>{color_name}</b> — {count}/5 صورة مضافة",
        "tr": "✅ <b>{color_name}</b> — {count}/5 fotoğraf eklendi",
        "en": "✅ <b>{color_name}</b> — {count}/5 photo(s) added",
    }
    # Build done button text with next color name if available
    _next_idx = index + 1
    _next_cn = colors[_next_idx]["name"] if _next_idx < len(colors) else None
    _DONE_FALLBACK = {
        "ar": f"✅ تم — انتقل لـ {_next_cn}" if _next_cn else "✅ تم — نشر المنتج",
        "tr": f"✅ Tamam — {_next_cn} Rengine Geç" if _next_cn else "✅ Tamam — Ürünü Yayınla",
        "en": f"✅ Done — Next: {_next_cn}" if _next_cn else "✅ Done — Publish",
    }
    def _gs2(key: str, fb: dict) -> str:
        v = get_string(lang, key)
        return fb.get(lang, fb["en"]) if v == key else v

    added_raw = _gs2("color_upload_added", _ADDED_FALLBACK)
    status_text = added_raw.format(color_name=color["name"], count=new_count)

    # After first photo: show "Add another photo" + "Done" buttons.
    # Photos are MANDATORY — no skip button is shown.
    _ADD_MORE_FALLBACK = {
        "ar": f"📸 إضافة صورة إضافية لـ {color['name']}",
        "tr": f"📸 {color['name']} için Ek Fotoğraf Ekle",
        "en": f"📸 Add Another Photo for {color['name']}",
    }
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            _ADD_MORE_FALLBACK.get(lang, _ADD_MORE_FALLBACK["en"]),
            callback_data="color_add_more",
        )],
        [
            InlineKeyboardButton(
                _gs2("color_upload_done_btn", _DONE_FALLBACK),
                callback_data="color_done",
            ),
        ],
    ])

    # Delete the old prompt message so the new status appears BELOW the photo
    if prev_msg_id and prev_chat_id:
        try:
            await context.bot.delete_message(
                chat_id=prev_chat_id,
                message_id=prev_msg_id,
            )
        except Exception:
            pass  # Already deleted or not found — ignore

    # Send new status message AFTER the photo (Telegram places it below)
    sent = await update.message.reply_text(
        status_text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )
    context.user_data["last_color_msg_id"]  = sent.message_id
    context.user_data["last_color_chat_id"] = sent.chat_id

    return COLOR_UPLOAD


async def handle_color_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: COLOR_UPLOAD — handles ✅ Done and 📸 Add More buttons.
    Skip is intentionally removed — photos are mandatory for every color.
    """
    query   = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

    colors = context.user_data.get("color_upload_list", [])
    index  = context.user_data.get("color_upload_index", 0)
    if not colors or index >= len(colors):
        return COLOR_UPLOAD

    color    = colors[index]
    color_id = color["id"]
    action   = query.data  # "color_done" or "color_add_more" (color_skip is disabled)

    if action == "color_add_more":
        # Supplier wants to add another photo for the current color
        # Just answer the query — the next photo they send will be handled by handle_color_image_upload
        _add_more_hint = {
            "ar": f"📸 أرسل صورة إضافية للون <b>{color['name']}</b>",
            "tr": f"📸 <b>{color['name']}</b> rengi için ek fotoğraf gönderin",
            "en": f"📸 Send another photo for <b>{color['name']}</b>",
        }
        await query.answer()
        await query.message.reply_text(
            _add_more_hint.get(lang, _add_more_hint["en"]),
            parse_mode=ParseMode.HTML,
        )
        return COLOR_UPLOAD

    if action == "color_done":
        # Photos are MANDATORY — block Done if no photo has been uploaded for this color
        uploaded = context.user_data.get("color_images_map", {}).get(color_id, [])
        if not uploaded:
            _no_photo_warn = {
                "ar": f"📸 يجب رفع صورة واحدة على الأقل للون <b>{color['name']}</b>.\n\nالصورة إلزامية لكل لون.",
                "tr": f"📸 <b>{color['name']}</b> rengi için en az 1 fotoğraf zorunludur.\n\nLütfen bir fotoğraf gönderin.",
                "en": f"📸 At least 1 photo is required for <b>{color['name']}</b>.\n\nPlease send a photo to continue.",
            }
            await query.answer(
                _no_photo_warn.get(lang, _no_photo_warn["en"]).replace("<b>", "").replace("</b>", ""),
                show_alert=True,
            )
            return COLOR_UPLOAD
        # color_done: do NOT edit the current message — leave it showing
        # "✅ ColorName — N/5 صورة مضافة" so photos appear above it correctly.

    elif action == "color_skip":
        # color_skip is DISABLED — photos are mandatory.
        # This branch handles any residual callbacks from old keyboards.
        _skip_blocked = {
            "ar": f"📸 الصورة إلزامية. يرجى إرسال صورة للون <b>{color['name']}</b>.",
            "tr": f"📸 Fotoğraf zorunludur. Lütfen <b>{color['name']}</b> rengi için fotoğraf gönderin.",
            "en": f"📸 Photos are required. Please send a photo for <b>{color['name']}</b>.",
        }
        await query.answer(
            _skip_blocked.get(lang, _skip_blocked["en"]).replace("<b>", "").replace("</b>", ""),
            show_alert=True,
        )
        return COLOR_UPLOAD

    # Advance to next color
    next_index = index + 1
    context.user_data["color_upload_index"] = next_index

    if next_index < len(colors):
        # Send next color prompt as a NEW message (so photos appear above it correctly)
        await _ask_color_photos(query.message, context, lang, colors, next_index)
        return COLOR_UPLOAD

    else:
        # ── All colors done ──────────────────────────────────────────────────────
        color_images_map = context.user_data.get("color_images_map", {})
        all_images = []
        for c in colors:
            all_images.extend(color_images_map.get(c["id"], []))
        context.user_data["images"] = all_images
        context.user_data["color_images_map_final"] = color_images_map

        # Step 1: Send summary message (new message, not edit)
        total_photos = len(all_images)
        summary_msg = {
            "ar": f"✅ <b>تم رفع جميع الصور!</b>\n\n📸 إجمالي الصور: <b>{total_photos}</b> صورة",
            "tr": f"✅ <b>Tüm fotoğraflar yüklendi!</b>\n\n📸 Toplam fotoğraf: <b>{total_photos}</b>",
            "en": f"✅ <b>All photos uploaded!</b>\n\n📸 Total photos: <b>{total_photos}</b>",
        }
        await query.message.reply_text(
            summary_msg.get(lang, summary_msg["en"]),
            parse_mode=ParseMode.HTML,
        )

        # Step 2: Build variant preview and send as a NEW message with confirm buttons
        product_details = context.user_data.get("product_details", {})
        processed_attrs = context.user_data.get("processed_attributes", {})
        raw_attributes  = context.user_data.get("raw_attributes", [])
        attr_map_prev   = processed_attrs.get("all_by_id", {})

        price_raw   = product_details.get("price", "0")
        price_float = _parse_price(price_raw)
        min_quantity = int(product_details.get("min_quantity", product_details.get("min_order", 1)))
        stock_count  = int(product_details.get("stock_count", product_details.get("stock", 100)))

        id_to_key_prev = {}
        for attr in raw_attributes:
            a_id  = attr.get("id", "")
            a_key = attr.get("key", "")
            if a_id and a_key:
                id_to_key_prev[a_id] = a_key

        ai_selector_attrs = product_details.get("selector_attributes", [])
        preview_variants  = _build_variants(
            product_name        = product_details.get("name", ""),
            description         = product_details.get("description", ""),
            price_float         = price_float,
            stock_count         = stock_count,
            min_quantity        = min_quantity,
            lang                = lang,
            uploaded_file_names = [],
            ai_selector_attrs   = ai_selector_attrs,
            raw_attributes      = raw_attributes,
            id_to_key           = id_to_key_prev,
        )
        context.user_data["preview_variants"] = preview_variants

        preview_text = _build_variants_preview(lang, preview_variants, attr_map_prev)

        _btn_confirm = {
            "ar": "✅ تأكيد ونشر",
            "tr": "✅ Onayla ve Yayınla",
            "en": "✅ Confirm & Publish",
        }
        _btn_cancel = {
            "ar": "❌ إلغاء",
            "tr": "❌ İptal",
            "en": "❌ Cancel",
        }
        _btn_confirm_text = get_string(lang, "btn_confirm_publish")
        if _btn_confirm_text == "btn_confirm_publish":
            _btn_confirm_text = _btn_confirm.get(lang, _btn_confirm["en"])
        _btn_cancel_text = get_string(lang, "btn_cancel")
        if _btn_cancel_text == "btn_cancel":
            _btn_cancel_text = _btn_cancel.get(lang, _btn_cancel["en"])

        confirm_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(_btn_confirm_text, callback_data="publish_yes"),
            InlineKeyboardButton(_btn_cancel_text,  callback_data="publish_no"),
        ]])

        await query.message.reply_text(
            preview_text,
            reply_markup=confirm_keyboard,
            parse_mode=ParseMode.HTML,
        )
        return CONFIRM_PUBLISH


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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

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

    # ── Color Analysis DISABLED ────────────────────────────────────────────────
    # Colors are selected by the supplier from KAYISOFT attribute options
    # (fetched from the KAYISOFT endpoint). AI color extraction from images
    # was removed to avoid conflicts with the official KAYISOFT color list.
    color_line = ""

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

    msg_text = (
        f"{progress}\n\n"
        + get_string(lang, "add_product_confirm").format(
            count=image_count,
            max=max_images,
        )
        + color_line
    )

    # Try to edit the previous image-upload message (if any) to keep only one active keyboard.
    # This prevents multiple active "Yayınla" buttons from accumulating.
    prev_msg_id   = context.user_data.get("last_image_msg_id")
    prev_chat_id  = context.user_data.get("last_image_chat_id")
    edited = False
    if prev_msg_id and prev_chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id    = prev_chat_id,
                message_id = prev_msg_id,
                text       = msg_text,
                reply_markup = keyboard,
                parse_mode   = ParseMode.HTML,
            )
            edited = True
        except Exception:
            edited = False  # Message too old or already edited — fall through to new message

    if not edited:
        sent = await update.message.reply_text(
            msg_text,
            reply_markup = keyboard,
            parse_mode   = ParseMode.HTML,
        )
        context.user_data["last_image_msg_id"]  = sent.message_id
        context.user_data["last_image_chat_id"] = sent.chat_id

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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

    # ── Add more images ──────────────────────────────────────────────────────────────────────────────────
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
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

    # ── Cancel ─────────────────────────────────────────────────────────────────────────────────────
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
    # BUG FIX (Band 12): Per-color image map — {color_option_id: [file_id, ...]}
    # Used to assign correct images to each color variant instead of distributing evenly
    color_images_map_final = context.user_data.get("color_images_map_final", {})
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

    # ── BUG FIX (Band 12): Build per-color uploaded filename map ─────────────────
    # image_file_ids is a flat list built by extending color_images_map_final in order:
    #   all_images = []; for c in colors: all_images.extend(color_images_map.get(c["id"], []))
    # So we can rebuild the per-color S3 filename map by tracking the same order.
    # uploaded_file_names[i] corresponds to image_file_ids[i] (successful uploads only).
    # We build a mapping: file_id → s3_filename, then reconstruct per-color map.
    color_uploaded_map: dict = {}  # {color_option_id: [s3_filename, ...]}
    if color_images_map_final and uploaded_file_names:
        # Build file_id → s3_filename index (positional, skipping failed uploads)
        file_id_to_s3: dict = {}
        upload_idx = 0
        for fid in image_file_ids:
            # Check if this file_id was successfully uploaded (results list matches image_file_ids order)
            result_idx = image_file_ids.index(fid) if fid in image_file_ids else -1
            if result_idx >= 0 and result_idx < len(results) and isinstance(results[result_idx], bytes):
                if upload_idx < len(uploaded_file_names):
                    file_id_to_s3[fid] = uploaded_file_names[upload_idx]
                    upload_idx += 1
        # Now map each color to its S3 filenames
        for color_id, fids in color_images_map_final.items():
            s3_names = [file_id_to_s3[fid] for fid in fids if fid in file_id_to_s3]
            if s3_names:
                color_uploaded_map[color_id] = s3_names
        logger.info("🎨 color_uploaded_map built: %d colors, keys=%s",
                    len(color_uploaded_map), list(color_uploaded_map.keys())[:5])

    # ── Step 5: Build product payload ───────────────────────────────────────────
    # Support both old format (name/description) and new multilingual format (name_ar/tr/en)
    product_name_ar = product_details.get("name_ar", "")
    product_name_tr = product_details.get("name_tr", "")
    product_name_en = product_details.get("name_en", "")
    description_ar  = product_details.get("description_ar", "")
    description_tr  = product_details.get("description_tr", "")
    description_en  = product_details.get("description_en", "")
    # Band-6 / Band-15 Fix: resolve the canonical product_name and description
    # from the correct language slot based on the supplier's language.
    # Old code always used product_name_ar as the primary fallback, which caused
    # Turkish suppliers' products to show empty names (name_ar was blank).
    # Now we check the supplier's own language slot first, then fall back to
    # the generic 'name' field, then to raw_text.
    _lang = context.user_data.get("lang", "tr")
    _name_by_lang = {
        "ar": product_name_ar,
        "tr": product_name_tr,
        "en": product_name_en,
    }
    _desc_by_lang = {
        "ar": description_ar,
        "tr": description_tr,
        "en": description_en,
    }
    product_name = (
        _name_by_lang.get(_lang)
        or product_name_ar
        or product_name_tr
        or product_name_en
        or product_details.get("name", product_details.get("raw_text", "")[:80])
    )
    description = (
        _desc_by_lang.get(_lang)
        or description_ar
        or description_tr
        or description_en
        or product_details.get("description", "")
    )
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
            parse_mode=ParseMode.HTML,
            reply_markup=_support_keyboard(lang),
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

    # ── Build shared_attributes: {attr_key: [option_uuid]} ─────────────────────
    # KAYISOFT API REQUIRES:
    #   - Key   = attribute KEY string (e.g. "material"), NOT the UUID
    #   - Value = list of option UUIDs (e.g. ["4411e6ed-..."])
    # Error if key is UUID:   "Invalid option for attribute filter"
    # Error if value is text: "Incorrect value for string attribute"
    ai_shared_attrs = product_details.get("shared_attributes", {})
    logger.info(
        "🔍 RAW shared_attributes from HTML: %s",
        str(ai_shared_attrs)[:500]
    )
    logger.info(
        "🔍 id_to_key map has %d entries: %s",
        len(id_to_key), str(id_to_key)[:300]
    )
    import re as _re_uuid
    _UUID_RE = _re_uuid.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        _re_uuid.I
    )

    # Build a lookup: {attr_id → attr_obj} so we can check ui_type per attribute
    id_to_attr = {attr.get("id", ""): attr for attr in raw_attributes}

    shared_attributes = {}
    for attr_id, option_ids in ai_shared_attrs.items():
        # Convert UUID key → string key using id_to_key map
        attr_key = id_to_key.get(attr_id, attr_id)  # fallback to UUID if key not found

        if not isinstance(option_ids, list):
            option_ids = [option_ids] if option_ids else []

        # Filter out empty values
        clean_ids = [oid for oid in option_ids if oid]

        if not clean_ids:
            continue

        # ── Determine how to send the value to KAYISOFT API ──────────────────────
        # KAYISOFT has two types of shared attributes:
        #   1. Option-based (select/multiselect/color): value = [uuid, uuid, ...]
        #   2. String-based (text/numeric/bool):        value = "plain string"
        #
        # We detect string-based by checking:
        #   a) The attribute has no options in raw_attributes (ui_type=text/numeric)
        #   b) OR the values themselves are NOT UUIDs (plain text entered by user)
        attr_obj   = id_to_attr.get(attr_id, {})
        has_opts   = bool(attr_obj.get("options"))
        all_uuids  = all(_UUID_RE.match(str(v)) for v in clean_ids)

        if has_opts and all_uuids:
            # Option-based attribute: send as list of UUIDs
            # CRITICAL: Validate each UUID exists in the real options list.
            # The AI sometimes generates a slightly wrong UUID (e.g. '4b47' vs '4c47').
            # Fix: if UUID not found in options, find the closest match by value/name.
            real_option_ids = {opt.get("id", ""): opt for opt in attr_obj.get("options", [])}
            validated_ids = []
            for oid in clean_ids:
                if oid in real_option_ids:
                    # UUID is correct — use as-is
                    validated_ids.append(oid)
                else:
                    # UUID not found — try to find the real option by fuzzy match on value/name
                    _found_id = None
                    for real_id, real_opt in real_option_ids.items():
                        raw_val = str(real_opt.get("value", "") or real_opt.get("name", "") or real_opt.get("label", ""))
                        # Strip hex color prefix if present (e.g. "#FF0000|أحمر" → "أحمر")
                        if "|" in raw_val:
                            raw_val = raw_val.split("|", 1)[-1].strip()
                        # Also try matching by UUID prefix (first 20 chars) in case of single-char typo
                        if oid[:20].lower() == real_id[:20].lower():
                            _found_id = real_id
                            break
                    if _found_id:
                        logger.warning(
                            "⚠️ UUID mismatch fixed: AI gave %r, real UUID is %r (attr_key=%s)",
                            oid, _found_id, attr_key
                        )
                        validated_ids.append(_found_id)
                    else:
                        # Last resort: keep original (will fail at API, but we log it)
                        logger.error(
                            "❌ UUID %r not found in options for attr_key=%s — sending as-is",
                            oid, attr_key
                        )
                        validated_ids.append(oid)
            final_value = validated_ids
            logger.info(
                "🔑 attr_id=%s → attr_key=%s | OPTION-BASED | value=%s",
                attr_id[:20] if len(attr_id) > 20 else attr_id,
                attr_key, str(final_value)[:80]
            )
        else:
            # String-based attribute: send as plain string
            # Join multiple values with comma if somehow multiple were provided
            final_value = ", ".join(str(v) for v in clean_ids)
            logger.info(
                "🔑 attr_id=%s → attr_key=%s | STRING-BASED | value=%r",
                attr_id[:20] if len(attr_id) > 20 else attr_id,
                attr_key, final_value
            )

        shared_attributes[attr_key] = final_value

    logger.info("📋 shared_attributes (smart-typed): %s", str(shared_attributes)[:500])

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
        product_name_ar     = product_name_ar,
        product_name_tr     = product_name_tr,
        product_name_en     = product_name_en,
        description_ar      = description_ar,
        description_tr      = description_tr,
        description_en      = description_en,
        # BUG FIX (Band 12): pass per-color S3 filename map
        color_uploaded_map  = color_uploaded_map,
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

    # ── Extract share_links (KAYISOFT deep links) ────────────────────────────
    # Per TelegramBackendEndpoints spec (confirmed by KAYISOFT team):
    #   share_links is returned at the TOP LEVEL of the response (NOT inside variants)
    #
    #   Response structure:
    #   {
    #     "id": "...",
    #     "variants": [...],
    #     "share_links": {                   ← TOP LEVEL
    #       "chat":    "https://kayisoft.dynalinks.app/topgate/start-chat-variant?id=...",
    #       "details": "https://kayisoft.dynalinks.app/topgate/product-variant?id=..."
    #     }
    #   }
    #
    # FALLBACK STRATEGY (if backend hasn't deployed share_links yet):
    #   Build dynalinks from first variant_id using the documented URL pattern.

    # Attempt 1: use share_links from TOP LEVEL of API response (correct location)
    _top_level_links = created_product.get("share_links", {}) or {}
    share_link_chat    = _top_level_links.get("chat", "")    or ""
    share_link_details = _top_level_links.get("details", "") or ""

    if share_link_chat or share_link_details:
        logger.info(
            "🔗 share_links from API response (top-level): chat=%s | details=%s",
            share_link_chat, share_link_details
        )
    else:
        # Attempt 2: build dynalinks from first variant_id as fallback
        _api_variants = created_product.get("variants", [])
        _first_variant_id = _api_variants[0].get("id", "") if _api_variants else ""
        _DYNALINKS_BASE = "https://kayisoft.dynalinks.app/topgate"
        if _first_variant_id:
            share_link_chat    = f"{_DYNALINKS_BASE}/start-chat-variant?id={_first_variant_id}"
            share_link_details = f"{_DYNALINKS_BASE}/product-variant?id={_first_variant_id}"
            logger.info(
                "🔗 share_links built from variant_id (fallback): chat=%s | details=%s",
                share_link_chat, share_link_details
            )
        else:
            logger.warning("⚠️ share_links not found in API response and no variant_id available — buttons will use legacy URLs")

    logger.info(
        "✅ Product created: id=%s, seller=%s, category=%s, variants=%d | "
        "share_links.chat=%s share_links.details=%s",
        product_id,
        supplier_id,
        category_id,
        len(variants),
        share_link_chat or "(none — will use fallback)",
        share_link_details or "(none — will use fallback)",
    )

    # ── Step 7: Publish professional post to Telegram Channel ─────────────────
    # channel_id is retrieved via get_channel_id_for_user which checks:
    #   1. bot_data["user_channels"] (in-memory, fast)
    #   2. /data/user_channels.json  (persistent, survives Railway restarts)
    from bot.handlers.channel_handler import get_channel_id_for_user
    channel_id = get_channel_id_for_user(user_id, context) or context.user_data.get("channel_id")
    # Safety normalization: strip spaces from channel_id (e.g. "-10014428 17937" → "-1001442817937")
    if channel_id:
        channel_id = channel_id.replace(" ", "").strip()

    channel_published = False
    if channel_id:
        logger.info(
            "📢 Attempting channel publish: channel_id=%s, user_id=%s, images=%d",
            channel_id, user_id, len(image_file_ids)
        )
        # ── Build human-readable attributes list for DeepSeek post ───────────────────────
        # Build a lookup: attr_id → attr dict (for name + options resolution)
        _attr_map_pub     = {a.get("id", ""): a for a in raw_attributes if a.get("id")}
        _attr_key_map_pub = {a.get("key", ""): a for a in raw_attributes if a.get("key")}
        _attrs_list_pub   = []

        def _pub_get_attr(aid: str) -> dict:
            """Lookup attr by UUID or key, returns {} if not found."""
            return _attr_map_pub.get(aid) or _attr_key_map_pub.get(aid) or {}

        # Group selector_attrs by attribute_id (e.g. all sizes together, all colors together)
        import re as _re_pub
        from collections import OrderedDict as _OD_pub
        _sel_grouped_pub: dict = _OD_pub()
        for _sel in ai_selector_attrs:
            _aid  = _sel.get("attribute_id", "")
            _oid  = _sel.get("option_id", "")
            if not _aid:
                continue
            if _aid not in _sel_grouped_pub:
                _a = _pub_get_attr(_aid)
                _sel_grouped_pub[_aid] = {"name": _deduplicate_name(_a.get("name") or _a.get("key") or _aid), "attr": _a, "vals": []}
            _sel_grouped_pub[_aid]["vals"].append(_oid)

        for _aid, _grp in _sel_grouped_pub.items():
            _rendered = []
            for _oid in _grp["vals"]:
                _display = _oid
                _raw_v   = ""
                for _opt in _grp["attr"].get("options", []):
                    if _opt.get("id") == _oid:
                        _raw_n = _opt.get("name") or _opt.get("value", _oid)
                        _raw_v = _opt.get("value", "")
                        if "|" in _raw_n:
                            _, _display = _raw_n.split("|", 1)
                            _display = _display.strip()
                            _raw_v   = _raw_n.split("|", 1)[0].strip()
                        elif "|" in _raw_v:
                            _raw_v, _lbl = _raw_v.split("|", 1)
                            _display = _lbl.strip() if _lbl.strip() else _raw_n
                        else:
                            _display = _raw_n
                        _display = _deduplicate_name(_display)
                        break
                # Strip any remaining hex from display
                if "|" in _display:
                    _, _display = _display.split("|", 1)
                    _display = _display.strip()
                if _re_pub.match(r'^#?[0-9A-Fa-f]{6,8}$', _display.strip()):
                    _display = ""  # pure hex — skip
                if _display:
                    _rendered.append(_display)
            if _rendered:
                _attrs_list_pub.append({"name": _grp["name"], "value": ", ".join(_rendered)})

        # Add shared attributes (material, pattern, etc.)
        for _aid, _opt_ids in ai_shared_attrs.items():
            _a = _pub_get_attr(_aid)
            _aname = _deduplicate_name(_a.get("name") or _a.get("key") or _aid)
            _rendered = []
            for _oid in (_opt_ids if isinstance(_opt_ids, list) else [_opt_ids]):
                for _opt in _a.get("options", []):
                    if _opt.get("id") == _oid:
                        _raw_n = _opt.get("label") or _opt.get("name") or _opt.get("value", _oid)
                        if "|" in _raw_n:
                            _, _raw_n = _raw_n.split("|", 1)
                            _raw_n = _raw_n.strip()
                        _rendered.append(_deduplicate_name(_raw_n))
                        break
                else:
                    _rendered.append(str(_oid))
            if _rendered:
                _attrs_list_pub.append({"name": _aname, "value": ", ".join(_rendered)})

        # Honour the language selection made by the supplier (webapp or manual flow)
        _post_languages = product_details.get("post_languages") or ["ar", "tr", "en"]
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
            attributes=_attrs_list_pub,
            share_link_chat=share_link_chat,
            share_link_details=share_link_details,
            post_languages=_post_languages,
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
        # Track stats for this supplier
        track_product_published(
            user_id=str(user_id),
            product_id=product_id or "",
            product_name=product_name or "",
        )
        # NOTE: _send_new_product_notification was removed — it caused a duplicate
        # second card to appear in the channel right after the main product post.
        # The main product post already contains all info + buttons, so no extra
        # notification is needed. (Removed 2026-06-21)
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

    # ── Inline button: Add Another Product ──────────────────────────────────
    add_another_labels = {
        "ar": "➕ إضافة منتج جديد",
        "tr": "➕ Yeni Ürün Ekle",
        "en": "➕ Add Another Product",
    }
    success_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                add_another_labels.get(lang, add_another_labels["en"]),
                callback_data="add_another_product",
            )
        ]
    ])

    await query.edit_message_text(
        success_text,
        parse_mode=ParseMode.HTML,
        reply_markup=success_keyboard,
    )
    # Re-send main keyboard so user sees all navigation buttons
    from bot.keyboards import supplier_main_keyboard as _smk
    try:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=get_string(lang, "main_menu_supplier"),
            reply_markup=_smk(lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
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
    # Read lang BEFORE clearing user_data (it will be cleared below)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    context.user_data.clear()

    await update.message.reply_text(
        get_string(lang, "add_product_cancelled"),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


## ══════════════════════════════════════════════════════════════════════════════
# WEBAPP — handle_form_submitted
# Triggered by __FORM_SUBMITTED__ sentinel message sent by /webapp/submit endpoint
# Reads the pending payload from pending_submissions dict and processes it
# ══════════════════════════════════════════════════════════════════════════════

async def handle_form_submitted(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: FILL_FORM → CONFIRM_DETAILS

    Called when the Mini App POSTs to /webapp/submit and the FastAPI endpoint
    sends a __FORM_SUBMITTED__ sentinel message to the user's chat.

    This replaces the old tg.sendData() mechanism which only works with
    ReplyKeyboard buttons (not InlineKeyboard — our case).

    Flow:
      1. FastAPI /webapp/submit stores payload in pending_submissions[user_id]
      2. FastAPI sends __FORM_SUBMITTED__ to the user via Bot API
      3. This handler fires, reads pending_submissions[user_id], processes it
      4. Returns CONFIRM_DETAILS so the supplier can review the summary

    Programmatic note:
      The __FORM_SUBMITTED__ sentinel is a text message (not web_app_data),
      so it must be registered BEFORE the generic TEXT handler in FILL_FORM.
    """
    user    = update.effective_user
    user_id = str(user.id)
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    # Import pending_submissions from the webapp routes module
    # Both FastAPI and PTB run in the same process → shared memory
    try:
        from bot.routes.webapp_routes import pending_submissions
    except ImportError:
        logger.error("handle_form_submitted: could not import pending_submissions")
        await update.effective_message.reply_text(
            "❌ حدث خطأ داخلي. يرجى المحاولة مجدداً.",
            parse_mode=ParseMode.HTML,
        )
        return FILL_FORM

    # Retrieve and consume the pending payload
    payload = pending_submissions.pop(user_id, None)
    if not payload:
        logger.warning(
            "handle_form_submitted: no pending submission for user_id=%s — "
            "message may have been a duplicate or payload already consumed",
            user_id,
        )
        # Silently ignore — do not send error (user didn't explicitly trigger this)
        return FILL_FORM

    logger.info(
        "handle_form_submitted: processing POST submission for user_id=%s keys=%s",
        user_id, list(payload.keys()),
    )

    # Delete the __FORM_SUBMITTED__ sentinel message so it doesn't clutter the chat
    try:
        await update.effective_message.delete()
    except Exception:
        pass  # Non-critical — message may already be gone

    # ── Validate payload ──────────────────────────────────────────────────────
    validation_errors = _validate_webapp_payload(payload, lang)
    if validation_errors:
        error_lines = "\n".join(f"  • {e}" for e in validation_errors)
        msg = {
            "ar": f"❌ <b>خطأ في بيانات النموذج:</b>\n{error_lines}\n\nيرجى العودة وتصحيح البيانات.",
            "tr": f"❌ <b>Form verilerinde hata:</b>\n{error_lines}\n\nLütfen geri dönüp düzeltin.",
            "en": f"❌ <b>Form validation error:</b>\n{error_lines}\n\nPlease go back and fix the issues.",
        }.get(lang, f"❌ Validation error:\n{error_lines}")
        await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)
        return FILL_FORM

    # ── Extract fields ─────────────────────────────────────────────────────────
    name         = str(payload.get("name", "")).strip()
    description  = str(payload.get("description", "")).strip()
    price_str    = str(payload.get("price", "0"))
    min_quantity = int(payload.get("min_quantity", 1))
    stock_count  = int(payload.get("stock_count", min_quantity))
    if stock_count < min_quantity:
        stock_count = min_quantity

    shared_attributes   = payload.get("shared_attributes",   {}) or {}
    selector_attributes = payload.get("selector_attributes", []) or []
    # Use the languages selected by the supplier in the form;
    # fall back to all 3 if the payload doesn't include a selection
    post_languages      = payload.get("post_languages") or ["ar", "tr", "en"]

    # ── Band 6 Fix: Store name/description under the supplier's language key ──────
    # This ensures _build_titles / _build_descriptions in _build_variants can
    # correctly assign each language its own text instead of copying the supplier's
    # language text into ALL language slots.
    # Strategy:
    #   - name_<lang> = the text the supplier typed (their own language)
    #   - name_<other_langs> = "" → _build_titles will use name_local as fallback
    #     for the other languages (acceptable until backend translation is added)
    # This also fixes Band 15: the supplier's original text is always preserved
    # under the correct language key and never overwritten by a blank value.
    _lang_name_key = f"name_{lang}"          if lang in ("ar", "tr", "en") else "name_tr"
    _lang_desc_key = f"description_{lang}"   if lang in ("ar", "tr", "en") else "description_tr"

    product_details = {
        "name":                name,
        "description":         description,
        # Per-language fields — only the supplier's language is populated;
        # the others remain empty so _build_variants uses name as fallback
        # without copying the wrong language text into every slot.
        _lang_name_key:        name,
        _lang_desc_key:        description,
        "price":               price_str,
        "min_quantity":        min_quantity,
        "stock_count":         stock_count,
        "shared_attributes":   shared_attributes,
        "selector_attributes": selector_attributes,
        "post_languages":      post_languages,
        "_source":             "webapp_post",
    }
    context.user_data["product_details"] = product_details

    logger.info(
        "handle_form_submitted: valid form data. "
        "user_id=%s name=%r price=%s min_qty=%d stock=%d shared=%d selector=%d",
        user_id, name, price_str, min_quantity, stock_count,
        len(shared_attributes), len(selector_attributes),
    )
    # DEBUG: log actual shared_attributes and selector_attributes values
    import json as _json_debug
    logger.info("[PAYLOAD_DEBUG] shared_attributes=%s", _json_debug.dumps(shared_attributes, ensure_ascii=False)[:500])
    logger.info("[PAYLOAD_DEBUG] selector_attributes=%s", _json_debug.dumps(selector_attributes, ensure_ascii=False)[:500])

    # ── Build and show summary with confirm/edit buttons ──────────────────────
    summary = _build_webapp_summary(product_details, lang, context)
    logger.info("[SUMMARY_FINAL] summary text:\n%s", summary)
    confirm_buttons = {
        "ar": ("✅ تأكيد", "✏️ تعديل"),
        "tr": ("✅ Onayla", "✏️ Düzenle"),
        "en": ("✅ Confirm", "✏️ Edit"),
    }
    confirm_label, edit_label = confirm_buttons.get(lang, confirm_buttons["en"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(confirm_label, callback_data="details_confirm"),
        InlineKeyboardButton(edit_label,    callback_data="details_edit"),
    ]])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=summary,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM_DETAILS


## ══════════════════════════════════════════════════════════════════════════════
# WEBAPP — handle_webapp_data
# Receives JSON submitted by the Mini App via Telegram.WebApp.sendData()
# (Legacy path — only fires when Mini App is opened via ReplyKeyboard)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_webapp_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: FILL_FORM → CONFIRM_DETAILS

    Receives the JSON payload sent by the Mini App after the supplier fills
    the product form and taps "✅ حفظ بيانات المنتج".

    Expected JSON structure:
    {
        "name":        str,
        "description": str,
        "price":       str | float,
        "min_quantity": int,
        "stock_count":  int,
        "shared_attributes":   { attr_uuid: [opt_uuid, ...] },
        "selector_attributes": [ { "attribute_id": uuid, "option_id": uuid }, ... ]
    }
    """
    user    = update.effective_user
    user_id = str(user.id)
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    web_app_data = update.effective_message.web_app_data
    if not web_app_data or not web_app_data.data:
        logger.warning("handle_webapp_data: empty web_app_data for user_id=%s", user_id)
        await update.effective_message.reply_text(
            "❌ لم يتم استقبال بيانات من النموذج. يرجى المحاولة مجدداً.",
            parse_mode=ParseMode.HTML,
            reply_markup=_support_keyboard(lang),
        )
        return FILL_FORM

    try:
        payload = json.loads(web_app_data.data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "handle_webapp_data: JSON parse error for user_id=%s: %s — raw=%s",
            user_id, exc, web_app_data.data[:200],
        )
        await update.effective_message.reply_text(
            "❌ بيانات النموذج غير صالحة. يرجى إعادة المحاولة.",
            parse_mode=ParseMode.HTML,
            reply_markup=_support_keyboard(lang),
        )
        return FILL_FORM

    validation_errors = _validate_webapp_payload(payload, lang)
    if validation_errors:
        error_lines = "\n".join(f"  • {e}" for e in validation_errors)
        msg = {
            "ar": f"❌ <b>خطأ في بيانات النموذج:</b>\n{error_lines}\n\nيرجى العودة وتصحيح البيانات.",
            "tr": f"❌ <b>Form verilerinde hata:</b>\n{error_lines}\n\nLütfen geri dönüp düzeltin.",
            "en": f"❌ <b>Form validation error:</b>\n{error_lines}\n\nPlease go back and fix the issues.",
        }.get(lang, f"❌ Validation error:\n{error_lines}")
        await update.effective_message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=_support_keyboard(lang),
        )
        return FILL_FORM

    name         = str(payload.get("name", "")).strip()
    description  = str(payload.get("description", "")).strip()
    price_str    = str(payload.get("price", "0"))
    min_quantity = int(payload.get("min_quantity", 1))
    stock_count  = int(payload.get("stock_count", min_quantity))
    if stock_count < min_quantity:
        stock_count = min_quantity

    shared_attributes   = payload.get("shared_attributes",   {}) or {}
    selector_attributes = payload.get("selector_attributes", []) or []

    product_details = {
        "name":                name,
        "description":         description,
        "price":               price_str,
        "min_quantity":        min_quantity,
        "stock_count":         stock_count,
        "shared_attributes":   shared_attributes,
        "selector_attributes": selector_attributes,
        "post_languages":      payload.get("post_languages") or context.user_data.get("post_languages") or ["ar", "tr", "en"],
        "_source":             "webapp",
    }
    context.user_data["product_details"] = product_details

    logger.info(
        "handle_webapp_data: valid form data received. "
        "user_id=%s name=%r price=%s min_qty=%d stock=%d shared=%d selector=%d",
        user_id, name, price_str, min_quantity, stock_count,
        len(shared_attributes), len(selector_attributes),
    )

    summary = _build_webapp_summary(product_details, lang, context)

    confirm_buttons = {
        "ar": ("✅ تأكيد", "✏️ تعديل"),
        "tr": ("✅ Onayla", "✏️ Düzenle"),
        "en": ("✅ Confirm", "✏️ Edit"),
    }
    confirm_label, edit_label = confirm_buttons.get(lang, confirm_buttons["en"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(confirm_label, callback_data="details_confirm"),
        InlineKeyboardButton(edit_label,    callback_data="details_edit"),
    ]])

    await update.effective_message.reply_text(
        summary, reply_markup=keyboard, parse_mode=ParseMode.HTML,
    )
    return CONFIRM_DETAILS


def _validate_webapp_payload(payload: dict, lang: str) -> list:
    """
    Validates the JSON payload from the Mini App.
    Returns a list of human-readable error strings (empty = valid).
    """
    errors = []
    field_labels = {
        "ar": {"name": "اسم المنتج", "price": "السعر", "min": "الحد الأدنى", "stock": "المخزون"},
        "tr": {"name": "Ürün adı",   "price": "Fiyat", "min": "Min. miktar", "stock": "Stok"},
        "en": {"name": "Product name","price": "Price", "min": "Min. qty",   "stock": "Stock"},
    }
    L = field_labels.get(lang, field_labels["en"])

    name = str(payload.get("name", "")).strip()
    if len(name) < 3:
        errors.append(f"{L['name']}: يجب أن يكون 3 أحرف على الأقل")

    try:
        price = float(payload.get("price", 0))
        if price < 0.01:
            errors.append(f"{L['price']}: يجب أن يكون أكبر من 0")
    except (ValueError, TypeError):
        errors.append(f"{L['price']}: قيمة غير صالحة")

    try:
        min_qty = int(payload.get("min_quantity", 0))
        if min_qty < 1:
            errors.append(f"{L['min']}: يجب أن يكون 1 على الأقل")
    except (ValueError, TypeError):
        errors.append(f"{L['min']}: قيمة غير صالحة")

    stock_raw = payload.get("stock_count")
    if stock_raw is not None:
        try:
            stock = int(stock_raw)
            if stock < 1:
                errors.append(f"{L['stock']}: يجب أن يكون 1 على الأقل")
        except (ValueError, TypeError):
            errors.append(f"{L['stock']}: قيمة غير صالحة")

    return errors


def _build_webapp_summary(product_details: dict, lang: str, context) -> str:
    """
    Builds an HTML summary of the WebApp form submission.
    Mirrors the style of _build_ai_summary() for a consistent UI.
    """
    name        = product_details.get("name", "—")
    description = product_details.get("description", "—") or "—"
    price       = product_details.get("price", "0")
    min_qty     = product_details.get("min_quantity", 1)
    stock       = product_details.get("stock_count", min_qty)
    shared_attrs   = product_details.get("shared_attributes",   {}) or {}
    selector_attrs = product_details.get("selector_attributes", []) or []

    # Use processed_attributes (which has _deduplicate_name applied) instead of raw
    processed_attrs = context.user_data.get("processed_attributes", {})
    attr_map        = processed_attrs.get("all_by_id", {})
    # Fallback: build from raw_attributes if processed not available
    if not attr_map:
        raw_attributes = context.user_data.get("raw_attributes", [])
        attr_map       = {a.get("id"): a for a in raw_attributes if a.get("id")}
    # Also build a key-based map as fallback (WebApp may send key instead of UUID)
    attr_key_map   = {a.get("key"): a for a in attr_map.values() if a.get("key")}

    def _resolve_attr(attr_id: str) -> dict:
        """Find attribute by UUID first, then by key string."""
        return attr_map.get(attr_id) or attr_key_map.get(attr_id) or {}

    cat_name = context.user_data.get("selected_category_name", "")
    sub_name = context.user_data.get("selected_subcategory_name", "")
    cat_label = {"tr": "Kategori", "ar": "الفئة",          "en": "Category"}.get(lang, "Category")
    sub_label = {"tr": "Alt Kategori", "ar": "الفئة الفرعية", "en": "Subcategory"}.get(lang, "Subcategory")

    breadcrumb_parts = []
    if cat_name:
        breadcrumb_parts.append(f"✅ <b>{cat_label}:</b> {cat_name}")
    if sub_name and sub_name != cat_name:
        breadcrumb_parts.append(f"📌 <b>{sub_label}:</b> {sub_name}")
    breadcrumb = "\n".join(breadcrumb_parts)

    headers = {
        "tr": "📋 <b>Ürün Özeti</b> (Formdan)",
        "ar": "📋 <b>ملخص المنتج</b> (من النموذج)",
        "en": "📋 <b>Product Summary</b> (from form)",
    }
    field_labels = {
        "tr": {"name": "🏷️ Ürün Adı",  "desc": "📝 Açıklama", "price": "💰 Fiyat", "min": "📦 Min. Sipariş", "stock": "🏭 Stok"},
        "ar": {"name": "🏷️ اسم المنتج","desc": "📝 الوصف",   "price": "💰 السعر", "min": "📦 الحد الأدنى",   "stock": "🏭 المخزون"},
        "en": {"name": "🏷️ Name",       "desc": "📝 Desc.",   "price": "💰 Price", "min": "📦 Min. Order",    "stock": "🏭 Stock"},
    }
    header = headers.get(lang, headers["en"])
    L      = field_labels.get(lang, field_labels["en"])

    lines = []
    if breadcrumb:
        lines.append(breadcrumb)
        lines.append("")
    lines += [
        header, "",
        f"{L['name']}: <b>{name}</b>",
        f"{L['desc']}: {description}",
        f"{L['price']}: <b>{price} ₺</b>",
        f"{L['stock']}: {stock}",
    ]

    import re as _re
    from collections import OrderedDict as _OD

    def _clean_option_display(opt: dict, fallback: str = "") -> tuple:
        """
        Returns (display_label, raw_hex) from an option dict.
        Handles pipe-separated format: '#FF000000|Siyah' → ('Siyah', '#FF000000')
        Never returns raw hex codes in the display label.
        """
        raw_name  = opt.get("name") or opt.get("label") or opt.get("value", fallback)
        raw_value = opt.get("value", "")
        display   = raw_name
        hex_val   = raw_value

        # Handle pipe-separated: '#FF000000|Siyah' in name or value
        if "|" in display:
            hex_part, lbl = display.split("|", 1)
            display = lbl.strip()
            hex_val = hex_part.strip()
        elif "|" in hex_val:
            hex_part, lbl = hex_val.split("|", 1)
            hex_val = hex_part.strip()
            if not display or _re.match(r'^#?[0-9A-Fa-f]{6,8}$', display.strip()):
                display = lbl.strip()

        # If display is still a raw hex code, clear it (will show emoji only)
        if _re.match(r'^#?[0-9A-Fa-f]{6,8}$', display.strip()):
            display = ""

        # Remove duplicated words from API (e.g. 'XS XS' → 'XS', 'Satin Satin' → 'Satin')
        display = _deduplicate_name(display)

        return display, hex_val

    if shared_attrs or selector_attrs:
        attr_header = {
            "tr": "\n📌 <b>Özellikler:</b>",
            "ar": "\n📌 <b>الخصائص:</b>",
            "en": "\n📌 <b>Attributes:</b>",
        }
        lines.append(attr_header.get(lang, attr_header["en"]))

        # ── Helper: sort by ui_order ──────────────────────────────────────────────────────────
        def _ui_order(attr_id_key: str) -> int:
            a = _resolve_attr(attr_id_key)
            v = a.get("ui_order")
            return v if (v is not None) else 9999

        # ── Shared attributes — sorted by ui_order ─────────────────────────────────────────────────────────
        sorted_shared = sorted(shared_attrs.items(), key=lambda kv: _ui_order(kv[0]))
        for attr_id, option_ids in sorted_shared:
            attr      = _resolve_attr(attr_id)
            attr_name = _deduplicate_name(attr.get("name", "") or attr_id)
            rendered  = []
            # Deduplicate option_ids while preserving order
            seen_opt_ids = set()
            deduped_ids  = []
            for oid in (option_ids if isinstance(option_ids, list) else [option_ids]):
                if oid not in seen_opt_ids:
                    seen_opt_ids.add(oid)
                    deduped_ids.append(oid)
            for opt_id in deduped_ids:
                import logging as _log_mod
                _log_ws = _log_mod.getLogger(__name__)
                _log_ws.info(f"[SUMMARY_DEBUG] attr_id={attr_id!r} attr_name={attr_name!r} opt_id={opt_id!r}")
                for opt in attr.get("options", []):
                    if opt.get("id") == opt_id:
                        display, hex_val = _clean_option_display(opt, opt_id)
                        _log_ws.info(f"[SUMMARY_DEBUG]   found opt: name={opt.get('name')!r} label={opt.get('label')!r} value={opt.get('value')!r} → display={display!r}")
                        # Only render color emoji if hex_val is an actual hex color code
                        import re as _re_chk
                        is_hex = bool(hex_val and _re_chk.match(r'^#?[0-9A-Fa-f]{6,8}$', hex_val.strip()))
                        if is_hex:
                            emoji = _render_color_value(hex_val)
                            if display:
                                rendered.append(f"{emoji} {display}")
                            else:
                                rendered.append(emoji)
                        else:
                            rendered.append(display if display else str(opt_id))
                        break
                else:
                    # opt_id may itself be the option name (text-type attrs)
                    _log_ws.info(f"[SUMMARY_DEBUG]   opt_id NOT found in options, using as text: {opt_id!r}")
                    rendered.append(_deduplicate_name(str(opt_id)))
            lines.append(f"  • {attr_name}: {', '.join(rendered)}")

        # ── Selector attributes — GROUP by attribute_id (one line per attr) ──
        # Before: 🎨 Beden: M / 🎨 Beden: L / 🎨 Beden: XL  (3 lines)
        # After:  🎨 Beden: M, L, XL                          (1 line)
        sel_grouped: dict = _OD()  # attr_id → {"name": str, "attr": dict, "values": list, "seen": set}
        for sel in selector_attrs:
            a_id = sel.get("attribute_id", "")
            o_id = sel.get("option_id", "")
            if not a_id:
                continue
            if a_id not in sel_grouped:
                a = _resolve_attr(a_id)
                sel_grouped[a_id] = {
                    "name": _deduplicate_name(a.get("name") or a_id),
                    "attr": a,
                    "values": [],
                    "seen": set(),
                }
            # Deduplicate option_ids
            if o_id and o_id not in sel_grouped[a_id]["seen"]:
                sel_grouped[a_id]["seen"].add(o_id)
                sel_grouped[a_id]["values"].append(o_id)

        # Sort sel_grouped by ui_order before rendering
        sorted_sel = sorted(sel_grouped.items(), key=lambda kv: _ui_order(kv[0]))
        for a_id, grp in sorted_sel:
            attr      = grp["attr"]
            attr_name = grp["name"]
            rendered  = []
            for o_id in grp["values"]:
                for opt in attr.get("options", []):
                    if opt.get("id") == o_id:
                        display, hex_val = _clean_option_display(opt, o_id)
                        # Only render color emoji if hex_val is an actual hex color code
                        import re as _re_chk2
                        is_hex = bool(hex_val and _re_chk2.match(r'^#?[0-9A-Fa-f]{6,8}$', hex_val.strip()))
                        if is_hex:
                            emoji = _render_color_value(hex_val)
                            if display:
                                rendered.append(f"{emoji} {display}")
                            else:
                                rendered.append(emoji)
                        else:
                            rendered.append(display if display else str(o_id))
                        break
                else:
                    # o_id may itself be the option name (text-type attrs)
                    rendered.append(_deduplicate_name(str(o_id)))
            lines.append(f"  🎨 {attr_name}: {', '.join(rendered)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# BACK NAVIGATION HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

async def handle_back_to_category(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Back button: returns to root category selection (Step 1).
    Called from SELECT_SUBCATEGORY state.
    """
    query   = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

    progress = _progress_bar(1)
    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_categories')}",
        parse_mode=ParseMode.HTML,
    )

    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    try:
        categories = await api.get_categories()
    except Exception:
        categories = None

    if not categories:
        _err = {"ar": "❌ تعذّر تحميل الفئات.", "tr": "❌ Kategoriler yüklenemedi.", "en": "❌ Could not load categories."}
        await query.edit_message_text(_err.get(lang, _err["en"]), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # ── Band 1 FIX: Sort by ui_order (ascending) — canonical order from the API ──
    visible_cats = [c for c in categories if c.get("is_visible_for_creating", True)]
    visible_cats.sort(key=lambda c: (int(c.get("ui_order") or 9999), c.get("name", "").lower()))
    categories_map = {}
    keyboard = []
    for cat in visible_cats:
        cid = cat.get("id")
        cname = cat.get("name", "—")
        categories_map[cid] = cname
        keyboard.append([InlineKeyboardButton(cname, callback_data=f"cat_{cid}")])
    context.user_data["categories_map"] = categories_map

    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_select_category')}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_CATEGORY


async def handle_back_to_subcategory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Back button: returns to subcategory selection (Step 2).
    Called from FILL_FORM state.
    """
    query   = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=query.from_user.language_code or "")

    cat_id = context.user_data.get("selected_category")
    if not cat_id:
        # No category saved — go all the way back to category selection
        return await handle_back_to_category(update, context)

    progress = _progress_bar(2)
    await query.edit_message_text(
        f"{progress}\n\n{get_string(lang, 'add_product_loading_subcategories')}",
        parse_mode=ParseMode.HTML,
    )

    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    subcategories = await api.get_categories(parent_id=cat_id)

    if not subcategories:
        # No subcategories — go back to category selection
        return await handle_back_to_category(update, context)

    cat_name = context.user_data.get("selected_category_name", "")
    # ── Band 1 FIX: Sort by ui_order (ascending) — canonical order from the API ──
    visible_subs = [s for s in subcategories if s.get("is_visible_for_creating", True)]
    visible_subs.sort(key=lambda s: (int(s.get("ui_order") or 9999), s.get("name", "").lower()))

    subcategories_map = {}
    keyboard = []
    for sub in visible_subs:
        sid   = sub.get("id")
        sname = sub.get("name", "—")
        subcategories_map[sid] = sname
        keyboard.append([InlineKeyboardButton(sname, callback_data=f"sub_{sid}")])
    context.user_data["subcategories_map"] = subcategories_map

    _back_labels = {"ar": "⬅️ رجوع للفئات", "tr": "⬅️ Kategorilere Dön", "en": "⬅️ Back to Categories"}
    keyboard.append([InlineKeyboardButton(_back_labels.get(lang, _back_labels["en"]), callback_data="back_to_category")])

    cat_label = {"tr": "Kategori", "ar": "الفئة", "en": "Category"}.get(lang, "Category")
    breadcrumb = f"✅ <b>{cat_label}:</b> {cat_name}" if cat_name else ""
    subcategory_prompt = get_string(lang, "add_product_select_subcategory")
    body = f"{breadcrumb}\n\n{subcategory_prompt}" if breadcrumb else subcategory_prompt

    await query.edit_message_text(
        f"{progress}\n\n{body}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return SELECT_SUBCATEGORY


async def handle_manual_entry_fallback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    STATE: SELECT_SUBCATEGORY → FILL_FORM

    Triggered when the supplier taps "✏️ الإدخال اليدوي" (Manual Entry).
    Sends the old free-text prompt so they can type the product description.
    """
    query   = update.callback_query
    await query.answer()
    user    = update.effective_user
    user_id = str(user.id)
    # Use lang stored in user_data (set at start_add_product) for consistency
    lang    = context.user_data.get("lang") or get_user_lang(user_id, telegram_language_code=user.language_code or "")

    processed_attrs = context.user_data.get("processed_attributes", {})
    required_names = (
        [a.get("name") for a in processed_attrs.get("shared_required", [])]
        + [a.get("name") for a in processed_attrs.get("selector_required", [])]
    )

    form_prompt = get_string(lang, "add_product_fill_form")
    if required_names:
        required_label = {
            "tr": "Zorunlu alanlar",
            "ar": "الحقول المطلوبة",
            "en": "Required fields",
        }.get(lang, "Required fields")
        form_prompt += f"\n\n📋 <b>{required_label}:</b>\n" + "\n".join(
            f"  • {n}" for n in required_names if n
        )

    await query.edit_message_text(form_prompt, parse_mode=ParseMode.HTML)
    logger.info("handle_manual_entry_fallback: user_id=%s switched to manual text entry", user_id)
    return FILL_FORM


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
            # ✅ Inline button after successful publish — "Add Another Product"
            CallbackQueryHandler(start_add_product, pattern=r"^add_another_product$"),
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
                # Back button: return to root category selection
                CallbackQueryHandler(
                    handle_back_to_category,
                    pattern=r"^back_to_category$",
                ),
                # NEW: Manual entry fallback when supplier taps "✏️ الإدخال اليدوي"
                CallbackQueryHandler(
                    handle_manual_entry_fallback,
                    pattern=r"^form_manual_entry$",
                ),
            ],
            FILL_FORM: [
                # PRIORITY 1: POST-based Mini App form submission (new mechanism)
                # Fires when FastAPI sends __FORM_SUBMITTED__ sentinel after receiving
                # the form data via POST /webapp/submit.
                # MUST be listed FIRST — before the generic TEXT handler.
                MessageHandler(
                    filters.Regex(r"^__FORM_SUBMITTED__$") & filters.TEXT,
                    handle_form_submitted,
                ),
                # PRIORITY 2: Legacy sendData path (only works with ReplyKeyboard)
                # Kept for backward compatibility in case Mini App is opened via
                # a ReplyKeyboard button in the future.
                MessageHandler(
                    filters.StatusUpdate.WEB_APP_DATA,
                    handle_webapp_data,
                ),
                # PRIORITY 3: manual entry fallback button (✏️ الإدخال اليدوي)
                # NOTE: This handler MUST be in FILL_FORM too (not just SELECT_SUBCATEGORY)
                # because _load_attributes_and_ask_form returns FILL_FORM state BEFORE
                # the supplier sees the WebApp button — so the callback arrives in FILL_FORM.
                CallbackQueryHandler(
                    handle_manual_entry_fallback,
                    pattern=r"^form_manual_entry$",
                ),
                # PRIORITY 3b: Confirm/Edit buttons from AI summary
                # These can arrive in FILL_FORM state when supplier edits and re-submits.
                # After handle_form_submitted returns CONFIRM_DETAILS, the next callback
                # (details_confirm / details_edit) may still be processed in FILL_FORM
                # if the state transition hasn't propagated yet.
                CallbackQueryHandler(
                    handle_confirm_details,
                    pattern=r"^(details_confirm|details_edit)$",
                ),
                # PRIORITY 3c: AI post review buttons (approve/regenerate/edit)
                # Can arrive in FILL_FORM after re-submission flow.
                CallbackQueryHandler(
                    handle_ai_post_review,
                    pattern=r"^(post_approve|post_regenerate|post_edit)$",
                ),
                # Back button: return to subcategory selection
                CallbackQueryHandler(
                    handle_back_to_subcategory,
                    pattern=r"^back_to_subcategory$",
                ),
                # PRIORITY 4: free-text description (legacy AI extraction path)
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
            AI_POST_REVIEW: [
                # Supplier presses ✅ Approve, 🔄 Regenerate, or ✏️ Edit
                CallbackQueryHandler(
                    handle_ai_post_review,
                    pattern=r"^(post_approve|post_regenerate|post_edit)$",
                ),
                # Supplier types their own post text (after pressing ✏️ Edit)
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_ai_post_manual_edit,
                ),
            ],
            COLOR_UPLOAD: [
                # Accept photos for current color
                MessageHandler(filters.PHOTO, handle_color_image_upload),
                # Accept photos sent as documents (high-res)
                MessageHandler(filters.Document.IMAGE, handle_color_image_upload),
                # Done / Skip / Add More buttons
                CallbackQueryHandler(
                    handle_color_action,
                    pattern=r"^color_(done|skip|add_more)$",
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
