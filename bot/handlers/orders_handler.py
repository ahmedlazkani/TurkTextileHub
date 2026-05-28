"""
bot/handlers/orders_handler.py — TopKap Order Notifications
============================================================
Handles incoming order notifications from KAYISOFT and delivers them
to the relevant supplier via Telegram.

Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │  KAYISOFT Backend                                           │
  │  POST /webhook/orders  ──────────────────────────────────►  │
  │  (new order event)                                          │
  └─────────────────────────────────────────────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  FastAPI (this service)                                     │
  │  POST /webhook/orders  → validate HMAC → notify supplier   │
  └─────────────────────────────────────────────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Telegram Bot                                               │
  │  send_message(supplier_telegram_id, order_card)            │
  └─────────────────────────────────────────────────────────────┘

Webhook Payload (expected from KAYISOFT):
  {
    "supplier_telegram_id": "123456789",   ← Telegram ID of the supplier
    "order_id":             "ORD-2026-001",
    "product_name":         "Erkek Kazak - Lacivert",
    "quantity":             3,
    "buyer_name":           "Ahmed Al-Rashid",
    "total_price":          "₺450.00",
    "currency":             "TRY",          ← optional
    "order_url":            "https://...",  ← optional deep link to order in app
    "secret":               "sha256=..."   ← HMAC signature (optional but recommended)
  }

Security:
  - HMAC-SHA256 signature verification (optional — enabled when ORDERS_WEBHOOK_SECRET is set)
  - Signature is passed in the `X-TopKap-Signature` header OR in the payload `secret` field
  - If ORDERS_WEBHOOK_SECRET is NOT set, signature check is skipped (dev mode)

Environment Variables:
  ORDERS_WEBHOOK_SECRET   — HMAC secret key shared with KAYISOFT (optional but recommended)
  TOPKAP_ORDERS_URL       — Base URL for order deep links (e.g. https://app.topkap.com/orders)

Status:
  ⏳ Awaiting KAYISOFT confirmation that webhooks are supported.
     Code is ready — just needs KAYISOFT to:
       1. Confirm webhook support
       2. Provide ORDERS_WEBHOOK_SECRET
       3. Configure their system to POST to: https://<railway-domain>/webhook/orders
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/webhook", tags=["Orders Webhook"])

# ── Config ─────────────────────────────────────────────────────────────────────
ORDERS_WEBHOOK_SECRET = os.getenv("ORDERS_WEBHOOK_SECRET", "")
TOPKAP_ORDERS_URL = os.getenv(
    "TOPKAP_ORDERS_URL",
    os.getenv("TOPKAP_APP_URL", "https://app-wholesale.dev.kayisoft.net"),
)

# ── Bot application reference ─────────────────────────────────────────────────
# Injected by main.py after the Telegram bot is initialized.
# Used to send messages directly without going through Telegram API.
_bot_application = None


def set_bot_application(application) -> None:
    """
    Called by main.py to share the PTB Application instance.
    This allows the webhook endpoint to send Telegram messages directly
    using the in-process bot, which is faster and more reliable than
    calling the Telegram HTTP API separately.
    """
    global _bot_application
    _bot_application = application
    logger.info("orders_handler: bot application registered ✅")


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — Webhook Payload Schema
# ══════════════════════════════════════════════════════════════════════════════

class OrderNotificationPayload(BaseModel):
    """
    Expected JSON body for POST /webhook/orders.

    All fields except supplier_telegram_id and order_id are optional
    to allow KAYISOFT to evolve the payload schema without breaking the bot.
    """
    # Required fields
    supplier_telegram_id: str = Field(
        ...,
        description="Telegram user ID of the supplier who should receive the notification",
        examples=["123456789"],
    )
    order_id: str = Field(
        ...,
        description="Unique order identifier",
        examples=["ORD-2026-001"],
    )

    # Optional fields — graceful fallbacks if missing
    product_name: Optional[str] = Field(
        None,
        description="Name of the ordered product",
        examples=["Erkek Kazak - Lacivert XL"],
    )
    quantity: Optional[int] = Field(
        None,
        description="Number of units ordered",
        examples=[3],
    )
    buyer_name: Optional[str] = Field(
        None,
        description="Name of the buyer (for display only, not personal data storage)",
        examples=["Ahmed Al-Rashid"],
    )
    total_price: Optional[str] = Field(
        None,
        description="Formatted total price string (e.g. '₺450.00')",
        examples=["₺450.00"],
    )
    currency: Optional[str] = Field(
        None,
        description="ISO 4217 currency code",
        examples=["TRY"],
    )
    order_url: Optional[str] = Field(
        None,
        description="Deep link to the order detail page in the TopKap app",
        examples=["https://app.topkap.com/orders/ORD-2026-001"],
    )
    # HMAC signature — alternative to X-TopKap-Signature header
    secret: Optional[str] = Field(
        None,
        description="HMAC-SHA256 signature: 'sha256=<hex_digest>'",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY — HMAC Signature Verification
# ══════════════════════════════════════════════════════════════════════════════

def _verify_signature(raw_body: bytes, provided_sig: Optional[str]) -> bool:
    """
    Verifies the HMAC-SHA256 signature of the incoming webhook payload.

    Signature format: "sha256=<hex_digest>"
    The digest is computed over the raw request body bytes using the
    ORDERS_WEBHOOK_SECRET as the key.

    Returns:
        True  — signature is valid OR secret is not configured (dev mode)
        False — signature is invalid (reject the request)
    """
    if not ORDERS_WEBHOOK_SECRET:
        # Secret not configured → skip verification (dev/staging mode)
        logger.debug("_verify_signature: ORDERS_WEBHOOK_SECRET not set — skipping check")
        return True

    if not provided_sig:
        logger.warning("_verify_signature: no signature provided but secret is configured")
        return False

    # Strip "sha256=" prefix if present
    sig_hex = provided_sig.removeprefix("sha256=").strip()

    # Compute expected signature
    expected = hmac.new(
        key=ORDERS_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected, sig_hex)
    if not is_valid:
        logger.warning(
            "_verify_signature: HMAC mismatch — expected=%s... provided=%s...",
            expected[:8], sig_hex[:8],
        )
    return is_valid


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUILDER — Order Notification Card
# ══════════════════════════════════════════════════════════════════════════════

def _build_order_notification(payload: OrderNotificationPayload, lang: str = "tr") -> str:
    """
    Builds a formatted Telegram HTML message for the order notification.

    The message is designed to be clear, professional, and actionable.
    Language is determined by the supplier's stored language preference.

    Args:
        payload: Validated order notification data from KAYISOFT
        lang:    Supplier's language code ("tr" | "ar" | "en")

    Returns:
        HTML-formatted string ready to send via Telegram
    """
    # ── Header per language ────────────────────────────────────────────────────
    headers = {
        "tr": "🛒 <b>Yeni Sipariş Geldi!</b>",
        "ar": "🛒 <b>طلبية جديدة وصلت!</b>",
        "en": "🛒 <b>New Order Received!</b>",
    }

    # ── Field labels per language ──────────────────────────────────────────────
    labels = {
        "tr": {
            "order_id":    "📋 Sipariş No",
            "product":     "📦 Ürün",
            "quantity":    "🔢 Adet",
            "buyer":       "👤 Alıcı",
            "total":       "💰 Toplam",
            "view_order":  "📲 Siparişi Görüntüle",
        },
        "ar": {
            "order_id":    "📋 رقم الطلبية",
            "product":     "📦 المنتج",
            "quantity":    "🔢 الكمية",
            "buyer":       "👤 المشتري",
            "total":       "💰 الإجمالي",
            "view_order":  "📲 عرض الطلبية",
        },
        "en": {
            "order_id":    "📋 Order ID",
            "product":     "📦 Product",
            "quantity":    "🔢 Quantity",
            "buyer":       "👤 Buyer",
            "total":       "💰 Total",
            "view_order":  "📲 View Order",
        },
    }

    lbl = labels.get(lang, labels["tr"])
    header = headers.get(lang, headers["tr"])

    # ── Build message body ─────────────────────────────────────────────────────
    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━━━",
        f"{lbl['order_id']}: <code>{payload.order_id}</code>",
    ]

    if payload.product_name:
        lines.append(f"{lbl['product']}: {payload.product_name}")

    if payload.quantity is not None:
        lines.append(f"{lbl['quantity']}: {payload.quantity}")

    if payload.buyer_name:
        lines.append(f"{lbl['buyer']}: {payload.buyer_name}")

    if payload.total_price:
        lines.append(f"{lbl['total']}: <b>{payload.total_price}</b>")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def _build_order_keyboard(payload: OrderNotificationPayload, lang: str = "tr"):
    """
    Builds an InlineKeyboardMarkup with a "View Order" button.

    The button opens the order detail page in the TopKap app.
    Falls back to the main orders page if no order_url is provided.

    Returns:
        InlineKeyboardMarkup | None
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # Determine the URL to open
    order_url = payload.order_url
    if not order_url:
        # Construct a fallback URL using the base orders URL + order_id
        order_url = f"{TOPKAP_ORDERS_URL}?order_id={payload.order_id}"

    view_labels = {
        "tr": "📲 Siparişi Görüntüle",
        "ar": "📲 عرض الطلبية",
        "en": "📲 View Order",
    }
    label = view_labels.get(lang, view_labels["tr"])

    keyboard = [[InlineKeyboardButton(label, url=order_url)]]
    return InlineKeyboardMarkup(keyboard)


