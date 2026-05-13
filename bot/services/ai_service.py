"""
bot/services/ai_service.py
==========================
AI Service — Product Data Extraction & Validation
==================================================

Purpose:
    Extracts structured product data from free-form Arabic/Turkish text
    using a configurable AI provider (DeepSeek, Gemini, or OpenAI).
    Validates extracted data against KAYISOFT category attributes.

Design:
    - Provider-agnostic: switch between providers via AI_PROVIDER env var
    - Lazy initialization: AI client is created on first use, not on import
    - Cache layer: results are cached in Supabase to reduce API costs
    - Graceful degradation: returns safe defaults if AI is unavailable

Environment Variables:
    AI_PROVIDER      : "deepseek" | "gemini" | "openai" (default: "openai")
    OPENAI_API_KEY   : required if AI_PROVIDER=openai
    DEEPSEEK_API_KEY : required if AI_PROVIDER=deepseek
    GEMINI_API_KEY   : required if AI_PROVIDER=gemini

Dependencies:
    openai>=1.0.0  (used for all providers via OpenAI-compatible interface)
"""

import json
import logging
import hashlib
import os
from typing import Optional, List, Dict, Any

import openai

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Provider Configuration
# ──────────────────────────────────────────────────────────

_PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "display_name": "DeepSeek",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
        "display_name": "Gemini",
    },
    "openai": {
        "base_url": None,  # uses default OpenAI base URL
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "display_name": "OpenAI",
    },
}

_AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()
_client: Optional[openai.OpenAI] = None


# ──────────────────────────────────────────────────────────
# Lazy Client Initialization
# ──────────────────────────────────────────────────────────

def _get_client() -> Optional[openai.OpenAI]:
    """
    Returns the AI client, creating it on first call (lazy initialization).

    Returns:
        openai.OpenAI instance if API key is present, None otherwise.
        The bot continues to function without AI when this returns None.
    """
    global _client
    if _client is not None:
        return _client

    config = _PROVIDER_CONFIG.get(_AI_PROVIDER, _PROVIDER_CONFIG["openai"])
    api_key = os.environ.get(config["api_key_env"])

    if not api_key:
        logger.warning(
            f"⚠️ {config['api_key_env']} not found in environment. "
            f"AI product extraction is disabled. "
            f"Add {config['api_key_env']} to Railway environment variables to enable it."
        )
        return None

    try:
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if config["base_url"]:
            kwargs["base_url"] = config["base_url"]

        _client = openai.OpenAI(**kwargs)
        logger.info(
            f"✅ AI client ready | Provider: {config['display_name']} | "
            f"Model: {config['model']}"
        )
        return _client
    except Exception as e:
        logger.error(f"❌ Failed to initialize AI client ({config['display_name']}): {e}")
        return None


def _get_model() -> str:
    """Returns the model name for the configured AI provider."""
    config = _PROVIDER_CONFIG.get(_AI_PROVIDER, _PROVIDER_CONFIG["openai"])
    return config["model"]


# ──────────────────────────────────────────────────────────
# Safe Defaults (used when AI is unavailable)
# ──────────────────────────────────────────────────────────

def get_default_product_data(raw_text: str = "") -> dict:
    """
    Returns a safe default product data structure.
    Used as fallback when AI extraction fails or is unavailable.

    Args:
        raw_text: Original text to preserve for manual review.

    Returns:
        dict: Product data with null/empty values.
    """
    return {
        "title": None,
        "title_tr": None,
        "description": None,
        "description_tr": None,
        "category_id": None,
        "attributes": {},
        "variants": [],
        "price": None,
        "currency": "TRY",
        "minimum_order_quantity": 1,
        "raw_text": raw_text,
        "ai_confidence": 0.0,
    }


# ──────────────────────────────────────────────────────────
# Core: Extract Product Data
# ──────────────────────────────────────────────────────────

