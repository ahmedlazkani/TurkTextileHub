# TopKap WebApp Mini App — Integration Guide

## Overview

The WebApp Mini App replaces the free-text product description step (Step 3)
with a structured HTML form that opens inside Telegram.

## Architecture

```
Supplier taps "📝 فتح نموذج المنتج"
        ↓
Telegram opens WebApp URL:
  https://<RAILWAY_DOMAIN>/webapp/product-form
  ?category_id=<uuid>&lang=ar&user_id=<telegram_id>
        ↓
Browser loads product_form.html (served by FastAPI)
        ↓
JS fetches attributes from /api/attributes/<category_id>
        ↓
Supplier fills form → taps "✅ حفظ بيانات المنتج"
        ↓
Telegram.WebApp.sendData(JSON) → Bot receives WEB_APP_DATA
        ↓
handle_webapp_data() validates + stores product_details
        ↓
Bot shows summary → Supplier confirms → Image upload step
```

## New Files

| File | Purpose |
|---|---|
| `bot/webapp/product_form.html` | Single-file HTML/CSS/JS Mini App form |
| `bot/routes/webapp_routes.py` | FastAPI router: serves form + proxies attributes |
| `bot/routes/__init__.py` | Package init |
| `bot/webapp/__init__.py` | Package init |

## Modified Files

| File | Change |
|---|---|
| `bot/main.py` | Added `_start_fastapi_server()` in background thread |
| `bot/handlers/product_handler.py` | Added `handle_webapp_data()`, `handle_manual_entry_fallback()`, updated `_load_attributes_and_ask_form()` and `get_product_conv_handler()` |
| `requirements.txt` | Added `fastapi`, `uvicorn[standard]`, `httpx` |

## Environment Variables Required

| Variable | Description | Example |
|---|---|---|
| `RAILWAY_DOMAIN` | **NEW** — Public domain of Railway service | `topkap.up.railway.app` |
| `PORT` | FastAPI server port (default: 8080) | `8080` |

## How to Set RAILWAY_DOMAIN in Railway

1. Go to Railway Dashboard → Your Service → Variables
2. Add: `RAILWAY_DOMAIN` = `<your-service-name>.up.railway.app`
3. Redeploy

## Fallback (Manual Entry)

If the supplier taps "✏️ الإدخال اليدوي", the bot falls back to the
original free-text description flow (AI extraction). This ensures
backward compatibility if the WebApp fails to load.

## Flow States

```
START_ADD_PRODUCT
    ↓
SELECT_CATEGORY      (inline keyboard — 2 per row)
    ↓
SELECT_SUBCATEGORY   (inline keyboard — 2 per row)
    ↓
FILL_FORM            ← WEB_APP_DATA handler (primary)
                     ← TEXT handler (fallback/manual)
    ↓
CONFIRM_DETAILS      (موافق / تعديل)
    ↓
FIX_MISSING          (if required attributes missing)
    ↓
UPLOAD_IMAGES        (send photos)
    ↓
CONFIRM_VARIANTS     (review variants)
    ↓
PUBLISH              (نشر ✅ / إلغاء ❌)
```
