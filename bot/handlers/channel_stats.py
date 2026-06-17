"""
bot/handlers/channel_stats.py
==============================
Channel statistics tracking and weekly report system.

Features:
  1. track_product_published(user_id)   — called after every successful channel post
  2. send_weekly_stats_to_all_suppliers — job_queue callback (runs every Monday 09:00 UTC)
  3. /mystats command                   — supplier can request stats on demand

Data model (JSON file per user):
  /data/channel_stats.json
  {
    "<user_id>": {
      "total_published": 42,
      "week_published": 5,
      "week_start": "2026-06-16",   # ISO date of current week's Monday
      "products": [
        {"product_id": "...", "product_name": "...", "published_at": "2026-06-17T10:00:00"}
      ]
    }
  }

Programmatic note:
  - "week_published" resets every Monday when the weekly report is sent.
  - "products" keeps the last 50 entries to avoid unbounded growth.
  - All file I/O is wrapped in try/except to never crash the bot.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram.ext import ContextTypes

from bot.services.language_service import get_user_lang
from bot.handlers.channel_handler import get_channel_id_for_user

logger = logging.getLogger(__name__)

# ── Persistent storage path ────────────────────────────────────────────────────
_STATS_FILE: Optional[str] = None

def _resolve_stats_file() -> str:
    global _STATS_FILE
    if _STATS_FILE:
        return _STATS_FILE
    data_dir = os.environ.get("CHANNELS_FILE", "").replace("user_channels.json", "").strip("/")
    if data_dir and os.path.isdir("/" + data_dir):
        path = os.path.join("/" + data_dir, "channel_stats.json")
    elif os.path.isdir("/data"):
        path = "/data/channel_stats.json"
    else:
        path = "/tmp/channel_stats.json"
    _STATS_FILE = path
    return path


def _load_stats() -> dict:
    path = _resolve_stats_file()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.error("❌ Failed to load channel_stats from %s: %s", path, exc)
    return {}


def _save_stats(data: dict) -> None:
    path = _resolve_stats_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error("❌ Failed to save channel_stats to %s: %s", path, exc)


def _current_week_start() -> str:
    """Return ISO date string for the most recent Monday (UTC)."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# Public API — called from product_handler after successful publish
