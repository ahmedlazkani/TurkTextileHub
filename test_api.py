"""
test_api.py — KAYISOFT API Connection Test

This diagnostic is intentionally read-only by default. It reads its credentials
from the environment and never stores a live token in source control.

Usage:
    TELEGRAM_BOT_API_ENDPOINT_KEY=... python3 test_api.py

Set RUN_MUTATING_API_TESTS=1 only in an isolated KAYISOFT development account
if the optional POST endpoint checks are explicitly required.
"""

import os
import sys

import requests

BASE_URL = os.getenv("KAYISOFT_API_URL", "https://api-wholesale.dev.kayisoft.net").rstrip("/")
API_TOKEN = os.getenv("TELEGRAM_BOT_API_ENDPOINT_KEY", "").strip()

if not API_TOKEN:
    sys.exit(
        "Missing TELEGRAM_BOT_API_ENDPOINT_KEY. Set it in the environment; "
        "never place a live API key in this file."
    )

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def test(name, method, endpoint, data=None, params=None):
    """Print a compact, token-free endpoint diagnostic."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    try:
        response = requests.request(
            method,
            url,
            headers=HEADERS,
            json=data,
            params=params,
            timeout=10,
        )
        status = response.status_code
        try:
            body = response.json()
        except Exception:
            body = response.text[:300]
        icon = "PASS" if status < 400 else "FAIL"
        print(f"{icon} [{status}] {name}")
        if status < 400:
            if isinstance(body, list):
                print(f"   Items returned: {len(body)}")
                if body:
                    print(f"   First item keys: {list(body[0].keys()) if isinstance(body[0], dict) else 'non-object'}")
            elif isinstance(body, dict):
                print(f"   Response keys: {list(body.keys())}")
        else:
            print(f"   Error: {body}")
    except requests.RequestException as exc:
        print(f"FAIL [NETWORK] {name}: {exc}")
    print()


def main():
    print("=" * 60)
    print("TopKap — KAYISOFT API Read-only Connection Test")
    print("=" * 60)
    print()

    # Safe GET diagnostics only.
    test(
        "GET Root Categories (parent='')",
        "GET",
        "api/seller/categories",
        params={"parent": ""},
    )
    test("GET Categories (no parent)", "GET", "api/seller/categories")

    # Any POST test can create records, trigger validation, or alter remote state.
    # It is deliberately opt-in and must run only against a disposable dev account.
    if os.getenv("RUN_MUTATING_API_TESTS") == "1":
        test(
            "POST Signed URLs (isolated development check)",
            "POST",
            "api/extensions/signed-urls",
            data={
                "operation": "put_product_variant_media",
                "file_names": ["2099-01-01T00:00:00.000Z-read-only-diagnostic"],
                "category_id": "00000000-0000-0000-0000-000000000000",
            },
        )
    else:
        print("POST diagnostics skipped. Set RUN_MUTATING_API_TESTS=1 only for an isolated dev account.\n")

    print("=" * 60)
    print("Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
