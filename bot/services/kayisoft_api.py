"""
bot/services/kayisoft_api.py
============================
Handles all communication with the KAYISOFT Backend API.
"""
import os
import logging
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class KayisoftAPI:
    def __init__(self):
        self.base_url = os.getenv("KAYISOFT_API_URL", "https://api.staging.kayisoft.com/v1")
        self.token = os.getenv("KAYISOFT_API_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(method, url, headers=self.headers, json=data, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"KAYISOFT API Error ({method} {url}): {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            return None

    def get_categories(self) -> List[Dict]:
        """Fetches main categories."""
        # TODO: Implement actual endpoint
        return self._request("GET", "/categories") or []

    def get_subcategories(self, category_id: str) -> List[Dict]:
        """Fetches subcategories for a given main category."""
        # TODO: Implement actual endpoint
        return self._request("GET", f"/categories/{category_id}/subcategories") or []

    def get_attributes(self, subcategory_id: str) -> List[Dict]:
        """Fetches attributes for a given subcategory."""
        # TODO: Implement actual endpoint
        return self._request("GET", f"/subcategories/{subcategory_id}/attributes") or []

    def create_product(self, product_data: Dict) -> Optional[Dict]:
        """Creates a new product."""
        # TODO: Implement actual endpoint
        return self._request("POST", "/products", data=product_data)

    def get_upload_url(self, filename: str, content_type: str) -> Optional[Dict]:
        """Gets a signed URL for direct S3 upload."""
        # TODO: Implement actual endpoint
        return self._request("POST", "/upload/signed-url", data={"filename": filename, "content_type": content_type})

kayisoft_api = KayisoftAPI()
