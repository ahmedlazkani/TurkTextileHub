"""
bot/services/deepseek_service.py
================================
AI Extraction Service — TopKap Telegram Bot
Version: 3.0 (Built from KAYISOFT API spec — API_ENDPOINTS_FULL.md)

PURPOSE
───────
Extracts structured product data from a supplier's free-text description
(Arabic, Turkish, or English) and maps it to the exact schema required by
KAYISOFT API endpoint: POST api/seller/products

KAYISOFT API PRODUCT SCHEMA (from API_ENDPOINTS_FULL.md §6):
─────────────────────────────────────────────────────────────
{
  "name": "string",
  "product_no": "auto",
  "category_id": "uuid",
  "shared_attributes": {
    "<attr_uuid>": ["<option_uuid>"]   ← ARRAY, not plain string!
  },
  "variants": [{
    "selector_attributes": [
      {"attribute_id": "<uuid>", "option_id": "<uuid>"}
    ],
    "prices": [{"min_quantity": 1, "price": 1299.99}],
    "stock_count": 100,
    ...
  }]
}

ATTRIBUTE TYPES (from GET api/seller/categories/{id}/attributes):
─────────────────────────────────────────────────────────────────
• is_variant_selector = true  → goes into variants[].selector_attributes[]
• is_variant_selector = false → goes into shared_attributes{}
• required = true             → MUST be present or product creation fails

PROVIDER CASCADE:
─────────────────
  1. DeepSeek  (DEEPSEEK_API_KEY)  — preferred
  2. OpenAI-compatible (OPENAI_API_KEY) — automatic fallback
  3. Mock mode — if no keys configured
"""

