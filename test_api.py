"""
test_api.py — KAYISOFT API Connection Test
Tests all endpoints defined in TelegramBackendEndpoints.pdf
"""
import requests
import json

BASE_URL = "https://api-wholesale.dev.kayisoft.net"
API_TOKEN = "wkW7n0uhRU+xmCL4bMllPFbEkD9hRNgm"

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def test(name, method, endpoint, data=None, params=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(method, url, headers=HEADERS, json=data, params=params, timeout=10)
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        icon = "✅" if status < 400 else "❌"
        print(f"{icon} [{status}] {name}")
        if status < 400:
            # Print first item or keys
            if isinstance(body, list):
                print(f"   → {len(body)} items returned")
                if body:
                    print(f"   → First item keys: {list(body[0].keys()) if isinstance(body[0], dict) else body[0]}")
            elif isinstance(body, dict):
                print(f"   → Keys: {list(body.keys())}")
        else:
            print(f"   → Error: {body}")
    except Exception as e:
        print(f"❌ [ERROR] {name}: {e}")
    print()

print("=" * 60)
print("TopKap — KAYISOFT API Connection Test")
print("=" * 60)
print()

# Test 1: Get root categories
test(
    "GET Root Categories (parent='')",
    "GET",
    "api/seller/categories",
    params={"parent": ""}
)

# Test 2: Get categories with no param
test(
    "GET Categories (no param)",
    "GET",
    "api/seller/categories"
)

# Test 3: Test connect endpoint (with dummy data)
test(
    "POST Connect Account (dummy test)",
    "POST",
    "api/seller/telegram-bot/connect",
    data={
        "token": "test_token_123",
        "telegram_user_id": "123456789",
        "telegram_user_name": "test_user"
    }
)

# Test 4: Test signed URLs endpoint
test(
    "POST Get Signed URLs",
    "POST",
    "api/extensions/signed-urls",
    data={
        "operation": "put_product_variant_media",
        "file_names": ["2026-05-14T10:00:00.000Z-abc123def456"],
        "category_id": "00000000-0000-0000-0000-000000000000"
    }
)

print("=" * 60)
print("Test complete.")
print("=" * 60)
