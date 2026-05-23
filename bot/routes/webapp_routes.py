"""
bot/routes/webapp_routes.py — TopKap WebApp Router
====================================================
FastAPI router that serves:

  1. GET /webapp/product-form?category_id={uuid}&lang={ar|tr|en}&user_id={telegram_id}
     → Serves the product form HTML page

  2. GET /api/attributes/{category_id}?user_id={telegram_id}
     → Proxies KAYISOFT GET /categories/{id}/attributes
     → Uses server-side JWT token fetched for the given user_id

USAGE (register in your FastAPI app / main.py):
    from bot.routes.webapp_routes import router as webapp_router
    app.include_router(webapp_router)

ENVIRONMENT VARIABLES REQUIRED:
    RAILWAY_DOMAIN          — public domain of this Railway service (e.g. "topkap.up.railway.app")
    KAYISOFT_API_BASE_URL   — base URL of KAYISOFT REST API
    TELEGRAM_BOT_API_ENDPOINT_KEY — same Bearer token used by the bot for all KAYISOFT calls
                              (used when no per-user token is in cache)

ARCHITECTURE NOTE:
    The /api/attributes/{category_id} endpoint must obtain a valid KAYISOFT JWT for the
    requesting user.  Two strategies are tried in order:
      1. In-memory token cache (token_cache[user_id]) — fastest, no network call
      2. Server-to-server token exchange via KAYISOFT /auth/token endpoint
         using the Telegram user_id as the subject claim

    If neither works, a 401 error is returned so the WebApp can handle it gracefully.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter()

# ── Pending submissions store ──────────────────────────────────────────────────
# Keys:   telegram_user_id (str)
# Values: dict with form payload — consumed once by the bot polling loop
# This is a simple in-memory store; it works because bot and FastAPI share the
# same process (same Python interpreter, same memory space).
pending_submissions: dict = {}

# ── Bot application reference ─────────────────────────────────────────────────
# Set by main.py after the bot is initialized so FastAPI can call bot methods
# directly without going through Telegram API (avoids the sendMessage hack).
_bot_application = None

def set_bot_application(application) -> None:
    """Called by main.py to share the PTB Application instance with FastAPI."""
    global _bot_application
    _bot_application = application
    logger.info("webapp_routes: bot application registered ✅")


class FormSubmission(BaseModel):
    """Pydantic model for the POST /webapp/submit request body."""
    user_id: str
    payload: dict[str, Any]

# ── In-memory token cache ──────────────────────────────────────────────────────
# Keys:   telegram_user_id (str)
# Values: {"access_token": str, "expires_at": float}  — expires_at is UNIX timestamp
# This cache is populated by the bot's auth flow when a user logs in.
# Import from your auth module or define the shared dict here.
try:
    from bot.services.kayisoft_api import _token_cache as token_cache  # type: ignore
except ImportError:
    # Fallback: define a module-level dict that auth code can import from this module
    token_cache: dict = {}
    logger.warning(
        "webapp_routes: could not import token_cache from kayisoft_api — "
        "using local empty dict. Auth will rely on server-to-server exchange only."
    )

# ── Config ─────────────────────────────────────────────────────────────────────
KAYISOFT_BASE    = os.getenv("KAYISOFT_API_URL", os.getenv("KAYISOFT_API_BASE_URL", "https://api-wholesale.dev.kayisoft.net"))
# Use the same token the bot uses — TELEGRAM_BOT_API_ENDPOINT_KEY (or legacy KAYISOFT_API_TOKEN)
# This is a static Bearer token, NOT a per-user JWT — it works as a server-level auth token
# .strip() is CRITICAL — env vars from Railway/dotenv may contain trailing \n
# which causes "Illegal header value" when used as Bearer token
KAYISOFT_API_KEY = (
    os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or
    os.getenv("KAYISOFT_API_TOKEN") or
    os.getenv("KAYISOFT_API_KEY") or
    ""
).strip()
RAILWAY_DOMAIN   = os.getenv("RAILWAY_DOMAIN", "localhost:8000")

# Path to the compiled HTML form file
# Adjust if your project layout differs
FORM_HTML_PATH = Path(__file__).parent.parent / "webapp" / "product_form.html"


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 1 — Serve the WebApp HTML page
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/webapp/product-form",
    response_class=HTMLResponse,
    summary="Serve the TopKap product addition Mini App form",
    tags=["WebApp"],
)
async def serve_product_form(
    request:     Request,
    category_id: str           = Query(...,  description="Leaf category UUID"),
    lang:        Optional[str] = Query("ar", description="UI language: ar | tr | en"),
    user_id:     Optional[str] = Query(None, description="Telegram user ID"),
) -> HTMLResponse:
    """
    Serves the single-file HTML WebApp for the product addition form.

    The HTML file already contains all CSS and JS.
    Query params (category_id, lang, user_id) are passed through — the
    embedded JavaScript reads them via window.location.search.

    Security: No auth required here — the page itself is static HTML.
    Actual data access is gated in the /api/attributes/{category_id} proxy.
    """
    if not FORM_HTML_PATH.exists():
        logger.error("Product form HTML not found at: %s", FORM_HTML_PATH)
        raise HTTPException(
            status_code=500,
            detail="Product form template not found. Check FORM_HTML_PATH in webapp_routes.py.",
        )

    html_content = FORM_HTML_PATH.read_text(encoding="utf-8")

    logger.info(
        "Serving product form: category_id=%s lang=%s user_id=%s remote=%s",
        category_id, lang, user_id, request.client.host,
    )

    return HTMLResponse(content=html_content, status_code=200)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 2 — Proxy KAYISOFT category attributes
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/api/attributes/{category_id}",
    response_class=JSONResponse,
    summary="Proxy: fetch category attributes from KAYISOFT API",
    tags=["WebApp"],
)
async def proxy_attributes(
    category_id: str,
    user_id:     Optional[str] = Query(None, description="Telegram user ID"),
    lang:        Optional[str] = Query(None, description="User language code (ar/tr/en)"),
) -> JSONResponse:
    """
    Proxies GET /api/categories/{category_id}/attributes from KAYISOFT.

    Why proxy instead of calling from the browser directly?
      - KAYISOFT requires a per-user JWT token (Bearer auth)
      - The token lives on the server (never exposed to the browser)
      - CORS: KAYISOFT may not whitelist the Telegram WebApp origin

    Auth flow:
      1. Try token_cache[user_id] — populated by bot login
      2. Try server-to-server exchange using KAYISOFT_API_KEY
      3. Return 401 if neither works

    Returns:
        JSON array of attribute objects compatible with the WebApp frontend.
    """
    # ── Step 1: Obtain JWT ─────────────────────────────────────────────────────
    token = await _get_user_token(user_id)
    if not token:
        logger.warning("proxy_attributes: no token for user_id=%s", user_id)
        raise HTTPException(
            status_code=401,
            detail="Could not obtain authentication token for this user.",
        )

    # ── Step 2: Call KAYISOFT API ──────────────────────────────────────────────
    kayisoft_url = f"{KAYISOFT_BASE}/api/seller/categories/{category_id}/attributes"

    logger.info(
        "Proxying attributes: url=%s user_id=%s",
        kayisoft_url, user_id,
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                kayisoft_url,
                headers={
                    "Authorization":    f"Bearer {token}",
                    "Telegram-User-Id": str(user_id or ""),
                    "Platform":         "telegram",
                    "Accept":           "application/json",
                    "Accept-Language":  lang or "ar",  # Task 10: Follow user's language
                },
            )
    except httpx.TimeoutException:
        logger.error("proxy_attributes: KAYISOFT request timed out for category_id=%s", category_id)
        raise HTTPException(status_code=504, detail="Upstream API timed out.")
    except httpx.RequestError as exc:
        logger.error("proxy_attributes: network error: %s", exc)
        raise HTTPException(status_code=502, detail="Network error reaching upstream API.")

    # ── Step 3: Forward response ───────────────────────────────────────────────
    if resp.status_code == 401:
        # Token may have expired — evict from cache for next request
        if user_id and user_id in token_cache:
            del token_cache[user_id]
        raise HTTPException(status_code=401, detail="KAYISOFT token rejected. Please re-login.")

    if resp.status_code == 404:
        # Category not found — return empty list so WebApp renders without attrs
        logger.warning("proxy_attributes: category_id=%s not found (404)", category_id)
        return JSONResponse(content=[], status_code=200)

    if resp.status_code not in (200, 201):
        logger.error(
            "proxy_attributes: upstream returned %d for category_id=%s — body: %s",
            resp.status_code, category_id, resp.text[:300],
        )
        raise HTTPException(
            status_code=502,
            detail=f"Upstream API returned HTTP {resp.status_code}.",
        )

    try:
        data = resp.json()
    except Exception:
        logger.error("proxy_attributes: invalid JSON from upstream: %s", resp.text[:300])
        raise HTTPException(status_code=502, detail="Upstream returned invalid JSON.")

    logger.info(
        "proxy_attributes: returning %d attributes for category_id=%s",
        len(data) if isinstance(data, list) else "?",
        category_id,
    )

    # ── DEBUG: log first attribute + first option to understand KAYISOFT response shape ──
    import json as _json
    if isinstance(data, list) and data:
        first_attr = data[0]
        logger.info(
            "proxy_attributes DEBUG — first attr keys: %s",
            list(first_attr.keys()) if isinstance(first_attr, dict) else type(first_attr),
        )
        first_opts = first_attr.get("options", []) if isinstance(first_attr, dict) else []
        if first_opts:
            logger.info(
                "proxy_attributes DEBUG — first option keys: %s | value: %s",
                list(first_opts[0].keys()) if isinstance(first_opts[0], dict) else type(first_opts[0]),
                _json.dumps(first_opts[0], ensure_ascii=False)[:300],
            )
        logger.info(
            "proxy_attributes DEBUG — full first attr: %s",
            _json.dumps(first_attr, ensure_ascii=False)[:500],
        )

    # ── NORMALIZE: ensure every option has a valid 'id' field ─────────────────
    # KAYISOFT may return options with different field names depending on the endpoint.
    # The WebApp HTML relies on opt.id for the value to send back.
    # If opt.id is missing/empty, fall back to: opt.uuid → opt.key → opt.value
    if isinstance(data, list):
        for attr in data:
            if not isinstance(attr, dict):
                continue
            options = attr.get("options", [])
            if not isinstance(options, list):
                continue
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                # Ensure 'id' is a non-empty string
                if not opt.get("id"):
                    opt["id"] = (
                        opt.get("uuid") or
                        opt.get("option_id") or
                        opt.get("key") or
                        opt.get("value") or
                        ""
                    )
                # Ensure 'label' is set for display (extract from pipe-separated value if needed)
                if not opt.get("label"):
                    raw_val = opt.get("value", "")
                    if raw_val and "|" in str(raw_val):
                        parts = str(raw_val).split("|")
                        opt["label"] = parts[-1].strip()  # last part = human-readable name
                    else:
                        opt["label"] = str(raw_val)

        logger.info(
            "proxy_attributes: normalized %d attributes with options",
            sum(1 for a in data if isinstance(a, dict) and a.get("options"))
        )

    return JSONResponse(content=data, status_code=200)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 3 — Receive form submission from Mini App (POST)
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/webapp/submit",
    response_class=JSONResponse,
    summary="Receive product form data from Mini App",
    tags=["WebApp"],
)
async def submit_product_form(
    body: FormSubmission,
) -> JSONResponse:
    """
    Called by the Mini App JavaScript via fetch() when the supplier taps Save.

    Stores the payload in pending_submissions[user_id] so the bot's
    check_pending_submission() can pick it up and continue the conversation.

    This replaces tg.sendData() which only works with ReplyKeyboard buttons.
    """
    user_id = str(body.user_id).strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    pending_submissions[user_id] = body.payload
    logger.info(
        "submit_product_form: stored submission for user_id=%s keys=%s",
        user_id, list(body.payload.keys()),
    )

    # ── Strategy 1: Direct in-process call (preferred) ─────────────────────────
    # If the bot application is registered, call handle_form_submitted directly
    # by injecting a fake Update into the bot's update queue.
    # This is reliable because bot and FastAPI run in the same asyncio event loop.
    triggered = False
    if _bot_application is not None:
        try:
            from telegram import Update, Message, User, Chat
            import datetime

            # Build a minimal fake Update that looks like a text message
            # from the user containing __FORM_SUBMITTED__
            fake_user = User(
                id=int(user_id),
                first_name="Supplier",
                is_bot=False,
            )
            fake_chat = Chat(id=int(user_id), type="private")
            fake_message = Message(
                message_id=999999,
                date=datetime.datetime.utcnow(),
                chat=fake_chat,
                from_user=fake_user,
                text="__FORM_SUBMITTED__",
            )
            fake_update = Update(
                update_id=999999,
                message=fake_message,
            )
            await _bot_application.update_queue.put(fake_update)
            triggered = True
            logger.info("submit_product_form: injected fake Update into bot queue for user_id=%s", user_id)
        except Exception as exc:
            logger.warning("submit_product_form: could not inject Update: %s", exc)

    # ── Strategy 2: sendMessage fallback (if direct injection failed) ───────────
    if not triggered:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
        if bot_token:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": int(user_id),
                            "text": "__FORM_SUBMITTED__",
                        },
                    )
                logger.info("submit_product_form: sent __FORM_SUBMITTED__ via sendMessage fallback")
            except Exception as exc:
                logger.warning("submit_product_form: sendMessage fallback also failed: %s", exc)

    return JSONResponse(content={"status": "ok", "user_id": user_id})


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL — Token Resolver
# ══════════════════════════════════════════════════════════════════════════════

async def _get_user_token(user_id: Optional[str]) -> Optional[str]:
    """
    Resolves a valid KAYISOFT Bearer token for the given Telegram user_id.

    Strategy:
      1. token_cache[user_id]   — already obtained during bot login (fastest)
      2. Server-to-server token exchange via KAYISOFT_API_KEY  (fallback)

    Returns:
        str | None — JWT access token, or None on failure
    """
    import time

    # ── Check in-memory cache first ────────────────────────────────────────────
    if user_id and user_id in token_cache:
        cached = token_cache[user_id]
        expires_at = cached.get("expires_at", 0)
        # Accept if more than 60 s of validity remaining
        if expires_at - time.time() > 60:
            logger.debug("_get_user_token: cache hit for user_id=%s", user_id)
            return cached.get("access_token")
        else:
            logger.debug("_get_user_token: cached token expired for user_id=%s", user_id)
            del token_cache[user_id]

    # ── Fallback: use static server-level Bearer token ────────────────────────
    # KAYISOFT uses a single static Bearer token (TELEGRAM_BOT_API_ENDPOINT_KEY)
    # for all server-side API calls — same token the bot uses.
    # This is NOT a per-user JWT; it's a server-to-server API key.
    if not KAYISOFT_API_KEY:
        logger.warning("_get_user_token: KAYISOFT_API_KEY not set — cannot exchange token")
        return None

    logger.info("_get_user_token: using static server token for user_id=%s", user_id)
    return KAYISOFT_API_KEY