# ══════════════════════════════════════════════════════════════════════════════
def track_product_published(
    user_id: str,
    product_id: str = "",
    product_name: str = "",
) -> None:
    """
    Increment published-product counters for a supplier.
    Called immediately after a successful channel post.

    Programmatic note:
      This is a synchronous function (no async) so it can be called
      from anywhere without await. File I/O is fast enough for this use case.
    """
    stats = _load_stats()
    week_start = _current_week_start()

    if user_id not in stats:
        stats[user_id] = {
            "total_published": 0,
            "week_published": 0,
            "week_start": week_start,
            "products": [],
        }

    entry = stats[user_id]

    # Reset weekly counter if a new week has started
    if entry.get("week_start") != week_start:
        entry["week_published"] = 0
        entry["week_start"] = week_start

    entry["total_published"] = entry.get("total_published", 0) + 1
    entry["week_published"] = entry.get("week_published", 0) + 1

    # Keep last 50 products
    products = entry.get("products", [])
    products.append({
        "product_id": product_id,
        "product_name": product_name,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    entry["products"] = products[-50:]

    _save_stats(stats)
    logger.info(
        "📊 Stats updated: user_id=%s | total=%d | week=%d",
        user_id, entry["total_published"], entry["week_published"]
    )


# ══════════════════════════════════════════════════════════════════════════════
# Weekly report — job_queue callback (every Monday 09:00 UTC)
# ══════════════════════════════════════════════════════════════════════════════
async def send_weekly_stats_to_all_suppliers(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends a weekly statistics report to every supplier who has published
    at least one product in the past week.

    Scheduled via job_queue in main.py:
      application.job_queue.run_daily(
          send_weekly_stats_to_all_suppliers,
          time=datetime.time(9, 0, tzinfo=timezone.utc),
          days=(0,),   # 0 = Monday
      )

    Programmatic note:
      job_queue callbacks receive a single argument: context.
      context.bot is the Bot instance used to send messages.
    """
    stats = _load_stats()
    week_start = _current_week_start()
    sent_count = 0

    for user_id, entry in stats.items():
        week_published = entry.get("week_published", 0)
        total_published = entry.get("total_published", 0)

        # Only send report if supplier published something this week
        if week_published == 0:
            continue

        # Find most published product this week
        products_this_week = [
            p for p in entry.get("products", [])
            if p.get("published_at", "")[:10] >= week_start
        ]
        top_product = products_this_week[-1].get("product_name", "—") if products_this_week else "—"

        lang = get_user_lang(user_id)

        report_texts = {
            "ar": (
                "📊 <b>تقريرك الأسبوعي — TopGate</b>\n\n"
                f"🗓️ الأسبوع: {week_start}\n\n"
                f"📦 <b>المنتجات المنشورة هذا الأسبوع:</b> {week_published}\n"
                f"📈 <b>إجمالي المنتجات المنشورة:</b> {total_published}\n"
                f"⭐ <b>آخر منتج منشور:</b> {top_product}\n\n"
                "💡 استمر في نشر منتجاتك لتصل لأكبر عدد من تجار الجملة."
            ),
            "tr": (
                "📊 <b>Haftalık Raporunuz — TopGate</b>\n\n"
                f"🗓️ Hafta: {week_start}\n\n"
                f"📦 <b>Bu hafta yayınlanan ürünler:</b> {week_published}\n"
                f"📈 <b>Toplam yayınlanan ürünler:</b> {total_published}\n"
                f"⭐ <b>Son yayınlanan ürün:</b> {top_product}\n\n"
                "💡 Daha fazla toptan alıcıya ulaşmak için ürün yayınlamaya devam edin."
            ),
            "en": (
                "📊 <b>Your Weekly Report — TopGate</b>\n\n"
                f"🗓️ Week: {week_start}\n\n"
                f"📦 <b>Products published this week:</b> {week_published}\n"
                f"📈 <b>Total products published:</b> {total_published}\n"
                f"⭐ <b>Last published product:</b> {top_product}\n\n"
                "💡 Keep publishing to reach more wholesale buyers."
            ),
        }

        text = report_texts.get(lang, report_texts["en"])

        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=text,
                parse_mode="HTML",
            )
            sent_count += 1
            logger.info("📊 Weekly report sent to user_id=%s", user_id)

            # Reset weekly counter after sending
            entry["week_published"] = 0
            entry["week_start"] = week_start

        except Exception as exc:
            logger.warning("⚠️ Could not send weekly report to user_id=%s: %s", user_id, exc)

    # Save updated stats (weekly counters reset)
    _save_stats(stats)
    logger.info("📊 Weekly reports sent to %d suppliers.", sent_count)


# ══════════════════════════════════════════════════════════════════════════════
# /mystats command — on-demand stats for the supplier
# ══════════════════════════════════════════════════════════════════════════════
async def handle_mystats(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /mystats command — supplier can request their stats at any time.
    Shows: total published, this week published, last 3 products.
    """
    user = update.effective_user
    user_id = str(user.id)
    lang = get_user_lang(user_id)

    stats = _load_stats()
    entry = stats.get(user_id)

    if not entry or entry.get("total_published", 0) == 0:
        no_stats = {
            "ar": "📊 لم تنشر أي منتجات بعد.\n\nابدأ بنشر منتجك الأول لترى إحصائياتك هنا!",
            "tr": "📊 Henüz ürün yayınlamadınız.\n\nİstatistiklerinizi görmek için ilk ürününüzü yayınlayın!",
            "en": "📊 You haven't published any products yet.\n\nPublish your first product to see your stats here!",
        }
        await update.message.reply_text(
            no_stats.get(lang, no_stats["en"]),
            parse_mode="HTML",
        )
        return

    week_start = _current_week_start()
    # Reset weekly counter if new week
    if entry.get("week_start") != week_start:
        entry["week_published"] = 0
        entry["week_start"] = week_start

    total = entry.get("total_published", 0)
    week = entry.get("week_published", 0)
    products = entry.get("products", [])
    last_3 = products[-3:][::-1]  # Last 3, newest first

    def fmt_product(p: dict) -> str:
        name = p.get("product_name") or p.get("product_id", "—")
        dt_str = p.get("published_at", "")[:10]
        return f"• {name} ({dt_str})"

    last_3_text = "\n".join(fmt_product(p) for p in last_3) if last_3 else "—"

    stats_texts = {
        "ar": (
            "📊 <b>إحصائياتك — TopGate</b>\n\n"
            f"📦 <b>إجمالي المنتجات المنشورة:</b> {total}\n"
            f"📅 <b>هذا الأسبوع:</b> {week}\n\n"
            f"🕐 <b>آخر المنتجات المنشورة:</b>\n{last_3_text}"
        ),
        "tr": (
            "📊 <b>İstatistikleriniz — TopGate</b>\n\n"
            f"📦 <b>Toplam yayınlanan ürünler:</b> {total}\n"
            f"📅 <b>Bu hafta:</b> {week}\n\n"
            f"🕐 <b>Son yayınlanan ürünler:</b>\n{last_3_text}"
        ),
        "en": (
            "📊 <b>Your Stats — TopGate</b>\n\n"
            f"📦 <b>Total products published:</b> {total}\n"
            f"📅 <b>This week:</b> {week}\n\n"
            f"🕐 <b>Last published products:</b>\n{last_3_text}"
        ),
    }

    await update.message.reply_text(
        stats_texts.get(lang, stats_texts["en"]),
        parse_mode="HTML",
    )
