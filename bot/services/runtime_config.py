"""Runtime configuration helpers shared by web-facing bot components.

The public base URL is deliberately resolved at call time.  This makes the bot
portable between Railway and the company server without embedding a platform
name or domain into product-flow code.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit


def get_public_base_url() -> str:
    """Return the normalized public HTTPS base URL, or an empty string.

    Preferred production setting:
        PUBLIC_BASE_URL=https://bot.example.com

    ``PUBLIC_DOMAIN`` and Railway-specific variables remain supported solely
    for compatibility with existing deployments.  No value is logged here.
    """
    raw_value = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_STATIC_URL")
        or ""
    ).strip()
    if not raw_value:
        return ""

    candidate = raw_value if "://" in raw_value else f"https://{raw_value}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    # The Telegram WebApp must use HTTPS in production.  ``http`` is retained
    # only for an explicit local-development value such as localhost.
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def get_public_domain() -> str:
    """Return only the hostname[:port] portion for legacy display use."""
    base_url = get_public_base_url()
    return urlsplit(base_url).netloc if base_url else ""
