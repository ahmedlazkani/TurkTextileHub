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
    prompt = f"""You are an elite AI data extraction engine specialized in wholesale textile e-commerce.
You work for TopKap — a B2B marketplace connecting Turkish textile manufacturers with global buyers.
Your mission: parse the supplier's raw product description and produce a perfectly structured JSON object.

╔══════════════════════════════════════════════════════════════════════════════╗
║  SUPPLIER INPUT  (Arabic / Turkish / English — any mix)                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
{user_text}

╔══════════════════════════════════════════════════════════════════════════════╗
║  GROUP A — VARIANT SELECTOR ATTRIBUTES                                     ║
║  → Define product variants (e.g. color, size, gender)                      ║
║  → Output location: "selector_attributes" array                            ║
║  → Item format: {{"attribute_id": "<uuid>", "option_id": "<uuid>"}}         ║
╚══════════════════════════════════════════════════════════════════════════════╝
{group_a_lines}

╔══════════════════════════════════════════════════════════════════════════════╗
║  GROUP B — SHARED ATTRIBUTES                                               ║
║  → Apply to the entire product (material, season, usage pattern, etc.)     ║
║  → Output location: "shared_attributes" object                             ║
║  → Item format: {{"<attr_uuid>": ["<option_uuid>"]}}  ← ARRAY required!    ║
╚══════════════════════════════════════════════════════════════════════════════╝
{group_b_lines}

╔══════════════════════════════════════════════════════════════════════════════╗
║  EXTRACTION RULES                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

RULE 1 — STRICT PLACEMENT:
  • GROUP A attributes → ONLY in "selector_attributes" array
  • GROUP B attributes → ONLY in "shared_attributes" object
  • Mixing is a critical error. Never cross-place attributes.

RULE 2 — MULTILINGUAL SEMANTIC MATCHING:
  Suppliers write in Arabic; options may be in Turkish or English. Match by meaning:
  Arabic → Turkish/English examples:
  • "شيفون" / "chiffon"          → "Şifon" / "Chiffon"
  • "فيسكوز" / "viscose"         → "Viskon" / "Viscose"
  • "قطن" / "cotton"             → "Pamuk" / "Cotton"
  • "صيفي" / "summer"            → "Yaz" / "Summer"
  • "شتوي" / "winter"            → "Kış" / "Winter"
  • "يومي" / "daily"             → "Günlük" / "Daily"
  • "رسمي" / "formal"            → "Resmi" / "Formal"
  • "أبيض" / "white"             → "Beyaz" / "White"
  • "أسود" / "black"             → "Siyah" / "Black"
  • "سكري" (light beige/cream)   → closest cream/beige option
  • "180 سم ب 70 سم" / "180x70"  → "180*70" / "180x70" / "180 cm"
  Always use the option UUID (id field), NEVER the display string.

RULE 3 — FREE TEXT ATTRIBUTES:
  For attributes with no predefined options, use the extracted value as plain string.
  Normalize measurements: "180 سم ب 70 سم" → "180x70"

RULE 4 — TOP-LEVEL FIELDS (all required unless missing from input):
  "name":
    • Short, clean product title in Arabic (3-6 words max)
    • Include key product type + material if mentioned
    • Example: "شال شيفون فاخر" or "طاقية نينجا فيسكوز"

  "description":
    • Write a PROFESSIONAL 3-sentence marketing description in Arabic
    • Sentence 1: Lead with the product's premium quality or unique material
    • Sentence 2: Highlight the main benefit, comfort, or design feature
    • Sentence 3: Describe the ideal use case, occasion, or target customer
    • Style: confident, elegant, commercial — like a luxury brand copywriter
    • Do NOT copy the supplier's raw text verbatim
    • Example input:  "شال شيفون صيفي جودة عالية"
    • Example output: "شال شيفون فاخر مصنوع من أجود أنواع القماش الخفيف والناعم. \
 يمنحك إطلالة أنيقة ومريحة تناسب كل يوم وكل مناسبة. \
 مثالي للمرأة العصرية التي تبحث عن الأناقة والراحة في آنٍ واحد."

  "price":         Numeric string only — "200 ليرة" → "200", "200 lira" → "200"
  "min_quantity":  Integer — "300 قطعة" → 300
  "stock_count":   Integer — "4000 قطعة" → 4000
  If only ONE quantity mentioned → use it for BOTH min_quantity AND stock_count.

RULE 5 — MISSING VALUES:
  If a field is not found in the supplier text → OMIT it entirely.
  Never use null, 0, "", or [] as placeholders.

RULE 6 — REQUIRED ATTRIBUTES (never skip):
  For [REQUIRED] attributes: ALWAYS pick an option, even if no perfect match.
  Fallback priority:
    1. Closest semantic match from the options list
    2. If still unclear → pick the FIRST option in the list
    3. NEVER omit a [REQUIRED] attribute from the output

RULE 7 — shared_attributes VALUE FORMAT:
  Each value MUST be an array: ["<option_uuid>"]
  Never a plain string. This is mandatory for the KAYISOFT API.

RULE 8 — SIZE + MEASUREMENT HANDLING:
  When supplier mentions a specific measurement ("180x70", "180 سم ب 70 سم", "70×180"):
  • If size options list has numeric/dimension options → pick the closest match
  • If size options list has ONLY "Tek Beden" / "One Size" / "مقاس موحد" → select it
  • CRITICAL: When specific measurement exists but only "Tek Beden" is available,
    APPEND the measurement to the product "name" field:
    Input: "شال شيفون 180x70"  → name: "شال شيفون 180×70 سم"
    Input: "شال صيفي 180 سم ب 70 سم" → name: "شال صيفي 180×70 سم"
  • Also weave the measurement naturally into the "description" field.
  • NEVER leave the size attribute empty.

RULE 9 — PRODUCT NAME QUALITY:
  • Clean, professional, marketable
  • No prices, no quantities, no phone numbers in the name
  • Max 6 words
  • Must be in Arabic

╔══════════════════════════════════════════════════════════════════════════════╗
║  REQUIRED OUTPUT FORMAT                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
Output ONLY a valid JSON object. No markdown. No explanation. No extra text.
Use the actual UUIDs from the attribute lists above (not the example UUIDs below).
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
            "You are a world-class textile color specialist with expertise in fashion, fabric manufacturing, "
            "and international color standards (Pantone, RAL, NCS). "
            "Your task: analyze the product image and identify the DOMINANT color of the textile/garment with maximum precision.\n\n"

            "## ANALYSIS METHODOLOGY\n"
            "Step 1 — Ignore background, mannequin, packaging, and shadows. Focus ONLY on the fabric/garment itself.\n"
            "Step 2 — Assess the HUE first (is it warm/cool/neutral?), then SATURATION (vivid/muted?), then LIGHTNESS (dark/medium/light?).\n"
            "Step 3 — Match to the closest professional color name from the reference list below.\n\n"

            "## COLOR REFERENCE (use ONLY these or close variants)\n"
            "REDS & DARK REDS: Burgundy, Wine Red, Maroon, Crimson, Scarlet, Cherry Red, Rust, Brick Red, Coral, Tomato Red\n"
            "BLUES: Navy Blue, Royal Blue, Cobalt Blue, Sky Blue, Baby Blue, Teal, Turquoise, Denim Blue, Indigo, Petrol Blue\n"
            "GREENS: Emerald Green, Olive Green, Forest Green, Sage Green, Mint Green, Bottle Green, Khaki Green, Hunter Green\n"
            "BROWNS & NEUTRALS: Camel, Chocolate Brown, Tan, Khaki, Beige, Taupe, Sand, Mocha, Walnut Brown, Latte\n"
            "WHITES & LIGHTS: Ivory, Cream, Off-White, Pearl White, Snow White, Ecru, Champagne\n"
            "PINKS: Blush Pink, Rose, Fuchsia, Salmon, Dusty Rose, Hot Pink, Powder Pink, Mauve Pink, Nude\n"
            "PURPLES: Lavender, Lilac, Violet, Plum, Mauve, Amethyst, Eggplant, Deep Purple\n"
            "YELLOWS & ORANGES: Mustard Yellow, Golden Yellow, Saffron, Tangerine, Peach, Amber, Honey, Apricot\n"
            "GRAYS: Light Gray, Medium Gray, Charcoal Gray, Anthracite, Slate Gray, Silver\n"
            "TRUE BLACK: Jet Black (ONLY when fabric is pure black with absolutely NO visible color hue)\n\n"

            "## CRITICAL RULES\n"
            "- NEVER classify a dark-colored fabric as 'Black' if it has ANY visible hue (red, blue, green, etc.)\n"
            "- Dark red/maroon/burgundy = use 'Burgundy' or 'Wine Red' or 'Maroon', NEVER 'Black'\n"
            "- Dark navy = use 'Navy Blue', NEVER 'Black'\n"
            "- Dark green = use 'Bottle Green' or 'Forest Green', NEVER 'Black'\n"
            "- If unsure between two colors, pick the one with the most visible hue\n\n"

            "## OUTPUT FORMAT\n"
            "Return ONLY a valid JSON object with exactly two keys:\n"
            '  "color_name": precise English color name (1-3 words, from the reference list above)\n'
            '  "color_emoji": single Unicode circle emoji from this set ONLY:\n'
            "    \U0001f534 = red/burgundy/wine/maroon/crimson/coral\n"
            "    \U0001f7e0 = orange/tangerine/amber/peach\n"
            "    \U0001f7e1 = yellow/mustard/golden/saffron\n"
            "    \U0001f7e2 = green (all shades)\n"
            "    \U0001f535 = blue/navy/teal/turquoise/indigo\n"
            "    \U0001f7e3 = purple/violet/plum/lavender/mauve\n"
            "    \U0001f7e4 = brown/camel/tan/khaki/beige/taupe/mocha\n"
            "    \u26ab = true black/jet black ONLY\n"
            "    \u26aa = white/ivory/cream/gray/silver\n\n"
            "No markdown, no explanation, no extra text. Return JSON only."
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


# ──# ═══════════════════════════════════════════════════════════════════════════════
# CHANNEL POST GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_channel_post(
    product_data: dict,
    languages: List[str],
) -> Optional[str]:
    """
    Generates a professional Telegram channel post for a textile product.

    Parameters
    ----------
    product_data : dict
        Keys: name, description, price, min_quantity, stock_count,
              product_code (optional), notes (optional),
              attributes (list of {name, value} dicts)
    languages : list[str]
        Subset of ["ar", "tr", "en"] — languages to include in the post.

    Returns
    -------
    str | None  — formatted post text, or None on failure.
    """
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    openai_key   = os.getenv("OPENAI_API_KEY", "").strip()

    if deepseek_key:
        _key   = deepseek_key
        _base  = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        if not _base.endswith("/v1"):
            _base += "/v1"
        _model = "deepseek-chat"
        logger.info("generate_channel_post: using DeepSeek")
    elif openai_key:
        _key   = openai_key
        _base  = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not _base.endswith("/v1"):
            _base += "/v1"
        _model = os.getenv("FALLBACK_AI_MODEL", "gpt-4.1-mini")
        logger.info("generate_channel_post: using OpenAI fallback (%s)", _model)
    else:
        logger.warning("generate_channel_post: no API key (DEEPSEEK_API_KEY or OPENAI_API_KEY) — returning None")
        return None

    # ── Build language instruction ──────────────────────────────────────────────
    lang_map = {"ar": "🇸🇦 Arabic (العربية)", "tr": "🇹🇷 Turkish (Türkçe)", "en": "🇬🇧 English"}
    lang_names = [lang_map.get(l, l) for l in languages]

    if len(languages) == 1:
        lang_instruction = f"Write the post ONLY in {lang_names[0]}."
    else:
        lang_instruction = (
            "Write the post in ALL of these languages, each section clearly separated:\n"
            + "\n".join(f"  • {n}" for n in lang_names)
            + "\nUse a divider line (────────────────────────) between language sections."
        )

    # ── Build product summary ───────────────────────────────────────────────
    attrs_text = ""
    for a in product_data.get("attributes", []):
        attrs_text += f"  • {a['name']}: {a['value']}\n"

    product_summary = (
        f"Product Name   : {product_data.get('name', '')}\n"
        f"Description    : {product_data.get('description', '') or '(not provided)'}\n"
        f"Price          : {product_data.get('price', '')} ₺\n"

        f"Product Code   : {product_data.get('product_code') or '(not provided)'}\n"
        f"Notes          : {product_data.get('notes') or '(none)'}\n"
        f"Attributes     :\n{attrs_text or '  (none)'}"
    ).strip()

    # ── System prompt ──────────────────────────────────────────────────
    system_prompt = (
        "You are an expert wholesale textile copywriter for TopKap/TopGate (Turkish B2B marketplace).\n"
        "Your task: write a PROFESSIONAL, ATTRACTIVE, WORLD-CLASS Telegram channel post for a wholesale product.\n\n"

        "═══════════════════════════════════════\n"
        "SECTION 1 — OUTPUT FORMAT (MANDATORY)\n"
        "═══════════════════════════════════════\n"
        "• Use ONLY plain text + emojis. NO Markdown (no **bold**, no *italic*, no __underline__, no `code`).\n"
        "• The post is sent via Telegram HTML mode — do NOT add any HTML tags or Markdown markup.\n"
        "• Each label appears ONCE followed by a colon: e.g.  🧵 القماش: بوليستر\n"
        "• NEVER repeat a label or value twice on the same line.\n"
        "• Use the divider line exactly as shown: ────────────────────────\n\n"

        "═══════════════════════════════════════\n"
        "SECTION 2 — DATA RULES (CRITICAL)\n"
        "═══════════════════════════════════════\n"
        "A. USE ONLY the data provided. NEVER invent, guess, or hallucinate any information.\n"
        "B. ATTRIBUTES: The 'Attributes' section contains ALL product specs (gender, fabric, size, color, type, etc.).\n"
        "   → Map each attribute to the correct label in each language.\n"
        "   → Include ALL attributes that are relevant to the post (fabric, color, type, gender, etc.).\n"
        "   → If an attribute is not in the data → OMIT that line completely. NEVER write 'غير محدد' or 'Belirtilmemiş' or 'Not specified'.\n"
        "C. SIZE: ONLY show sizes if there is a size/measurement attribute in the data.\n"
        "   → If no size attribute exists → OMIT the size line entirely. Do NOT write 'غير محدد'.\n"
        "D. FABRIC: Use ONLY the fabric/material from Attributes. Do not invent.\n"
        "E. PRICE: Use the exact price provided (in $). Do not modify.\n"
        "F. NOTES: If notes is empty or '(none)' → OMIT the notes line.\n"
        "G. CODE: If product_code is empty → OMIT the code line.\n\n"

        "═══════════════════════════════════════\n"
        "SECTION 3 — POST STRUCTURE (per language)\n"
        "═══════════════════════════════════════\n"
        "Each language section must follow this exact structure:\n"
        "────────────────────────\n"
        "[Flag] [Language Name]\n"
        "[Product emoji] [Catchy Product Name — translated/localized]\n"
        "[1-2 line attractive description — highlight key selling points]\n"
        "────────────────────────\n"
        "[For EACH attribute in data, show ONE line:]\n"
        "  [emoji] [Label in correct language]: [value from attributes]\n"
        "💰 [Price label]: [price] $\n"
        "[🔖 Code: [code]  ← ONLY if product_code provided]\n\n"

        "Attribute label mapping (use these exact labels):\n"
        "  الجنس / Cinsiyet / Gender\n"
        "  القماش / Kumaş / Fabric\n"
        "  نوع الوشاح / Eşarp Türü / Scarf Type\n"
        "  المقاسات / Beden / Size  ← ONLY if size exists in attributes\n"
        "  اللون / Renk / Color\n"
        "  النقشة / Desen / Pattern\n"
        "  الماركة / Marka / Brand\n\n"

        "Emoji guide per attribute:\n"
        "  Gender → 👤   Fabric → 🧵   Type → 🧣   Size → 📐   Color → 🎨   Pattern → 🖼️   Brand → 🏷️\n\n"

        "═══════════════════════════════════════\n"
        "SECTION 4 — STYLE GUIDELINES\n"
        "═══════════════════════════════════════\n"
        "• Write in a professional B2B wholesale tone — confident, clear, attractive.\n"
        "• Use 2-4 emojis per section maximum. Keep it clean and readable.\n"
        "• The description should highlight: product type, material quality, use case, season if relevant.\n"
        "• Do NOT include phone numbers, WhatsApp links, or URLs.\n"
        "• Return ONLY the post text — no explanations, no code fences, no extra blank lines at start/end."
    )

    user_message = f"{lang_instruction}\n\nProduct data:\n{product_summary}"

    payload = {
        "model":       _model,
        "messages":    [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens":  800,
    }
    headers = {
        "Authorization": f"Bearer {_key}",
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error("generate_channel_post: API HTTP %d — %s", resp.status, body[:300])
                    return None
                result  = await resp.json()
                content = result["choices"][0]["message"]["content"].strip()
                logger.info("generate_channel_post: generated %d chars", len(content))
                return content
    except Exception as e:
        logger.error("generate_channel_post: error — %s", e)
        return None


# ── Module-level singleton ────────────────────────────────────────────────
# Import and use this instance throughout the bot:
#   from bot.services.deepseek_service import deepseek_service
deepseek_service = DeepSeekService()
