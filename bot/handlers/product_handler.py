"""
bot/handlers/product_handler.py
================================
Product Addition Flow — KAYISOFT Integration (v2.0)
====================================================

Purpose:
    Guides the supplier through a structured, AI-assisted product addition flow:
    Root Category → Sub-Category → Attributes (Form) → Images → Variants → Publish

    Design Principles:
    - Frictionless UX  : AI pre-fills what it can; supplier only confirms/corrects.
    - Accuracy First   : All required KAYISOFT attributes collected before submission.
    - Non-Blocking     : All AI and API calls run in executor threads (async-safe).
    - Dual Keyboard    : Reply Keyboard for main navigation, Inline Keyboard for flow steps.

Product Addition Flow:
    /add_product or channel post detected
        │
        ▼
    [1] SELECT ROOT CATEGORY        (GETTING_MAIN_CATEGORY)
        │  Inline keyboard — root categories from KAYISOFT API
        ▼
    [2] SELECT SUB-CATEGORY         (GETTING_SUB_CATEGORY)
        │  Inline keyboard — sub-categories (skipped if none exist)
        ▼
    [3] FILL ATTRIBUTES FORM        (GETTING_ATTRIBUTES)
        │  Required attributes → asked one by one with options or free-text
        │  AI pre-fills optional attributes from channel post text
        ▼
    [4] COLLECT IMAGES              (GETTING_IMAGES)
        │  Bot requests images per variant attribute (e.g., per color)
        ▼
    [5] CONFIRM & PUBLISH           (CONFIRM_KAYISOFT_PRODUCT)
            │  Preview card shown to supplier
            ▼
        [5a] UPLOAD IMAGES     → KAYISOFT Signed URLs → MinIO
        [5b] SUBMIT PRODUCT    → POST /api/seller/products
        [5c] PUBLISH TO CHANNEL → Telegram channel post with Deep Links

Deep Links:
    TopKap  (Supplier App) : https://topkap.app/product/{product_id}
    TopGate (Buyer App)    : https://topgate.app/product/{product_id}

Author:
    TurkTextileHub Engineering Team

Dependencies:
    - bot/services/kayisoft_api.py    : KAYISOFT REST API client
    - bot/services/ai_service.py      : AI extraction & validation (DeepSeek / Gemini)
    - bot/services/session_manager.py : Per-user session state management
    - bot/services/database_service.py: Supabase fallback & channel info
    - bot/states.py                   : ConversationHandler state constants
"""

import asyncio
import logging
import os
import re
import tempfile
from typing import Optional, List, Dict, Any

import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.states import (
    GETTING_MAIN_CATEGORY,
    GETTING_SUB_CATEGORY,
    GETTING_ATTRIBUTES,
    GETTING_IMAGES,
    CONFIRM_KAYISOFT_PRODUCT,
)
from bot.services import kayisoft_api, ai_service, database_service, session_manager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# App Deep Link Base URLs
# ──────────────────────────────────────────────────────────
TOPKAP_BASE_URL  = os.getenv("TOPKAP_BASE_URL",  "https://topkap.app")
TOPGATE_BASE_URL = os.getenv("TOPGATE_BASE_URL", "https://topgate.app")

# ──────────────────────────────────────────────────────────
# Session Keys
# All product-related session data is namespaced under "product_"
# to avoid collisions with other handlers.
# ──────────────────────────────────────────────────────────
_SK_CATEGORY_ID     = "product_category_id"       # Selected leaf category ID
_SK_PARENT_CAT_ID   = "product_parent_category_id" # Selected root category ID
_SK_ATTRIBUTES      = "product_attributes"         # {attr_id: value} — collected so far
_SK_PENDING_ATTRS   = "product_pending_attrs"       # [attr_dict, ...] — queue to ask
_SK_ATTR_INDEX      = "product_current_attr_idx"   # Current position in pending queue
_SK_VARIANT_ATTR    = "product_variant_attr"        # Attribute ID used for variants
_SK_IMAGES          = "product_images"              # {variant_value: [file_id, ...]}
_SK_CURRENT_VARIANT = "product_current_variant"     # Variant being imaged now
_SK_PENDING_VARS    = "product_pending_variants"    # Variants still needing images
_SK_AI_DATA         = "product_ai_data"             # AI-extracted product data
_SK_RAW_TEXT        = "product_raw_text"            # Original channel post text


# ══════════════════════════════════════════════════════════
# ENTRY POINTS
# ══════════════════════════════════════════════════════════

