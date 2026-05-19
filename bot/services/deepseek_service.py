"""
bot/services/deepseek_service.py
================================
AI Extraction Service — TopKap Telegram Bot

Handles AI-powered extraction of structured product attributes from
free-text descriptions provided by suppliers in Arabic, Turkish, or English.

Provider priority:
  1. DeepSeek (DEEPSEEK_API_KEY env var) — preferred, cost-effective
  2. OpenAI-compatible API (OPENAI_API_KEY env var) — automatic fallback
     Uses gpt-4.1-mini by default; set FALLBACK_AI_MODEL to override.
  3. Mock mode — if neither key is available (returns minimal data)

Key design decisions:
  - The prompt explicitly maps each attribute to its UUID (id field from API)
  - The AI is instructed to output JSON keyed by attribute UUID, not by name
  - Options are listed with their UUIDs so the AI can match them correctly
  - The output schema matches exactly what _check_missing_required() expects:
      shared_attributes:    { attr_id: value_or_option_id }
      selector_attributes:  [ { attribute_id: ..., option_id: ... } ]
  - Fuzzy matching: if the user writes "شيفون" and the option is "Şifon",
    the AI is instructed to match semantically, not just by exact string
"""
import os
import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Prompt Builder
# Converts raw_attributes list into a clear, structured prompt for the AI
# ══════════════════════════════════════════════════════════════════════════════

def _build_extraction_prompt(user_text: str, attributes: List[dict]) -> str:
    """
    Builds a detailed, structured prompt for the AI to extract product
    attributes from the supplier's free-text description.

    The prompt:
    1. Lists every attribute with its UUID, name, type, required flag
    2. For selector/option attributes: lists all valid option UUIDs + values
    3. Specifies the exact JSON output schema keyed by attribute UUID
    4. Instructs the AI to handle Arabic/Turkish/English input
    5. Instructs the AI to match semantically (e.g. "شيفون" → "Şifon")

    Args:
        user_text:   The supplier's free-text product description
        attributes:  List of attribute dicts from KAYISOFT API

    Returns:
        str: The complete prompt to send to the AI
    """
    # ── Build attribute catalog ───────────────────────────────────────────────
    attr_lines = []
    for attr in attributes:
        attr_id     = attr.get("id", "")
        attr_name   = attr.get("name", "")
        attr_key    = attr.get("key", "")
        ui_type     = attr.get("ui_type", "text")
        required    = attr.get("required", False)
        is_selector = attr.get("is_variant_selector", False)
        options     = attr.get("options", [])

        req_label = "REQUIRED" if required else "optional"
        sel_label = " [VARIANT SELECTOR]" if is_selector else ""

        line = (
            f'  - id="{attr_id}" | name="{attr_name}" | key="{attr_key}" '
            f'| type={ui_type} | {req_label}{sel_label}'
        )

        if options:
            opts_str = ", ".join(
                f'id="{o.get("id","")}" value="{o.get("value","")}"'
                for o in options
            )
            line += f'\n    Options: [{opts_str}]'

        attr_lines.append(line)

    attrs_catalog = "\n".join(attr_lines) if attr_lines else "  (no attributes defined)"

    # ── Build output schema example ───────────────────────────────────────────
    schema_example = json.dumps({
        "name": "Product name extracted from text",
        "description": "Full product description",
        "price": "100.00",
        "min_quantity": 1,
        "stock_count": 200,
        "shared_attributes": {
            "<attr_uuid_for_non_variant_attr>": "<extracted_value_or_option_id>"
        },
        "selector_attributes": [
            {
                "attribute_id": "<attr_uuid_for_variant_selector_attr>",
                "option_id": "<option_uuid_that_matches_user_text>"
            }
        ]
    }, ensure_ascii=False, indent=2)

    prompt = f"""You are an AI assistant for TopKap, a wholesale textile marketplace.
Your task: extract structured product data from a supplier's free-text description.

=== SUPPLIER TEXT ===
{user_text}

=== AVAILABLE ATTRIBUTES (from KAYISOFT API) ===
{attrs_catalog}

=== EXTRACTION RULES ===
1. For each attribute, find the matching value in the supplier text.
2. The supplier may write in Arabic, Turkish, or English — handle all three.
3. For attributes WITH options: match semantically (e.g. "شيفون"→"Şifon", "صيفي"→"Yaz").
   Use the OPTION UUID (id field) as the value in selector_attributes.
4. For attributes WITHOUT options (numeric/text): use the raw extracted value as string.
5. For shared (non-variant) attributes: put them in "shared_attributes" keyed by attribute UUID.
6. For variant selector attributes (marked [VARIANT SELECTOR]): put them in "selector_attributes"
   as objects with "attribute_id" and "option_id".
7. Extract "name", "description", "price" (numeric string), "min_quantity" (int), "stock_count" (int).
8. If a value is not found in the text, OMIT that key entirely (do not set null or empty string).
9. For price: extract the numeric value only (e.g. "100 ليرة" → "100", "120 lira" → "120").
10. For quantities: "200 قطعة" → min_quantity=200, "4000 قطعة" → stock_count=4000.
    If only one quantity is given, use it for both min_quantity and stock_count.
11. For size/dimensions like "170 سم ب 80 سم" or "170x80": extract as a string value.
12. For colors like "سكري" (sugar/beige), "أبيض" (white), "أسود" (black): match to the closest option.

=== REQUIRED OUTPUT FORMAT ===
Return ONLY a valid JSON object matching this schema (no markdown, no explanation):
{schema_example}

=== IMPORTANT ===
- Keys in shared_attributes and attribute_id in selector_attributes MUST be attribute UUIDs from the catalog above.
- Do NOT use attribute names as keys — use the UUID id field.
- Do NOT include attributes that are not found in the supplier text.
"""
    return prompt