def extract_product_data(
    raw_text: str,
    image_count: int = 0,
    category_attributes: Optional[List[Dict]] = None,
) -> dict:
    """
    Extracts structured product data from free-form text using AI.

    Flow:
        1. Check cache (Supabase) to avoid duplicate API calls
        2. Build a context-aware prompt using category attributes if available
        3. Call AI provider (DeepSeek / Gemini / OpenAI)
        4. Validate and clean the response
        5. Cache the result for 24 hours
        6. Return defaults if any step fails

    Args:
        raw_text            : Free-form product description (Arabic/Turkish).
        image_count         : Number of images attached to the post.
        category_attributes : List of attribute dicts from KAYISOFT API
                              (used to guide AI extraction).

    Returns:
        dict: Structured product data. Keys:
            - title, title_tr        : Product name (Arabic, Turkish)
            - description, description_tr : Product description
            - category_id            : KAYISOFT category ID (if known)
            - attributes             : Dict of {attribute_id: value}
            - variants               : List of variant dicts
            - price, currency        : Pricing info
            - minimum_order_quantity : MOQ
            - ai_confidence          : Float 0.0-1.0 (AI self-assessment)
    """
    if not raw_text or not raw_text.strip():
        logger.debug("Empty post text — returning defaults")
        return get_default_product_data(raw_text)

    client = _get_client()
    if not client:
        return get_default_product_data(raw_text)

    # 1. Cache check
    cache_key = f"ai_extract_{hashlib.md5(raw_text.encode()).hexdigest()}"
    try:
        from bot.services import database_service
        cached = database_service.get_cache(cache_key)
        if cached:
            logger.info(f"✅ AI cache hit: {cache_key}")
            return cached
    except Exception as e:
        logger.warning(f"⚠️ Cache read error: {e}")

    # 2. Build attributes hint for the prompt
    attributes_hint = ""
    if category_attributes:
        attr_lines = []
        for attr in category_attributes:
            options_str = ", ".join(
                opt.get("name", "") for opt in attr.get("options", [])
            )
            required_label = "REQUIRED" if attr.get("is_required") else "optional"
            attr_lines.append(
                f"  - {attr.get('name', '')} "
                f"(id={attr.get('id', '')}, {required_label})"
                + (f": [{options_str}]" if options_str else "")
            )
        attributes_hint = "\n\nProduct attributes to extract:\n" + "\n".join(attr_lines)

    # 3. Build prompt
    prompt = f"""You are an expert product data extractor for a wholesale textile marketplace.
Extract structured product data from the following text.

Text: {raw_text}
Number of images: {image_count}{attributes_hint}

Return ONLY a valid JSON object with these fields (use null if information is not found):
{{
  "title": "Product name in Arabic",
  "title_tr": "Product name in Turkish",
  "description": "Short description in Arabic (2 sentences max)",
  "description_tr": "Short description in Turkish (2 sentences max)",
  "attributes": {{
    "<attribute_id>": "<selected_option_or_value>"
  }},
  "variants": [
    {{
      "attribute_id": "<id of the variant attribute>",
      "value": "<variant value>",
      "images": []
    }}
  ],
  "price": <number or null>,
  "currency": "TRY|USD|EUR or null",
  "minimum_order_quantity": <number or null>,
  "ai_confidence": <float 0.0-1.0 representing extraction confidence>
}}"""

    # 4. Call AI
    try:
        logger.info(
            f"🤖 Calling AI | Provider: {_AI_PROVIDER} | Model: {_get_model()} "
            f"| Text length: {len(raw_text)} chars"
        )
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise product data extractor for a wholesale "
                        "textile marketplace. Return ONLY valid JSON with no "
                        "additional text or markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        raw_response = response.choices[0].message.content
        logger.debug(f"AI raw response (first 300 chars): {raw_response[:300]}")

        extracted_data = json.loads(raw_response)

        # 5. Merge with defaults for missing keys
        defaults = get_default_product_data(raw_text)
        for key, default_val in defaults.items():
            if key not in extracted_data or extracted_data[key] is None:
                if key != "raw_text":
                    extracted_data.setdefault(key, default_val)

        extracted_data["raw_text"] = raw_text

        logger.info(
            f"✅ AI extraction complete | "
            f"Title: {extracted_data.get('title', 'N/A')} | "
            f"Confidence: {extracted_data.get('ai_confidence', 0):.0%}"
        )

        # 6. Cache result for 24 hours
        try:
            from bot.services import database_service
            database_service.set_cache(cache_key, extracted_data, ttl_hours=24)
        except Exception as e:
            logger.warning(f"⚠️ Cache write error: {e}")

        return extracted_data

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parse error from AI response: {e}")
        return get_default_product_data(raw_text)
    except openai.RateLimitError as e:
        logger.error(f"❌ AI rate limit exceeded: {e}")
        return get_default_product_data(raw_text)
    except openai.AuthenticationError as e:
        logger.error(f"❌ AI authentication error — check API key: {e}")
        return get_default_product_data(raw_text)
    except Exception as e:
        logger.error(f"❌ Unexpected AI error: {e}")
        return get_default_product_data(raw_text)


# ──────────────────────────────────────────────────────────
# Validation: Check Extracted Data Against Required Fields
# ──────────────────────────────────────────────────────────

def validate_product_data(
    extracted_data: dict,
    category_attributes: List[Dict],
) -> Dict[str, Any]:
    """
    Validates extracted product data against required category attributes.

    Args:
        extracted_data      : Output from extract_product_data().
        category_attributes : List of attribute dicts from KAYISOFT API.

    Returns:
        dict: {
            "is_valid"        : bool — True if all required fields are present,
            "missing_required": list — attribute dicts for missing required fields,
            "missing_optional": list — attribute dicts for missing optional fields,
        }
    """
    extracted_attrs = extracted_data.get("attributes", {})
    missing_required = []
    missing_optional = []

    for attr in category_attributes:
        attr_id = str(attr.get("id", ""))
        is_required = attr.get("is_required", False)
        value = extracted_attrs.get(attr_id)

        if not value or str(value).strip() == "":
            if is_required:
                missing_required.append(attr)
            else:
                missing_optional.append(attr)

    return {
        "is_valid": len(missing_required) == 0,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }
