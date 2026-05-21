# تقييم فورم إضافة المنتج + Prompt احترافي لـ Claude/Gemini

---

## أولاً: تقييم الإمكانية

### الوضع الحالي (الخطوة 3)
البوت حالياً يطلب من المورد **إرسال نص حر** يصف المنتج، ثم يُحلله الـ AI.
هذا يسبب مشاكل:
- المورد لا يعرف ماذا يكتب بالضبط
- السعر قد يأتي بصيغة خاطئة
- الحقول المطلوبة قد تُنسى

### الحل المقترح: Telegram Mini App (Web App)
فورم HTML/CSS/JS يُفتح داخل تيليغرام كـ WebApp عند الضغط على زر.

---

## ثانياً: جدول الإمكانية

| الميزة | الإمكانية | ملاحظات |
|---|---|---|
| فورم HTML داخل تيليغرام | ✅ ممكن 100% | Telegram WebApp API مدعوم كاملاً |
| حقل نص (اسم، وصف) | ✅ سهل | `<input>` و `<textarea>` عادية |
| حقل سعر رقمي | ✅ سهل | `<input type="number">` مع validation |
| dropdown للعملة | ✅ سهل | `<select>` عادي |
| حقل كمية | ✅ سهل | `<input type="number" min="1">` |
| رفع صور متعددة | ✅ ممكن | `<input type="file" multiple accept="image/*">` |
| حقول ديناميكية (attributes من API) | ✅ ممكن | تُبنى بـ JavaScript بعد fetch من API |
| color picker للألوان | ✅ ممكن | `<input type="color">` أو مكتبة جاهزة |
| إرسال البيانات للبوت | ✅ ممكن | `Telegram.WebApp.sendData(JSON)` |
| تصميم RTL (عربي) | ✅ سهل | `dir="rtl"` + TailwindCSS |
| Telegram theme colors | ✅ ممكن | `Telegram.WebApp.themeParams` |
| استضافة | ✅ على Railway | نفس الـ server الحالي |

---

## ثالثاً: الملاحظات الهامة

1. **الـ WebApp يحتاج HTTPS** — Railway يوفره تلقائياً ✅
2. **الـ attributes ديناميكية** — كل فئة لها attributes مختلفة، يجب fetch من API عند فتح الفورم
3. **الصور** — يمكن رفعها مباشرة من الفورم أو الإبقاء على رفعها في البوت بعد الفورم
4. **الـ Bot Token** — يجب تمريره بأمان (لا يُعرض في الـ frontend)
5. **التحقق** — يجب التحقق من `initData` من تيليغرام لضمان الأمان

---

## رابعاً: Prompt احترافي لـ Claude/Gemini

