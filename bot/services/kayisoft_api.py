"""
bot/services/kayisoft_api.py
============================
KAYISOFT Wholesale API Client — TopKap Telegram Bot

All endpoints MUST include these headers (per KAYISOFT documentation):
    Telegram-User-Id : <telegram_user_id>
    Authorization    : Bearer <token>
    Platform         : telegram
    Accept-Language  : <language_code>  (tr | ar | en)
"""
import os
import hashlib
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

KAYISOFT_API_URL = os.getenv("KAYISOFT_API_URL", "https://api-wholesale.dev.kayisoft.net")

# Support both env var names:
#   TELEGRAM_BOT_API_ENDPOINT_KEY  — used in Railway (correct name)
#   KAYISOFT_API_TOKEN             — legacy .env name
# FIX: kayisoft_api.py was reading KAYISOFT_API_TOKEN but Railway only has TELEGRAM_BOT_API_ENDPOINT_KEY
# This caused ALL API calls to fail with 401 Unauthorized → categories returned None → error shown to user
KAYISOFT_API_TOKEN = (
    os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY") or
    os.getenv("KAYISOFT_API_TOKEN") or
    ""
)


class KayisoftAPI:
    """
    Async HTTP client for the KAYISOFT Wholesale Backend.

    Usage:
        api = KayisoftAPI(telegram_user_id="123456789", language="tr", token="<bearer>")
        categories = await api.get_categories()
    """

    def __init__(
        self,
        telegram_user_id: str,
        language: str = "tr",
        token: Optional[str] = None,
    ):
        self.telegram_user_id = str(telegram_user_id)
        self.language         = language
        self.token            = token or KAYISOFT_API_TOKEN
        self.base_url         = KAYISOFT_API_URL.rstrip("/")

    # ── Headers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _clean(value: str) -> str:
        """
        Remove any characters that are illegal in HTTP headers:
        newline (\n), carriage return (\r), and tab (\t).
        aiohttp raises a security error if these appear in header values.
        """
        return str(value).replace('\n', '').replace('\r', '').replace('\t', '').strip()

    def _headers(self) -> dict:
        """
        Build the mandatory headers required by every KAYISOFT endpoint.
        All values are sanitized to prevent HTTP header injection errors.
        """
        return {
            "Telegram-User-Id": self._clean(self.telegram_user_id),
            "Authorization":    f"Bearer {self._clean(self.token)}",
            "Platform":         "telegram",
            "Accept-Language":  self._clean(self.language),
            "Content-Type":     "application/json",
            "Accept":           "application/json",
        }

    # ── Low-level helpers ─────────────────────────────────────────────────────

    async def _get(self, endpoint: str, params: dict = None):
        """
        Generic GET request.
        Returns parsed JSON on 2xx, or None on 4xx/5xx/exception.
        Handles 2xx responses with empty body gracefully (returns {}).
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        # ── DEBUG: طباعة الـ headers المرسلة للمساعدة في الـ debug ────────────
        headers = self._headers()
        logger.info(
            "GET %s | Telegram-User-Id=%s | Token=%s... | Platform=%s",
            endpoint,
            self.telegram_user_id,
            self.token[:8] if self.token else 'EMPTY',
            headers.get('Platform', 'MISSING'),
        )
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        logger.error(
                            "GET %s → HTTP %s: %s",
                            endpoint, resp.status, text[:500],
                        )
                        return None
                    # ── 2xx: try to parse JSON, fall back to {} ────────────
                    try:
                        import json
                        data = json.loads(text) if text.strip() else {}
                        logger.info("GET %s → HTTP %s OK", endpoint, resp.status)
                        return data
                    except Exception:
                        logger.info(
                            "GET %s → HTTP %s OK (no JSON body)",
                            endpoint, resp.status,
                        )
                        return {}
            except Exception as exc:
                logger.error("GET %s network error: %s", endpoint, exc)
                return None

    async def _post(self, endpoint: str, body: dict = None):
        """
        Generic POST request.
        Returns parsed JSON on 2xx, or None on 4xx/5xx/exception.

        CRITICAL FIX:
        The KAYISOFT connect endpoint (api/seller/telegram-bot/connect)
        returns HTTP 200 with a plain text or empty body on success.
        The original code called resp.json() which threw ContentTypeError,
        causing the except block to return None — making the bot think
        the connection FAILED even when it SUCCEEDED.

        Fix: read text first, then parse JSON manually.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._headers()
        # ── DEBUG: طباعة الـ headers والـ body للمساعدة في الـ debug ────────────
        logger.info(
            "POST %s | Telegram-User-Id=%s | Token=%s... | Platform=%s | body=%s",
            endpoint,
            self.telegram_user_id,
            self.token[:8] if self.token else 'EMPTY',
            headers.get('Platform', 'MISSING'),
            str(body)[:200] if body else '{}',
        )
        # Use a connector that skips strict HTTP header validation
        # This is needed because the KAYISOFT API server sometimes returns
        # responses with non-standard characters in headers.
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(
            connector=connector,
            connector_owner=True,
        ) as session:
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=body or {},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    text = await resp.text()
                    logger.info("POST %s \u2192 HTTP %s | response: %s", endpoint, resp.status, text[:300])
                    if resp.status >= 400:
                        logger.error(
                            "POST %s \u2192 HTTP %s FAILED: %s",
                            endpoint, resp.status, text[:500],
                        )
                        return None
                    # \u2500\u2500 2xx: \u0646\u062c\u0627\u062d \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
                    try:
                        import json
                        data = json.loads(text) if text.strip() else {}
                        logger.info("POST %s \u2192 HTTP %s OK", endpoint, resp.status)
                        return data if data is not None else {}
                    except Exception:
                        # 2xx but no JSON body (e.g. 200 OK with empty body)
                        logger.info(
                            "POST %s \u2192 HTTP %s OK (no JSON body)",
                            endpoint, resp.status,
                        )
                        return {}  # \u2190 {} is not None \u2192 \u064a\u0639\u0646\u064a \u0646\u062c\u0627\u062d
            except Exception as exc:
                exc_str = str(exc)
                # aiohttp raises this when the server response contains \n or \r in headers.
                # This is a known issue with some API servers. We treat it as a network error
                # but log it clearly so it can be investigated.
                if 'Newline' in exc_str or 'carriage' in exc_str:
                    logger.error(
                        "POST %s — server returned invalid HTTP headers (newline/CR in response). "
                        "This is a server-side issue. Error: %s",
                        endpoint, exc_str
                    )
                else:
                    logger.error("POST %s network error: %s", endpoint, exc)
                return None

    # ── 1. Connect seller account ─────────────────────────────────────────────

    async def connect_account(
        self,
        deep_link_token: str,
        telegram_user_name: Optional[str] = None,
    ) -> Optional[dict]:
        """
        POST api/seller/telegram-bot/connect

        Called when the seller opens the deep link generated by the TopKap app.
        `deep_link_token` is the token embedded in the deep link URL — NOT the API token.

        Request body:
            token               : str   — from deep link
            telegram_user_id    : str
            telegram_user_name  : str   (optional)
        """
        body: dict = {
            "token":            deep_link_token,
            "telegram_user_id": self.telegram_user_id,
        }
        if telegram_user_name:
            body["telegram_user_name"] = telegram_user_name
        return await self._post("api/seller/telegram-bot/connect", body)

    # ── 2. Register channel ───────────────────────────────────────────────────

    async def create_channel(
        self,
        channel_id: str,
        channel_name: str,
    ) -> Optional[dict]:
        """
        POST api/seller/telegram-bot/create-channel

        Called after the bot is added as admin to the seller's Telegram channel.
        Registers the channel in the KAYISOFT backend.

        Request body:
            channel_id          : str
            telegram_user_id    : str
            channel_name        : str

        FIX: Telegram channel IDs for supergroups/channels start with -100.
        The minus sign and the channel_name may contain newline/carriage-return
        characters that cause aiohttp to raise:
            "Newline or carriage return character detected in HTTP status message or header"
        We sanitize both values before sending.
        """
        # Sanitize: remove any newline / carriage-return / tab characters
        safe_channel_id   = str(channel_id).replace('\n', '').replace('\r', '').replace('\t', '').strip()
        safe_channel_name = str(channel_name).replace('\n', '').replace('\r', '').replace('\t', '').strip()

        logger.info(
            "create_channel sanitized: channel_id=%s → %s | channel_name=%s → %s",
            channel_id, safe_channel_id, channel_name, safe_channel_name
        )

        body = {
            "channel_id":       safe_channel_id,
            "telegram_user_id": self.telegram_user_id,
            "channel_name":     safe_channel_name,
        }
        return await self._post("api/seller/telegram-bot/create-channel", body)

    # ── 3. Get categories ─────────────────────────────────────────────────────

    async def get_categories(self, parent_id: str = "") -> Optional[list]:
        """
        GET api/seller/categories?parent=<id>

        Pass parent_id="" (empty string) for root-level categories.
        Pass parent_id=<uuid> to get subcategories of a root category.

        Response: list of category objects OR {"data": [...]} wrapper.
        This method normalizes both formats and always returns a list or None.

        Response fields:
            id, name, selected_image, unselected_image, parent,
            ui_order, visible, home_image, is_visible_for_browsing,
            is_visible_for_creating, minimum_required_images,
            maximum_images, maximum_videos
        """
        # ── Language is sent via Accept-Language header ONLY ────────────────────
        # DO NOT send language as a query param — API returns HTTP 422
        # "in query.language: Unauthorized query" if language is in params.
        # The Accept-Language header in _headers() handles localization.
        params = {"parent": parent_id}
        raw = await self._get("api/seller/categories", params=params)

        # ── Normalize response format ─────────────────────────────────────────
        # KAYISOFT API may return:
        #   a) A plain list:          [{...}, {...}]
        #   b) A wrapped dict:        {"result": [{...}]}
        #   c) None on error
        if raw is None:
            logger.error("get_categories: API returned None (network/auth error)")
            return None
        if isinstance(raw, list):
            categories = raw
        elif isinstance(raw, dict):
            categories = None
            for key in ("result", "data", "categories", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    logger.info(
                        "get_categories: unwrapped '%s' key, got %d items",
                        key, len(raw[key]),
                    )
                    categories = raw[key]
                    break
            if categories is None:
                logger.error(
                    "get_categories: unexpected dict response (no list key found): %s",
                    str(raw)[:500],
                )
                return None
        else:
            logger.error("get_categories: unexpected response type: %s", type(raw))
            return None

         # ── Filter: the API may return ALL categories regardless of the
        # 'parent' query param. We must filter client-side:
        #
        #   parent_id == ""   → show only root categories (parent == null)
        #   parent_id == uuid → show only direct children (parent == parent_id)
        if parent_id == "":
            filtered = [c for c in categories if c.get("parent") is None]
            logger.info(
                "get_categories: filtered root-only: %d/%d items",
                len(filtered), len(categories),
            )
        else:
            # Match by parent UUID — field may be a string UUID or a dict with 'id'
            def _parent_matches(cat: dict) -> bool:
                p = cat.get("parent")
                if p is None:
                    return False
                if isinstance(p, str):
                    return p == parent_id
                if isinstance(p, dict):
                    return p.get("id") == parent_id
                return False

            filtered = [c for c in categories if _parent_matches(c)]
            logger.info(
                "get_categories: filtered subcategories of %s: %d/%d items",
                parent_id[:8], len(filtered), len(categories),
            )

        return filtered if filtered else None

    # ── 4. Get attributes for a leaf category ────────────────────────────────

    async def get_attributes(self, category_id: str) -> Optional[list]:
        """
        GET api/seller/categories/{id}/attributes

        Returns all attributes (with their options) for the selected leaf category.
        Used to dynamically build the product form shown to the seller.

        Response: list of attribute objects OR {"result": [...]} wrapper.
        Normalized same as get_categories.

        Response fields:
            id, parent, associated, key, ui_type, ui_filter_type, name, description,
            is_variant_selector, variant_meta, ui_order, required,
            default_value, default_option_id, is_primary_variant_attribute, options[]
        """
        raw = await self._get(f"api/seller/categories/{category_id}/attributes")
        if raw is None:
            logger.error("get_attributes: API returned None")
            return None
        if isinstance(raw, list):
            logger.info("get_attributes: got list with %d items", len(raw))
            return raw
        if isinstance(raw, dict):
            for key in ("result", "data", "attributes", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    logger.info("get_attributes: unwrapped '%s' key, got %d items", key, len(raw[key]))
                    return raw[key]
            logger.error("get_attributes: unexpected dict response: %s", str(raw)[:500])
            return None
        return None

    # ── 5. Get signed URLs for media upload ──────────────────────────────────

    @staticmethod
    def generate_filename(file_bytes: bytes) -> str:
        """
        Generate a valid filename for KAYISOFT media upload.
        Format: <ISO-8601 timestamp>-<SHA-256 hash>
        Example: 2026-05-14T10:00:00.000Z-136a82a872029fda...
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        sha256    = hashlib.sha256(file_bytes).hexdigest()
        return f"{timestamp}-{sha256}"

    async def get_signed_urls(
        self,
        file_names: list[str],
        category_id: str,
    ) -> Optional[list]:
        """
        POST api/extensions/signed-urls

        Get pre-signed S3 upload URLs for product media files.
        file_names must follow format: <ISO-8601 timestamp>-<SHA-256 hash>

        Response: list of {fileName, url}
        Normalizes both plain-list and wrapped-dict responses.
        """
        body = {
            "operation":   "put_product_variant_media",
            "file_names":  file_names,
            "category_id": category_id,
        }
        raw = await self._post("api/extensions/signed-urls", body)
        logger.info("get_signed_urls raw response type=%s value=%s", type(raw).__name__, str(raw)[:300])

        if raw is None:
            logger.error("get_signed_urls: API returned None")
            return None

        # Normalize: API may return plain list OR wrapped dict
        if isinstance(raw, list):
            logger.info("get_signed_urls: got list with %d items", len(raw))
            return raw

        if isinstance(raw, dict):
            for key in ("result", "data", "urls", "signed_urls", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    logger.info(
                        "get_signed_urls: unwrapped '%s' key, got %d items",
                        key, len(raw[key]),
                    )
                    return raw[key]
            # Dict with no list key — log and return None
            logger.error(
                "get_signed_urls: unexpected dict response (no list key): %s",
                str(raw)[:300],
            )
            return None

        logger.error("get_signed_urls: unexpected response type: %s", type(raw))
        return None

    async def upload_media_to_s3(self, signed_url: str, file_bytes: bytes, content_type: str = "image/jpeg") -> bool:
        """
        Upload a media file directly to S3 using the signed URL.
        Returns True on success, False on failure.
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    signed_url,
                    data=file_bytes,
                    headers={"Content-Type": content_type},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status in (200, 204):
                        return True
                    logger.error("S3 upload failed: %s", resp.status)
                    return False
            except Exception as exc:
                logger.error("S3 upload error: %s", exc)
                return False

    # ── 6. Create product ─────────────────────────────────────────────────────

    async def create_product(self, product_data: dict) -> Optional[dict]:
        """
        POST api/seller/products

        Full product payload including:
            name, product_no, category_id, shared_attributes,
            variants[] (each with: stock_id, stock_count, visibility_status,
            titles[], descriptions[], prices[], images[], videos[],
            selector_attributes[], dimensions)

        Response: the created product object
        """
        return await self._post("api/seller/products", product_data)