# ══════════════════════════════════════════════════════════════════════════════
# CORE NOTIFICATION SENDER
# ══════════════════════════════════════════════════════════════════════════════

async def _send_order_notification(payload: OrderNotificationPayload) -> bool:
    """
    Sends the order notification message to the supplier via Telegram.

    Uses the in-process bot application (fastest path) if available,
    otherwise falls back to the Telegram HTTP API.

    Args:
        payload: Validated order notification data

    Returns:
        True if message was sent successfully, False otherwise
    """
    supplier_id = payload.supplier_telegram_id

    # ── Resolve supplier's language preference ────────────────────────────────
    try:
        from bot.services.language_service import get_user_lang
        lang = get_user_lang(supplier_id) or "tr"
    except Exception:
        lang = "tr"

    # ── Build message content ─────────────────────────────────────────────────
    text = _build_order_notification(payload, lang)
    keyboard = _build_order_keyboard(payload, lang)

    logger.info(
        "Sending order notification: supplier=%s order_id=%s lang=%s",
        supplier_id, payload.order_id, lang,
    )

    # ── Strategy 1: In-process bot application (preferred) ────────────────────
    if _bot_application is not None:
        try:
            await _bot_application.bot.send_message(
                chat_id=int(supplier_id),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            logger.info(
                "Order notification sent via in-process bot: supplier=%s order_id=%s",
                supplier_id, payload.order_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "In-process send failed for supplier=%s: %s — trying HTTP fallback",
                supplier_id, exc,
            )

    # ── Strategy 2: Telegram HTTP API fallback ────────────────────────────────
    import httpx

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    if not bot_token:
        logger.error("Cannot send notification: TELEGRAM_BOT_TOKEN not set")
        return False

    # Build inline keyboard payload for HTTP API
    keyboard_json = None
    if keyboard:
        keyboard_json = {
            "inline_keyboard": [
                [{"text": btn.text, "url": btn.url} for btn in row]
                for row in keyboard.inline_keyboard
            ]
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": int(supplier_id),
                    "text": text,
                    "parse_mode": "HTML",
                    **({"reply_markup": keyboard_json} if keyboard_json else {}),
                },
            )
        if resp.status_code == 200:
            logger.info(
                "Order notification sent via HTTP API: supplier=%s order_id=%s",
                supplier_id, payload.order_id,
            )
            return True
        else:
            logger.error(
                "HTTP API returned %d for supplier=%s: %s",
                resp.status_code, supplier_id, resp.text[:300],
            )
            return False
    except Exception as exc:
        logger.error("HTTP API fallback failed for supplier=%s: %s", supplier_id, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI ROUTE — POST /webhook/orders
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/orders",
    response_class=JSONResponse,
    summary="Receive new order notifications from KAYISOFT",
    description=(
        "Called by KAYISOFT backend when a new order is placed for a supplier. "
        "Validates the HMAC signature (if configured), then sends a Telegram "
        "notification to the supplier with order details and a 'View Order' button."
    ),
)
async def receive_order_notification(request: Request) -> JSONResponse:
    """
    Webhook endpoint for KAYISOFT order notifications.

    Flow:
      1. Read raw request body (needed for HMAC verification)
      2. Verify HMAC signature (if ORDERS_WEBHOOK_SECRET is configured)
      3. Parse JSON payload into OrderNotificationPayload
      4. Send Telegram notification to the supplier
      5. Return 200 OK (or error code on failure)

    KAYISOFT should configure their system to POST to:
      https://<railway-domain>/webhook/orders

    Headers expected (optional but recommended):
      X-TopKap-Signature: sha256=<hmac_hex>
      Content-Type: application/json
    """
    # ── Step 1: Read raw body ─────────────────────────────────────────────────
    raw_body = await request.body()

    # ── Step 2: Verify HMAC signature ────────────────────────────────────────
    # Check header first, then fall back to payload field
    sig_header = request.headers.get("X-TopKap-Signature", "")

    if not _verify_signature(raw_body, sig_header or None):
        logger.warning(
            "receive_order_notification: invalid signature from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature. Check ORDERS_WEBHOOK_SECRET configuration.",
        )

    # ── Step 3: Parse payload ─────────────────────────────────────────────────
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        logger.error("receive_order_notification: invalid JSON: %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    try:
        payload = OrderNotificationPayload(**data)
    except Exception as exc:
        logger.error("receive_order_notification: payload validation failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"Payload validation error: {exc}")

    # ── Also check signature from payload body (alternative to header) ────────
    if not sig_header and payload.secret:
        if not _verify_signature(raw_body, payload.secret):
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature in payload body.",
            )

    logger.info(
        "receive_order_notification: valid request — supplier=%s order_id=%s",
        payload.supplier_telegram_id, payload.order_id,
    )

    # ── Step 4: Send Telegram notification ───────────────────────────────────
    success = await _send_order_notification(payload)

    if not success:
        # Return 200 anyway to prevent KAYISOFT from retrying endlessly.
        # Log the failure for monitoring.
        logger.error(
            "receive_order_notification: failed to notify supplier=%s for order=%s",
            payload.supplier_telegram_id, payload.order_id,
        )
        return JSONResponse(
            content={
                "status": "error",
                "message": "Notification delivery failed. Check bot logs.",
                "order_id": payload.order_id,
            },
            status_code=200,  # Return 200 to prevent KAYISOFT retry storm
        )

    # ── Step 5: Return success ────────────────────────────────────────────────
    return JSONResponse(
        content={
            "status": "ok",
            "message": "Notification sent successfully.",
            "order_id": payload.order_id,
            "supplier_telegram_id": payload.supplier_telegram_id,
        },
        status_code=200,
    )


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI ROUTE — GET /webhook/orders/test
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/orders/test",
    response_class=JSONResponse,
    summary="Test webhook endpoint availability",
    description="Simple GET endpoint to verify the webhook route is reachable. Returns configuration status.",
)
async def test_webhook_endpoint() -> JSONResponse:
    """
    Health check for the orders webhook endpoint.

    KAYISOFT can call this to verify the endpoint is reachable before
    configuring their webhook integration.

    Returns:
        JSON with endpoint status and configuration summary
    """
    return JSONResponse(
        content={
            "status": "ok",
            "endpoint": "POST /webhook/orders",
            "signature_verification": "enabled" if ORDERS_WEBHOOK_SECRET else "disabled (set ORDERS_WEBHOOK_SECRET to enable)",
            "bot_application_registered": _bot_application is not None,
            "orders_url": TOPKAP_ORDERS_URL,
            "note": (
                "Awaiting KAYISOFT webhook configuration. "
                "Once configured, POST order payloads to /webhook/orders"
            ),
        }
    )
