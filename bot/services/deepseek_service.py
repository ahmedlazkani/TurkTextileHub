"""
bot/services/deepseek_service.py
================================
Handles AI operations using DeepSeek API as required by KAYISOFT.
"""
import os
import json
import logging
import aiohttp
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DeepSeekService:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def analyze_product_text(self, text: str, expected_attributes: list) -> Optional[Dict[str, Any]]:
        """
        Analyzes raw text from the user and extracts structured attributes.
        """
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not set. Returning mock data.")
            return {"status": "mock", "extracted": {}}

        prompt = f"""
        You are an AI assistant for a wholesale textile marketplace.
        Extract the following attributes from the user's text:
        Expected Attributes: {expected_attributes}
        
        User Text: "{text}"
        
        Return ONLY a valid JSON object with the extracted attributes. Do not include markdown formatting like ```json.
        """
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured data from text. Always output valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status >= 400:
                        error_data = await resp.text()
                        logger.error(f"DeepSeek API Error: {resp.status} - {error_data}")
                        return None
                    
                    result = await resp.json()
                    content = result['choices'][0]['message']['content'].strip()
                    
                    # Clean up markdown if present
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                        
                    return json.loads(content.strip())
            except Exception as e:
                logger.error(f"DeepSeek API Exception: {e}")
                return None

deepseek_service = DeepSeekService()