import os
import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _build_extraction_prompt(user_text: str, attributes: List[dict]) -> str:
    """
    Builds a professional, structured extraction prompt for DeepSeek.

    DESIGN PRINCIPLES:
    ──────────────────
    1. Attributes are split into two clearly labeled groups matching the API:
       • GROUP A (VARIANT SELECTORS): is_variant_selector=True
         → output format: selector_attributes[] array
         → each item: {"attribute_id": "<uuid>", "option_id": "<uuid>"}

       • GROUP B (SHARED ATTRIBUTES): is_variant_selector=False
         → output format: shared_attributes{} object
         → each item: {"<attr_uuid>": ["<option_uuid>"]}  ← ARRAY per API spec!

    2. Every attribute is listed with:
       - Its exact UUID (so AI uses it directly, no guessing)
       - Its Arabic/Turkish name
       - Whether it's REQUIRED or optional
       - All valid options with their exact UUIDs and display values

    3. The prompt uses concrete Arabic examples to guide semantic matching:
       "شيفون" → option "Şifon", "صيفي" → option "Yaz", etc.

    4. Temperature is set to 0.0 to ensure deterministic, consistent output.

    Args:
        user_text:   Supplier's free-text description (any language)
        attributes:  List of attribute dicts from GET /categories/{id}/attributes

    Returns:
        Complete prompt string ready to send to DeepSeek
    """
    # ── Separate attributes into two groups ───────────────────────────────────
    selector_attrs = []  # is_variant_selector = True  → selector_attributes[]
    shared_attrs   = []  # is_variant_selector = False → shared_attributes{}

    for attr in attributes:
        if attr.get("is_variant_selector", False):
            selector_attrs.append(attr)
        else:
            shared_attrs.append(attr)

    # ── Format GROUP A: Variant Selector Attributes ───────────────────────────
    def format_attr_block(attr: dict) -> str:
        attr_id   = attr.get("id", "")
        attr_name = attr.get("name", "")
        attr_key  = attr.get("key", "")
        ui_type   = attr.get("ui_type", "text")
        required  = attr.get("required", False)
        options   = attr.get("options", [])

        req_tag = "[REQUIRED]" if required else "[optional]"
        block = f'  Attribute:\n    id: "{attr_id}"\n    name: "{attr_name}" (key: {attr_key})\n    type: {ui_type} | {req_tag}'

        if options:
            block += "\n    Valid options (use ONLY these UUIDs):"
            for opt in options:
                block += f'\n      - option_id: "{opt.get("id","")}"  →  value: "{opt.get("value","")}"'
        else:
            block += "\n    (free text — no predefined options)"

        return block

    group_a_lines = "\n\n".join(format_attr_block(a) for a in selector_attrs) \
                    if selector_attrs else "  (none — no variant selectors for this category)"

    group_b_lines = "\n\n".join(format_attr_block(a) for a in shared_attrs) \
                    if shared_attrs else "  (none — no shared attributes for this category)"

    # ── Output schema example ─────────────────────────────────────────────────
    # This mirrors the exact structure expected by _check_missing_required()
    # and the KAYISOFT POST api/seller/products endpoint.
    output_example = {
        "name": "شال شيفون صيفي",
        "description": "شال شيفون مناسب للصيف ومريح لكل الوجوه",
        "price": "120",
        "min_quantity": 200,
        "stock_count": 4000,
        "shared_attributes": {
            "<GROUP_B_attr_uuid>": ["<option_uuid_from_valid_options>"]
        },
        "selector_attributes": [
            {
                "attribute_id": "<GROUP_A_attr_uuid>",
                "option_id": "<option_uuid_from_valid_options>"
            }
        ]
    }

    # ── Assemble the full prompt ───────────────────────────────────────────────
    prompt = f"""You are a precise data extraction engine for TopKap, a wholesale textile marketplace.
Your ONLY job: read the supplier's product description and output a single valid JSON object.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPLIER TEXT (may be Arabic, Turkish, or English):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{user_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GROUP A — VARIANT SELECTOR ATTRIBUTES
→ These define product variants (size, color, etc.)
→ In your output: put them inside "selector_attributes" as an ARRAY
→ Format per item: {{"attribute_id": "<uuid>", "option_id": "<uuid>"}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{group_a_lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GROUP B — SHARED ATTRIBUTES
→ These apply to the whole product (material, usage pattern, etc.)
→ In your output: put them inside "shared_attributes" as an OBJECT
→ Format per item: {{"<attr_uuid>": ["<option_uuid>"]}}  ← value is an ARRAY!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{group_b_lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION RULES — READ CAREFULLY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — PLACEMENT IS CRITICAL:
  • GROUP A attributes → ONLY in "selector_attributes" array
  • GROUP B attributes → ONLY in "shared_attributes" object
  • NEVER mix them. A GROUP A attribute must NEVER appear in shared_attributes.
  • A GROUP B attribute must NEVER appear in selector_attributes.

RULE 2 — OPTION MATCHING (for attributes WITH options):
  Use SEMANTIC matching — the supplier writes in Arabic but options may be Turkish:
  • "شيفون" or "chiffon"         → find option with value containing "Şifon" or "Chiffon"
  • "صيفي" or "صيف" or "summer"  → find option with value containing "Yaz" or "Summer"
  • "يومي" or "daily"            → find option with value containing "Günlük" or "Daily"
  • "سكري" (sugar = light beige) → find closest color option (cream/beige/şeker)
  • "180 سم ب 70 سم" or "180x70" → find size option closest to "180*70" or "180x70" or "180 cm"
  • "أبيض" or "white"            → find option with value containing "Beyaz" or "White"
  • "أسود" or "black"            → find option with value containing "Siyah" or "Black"
  Always use the option's UUID (id field), NOT the display value string.

RULE 3 — FREE TEXT ATTRIBUTES (no options list):
  Use the raw extracted value as a plain string.
  Example: size "180 سم ب 70 سم" → "180x70"

RULE 4 — TOP-LEVEL FIELDS:
  • "name":         Product title (e.g. "شال شيفون")
  • "description":  Write a PROFESSIONAL 2-sentence marketing description in Arabic.
                    Do NOT copy the supplier's raw text. Write like a copywriter:
                    Sentence 1: Highlight the product's key benefit or material quality.
                    Sentence 2: Mention the use case, target customer, or occasion.
                    Example input: "شال شيفون صيفي جودة عالية"
                    Example output: "شال شيفون فاخر بجودة عالية يمنحك إطلالة أنيقة وراحة تامة طوال اليوم. مثالي للاستخدام اليومي والمناسبات الصيفية، يتميز بخامته الخفيفة التي تلائم جميع الأذواق."
  • "price":        Numeric string only — "120 ليرة" → "120", "120 lira" → "120"
  • "min_quantity": Integer — "200 قطعة" → 200
  • "stock_count":  Integer — "4000 قطعة" → 4000
  If only ONE quantity is mentioned, use it for BOTH min_quantity AND stock_count.

RULE 5 — MISSING VALUES:
  If a value is NOT found in the supplier text → OMIT that key entirely.
  Do NOT set null, 0, "", or [] for missing values.

RULE 6 — CLOSEST MATCH (CRITICAL FOR REQUIRED ATTRIBUTES):
  If no exact option matches, pick the CLOSEST semantic match from the valid options list.
  For [REQUIRED] attributes: you MUST always pick an option — NEVER leave it empty.
  Fallback priority for [REQUIRED] attributes with no match:
    1. Pick the option whose value is closest semantically
    2. If still unsure, pick the FIRST option in the list
    3. NEVER omit a [REQUIRED] attribute from selector_attributes

RULE 8 — SIZE ATTRIBUTE SPECIAL HANDLING:
  When the supplier mentions a specific measurement like "180 سم ب 70 سم" or "180x70":
  • If the size options list contains ONLY "مقاس موحد" or "Tek Beden" or "One Size" → choose that option
  • If the size options list contains numeric sizes (S, M, L, XL, 38, 40, etc.) → pick the closest
  • If the size options list contains dimension-based options (180x70, 170x80) → pick the closest match
  • NEVER leave the size attribute empty — always pick the best available option
  • Store the actual measurement in the product name or description if needed

RULE 7 — shared_attributes VALUE FORMAT:
  The value for each shared_attribute MUST be an array: ["<option_uuid>"]
  NOT a plain string. This matches the KAYISOFT API specification exactly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED OUTPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output ONLY a valid JSON object. No markdown. No explanation. No extra text.
Example structure (use actual UUIDs from the attribute lists above):
{json.dumps(output_example, ensure_ascii=False, indent=2)}
"""
    return prompt


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE PARSER
# ══════════════════════════════════════════════════════════════════════════════

