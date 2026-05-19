"""
bot/services/deepseek_service.py
================================
DeepSeek AI Service — TopKap Telegram Bot

Handles AI-powered extraction of structured product attributes from
free-text descriptions provided by suppliers in Arabic, Turkish, or English.

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
# Converts raw_attributes list into a clear, structured prompt for DeepSeek
# ══════════════════════════════════════════════════════════════════════════════

def _build_extraction_prompt(user_text: str, attributes: List[dict]) -> str:
    """
    Builds a detailed, structured prompt for DeepSeek to extract product
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
        str: The complete prompt to send to DeepSeek
    """
    # ── Build attribute catalog ───────────────────────────────────────────────
    attr_lines = []
    for attr in attributes:
        attr_id   = attr.get("id", "")
        attr_name = attr.get("name", "")
        attr_key  = attr.get("key", "")
        ui_type   = attr.get("ui_type", "text")
        required  = attr.get("required", False)
        is_selector = attr.get("is_variant_selector", False)
        options   = attr.get("options", [])

        req_label = "REQUIRED" if required else "optional"
        sel_label = " [VARIANT SELECTOR]" if is_selector else ""

        line = f'  - id="{attr_id}" | name="{attr_name}" | key="{attr_key}" | type={ui_type} | {req_label}{sel_label}'

        if options:
            opts_str = ", ".join(
                f'id="{o.get("id","")}" value="{o.get("value","")}"'
                for o in options
            )
            line += f'\n    Options: [{opts_str}]'

        attr_lines.append(line)

    attrs_catalog = "\n".join(attr_lines) if attr_lines else "  (no attributes defined)"

    # ── Build output schema example ───────────────────────────────────────────
    # Helps the AI understand exactly what format to produce
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
9. For price: extract the numeric value only (e.g. "100 ليرة" → "100").
10. For quantities: "200 قطعة" → min_quantity=200, "4000 قطعة" → stock_count=4000.
    If only one quantity is given, use it for both min_quantity and stock_count.

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
# DeepSeek Service
# ══════════════════════════════════════════════════════════════════════════════

class DeepSeekService:
    """
    Async client for the DeepSeek Chat API.

    Used to extract structured product attributes from free-text supplier
    descriptions. The AI is given the full attribute catalog (with UUIDs and
    valid options) so it can produce output that matches the KAYISOFT API schema.

    Environment:
        DEEPSEEK_API_KEY — required for live mode; if absent, returns mock data
    """

    def __init__(self):
        self.api_key  = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com/v1"
        self.headers  = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

    async def analyze_product_text(
        self,
        text: str,
        expected_attributes: List[dict],
    ) -> Optional[Dict[str, Any]]:
        """
        Analyzes the supplier's free-text description and extracts structured
        product data including all required and optional attributes.

        The prompt is built dynamically from expected_attributes so the AI
        knows the exact UUID and valid options for each attribute — this
        prevents the AI from inventing keys or missing required fields.

        Args:
            text:                The supplier's product description (any language)
            expected_attributes: List of attribute dicts from KAYISOFT API
                                 (each has: id, name, key, ui_type, required,
                                  is_variant_selector, options[])

        Returns:
            dict with keys:
                name, description, price, min_quantity, stock_count,
                shared_attributes   { attr_uuid: value_or_option_id },
                selector_attributes [ { attribute_id, option_id } ]
            or None on API failure.
        """
        if not self.api_key:
            logger.warning(
                "DEEPSEEK_API_KEY not set — returning mock extraction. "
                "Set DEEPSEEK_API_KEY env var for live AI extraction."
            )
            # Return a minimal mock so the flow continues without crashing
            return {
                "name":                text[:80],
                "description":         text,
                "price":               "0",
                "min_quantity":        1,
                "stock_count":         100,
                "shared_attributes":   {},
                "selector_attributes": [],
            }

        prompt = _build_extraction_prompt(text, expected_attributes)

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise data extraction assistant for a wholesale textile marketplace. "
                        "You always output valid JSON only, with no markdown fences, no explanation, "
                        "no extra text. You understand Arabic, Turkish, and English product descriptions."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.0,   # Deterministic output for structured extraction
            "max_tokens":  1024,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        logger.error(
                            "DeepSeek API error %s: %s",
                            resp.status, error_text[:300],
                        )
                        return None

                    result  = await resp.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Strip markdown fences if the model adds them despite instructions
                    if content.startswith("```json"):
                        content = content[7:]
                    elif content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]

                    parsed = json.loads(content.strip())
                    logger.info(
                        "DeepSeek extraction OK — keys: %s",
                        list(parsed.keys()),
                    )
                    return parsed

            except json.JSONDecodeError as e:
                logger.error("DeepSeek returned invalid JSON: %s", e)
                return None
            except Exception as e:
                logger.error("DeepSeek API exception: %s", e)
                return None


# ── Singleton instance ────────────────────────────────────────────────────────
deepseek_service = DeepSeekService()