async def start_add_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Entry point for the product addition flow.
    Triggered by /add_product command or the Reply Keyboard button.

    Validates supplier registration, clears previous session data,
    fetches root categories from KAYISOFT API, and presents the
    category selection keyboard.

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.

    Returns:
        GETTING_MAIN_CATEGORY state, or ConversationHandler.END on error.
    """
    user_id = str(update.effective_user.id)
    logger.info(f"[product_handler] User {user_id} started product addition")

    # Validate supplier is registered and approved
    supplier = database_service.get_supplier_by_telegram_id(user_id)
    if not supplier:
        await update.effective_message.reply_text(
            "⚠️ يجب أن تكون مسجلاً كمورد أولاً.\n"
            "استخدم /start للتسجيل."
        )
        return ConversationHandler.END

    if supplier.get("status") != "approved":
        await update.effective_message.reply_text(
            "⏳ حسابك قيد المراجعة. سيتم إشعارك عند الموافقة."
        )
        return ConversationHandler.END

    # Clear any stale product session data
    _clear_product_session(user_id)

    # Fetch root categories from KAYISOFT API (non-blocking)
    await update.effective_message.reply_text("⏳ جاري تحميل فئات المنتجات...")

    categories = await asyncio.get_event_loop().run_in_executor(
        None, kayisoft_api.get_categories, user_id, ""
    )

    if not categories:
        logger.warning(
            f"[product_handler] KAYISOFT categories unavailable for user {user_id} "
            f"— using local fallback"
        )
        categories = database_service.get_local_categories(parent_id=None) or []

    if not categories:
        await update.effective_message.reply_text(
            "❌ تعذّر تحميل فئات المنتجات. يرجى المحاولة لاحقاً.\n"
            "للمساعدة: @TurkTextileSupport"
        )
        return ConversationHandler.END

    keyboard = _build_category_keyboard(categories)

    await update.effective_message.reply_text(
        "📦 *اختر الفئة الرئيسية للمنتج:*\n\n"
        "_يمكنك إلغاء العملية في أي وقت بكتابة /cancel_",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return GETTING_MAIN_CATEGORY


async def start_add_product_with_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_text: str,
) -> int:
    """
    Entry point when product addition is triggered from a channel post.
    AI pre-extracts product data from the raw post text before showing
    the category selector, reducing the number of questions asked.

    Args:
        update   : Incoming Telegram update.
        context  : PTB context object.
        raw_text : Original channel post text for AI extraction.

    Returns:
        GETTING_MAIN_CATEGORY state, or ConversationHandler.END on error.
    """
    user_id = str(update.effective_user.id)
    _clear_product_session(user_id)

    # Store raw text
    session_manager.set(user_id, _SK_RAW_TEXT, raw_text)

    # Run AI extraction in background (non-blocking)
    ai_data = await asyncio.get_event_loop().run_in_executor(
        None, ai_service.extract_product_data, raw_text
    )

    if ai_data and ai_data.get("ai_confidence", 0) > 0.3:
        session_manager.set(user_id, _SK_AI_DATA, ai_data)
        logger.info(
            f"[product_handler] AI pre-extracted data for user {user_id} "
            f"| Confidence: {ai_data.get('ai_confidence', 0):.0%}"
        )

    return await start_add_product(update, context)


# ══════════════════════════════════════════════════════════
# STEP 1 — ROOT CATEGORY SELECTION
# ══════════════════════════════════════════════════════════

async def handle_main_category_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles the supplier's root category selection.
    Fetches sub-categories for the selected category.

    If sub-categories exist → proceed to sub-category selection.
    If no sub-categories → proceed directly to attribute collection.

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        GETTING_SUB_CATEGORY or GETTING_ATTRIBUTES state.
    """
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    category_id = query.data.replace("cat_", "")

    session_manager.set(user_id, _SK_PARENT_CAT_ID, category_id)

    # Fetch sub-categories (non-blocking)
    sub_categories = await asyncio.get_event_loop().run_in_executor(
        None, kayisoft_api.get_categories, user_id, category_id
    )

    if sub_categories:
        keyboard = _build_category_keyboard(sub_categories, prefix="subcat_")
        await query.edit_message_text(
            "📂 *اختر الفئة الفرعية:*",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return GETTING_SUB_CATEGORY
    else:
        # Leaf category — go to attributes
        session_manager.set(user_id, _SK_CATEGORY_ID, category_id)
        return await _start_attributes_collection(update, context, user_id, category_id)


# ══════════════════════════════════════════════════════════
# STEP 2 — SUB-CATEGORY SELECTION
# ══════════════════════════════════════════════════════════

async def handle_sub_category_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles the supplier's sub-category (leaf) selection.
    Proceeds to attribute collection for the selected category.

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        GETTING_ATTRIBUTES state.
    """
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    category_id = query.data.replace("subcat_", "")

    session_manager.set(user_id, _SK_CATEGORY_ID, category_id)
    return await _start_attributes_collection(update, context, user_id, category_id)


# ══════════════════════════════════════════════════════════
# STEP 3 — ATTRIBUTES COLLECTION (FORM)
# ══════════════════════════════════════════════════════════

async def _start_attributes_collection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    category_id: str,
) -> int:
    """
    Fetches category-specific attributes from KAYISOFT API and begins
    the guided form collection.

    Logic:
        1. Fetch attributes for the selected category.
        2. AI pre-fills attributes it extracted from the post text.
        3. Validate: identify missing required fields.
        4. If all required fields are filled → show AI confirmation card.
        5. Otherwise → queue missing fields and ask one by one.

    Args:
        update      : Incoming Telegram update.
        context     : PTB context object.
        user_id     : Telegram user ID as string.
        category_id : Selected leaf category ID.

    Returns:
        GETTING_ATTRIBUTES state, or GETTING_IMAGES if no attributes needed.
    """
    # Fetch category attributes from KAYISOFT (non-blocking)
    attributes_schema = await asyncio.get_event_loop().run_in_executor(
        None, kayisoft_api.get_category_attributes, user_id, category_id
    )

    if not attributes_schema:
        logger.warning(
            f"[product_handler] No attributes schema for category {category_id} "
            f"— skipping to image collection"
        )
        return await _start_image_collection(update, context, user_id)

    # Identify variant attribute (used for image grouping)
    variant_attr = _find_variant_attribute(attributes_schema)
    if variant_attr:
        session_manager.set(user_id, _SK_VARIANT_ATTR, variant_attr)

    # Get AI pre-filled data
    ai_data = session_manager.get(user_id, _SK_AI_DATA) or {}
    ai_attributes = ai_data.get("attributes", {})

    # Validate AI data against schema
    validation = ai_service.validate_product_data(
        {"attributes": ai_attributes},
        attributes_schema,
    )

    # Pre-fill confirmed AI attributes
    session_manager.set(user_id, _SK_ATTRIBUTES, ai_attributes.copy())

    missing_required = validation.get("missing_required", [])

    if not missing_required:
        # AI filled everything — show confirmation card
        await _show_ai_prefill_confirmation(update, context, user_id, attributes_schema, ai_attributes)
        return GETTING_ATTRIBUTES

    # Queue missing required attributes
    session_manager.set(user_id, _SK_PENDING_ATTRS, missing_required)
    session_manager.set(user_id, _SK_ATTR_INDEX, 0)

    return await _ask_next_attribute(update, context, user_id)


async def _ask_next_attribute(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
) -> int:
    """
    Asks the supplier for the next pending required attribute.

    Presentation:
        - If attribute has predefined options → Inline keyboard (3 per row).
        - If attribute is free-text → Plain text prompt.
        - Progress indicator shown: (2/5).

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.
        user_id : Telegram user ID as string.

    Returns:
        GETTING_ATTRIBUTES state, or GETTING_IMAGES when all done.
    """
    pending = session_manager.get(user_id, _SK_PENDING_ATTRS) or []
    idx = session_manager.get(user_id, _SK_ATTR_INDEX) or 0

    if idx >= len(pending):
        # All attributes collected
        return await _start_image_collection(update, context, user_id)

    attr = pending[idx]
    attr_name = attr.get("name_ar") or attr.get("name", "")
    options = attr.get("options", [])
    total = len(pending)
    progress = f"({idx + 1}/{total})"

    if options:
        keyboard = _build_options_keyboard(options, attr_id=str(attr.get("id", "")))
        text = (
            f"📝 *{attr_name}* {progress}\n\n"
            f"اختر من القائمة أو اكتب قيمة مخصصة:"
        )
    else:
        keyboard = None
        text = f"✏️ *{attr_name}* {progress}\n\nاكتب القيمة:"

    msg = update.callback_query.message if (
        update.callback_query
    ) else update.effective_message

    if keyboard:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await msg.reply_text(text, parse_mode="Markdown")

    return GETTING_ATTRIBUTES


async def handle_attribute_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles free-text input for a pending attribute.

    Args:
        update  : Incoming Telegram update (message).
        context : PTB context object.

    Returns:
        GETTING_ATTRIBUTES (next attribute) or GETTING_IMAGES (all done).
    """
    user_id = str(update.effective_user.id)
    value = update.message.text.strip()
    return await _save_attribute_and_advance(update, context, user_id, value)


async def handle_attribute_option_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles inline button selection for an attribute option.

    Callback data format: "attr_{attr_id}_{option_value}"

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        GETTING_ATTRIBUTES (next attribute) or GETTING_IMAGES (all done).
    """
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)

    # Parse callback: "attr_{attr_id}_{value}"
    parts = query.data.split("_", 2)
    value = parts[2] if len(parts) >= 3 else ""

    return await _save_attribute_and_advance(update, context, user_id, value)


async def _save_attribute_and_advance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    value: str,
) -> int:
    """
    Saves the current attribute value and advances the queue index.

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.
        user_id : Telegram user ID as string.
        value   : The attribute value entered by the supplier.

    Returns:
        GETTING_ATTRIBUTES or GETTING_IMAGES state.
    """
    pending = session_manager.get(user_id, _SK_PENDING_ATTRS) or []
    idx = session_manager.get(user_id, _SK_ATTR_INDEX) or 0

    if idx < len(pending):
        attr_id = str(pending[idx].get("id", ""))
        collected = session_manager.get(user_id, _SK_ATTRIBUTES) or {}
        collected[attr_id] = value
        session_manager.set(user_id, _SK_ATTRIBUTES, collected)
        session_manager.set(user_id, _SK_ATTR_INDEX, idx + 1)

    return await _ask_next_attribute(update, context, user_id)


async def _show_ai_prefill_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    attributes_schema: List[Dict],
    ai_attributes: Dict,
) -> None:
    """
    Shows a confirmation card when AI has successfully pre-filled all
    required attributes. Supplier can confirm or request manual editing.

    Card format:
        ✅ AI extracted the following data:
        🔴 Color: Red
        🔵 Fabric: Silk (optional)
        ...
        [✅ Confirm] [✏️ Edit]

    Args:
        update            : Incoming Telegram update.
        context           : PTB context object.
        user_id           : Telegram user ID as string.
        attributes_schema : Full attribute schema from KAYISOFT API.
        ai_attributes     : AI-extracted attribute values.
    """
    lines = ["✅ *استخرج الذكاء الاصطناعي البيانات التالية:*\n"]

    for attr in attributes_schema:
        attr_id = str(attr.get("id", ""))
        name = attr.get("name_ar") or attr.get("name", "")
        value = ai_attributes.get(attr_id, "—")
        icon = "🔴" if attr.get("is_required") else "🔵"
        lines.append(f"{icon} *{name}:* {value}")

    lines.append("\n_هل البيانات صحيحة؟_")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ صحيح، تابع", callback_data="attrs_confirmed"),
            InlineKeyboardButton("✏️ تعديل", callback_data="attrs_edit"),
        ]
    ])

    msg = update.callback_query.message if update.callback_query else update.effective_message
    await msg.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_attrs_confirmed(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles supplier confirming AI-prefilled attributes.
    Proceeds to image collection.

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        GETTING_IMAGES state.
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    return await _start_image_collection(update, context, user_id)


async def handle_attrs_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles supplier requesting to manually edit AI-prefilled attributes.
    Re-queues all attributes for manual entry.

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        GETTING_ATTRIBUTES state.
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    category_id = session_manager.get(user_id, _SK_CATEGORY_ID)
    attributes_schema = await asyncio.get_event_loop().run_in_executor(
        None, kayisoft_api.get_category_attributes, user_id, category_id
    )

    session_manager.set(user_id, _SK_PENDING_ATTRS, attributes_schema or [])
    session_manager.set(user_id, _SK_ATTR_INDEX, 0)

    return await _ask_next_attribute(update, context, user_id)


# ══════════════════════════════════════════════════════════
# STEP 4 — IMAGE COLLECTION
# ══════════════════════════════════════════════════════════

async def _start_image_collection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
) -> int:
    """
    Starts the image collection phase.

    If a variant attribute exists (e.g., color), requests images per variant value.
    Otherwise, requests general product images.

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.
        user_id : Telegram user ID as string.

    Returns:
        GETTING_IMAGES state.
    """
    variant_attr = session_manager.get(user_id, _SK_VARIANT_ATTR)
    attributes = session_manager.get(user_id, _SK_ATTRIBUTES) or {}

    if variant_attr:
        variant_values = _extract_variant_values(attributes, variant_attr)
        if variant_values:
            session_manager.set(user_id, _SK_PENDING_VARS, variant_values)
            session_manager.set(user_id, _SK_IMAGES, {})
            return await _ask_next_variant_images(update, context, user_id)

    # No variants — general images
    session_manager.set(user_id, _SK_IMAGES, {"general": []})
    session_manager.set(user_id, _SK_CURRENT_VARIANT, "general")

    msg = update.callback_query.message if update.callback_query else update.effective_message
    await msg.reply_text(
        "📸 *أرسل صور المنتج* (حتى 10 صور)\n\n"
        "أرسل /done عند الانتهاء من إرسال الصور.",
        parse_mode="Markdown",
    )
    return GETTING_IMAGES


async def _ask_next_variant_images(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
) -> int:
    """
    Requests images for the next pending variant value.

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.
        user_id : Telegram user ID as string.

    Returns:
        GETTING_IMAGES state, or CONFIRM_KAYISOFT_PRODUCT if all variants done.
    """
    pending = session_manager.get(user_id, _SK_PENDING_VARS) or []

    if not pending:
        return await _show_product_confirmation(update, context, user_id)

    current = pending[0]
    session_manager.set(user_id, _SK_CURRENT_VARIANT, current)
    session_manager.set(user_id, _SK_PENDING_VARS, pending[1:])

    msg = update.callback_query.message if update.callback_query else update.effective_message
    await msg.reply_text(
        f"📸 *أرسل صور المنتج — {current}*\n\n"
        f"أرسل صور هذا اللون/المقاس، ثم /done للانتقال للتالي.",
        parse_mode="Markdown",
    )
    return GETTING_IMAGES


async def handle_image_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles an incoming product image from the supplier.
    Stores the Telegram file_id for later upload to MinIO.

    Args:
        update  : Incoming Telegram update (message with photo).
        context : PTB context object.

    Returns:
        GETTING_IMAGES state.
    """
    user_id = str(update.effective_user.id)
    current_variant = session_manager.get(user_id, _SK_CURRENT_VARIANT) or "general"

    photo = update.message.photo[-1]  # Highest resolution
    file_id = photo.file_id

    images = session_manager.get(user_id, _SK_IMAGES) or {}
    if current_variant not in images:
        images[current_variant] = []

    if len(images[current_variant]) >= 10:
        await update.message.reply_text(
            "⚠️ الحد الأقصى 10 صور لكل لون/مقاس. أرسل /done للمتابعة."
        )
        return GETTING_IMAGES

    images[current_variant].append(file_id)
    session_manager.set(user_id, _SK_IMAGES, images)

    count = len(images[current_variant])
    await update.message.reply_text(
        f"✅ تم استلام الصورة ({count}/10). أرسل المزيد أو /done للمتابعة."
    )
    return GETTING_IMAGES


async def handle_images_done(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles /done command during image collection.
    Validates at least one image was received, then checks for
    remaining variant queues or proceeds to confirmation.

    Args:
        update  : Incoming Telegram update (message with /done).
        context : PTB context object.

    Returns:
        GETTING_IMAGES (next variant) or CONFIRM_KAYISOFT_PRODUCT.
    """
    user_id = str(update.effective_user.id)
    current_variant = session_manager.get(user_id, _SK_CURRENT_VARIANT) or "general"
    images = session_manager.get(user_id, _SK_IMAGES) or {}

    if not images.get(current_variant):
        await update.message.reply_text(
            "⚠️ يرجى إرسال صورة واحدة على الأقل قبل المتابعة."
        )
        return GETTING_IMAGES

    pending = session_manager.get(user_id, _SK_PENDING_VARS) or []
    if pending:
        return await _ask_next_variant_images(update, context, user_id)

    return await _show_product_confirmation(update, context, user_id)


# ══════════════════════════════════════════════════════════
# STEP 5 — CONFIRMATION & PUBLISHING
# ══════════════════════════════════════════════════════════

async def _show_product_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
) -> int:
    """
    Displays a product preview card for supplier confirmation before publishing.

    Card includes: title, price, MOQ, attributes summary, image count.
    Actions: Publish Now | Edit | Cancel.

    Args:
        update  : Incoming Telegram update.
        context : PTB context object.
        user_id : Telegram user ID as string.

    Returns:
        CONFIRM_KAYISOFT_PRODUCT state.
    """
    ai_data = session_manager.get(user_id, _SK_AI_DATA) or {}
    attributes = session_manager.get(user_id, _SK_ATTRIBUTES) or {}
    images = session_manager.get(user_id, _SK_IMAGES) or {}
    category_id = session_manager.get(user_id, _SK_CATEGORY_ID) or ""

    title = ai_data.get("title") or "—"
    price = ai_data.get("price") or "—"
    currency = ai_data.get("currency") or "TRY"
    min_qty = ai_data.get("minimum_order_quantity") or 1
    total_images = sum(len(imgs) for imgs in images.values())

    lines = [
        "📋 *مراجعة المنتج قبل النشر*\n",
        f"🏷️ *الاسم:* {title}",
        f"💰 *السعر:* {price} {currency}",
        f"📦 *الحد الأدنى للطلب:* {min_qty} قطعة",
        f"🖼️ *عدد الصور:* {total_images}",
        f"📂 *الفئة:* `{category_id}`",
    ]

    if attributes:
        lines.append("\n*المواصفات:*")
        for attr_id, value in list(attributes.items())[:6]:
            lines.append(f"  • {attr_id}: {value}")

    lines.append("\n_هل تريد نشر هذا المنتج الآن؟_")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 نشر الآن", callback_data="product_confirm_publish"),
            InlineKeyboardButton("✏️ تعديل", callback_data="product_edit"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="product_cancel")],
    ])

    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return CONFIRM_KAYISOFT_PRODUCT


async def handle_product_confirm_publish(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles supplier confirming product publication.

    Executes the full publish pipeline:
        1. Download images from Telegram
        2. Request Signed URLs from KAYISOFT API
        3. Upload images to MinIO via signed URLs
        4. Build structured product payload
        5. Submit product to KAYISOFT API
        6. Publish formatted post to supplier's Telegram channel
           with Deep Links to TopKap and TopGate

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    await query.edit_message_text(
        "⏳ *جاري رفع الصور ونشر المنتج...*\n_قد يستغرق هذا بضع ثوانٍ_",
        parse_mode="Markdown",
    )

    try:
        result = await _execute_publish_pipeline(user_id, context)

        if result["success"]:
            product_id = result.get("product_id", "")
            await query.message.reply_text(
                _build_success_message(product_id),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        else:
            error_msg = result.get("error", "خطأ غير معروف")
            logger.error(
                f"[product_handler] Publish failed for user {user_id}: {error_msg}"
            )
            await query.message.reply_text(
                f"❌ *فشل نشر المنتج*\n\n`{error_msg}`\n\n"
                f"يرجى المحاولة مجدداً أو التواصل مع الدعم: @TurkTextileSupport",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.exception(
            f"[product_handler] Unexpected error in publish pipeline for user {user_id}"
        )
        await query.message.reply_text(
            "❌ حدث خطأ غير متوقع أثناء النشر. يرجى المحاولة لاحقاً."
        )
    finally:
        _clear_product_session(user_id)

    return ConversationHandler.END


async def _execute_publish_pipeline(
    user_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> Dict[str, Any]:
    """
    Executes the complete product publish pipeline.

    Pipeline Steps:
        1. Collect all Telegram file_ids from session.
        2. Request Signed Upload URLs from KAYISOFT API.
        3. Download each image from Telegram and upload to MinIO.
        4. Build product variants from images grouped by variant attribute.
        5. Construct the full KAYISOFT product payload.
        6. Submit product to KAYISOFT API.
        7. Publish formatted post to supplier's Telegram channel.

    Args:
        user_id : Telegram user ID as string.
        context : PTB context object (provides bot instance).

    Returns:
        dict: {
            "success"   : bool,
            "product_id": str  (on success),
            "error"     : str  (on failure),
        }
    """
    ai_data = session_manager.get(user_id, _SK_AI_DATA) or {}
    attributes = session_manager.get(user_id, _SK_ATTRIBUTES) or {}
    images_dict = session_manager.get(user_id, _SK_IMAGES) or {}
    category_id = session_manager.get(user_id, _SK_CATEGORY_ID) or ""

    # ── 1. Collect all file_ids ─────────────────────────────
    all_file_ids = []
    for file_ids in images_dict.values():
        all_file_ids.extend(file_ids)

    # ── 2 & 3. Upload images to MinIO ──────────────────────
    uploaded_images = []
    if all_file_ids:
        file_names = [f"product_{user_id}_{i}.jpg" for i in range(len(all_file_ids))]

        signed_urls_data = await asyncio.get_event_loop().run_in_executor(
            None, kayisoft_api.get_signed_urls, user_id, category_id, file_names
        )

        if signed_urls_data:
            uploaded_images = await _upload_images_to_minio(
                context.bot, all_file_ids, signed_urls_data
            )
        else:
            logger.warning(
                f"[product_handler] Signed URLs unavailable for user {user_id} "
                f"— proceeding without images"
            )

    # ── 4. Build variants ───────────────────────────────────
    variants = []
    variant_attr = session_manager.get(user_id, _SK_VARIANT_ATTR)

    if variant_attr and uploaded_images:
        img_cursor = 0
        for variant_value, file_ids in images_dict.items():
            count = len(file_ids)
            variant_images = uploaded_images[img_cursor: img_cursor + count]
            img_cursor += count
            variants.append({
                "attribute_id": variant_attr,
                "value": variant_value,
                "images": variant_images,
            })

    # ── 5. Build product payload ────────────────────────────
    product_payload = {
        "category_id"            : category_id,
        "title"                  : ai_data.get("title", ""),
        "title_tr"               : ai_data.get("title_tr", ""),
        "description"            : ai_data.get("description", ""),
        "description_tr"         : ai_data.get("description_tr", ""),
        "price"                  : ai_data.get("price"),
        "currency"               : ai_data.get("currency", "TRY"),
        "minimum_order_quantity" : ai_data.get("minimum_order_quantity", 1),
        "attributes"             : attributes,
        "variants"               : variants,
        "images"                 : uploaded_images if not variants else [],
    }

    # ── 6. Submit to KAYISOFT ───────────────────────────────
    kayisoft_result = await asyncio.get_event_loop().run_in_executor(
        None, kayisoft_api.submit_product, user_id, product_payload
    )

    if not kayisoft_result:
        # Fallback: save to Supabase
        logger.warning(
            f"[product_handler] KAYISOFT submit failed for user {user_id} "
            f"— saving to Supabase fallback"
        )
        database_service.add_product({**product_payload, "telegram_id": user_id})
        return {
            "success": True,
            "product_id": "",
            "note": "saved_to_supabase_fallback",
        }

    product_id = kayisoft_result.get("id", "")

    # ── 7. Publish to Telegram channel ─────────────────────
    channel_info = database_service.get_supplier_channel(user_id)
    if channel_info:
        await _publish_to_channel(
            bot=context.bot,
            channel_id=channel_info["channel_id"],
            product_payload=product_payload,
            product_id=product_id,
            image_urls=uploaded_images,
        )

    return {"success": True, "product_id": product_id}


async def _upload_images_to_minio(
    bot,
    file_ids: List[str],
    signed_urls_data: List[Dict],
) -> List[str]:
    """
    Downloads images from Telegram servers and uploads them to MinIO
    object storage via KAYISOFT-provided signed upload URLs.

    Args:
        bot             : Telegram Bot instance (for file download).
        file_ids        : List of Telegram file IDs to download.
        signed_urls_data: List of {signed_url, public_url} dicts from KAYISOFT API.

    Returns:
        List of public MinIO URLs for successfully uploaded images.
        Failed uploads are skipped (not included in result).
    """
    public_urls = []

    for i, file_id in enumerate(file_ids):
        if i >= len(signed_urls_data):
            break

        signed_url = signed_urls_data[i].get("signed_url", "")
        public_url = signed_urls_data[i].get("public_url", "")

        if not signed_url:
            logger.warning(f"[product_handler] Missing signed_url at index {i}")
            continue

        tmp_path = None
        try:
            # Download from Telegram
            tg_file = await bot.get_file(file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                await tg_file.download_to_drive(tmp.name)
                tmp_path = tmp.name

            # Upload to MinIO via PUT request
            with open(tmp_path, "rb") as f:
                response = requests.put(
                    signed_url,
                    data=f,
                    headers={"Content-Type": "image/jpeg"},
                    timeout=30,
                )

            if response.status_code in (200, 204):
                public_urls.append(public_url)
                logger.info(f"[product_handler] ✅ Image {i+1} uploaded: {public_url}")
            else:
                logger.error(
                    f"[product_handler] ❌ MinIO upload failed [{response.status_code}]: "
                    f"{signed_url[:60]}..."
                )

        except Exception as e:
            logger.error(f"[product_handler] ❌ Image upload error at index {i}: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return public_urls


async def _publish_to_channel(
    bot,
    channel_id: str,
    product_payload: Dict,
    product_id: str,
    image_urls: List[str],
) -> None:
    """
    Publishes a professionally formatted product post to the supplier's
    Telegram channel with Deep Links to TopKap and TopGate.

    Post Structure:
        [Product images as media group — max 10]
        ─────────────────────────────────────────
        🏷️ Product Title
        💰 Price | Currency
        📦 Minimum Order Quantity
        ─────────────────────────────────────────
        • Attribute 1: Value
        • Attribute 2: Value  (max 4 shown)
        ─────────────────────────────────────────
        [📲 View on TopKap]  [🛒 Buy on TopGate]

    Args:
        bot            : Telegram Bot instance.
        channel_id     : Telegram channel ID (e.g., -100xxxxxxxxxx).
        product_payload: Structured product data dict.
        product_id     : KAYISOFT product ID for Deep Links.
        image_urls     : List of public MinIO image URLs.
    """
    title    = product_payload.get("title", "")
    price    = product_payload.get("price", "")
    currency = product_payload.get("currency", "TRY")
    min_qty  = product_payload.get("minimum_order_quantity", 1)
    attrs    = product_payload.get("attributes", {})

    # Build caption
    caption_lines = [
        f"🏷️ *{title}*",
        "─" * 28,
        f"💰 *السعر:* {price} {currency}",
        f"📦 *الحد الأدنى للطلب:* {min_qty} قطعة",
    ]

    if attrs:
        caption_lines.append("─" * 28)
        for attr_id, value in list(attrs.items())[:4]:
            caption_lines.append(f"• {attr_id}: {value}")

    caption_lines.append("─" * 28)
    caption = "\n".join(caption_lines)

    # Deep Links
    topkap_url  = f"{TOPKAP_BASE_URL}/product/{product_id}"
    topgate_url = f"{TOPGATE_BASE_URL}/product/{product_id}"

    deep_link_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📲 عرض في TopKap",  url=topkap_url),
            InlineKeyboardButton("🛒 شراء من TopGate", url=topgate_url),
        ]
    ])

    try:
        if image_urls:
            # Send images as media group (max 10)
            media_group = [
                InputMediaPhoto(
                    media=url,
                    caption=caption if i == 0 else None,
                    parse_mode="Markdown" if i == 0 else None,
                )
                for i, url in enumerate(image_urls[:10])
            ]
            await bot.send_media_group(chat_id=channel_id, media=media_group)

            # Send Deep Link buttons as a follow-up message
            await bot.send_message(
                chat_id=channel_id,
                text="🔗 *روابط المنتج:*",
                parse_mode="Markdown",
                reply_markup=deep_link_keyboard,
            )
        else:
            # Text-only post (no images available)
            await bot.send_message(
                chat_id=channel_id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=deep_link_keyboard,
            )

        logger.info(
            f"[product_handler] ✅ Published to channel {channel_id} "
            f"| Product ID: {product_id}"
        )

    except Exception as e:
        logger.error(
            f"[product_handler] ❌ Channel publish error for channel {channel_id}: {e}"
        )


def _build_success_message(product_id: str) -> str:
    """
    Builds the success confirmation message shown to the supplier
    after a product is successfully published.

    Args:
        product_id: KAYISOFT product ID.

    Returns:
        Formatted Markdown string with product links.
    """
    topkap_url  = f"{TOPKAP_BASE_URL}/product/{product_id}"
    topgate_url = f"{TOPGATE_BASE_URL}/product/{product_id}"

    return (
        "✅ *تم نشر المنتج بنجاح!*\n\n"
        f"🆔 معرّف المنتج: `{product_id}`\n\n"
        f"📲 [عرض في TopKap]({topkap_url})\n"
        f"🛒 [عرض في TopGate]({topgate_url})\n\n"
        "_تم نشر المنتج أيضاً على قناتك في تيليغرام._"
    )


# ══════════════════════════════════════════════════════════
# CANCELLATION HANDLERS
# ══════════════════════════════════════════════════════════

async def handle_product_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles product addition cancellation via inline button.

    Args:
        update  : Incoming Telegram update (callback_query).
        context : PTB context object.

    Returns:
        ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    _clear_product_session(user_id)

    await query.edit_message_text(
        "❌ تم إلغاء إضافة المنتج.\n\n"
        "يمكنك البدء من جديد بالضغط على زر *إضافة منتج جديد* أو كتابة /add_product",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel_product_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Handles /cancel command during any step of the product addition flow.

    Args:
        update  : Incoming Telegram update (message).
        context : PTB context object.

    Returns:
        ConversationHandler.END
    """
    user_id = str(update.effective_user.id)
    _clear_product_session(user_id)

    await update.message.reply_text(
        "❌ تم إلغاء إضافة المنتج.\n\n"
        "يمكنك البدء من جديد بالضغط على زر *إضافة منتج جديد* أو كتابة /add_product",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
# CONVERSATION HANDLER BUILDER
# ══════════════════════════════════════════════════════════

def build_product_conversation_handler() -> ConversationHandler:
    """
    Builds and returns the PTB ConversationHandler for the product addition flow.

    State Machine:
        GETTING_MAIN_CATEGORY   → root category selected via inline button
        GETTING_SUB_CATEGORY    → sub-category selected via inline button
        GETTING_ATTRIBUTES      → attribute filled via text or inline button
        GETTING_IMAGES          → images received via photo messages
        CONFIRM_KAYISOFT_PRODUCT→ publish confirmed or cancelled

    Fallbacks:
        /cancel command → cancels from any state

    Returns:
        Configured ConversationHandler instance.
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("add_product", start_add_product),
        ],
        states={
            GETTING_MAIN_CATEGORY: [
                CallbackQueryHandler(
                    handle_main_category_selection,
                    pattern=r"^cat_",
                ),
            ],
            GETTING_SUB_CATEGORY: [
                CallbackQueryHandler(
                    handle_sub_category_selection,
                    pattern=r"^subcat_",
                ),
            ],
            GETTING_ATTRIBUTES: [
                CallbackQueryHandler(
                    handle_attribute_option_selection,
                    pattern=r"^attr_",
                ),
                CallbackQueryHandler(
                    handle_attrs_confirmed,
                    pattern="^attrs_confirmed$",
                ),
                CallbackQueryHandler(
                    handle_attrs_edit,
                    pattern="^attrs_edit$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_attribute_text_input,
                ),
            ],
            GETTING_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_received),
                CommandHandler("done", handle_images_done),
            ],
            CONFIRM_KAYISOFT_PRODUCT: [
                CallbackQueryHandler(
                    handle_product_confirm_publish,
                    pattern="^product_confirm_publish$",
                ),
                CallbackQueryHandler(
                    handle_product_cancel,
                    pattern="^product_cancel$",
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_product_command),
        ],
        name="product_addition",
        persistent=False,
    )


# ══════════════════════════════════════════════════════════
# HELPER UTILITIES
# ══════════════════════════════════════════════════════════

def _build_category_keyboard(
    categories: List[Dict],
    prefix: str = "cat_",
) -> InlineKeyboardMarkup:
    """
    Builds an inline keyboard from a list of KAYISOFT category dicts.
    Arranges buttons in rows of 2 for readability.

    Args:
        categories : List of {id, name, name_ar, name_tr} dicts.
        prefix     : Callback data prefix. Use "cat_" for root, "subcat_" for sub.

    Returns:
        InlineKeyboardMarkup instance.
    """
    buttons = []
    row = []

    for cat in categories:
        cat_id = str(cat.get("id", ""))
        name = cat.get("name_ar") or cat.get("name") or cat_id
        row.append(InlineKeyboardButton(name, callback_data=f"{prefix}{cat_id}"))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


def _build_options_keyboard(
    options: List[Dict],
    attr_id: str,
) -> InlineKeyboardMarkup:
    """
    Builds an inline keyboard from attribute option values.
    Arranges buttons in rows of 3.

    Callback data format: "attr_{attr_id}_{option_value}"

    Args:
        options : List of {id, name, name_ar} option dicts.
        attr_id : Parent attribute ID (embedded in callback data).

    Returns:
        InlineKeyboardMarkup instance.
    """
    buttons = []
    row = []

    for opt in options:
        value = opt.get("name_ar") or opt.get("name") or str(opt.get("id", ""))
        row.append(
            InlineKeyboardButton(
                value,
                callback_data=f"attr_{attr_id}_{value}",
            )
        )

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


def build_supplier_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Builds the persistent Reply Keyboard for the supplier's main menu.
    This keyboard replaces the default Telegram keyboard and stays visible
    throughout the session.

    Layout:
        [ ➕ إضافة منتج جديد ]
        [ 📦 منتجاتي    |  📊 إحصائياتي ]
        [ 🔗 إدارة القناة              ]
        [ ⚙️ الإعدادات  |  💎 اشتراكي  ]

    Returns:
        ReplyKeyboardMarkup with resize_keyboard=True for compact display.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("➕ إضافة منتج جديد")],
            [KeyboardButton("📦 منتجاتي"), KeyboardButton("📊 إحصائياتي")],
            [KeyboardButton("🔗 إدارة القناة")],
            [KeyboardButton("⚙️ الإعدادات"), KeyboardButton("💎 اشتراكي")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def build_trader_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Builds the persistent Reply Keyboard for the trader's main menu.

    Layout:
        [ 🔍 تصفح المنتجات             ]
        [ 🛒 طلباتي     |  ❤️ المفضلة  ]
        [ 🔔 الإشعارات  |  👤 ملفي     ]

    Returns:
        ReplyKeyboardMarkup with resize_keyboard=True for compact display.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🔍 تصفح المنتجات")],
            [KeyboardButton("🛒 طلباتي"), KeyboardButton("❤️ المفضلة")],
            [KeyboardButton("🔔 الإشعارات"), KeyboardButton("👤 ملفي")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _find_variant_attribute(attributes_schema: List[Dict]) -> Optional[str]:
    """
    Identifies the attribute designated for product variants (e.g., color).
    Returns the attribute ID marked with is_variant=True, or None.

    Args:
        attributes_schema: List of attribute dicts from KAYISOFT API.

    Returns:
        Attribute ID string, or None if no variant attribute is defined.
    """
    for attr in attributes_schema:
        if attr.get("is_variant") or attr.get("use_for_variants"):
            return str(attr.get("id", ""))
    return None


def _extract_variant_values(
    attributes: Dict[str, str],
    variant_attr_id: str,
) -> List[str]:
    """
    Extracts individual variant values from a potentially comma-separated
    attribute value string (e.g., "أحمر, أزرق, أخضر" → ["أحمر", "أزرق", "أخضر"]).

    Args:
        attributes      : Dict of {attr_id: value} collected from supplier.
        variant_attr_id : The attribute ID whose value contains variant list.

    Returns:
        List of cleaned individual variant value strings.
    """
    raw = attributes.get(str(variant_attr_id), "")
    if not raw:
        return []

    # Split on comma, Arabic comma, or slash
    values = re.split(r"[,،/]", str(raw))
    return [v.strip() for v in values if v.strip()]


def _clear_product_session(user_id: str) -> None:
    """
    Clears all product-related session keys for a user.
    Called at flow start (to reset stale data) and at flow end
    (after success or cancellation).

    Args:
        user_id: Telegram user ID as string.
    """
    keys = [
        _SK_CATEGORY_ID,
        _SK_PARENT_CAT_ID,
        _SK_ATTRIBUTES,
        _SK_PENDING_ATTRS,
        _SK_ATTR_INDEX,
        _SK_VARIANT_ATTR,
        _SK_IMAGES,
        _SK_CURRENT_VARIANT,
        _SK_PENDING_VARS,
        _SK_AI_DATA,
        _SK_RAW_TEXT,
    ]
    for key in keys:
        session_manager.delete(user_id, key)