def _parse_ai_response(content: str) -> Optional[Dict[str, Any]]:
    """
    Parses the raw AI response string into a validated Python dict.

    Handles:
    - Markdown code fences (```json ... ```) that some models add
    - Leading/trailing whitespace
    - Invalid JSON (returns None with error log)

    Also normalizes shared_attributes values:
    - If AI returns {"attr_id": "option_uuid"} (string) instead of
      {"attr_id": ["option_uuid"]} (array), we wrap it automatically.
    This ensures compatibility with the KAYISOFT API spec.

    Args:
        content: Raw string from AI response

    Returns:
        Parsed and normalized dict, or None on failure
    """
    content = content.strip()

    # Strip markdown code fences if present
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(
            "AI returned invalid JSON: %s\nContent preview: %s",
            e, content[:500]
        )
        return None

    # ── Normalize shared_attributes values to arrays ──────────────────────────
    # KAYISOFT API requires: {"attr_uuid": ["option_uuid"]}
    # Some AI responses return: {"attr_uuid": "option_uuid"} (plain string)
    # We fix this automatically here so the API call never fails.
    shared = parsed.get("shared_attributes", {})
    if isinstance(shared, dict):
        normalized_shared = {}
        for k, v in shared.items():
            if isinstance(v, str) and v:
                normalized_shared[k] = [v]   # wrap string in array
            elif isinstance(v, list):
                normalized_shared[k] = v      # already correct
            elif v:
                normalized_shared[k] = [str(v)]
        parsed["shared_attributes"] = normalized_shared

    logger.info(
        "AI extraction parsed OK — name=%s, price=%s, "
        "shared_attrs=%d, selector_attrs=%d",
        parsed.get("name", "?")[:40],
        parsed.get("price", "?"),
        len(parsed.get("shared_attributes", {})),
        len(parsed.get("selector_attributes", [])),
    )
    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# AI EXTRACTION SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class DeepSeekService:
    """
    Async AI client for structured product attribute extraction.

    Implements a provider cascade for maximum reliability:
      1. DeepSeek (DEEPSEEK_API_KEY) — preferred, cost-effective
      2. OpenAI-compatible (OPENAI_API_KEY) — automatic fallback
      3. Mock mode — returns minimal data if no keys configured

    All providers use the same prompt and response parsing logic,
    ensuring consistent output regardless of which provider is active.

    Usage:
        result = await deepseek_service.analyze_product_text(text, attributes)
        # result is a dict with: name, description, price, min_quantity,
        #   stock_count, shared_attributes, selector_attributes
    """

    # DeepSeek API config
    DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL    = "deepseek-chat"

    # OpenAI-compatible fallback config
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    FALLBACK_MODEL  = os.getenv("FALLBACK_AI_MODEL", "gpt-4.1-mini")

    # System prompt: sets the AI's role and output constraints
    SYSTEM_PROMPT = (
        "You are a precise JSON extraction engine for a wholesale textile marketplace. "
        "You ALWAYS output valid JSON only — no markdown fences, no explanation, no extra text. "
        "You are an expert at understanding Arabic, Turkish, and English product descriptions. "
        "You match Arabic textile terms to their Turkish/English equivalents with high accuracy. "
        "You follow the extraction rules exactly as specified in the user prompt. "
        "Your output is consumed directly by an API — any formatting error will cause a failure."
    )

    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.openai_key   = os.getenv("OPENAI_API_KEY", "").strip()

        if self.deepseek_key:
            logger.info(
                "DeepSeekService initialized — provider: DeepSeek (model=%s)",
                self.DEEPSEEK_MODEL
            )
        elif self.openai_key:
            logger.info(
                "DeepSeekService initialized — provider: OpenAI fallback "
                "(model=%s, base=%s)",
                self.FALLBACK_MODEL, self.OPENAI_BASE_URL
            )
        else:
            logger.warning(
                "DeepSeekService initialized — MOCK MODE "
                "(set DEEPSEEK_API_KEY or OPENAI_API_KEY in Railway Variables)"
            )

    async def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> Optional[str]:
        """
        Makes an async POST to any OpenAI-compatible /chat/completions endpoint.

        Uses temperature=0.0 for deterministic, reproducible output.
        Timeout is 45 seconds to handle slow API responses gracefully.

        Args:
            base_url: API base URL (e.g. "https://api.deepseek.com/v1")
            api_key:  Bearer authentication token
            model:    Model identifier (e.g. "deepseek-chat", "gpt-4.1-mini")
            prompt:   The full extraction prompt

        Returns:
            Raw response content string from the AI, or None on any error
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "temperature": 0.0,    # deterministic output — no randomness
            "max_tokens":  2000,   # enough for complex multi-attribute products
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    if resp.status >= 400:
                        error_body = await resp.text()
                        logger.error(
                            "AI API HTTP %d (model=%s, base=%s): %s",
                            resp.status, model, base_url, error_body[:300]
                        )
                        return None

                    result  = await resp.json()
                    content = result["choices"][0]["message"]["content"]
                    logger.debug(
                        "AI raw response (model=%s): %s",
                        model, content[:200]
                    )
                    return content

            except aiohttp.ClientError as e:
                logger.error("AI network error (model=%s): %s", model, e)
                return None
            except Exception as e:
                logger.error("AI unexpected error (model=%s): %s", model, e)
                return None

    async def analyze_product_text(
        self,
        text: str,
        expected_attributes: List[dict],
    ) -> Optional[Dict[str, Any]]:
        """
        Analyzes a supplier's free-text product description and extracts
        structured data matching the KAYISOFT POST api/seller/products schema.

        PROVIDER CASCADE:
          1. DeepSeek (if DEEPSEEK_API_KEY is set)
          2. OpenAI-compatible (if OPENAI_API_KEY is set)
          3. Mock data (if neither key is configured)

        OUTPUT SCHEMA:
          {
            "name":                str,
            "description":         str,
            "price":               str (numeric only, e.g. "120"),
            "min_quantity":        int,
            "stock_count":         int,
            "shared_attributes":   { "<attr_uuid>": ["<option_uuid>"] },
            "selector_attributes": [ {"attribute_id": "<uuid>", "option_id": "<uuid>"} ]
          }

        Args:
            text:                Supplier's product description (any language)
            expected_attributes: Attribute list from GET /categories/{id}/attributes

        Returns:
            Extracted data dict, or None if all providers fail
        """
        prompt = _build_extraction_prompt(text, expected_attributes)

        # ── Provider 1: DeepSeek ──────────────────────────────────────────────
        if self.deepseek_key:
            logger.info("Calling DeepSeek API for product extraction...")
            content = await self._call_openai_compatible(
                base_url=self.DEEPSEEK_BASE_URL,
                api_key=self.deepseek_key,
                model=self.DEEPSEEK_MODEL,
                prompt=prompt,
            )
            if content is not None:
                result = _parse_ai_response(content)
                if result is not None:
                    logger.info("DeepSeek extraction successful")
                    return result
                logger.warning("DeepSeek returned unparseable JSON — trying fallback")
            else:
                logger.warning("DeepSeek API call failed — trying OpenAI fallback")

        # ── Provider 2: OpenAI-compatible fallback ────────────────────────────
        if self.openai_key:
            logger.info(
                "Calling OpenAI-compatible API (model=%s) for product extraction...",
                self.FALLBACK_MODEL
            )
            content = await self._call_openai_compatible(
                base_url=self.OPENAI_BASE_URL,
                api_key=self.openai_key,
                model=self.FALLBACK_MODEL,
                prompt=prompt,
            )
            if content is not None:
                result = _parse_ai_response(content)
                if result is not None:
                    logger.info("OpenAI fallback extraction successful")
                    return result
                logger.warning("OpenAI fallback returned unparseable JSON")
            else:
                logger.warning("OpenAI fallback API call also failed")

        # ── Provider 3: Mock mode ─────────────────────────────────────────────
        if not self.deepseek_key and not self.openai_key:
            logger.warning(
                "MOCK MODE ACTIVE — Returning minimal product data. "
                "To enable AI extraction, set DEEPSEEK_API_KEY or OPENAI_API_KEY "
                "in Railway → Variables."
            )
            return {
                "name":                text[:80],
                "description":         text,
                "price":               "0",
                "min_quantity":        1,
                "stock_count":         100,
                "shared_attributes":   {},
                "selector_attributes": [],
            }

        # All configured providers failed
        logger.error(
            "All AI providers failed. Supplier text: %s...",
            text[:100]
        )
        return None


    async def analyze_image_color(
        self,
        image_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyzes a product image to extract the primary textile color.

        Returns:
            Dict with keys:
              - "color_name":  str  e.g. "Navy Blue"
              - "color_emoji": str  e.g. "🔵"
            Or None if analysis fails

        IMPLEMENTATION NOTES:
        ─────────────────────
        - DeepSeek does NOT support `image_url` content type in messages.
          It only accepts `text` content type.
        - FIX: Download the image bytes, encode as base64, and send as
          `data:image/jpeg;base64,...` inline URL — this is the only format
          DeepSeek-VL and most OpenAI-compatible vision APIs accept.
        - If OPENAI_API_KEY is set, use GPT-4o-mini (supports image_url natively).
        - If only DEEPSEEK_API_KEY is set, use deepseek-chat with base64 inline.
        """
        import base64

        vision_key   = self.openai_key or self.deepseek_key
        vision_base  = "https://api.openai.com/v1" if self.openai_key else self.DEEPSEEK_BASE_URL
        vision_model = "gpt-4o-mini" if self.openai_key else "deepseek-chat"

        if not vision_key:
            logger.warning("analyze_image_color: No OPENAI_API_KEY or DEEPSEEK_API_KEY set — skipping color analysis")
            return None

        system_prompt = (
            "You are a professional color analyst for a textile marketplace. "
            "When given a product image, identify the PRIMARY color of the textile/fabric. "
            "Return ONLY a valid JSON object with exactly two keys: "
            '"color_name" (the international standard English color name, e.g. \'Navy Blue\', \'Burgundy\', \'Ivory\') '
            'and "color_emoji" (the single Unicode circle emoji that best represents the color). '
            "Use ONLY these circle emojis: 🔴🟠🟡🟢🔵🟣🟤⚫⚪. "
            "No markdown, no explanation, just JSON."
        )

        async with aiohttp.ClientSession() as session:
            try:
                # ── Step 1: Download the image and encode as base64 ───────────
                # DeepSeek rejects `image_url` content type — must use base64
                # GPT-4o-mini accepts both, but base64 works universally
                async with session.get(
                    image_url,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as img_resp:
                    if img_resp.status != 200:
                        logger.error(
                            "Color analysis: failed to download image (HTTP %d)",
                            img_resp.status
                        )
                        return None
                    image_bytes   = await img_resp.read()
                    image_b64    = base64.b64encode(image_bytes).decode("utf-8")
                    # Force image/jpeg — Telegram CDN may return 'application/octet-stream'
                    # which GPT-4o-mini rejects as invalid_image_format.
                    # JPEG is safe for all textile product photos.
                    raw_ct       = img_resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    if raw_ct in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                        content_type = raw_ct
                    else:
                        content_type = "image/jpeg"  # safe default
                    image_data_url = f"data:{content_type};base64,{image_b64}"

                # ── Step 2: Build vision payload with base64 inline image ─────
                payload = {
                    "model": vision_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                                {
                                    "type": "text",
                                    "text": "What is the primary color of this textile product? Return JSON only.",
                                },
                            ],
                        },
                    ],
                    "temperature": 0.0,
                    "max_tokens":  100,
                }

                headers = {
                    "Authorization": f"Bearer {vision_key}",
                    "Content-Type":  "application/json",
                }

                # ── Step 3: Call vision API ───────────────────────────────────
                async with session.post(
                    f"{vision_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status >= 400:
                        error_body = await resp.text()
                        logger.error(
                            "Color analysis API HTTP %d: %s",
                            resp.status, error_body[:300]
                        )
                        return None

                    result  = await resp.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Strip markdown fences if present
                    if content.startswith("```"):
                        content = content.split("\n", 1)[-1]
                    if content.endswith("```"):
                        content = content.rsplit("```", 1)[0]
                    content = content.strip()

                    parsed      = json.loads(content)
                    color_name  = parsed.get("color_name", "")
                    color_emoji = parsed.get("color_emoji", "🔵")

                    logger.info("Color analysis result: %s %s", color_emoji, color_name)
                    return {"color_name": color_name, "color_emoji": color_emoji}

            except json.JSONDecodeError as e:
                logger.error("Color analysis: invalid JSON response: %s", e)
                return None
            except aiohttp.ClientError as e:
                logger.error("Color analysis: network error: %s", e)
                return None
            except Exception as e:
                logger.error("Color analysis: unexpected error: %s", e)
                return None


# ── Module-level singleton ────────────────────────────────────────────────────
# Import and use this instance throughout the bot:
#   from bot.services.deepseek_service import deepseek_service
deepseek_service = DeepSeekService()
