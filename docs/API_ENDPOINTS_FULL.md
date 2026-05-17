# KAYISOFT API Endpoints — Full Documentation

## 1. Connect Seller Account
**POST** `api/seller/telegram-bot/connect`

Request Body:
```json
{
  "token": "string",           // from deep link
  "telegram_user_id": "string",
  "telegram_user_name": "string"  // optional
}
```
Response: Success 200 or error 422, 500

---

## 2. Create Channel
**POST** `api/seller/telegram-bot/create-channel`

Request Body:
```json
{
  "channel_id": "string",
  "telegram_user_id": "string",
  "channel_name": "string"
}
```
Response: Success 200 or error 422, 500

---

## 3. Get Categories
**GET** `api/seller/categories`

Query Parameters:
- `parent`: string or empty string — Pass "" for root categories, or category_id for subcategories

Response: list of categories
```json
[{
  "id": "uuid",
  "name": "string",
  "selected_image": "string",
  "unselected_image": "string",
  "parent": null,
  "ui_order": 0,
  "visible": true,
  "home_image": "string",
  "is_visible_for_browsing": true,
  "is_visible_for_creating": true,
  "minimum_required_images": 0,
  "maximum_images": 0,
  "maximum_videos": 0
}]
```

---

## 4. Get Attributes for Leaf Category
**GET** `api/seller/categories/{id}/attributes`

Response: list of attributes with options
```json
[{
  "id": "uuid",
  "key": "storage",
  "ui_type": "numeric",
  "name": "Storage",
  "description": "...",
  "is_variant_selector": true,
  "variant_meta": {"title": "string", "description": "string"},
  "ui_order": 0,
  "required": true,
  "default_value": "128",
  "default_option_id": "uuid",
  "is_primary_variant_attribute": true,
  "options": [{
    "id": "uuid",
    "value": "128 GB",
    "is_default": true
  }]
}]
```

**Form static fields:**
- `name`: user enters it
- `product_no`: Auto-generated unique friendly id
- `stock_id`: Auto-generated unique friendly id
- `stock_count`: default 100
- `visibility_status`: default "public"
- `tax_percentage`: default null
- `cost_price`: default null
- `prices`: `[{"min_quantity": 1, "price": 1299.99}]`
- `titles`: `[{"language": "en", "text": "..."}]` — ONE language only, backend translates
- `descriptions`: `[{"language": "en", "text": "..."}]` — ONE language only
- `dimensions`: default null

---

## 5. Get Signed URLs for Media Upload
**POST** `api/extensions/signed-urls`

Request Body:
```json
{
  "operation": "put_product_variant_media",
  "file_names": ["<ISO-8601 timestamp>-<SHA-256 hash>"],
  "category_id": "uuid"
}
```

File name format: `2026-05-09T12:19:58.587Z-136a82a872029fda805f78fa313f8d0c38635887...`

Response:
```json
[{
  "fileName": "...",
  "url": "https://storage.example.com/upload/abc123"
}]
```

---

## 6. Post Product
**POST** `api/seller/products`

Request Body:
```json
{
  "name": "iPhone 15 Pro",
  "product_no": "APL-IP15P",
  "category_id": "uuid",
  "shared_attributes": {
    "condition": ["option-uuid"],
    "brand": ["option-uuid"]
  },
  "variants": [{
    "stock_id": "string",
    "stock_count": 100,
    "status": "review",
    "visibility_status": "public",
    "tax_percentage": null,
    "cost_price": null,
    "titles": [{"language": "en", "text": "..."}],
    "descriptions": [{"language": "en", "text": "..."}],
    "selector_attributes": [{"attribute_id": "uuid", "option_id": "uuid"}],
    "prices": [{"min_quantity": 1, "price": 1299.99}],
    "images": ["filename1", "filename2"],
    "videos": [],
    "currency": "TRY",
    "dimensions": null
  }]
}
```

Response: The posted product with full details

---

## Bot Workflow (Arabic from PDF)

1. **ربط الحساب**: البائع يضغط زر الربط في التطبيق → يُولَّد رابط خاص → يفتح البوت → البوت يستخلص الـ Token → يستدعي POST api/seller/telegram-bot/connect → عند النجاح يُؤكَّد للبائع

2. **إضافة البوت كمسؤول في القناة**: بعد نجاح الربط

3. **تسجيل القناة**: البوت يُبلغ السيرفر بالقناة → POST api/seller/telegram-bot/create-channel

4. **بدء إضافة منتج**: البائع يضغط "إضافة منتج" → البوت يعرض الفئات الأساسية (GET api/seller/categories) → اختيار فئة أساسية → عرض الفئات الفرعية → اختيار الفئة الفرعية → عرض نموذج البيانات

5. **تعبئة بيانات المنتج**: البائع يُدخل المعلومات → البوت يستخدم DeepSeek AI لتحليل البيانات والتحقق منها واستنتاج الـ Options المناسبة

6. **مراجعة البيانات**: إذا ناقصة → طلب استكمال. إذا مكتملة → عرض ملخص نهائي وطلب تأكيد

7. **رفع صور المنتج**: طلب الصور من البائع

8. **إنشاء الـ Variants**: تلقائياً — تشكيل الـ Variants، تعبئة الحقول الناقصة بالـ Default values، توزيع الصور، عرض النتيجة للتأكيد

9. **رفع الصور وإضافة المنتج**: 
   - رفع الصور: POST api/extensions/signed-urls
   - إضافة المنتج: POST api/seller/products
   - نشر تلقائي على قناة Telegram الخاصة بالبائع

## Additional Notes
1. قابلية النقل — يجب تجنب أي اعتماد مباشر على بيئة محلية
2. استخدام DeepSeek API في جميع عمليات الذكاء الاصطناعي
3. البوت لا يترجم title و description — الترجمة تتم من Backend Service