# ══════════════════════════════════════════════════════════════════════════════
# AI Response Parser
# ══════════════════════════════════════════════════════════════════════════════

def _parse_ai_response(content: str) -> Optional[Dict[str, Any]]:
    """
    Parses the raw AI response string into a Python dict.

    Handles:
    - Markdown code fences (```json ... ```)
    - Extra whitespace
    - Invalid JSON (returns None)

    Args:
        content: Raw string from AI response

    Returns:
        Parsed dict or None on failure
    """
    content = content.strip()

    # Strip markdown fences if the model adds them despite instructions
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    try:
        parsed = json.loads(content)
        logger.info("AI extraction OK — keys: %s", list(parsed.keys()))
        return parsed
    except json.JSONDecodeError as e:
        logger.error("AI returned invalid JSON: %s | content: %s", e, content[:200])
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AI Extraction Service
# ══════════════════════════════════════════════════════════════════════════════

class DeepSeekService:
    """
    Async AI client for structured product attribute extraction.

    Provider priority:
      1. DeepSeek (DEEPSEEK_API_KEY) — https://api.deepseek.com/v1
      2. OpenAI-compatible (OPENAI_API_KEY) — automatic fallback
      3. Mock mode — if neither key is set

    The service is transparent: callers always call analyze_product_text()
    regardless of which provider is actually used.
    """

    DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL    = "deepseek-chat"

    # OpenAI-compatible fallback (supports gpt-4.1-mini, gemini-2.5-flash, etc.)
    OPENAI_BASE_URL   = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    FALLBACK_MODEL    = os.getenv("FALLBACK_AI_MODEL", "gpt-4.1-mini")

    SYSTEM_PROMPT = (
        "You are a precise data extraction assistant for a wholesale textile marketplace. "
        "You always output valid JSON only, with no markdown fences, no explanation, "
        "no extra text. You understand Arabic, Turkish, and English product descriptions."
    )

    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.openai_key   = os.getenv("OPENAI_API_KEY", "").strip()

        if self.deepseek_key:
            logger.info("AI provider: DeepSeek (primary)")
        elif self.openai_key:
            logger.info(
                "AI provider: OpenAI-compatible fallback (model=%s, base=%s)",
                self.FALLBACK_MODEL, self.OPENAI_BASE_URL,
            )
        else:
            logger.warning("AI provider: MOCK MODE — no API keys found")

    # ── Internal: call any OpenAI-compatible endpoint ─────────────────────────

    async def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> Optional[str]:
        """
        Makes a POST request to an OpenAI-compatible /chat/completions endpoint.

        Args:
            base_url: API base URL (e.g. "https://api.deepseek.com/v1")
            api_key:  Bearer token
            model:    Model name (e.g. "deepseek-chat", "gpt-4.1-mini")
            prompt:   User prompt text

        Returns:
            Raw response content string, or None on error
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
            "temperature": 0.0,   # Deterministic output for structured extraction
            "max_tokens":  1024,
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
                        error_text = await resp.text()
                        logger.error(
                            "AI API error %s (model=%s): %s",
                            resp.status, model, error_text[:300],
                        )
                        return None

                    result  = await resp.json()
                    content = result["choices"][0]["message"]["content"]
                    return content

            except Exception as e:
                logger.error("AI API exception (model=%s): %s", model, e)
                return None

    # ── Public interface ──────────────────────────────────────────────────────

    async def analyze_product_text(
        self,
        text: str,
        expected_attributes: List[dict],
    ) -> Optional[Dict[str, Any]]:
        """
        Analyzes the supplier's free-text description and extracts structured
        product data including all required and optional attributes.

        Provider cascade:
          1. Try DeepSeek if DEEPSEEK_API_KEY is set
          2. Try OpenAI-compatible if OPENAI_API_KEY is set
          3. Return mock data if neither key is available

        Args:
            text:                The supplier's product description (any language)
            expected_attributes: List of attribute dicts from KAYISOFT API

        Returns:
            dict with keys: name, description, price, min_quantity, stock_count,
                            shared_attributes, selector_attributes
            or None on complete failure.
        """
        prompt = _build_extraction_prompt(text, expected_attributes)

        # ── 1. Try DeepSeek ───────────────────────────────────────────────────
        if self.deepseek_key:
            logger.info("Attempting extraction via DeepSeek...")
            content = await self._call_openai_compatible(
                base_url=self.DEEPSEEK_BASE_URL,
                api_key=self.deepseek_key,
                model=self.DEEPSEEK_MODEL,
                prompt=prompt,
            )
            if content is not None:
                result = _parse_ai_response(content)
                if result is not None:
                    return result
                logger.warning("DeepSeek returned unparseable response — trying fallback")
            else:
                logger.warning("DeepSeek API call failed — trying OpenAI fallback")

        # ── 2. Try OpenAI-compatible fallback ─────────────────────────────────
        if self.openai_key:
            logger.info(
                "Attempting extraction via OpenAI-compatible API (model=%s)...",
                self.FALLBACK_MODEL,
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
                    return result
                logger.warning("OpenAI fallback returned unparseable response")
            else:
                logger.warning("OpenAI fallback API call also failed")

        # ── 3. Mock mode ──────────────────────────────────────────────────────
        if not self.deepseek_key and not self.openai_key:
            logger.warning(
                "MOCK MODE: No AI API keys configured. "
                "Set DEEPSEEK_API_KEY or OPENAI_API_KEY in Railway environment variables."
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

        # Both providers failed
        logger.error(
            "All AI providers failed for text: %s...",
            text[:100],
        )
        return None


# ── Singleton instance ────────────────────────────────────────────────────────
deepseek_service = DeepSeekService()
