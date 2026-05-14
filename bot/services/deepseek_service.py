"""
bot/services/deepseek_service.py
================================
Handles AI operations using DeepSeek API as required by KAYISOFT.
"""
import os
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DeepSeekService:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com/v1" # Adjust based on actual DeepSeek API docs
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def analyze_product_text(self, text: str, expected_attributes: list) -> Optional[Dict[str, Any]]:
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
        
        Return ONLY a JSON object with the extracted attributes.
        """
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured data from text."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=data, timeout=15)
            response.raise_for_status()
            result = response.json()
            # Parse the JSON from the response content
            # This is a simplified version; robust parsing is needed in production
            content = result['choices'][0]['message']['content']
            import json
            return json.loads(content)
        except Exception as e:
            logger.error(f"DeepSeek API Error: {e}")
            return None

deepseek_service = DeepSeekService()