```
You are a senior full-stack developer specializing in Telegram Mini Apps (WebApps).
Your task: build a complete, production-ready Telegram Mini App for a B2B textile marketplace bot called "TopKap".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT & ARCHITECTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The bot is built with python-telegram-bot v20 (async), deployed on Railway.
The backend API is KAYISOFT (REST, JWT auth).
The Mini App replaces Step 3 of the product-addition flow:
  BEFORE: Bot sends a text prompt → Supplier types free text → AI parses it
  AFTER:  Bot sends a WebApp button → Supplier fills a structured form → Form sends JSON to bot

The Mini App is served by a FastAPI server running alongside the bot on the same Railway service.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORM FIELDS (in order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. اسم المنتج (Product Name) — REQUIRED
   • Type: text input
   • Placeholder: "مثال: شال شيفون صيفي"
   • Max: 100 chars
   • Validation: min 3 chars

2. الوصف (Description) — optional
   • Type: textarea
   • Placeholder: "اكتب وصف المنتج بالتفصيل..."
   • Max: 1000 chars

3. السعر (Price) — REQUIRED
   • Type: number input (decimal allowed)
   • Placeholder: "مثال: 200"
   • Min: 0.01
   • Note: currency is always TRY (Turkish Lira), no currency selector needed

4. الحد الأدنى للطلب (Minimum Order Quantity) — REQUIRED
   • Type: integer input
   • Placeholder: "مثال: 300"
   • Min: 1

5. المخزون (Stock Count) — REQUIRED
   • Type: integer input
   • Placeholder: "مثال: 5000"
   • Min: 1
   • Default: same value as min_quantity if left empty

6. الخصائص الديناميكية (Dynamic Attributes) — loaded from API
   • These are fetched dynamically from:
     GET /api/categories/{category_id}/attributes
     (category_id is passed as a URL query param when opening the WebApp)
   • Each attribute has:
     - id (UUID)
     - name (display name, Arabic/Turkish)
     - key (string key)
     - ui_type: "select" | "color" | "text" | "multiselect"
     - required: true/false
     - is_variant_selector: true/false
     - options: [{id, value, hex_code?}]
   • Render rules:
     - ui_type="select"      → <select> dropdown
     - ui_type="color"       → color swatches grid (show hex color circles + label)
     - ui_type="text"        → <input type="text">
     - ui_type="multiselect" → checkbox group
     - required=true         → show red asterisk (*) and validate before submit
     - is_variant_selector=true → mark with a "🎨 Variant" badge

7. صور المنتج (Product Images) — optional in form (uploaded separately in bot)
   • Show a note: "سيتم طلب الصور في الخطوة التالية"
   • Do NOT include file upload in the form (images are handled by the bot after form submission)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT JSON STRUCTURE (sent to bot via Telegram.WebApp.sendData)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "name": "شال شيفون صيفي",
  "description": "شال شيفون فاخر مناسب للصيف",
  "price": "200",
  "min_quantity": 300,
  "stock_count": 5000,
  "shared_attributes": {
    "<attr_uuid>": ["<option_uuid>"]
  },
  "selector_attributes": [
    {
      "attribute_id": "<attr_uuid>",
      "option_id": "<option_uuid>"
    }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECHNICAL REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Frontend:
- Pure HTML + CSS + Vanilla JavaScript (NO React/Vue — keep it lightweight)
- Use Telegram WebApp CSS variables for theming:
    --tg-theme-bg-color, --tg-theme-text-color, --tg-theme-button-color, etc.
- RTL layout (dir="rtl", text-align: right)
- Arabic UI text
- Mobile-first responsive design
- Smooth animations for loading states
- Show loading spinner while fetching attributes from API
- Disable submit button until all required fields are valid
- Show inline validation errors (red text under each field)
- Use Telegram.WebApp.MainButton for the submit action (styled with bot's theme)
- Call Telegram.WebApp.ready() on load
- Call Telegram.WebApp.expand() on load
- On submit: call Telegram.WebApp.sendData(JSON.stringify(formData))

Backend (FastAPI — add to existing server):
- Route: GET /webapp/product-form?category_id={uuid}&lang={ar|tr|en}&user_id={telegram_id}
  → Serves the HTML page
- Route: GET /api/attributes/{category_id}
  → Proxies KAYISOFT GET /categories/{id}/attributes
  → Requires: KAYISOFT JWT token (fetched server-side using user_id)
  → Returns: JSON array of attributes

Bot integration (python-telegram-bot):
- After subcategory selection, instead of asking for free text:
  1. Build WebApp URL: https://{RAILWAY_DOMAIN}/webapp/product-form?category_id={sub_id}&lang={lang}&user_id={user_id}
  2. Send message with InlineKeyboardButton(text="📝 فتح فورم المنتج", web_app=WebAppInfo(url=...))
- Handle WebApp data: register a MessageHandler for filters.StatusUpdate.WEB_APP_DATA
  → Parse the JSON from update.effective_message.web_app_data.data
  → Store in context.user_data["product_details"]
  → Proceed to image upload step (UPLOAD_IMAGES state)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN SPECIFICATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Header: "📦 إضافة منتج جديد" with subtitle "يرجى تعبئة معلومات المنتج أدناه"
- Each field has:
  - Icon on the right (emoji)
  - Label in Arabic
  - Red asterisk for required fields
  - Input/select/swatches below
  - Error message in red if validation fails
- Color swatches: circular divs (32px) with hex background + tooltip on hover
- Submit button: full-width, uses Telegram.WebApp.MainButton (blue, bottom of screen)
- Loading state: skeleton placeholders for dynamic attribute fields
- Success state: brief checkmark animation before window closes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXISTING CODE CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The existing bot handler that needs to be modified is:
  bot/handlers/product_handler.py → function: _load_attributes_and_ask_form()

Currently it sends a text message asking for free text.
You must:
1. Replace the text message with a WebApp button
2. Add a new handler for WEB_APP_DATA messages
3. Keep the existing fallback (free text) as a secondary option for users who can't use WebApp

The existing FastAPI server is at:
  bot/server.py (or main.py — check the project structure)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please provide:

1. webapp/product_form.html — Complete HTML file with embedded CSS and JavaScript
2. bot/routes/webapp_routes.py — FastAPI router with 2 routes (serve HTML + proxy attributes)
3. bot/handlers/product_handler.py — Modified _load_attributes_and_ask_form() function
4. bot/handlers/product_handler.py — New handle_webapp_data() handler function
5. Integration instructions — How to register the new handler in the ConversationHandler

Each file must be complete, production-ready, and include professional inline comments.
```

---

## خامساً: كيفية الاستخدام

1. انسخ الـ prompt كاملاً
2. أرسله لـ Claude أو Gemini مع إرفاق ملف `product_handler.py` الحالي
3. سيُنتج الكود الكامل جاهزاً للتنفيذ
