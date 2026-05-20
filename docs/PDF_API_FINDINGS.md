# نتائج مراجعة PDF الرسمي — KAYISOFT API

## بنية POST api/seller/products (الصحيحة 100%)

### Request Body:
```json
{
  "name": "iPhone 15 Pro",
  "product_no": "APL-IP15P",
  "category_id": "8de4c9fd-61a4-4c0b-bf88-0ed3a0fe3fa2",
  "shared_attributes": {
    "condition": ["ccb64c69-6949-4893-8381-224f87850678"],
    "brand": ["550e8400-e29b-41d4-a716-446655440000"]
  },
  "variants": [
    {
      "stock_id": "IP15P-BLK-256",
      "stock_count": 12,
      "visibility_status": "public",
      "tax_percentage": 18,
      "cost_price": 950,
      "selector_attributes": {
        "size": ["550e8400-e29b-41d4-a716-446655440001"],
        "color": ["550e8400-e29b-41d4-a716-446655440002"]
      },
      "images": ["2026-05-09T12:19:58.587Z-136a82a872029fda805f78fa313f8d0c386358871d180cef3346ba1b804bb7d9"],
      "videos": [],
      "prices": [
        {
          "min_quantity": 1,
          "price": 1299.99
        }
      ],
      "titles": [
        {
          "language": "en",
          "text": "iPhone 15 Pro 256GB Black"
        }
      ],
      "descriptions": [
        {
          "language": "en",
          "text": "Apple iPhone 15 Pro with 256GB storage."
        }
      ],
      "dimensions": {
        "length": 14.7,
        "width": 7.1,
        "height": 0.8,
        "weight": 0.19
      }
    }
  ]
}
```

## ملاحظات مهمة جداً:

### 1. currency — موقعه الصحيح:
- **في Request Body**: `currency` ليس موجوداً أبداً في variant
- **في Response**: `currency` يظهر في variant كـ response field فقط (يُعاد من الـ API)
- **الخلاصة**: يجب حذف `"currency": "TRY"` من الـ variant في Request تماماً

### 2. selector_attributes:
- dict حيث key = attribute.key (مثل "size", "color")
- value = array of option UUIDs
- **لا يجب إرسال key فارغ**: إذا كان الـ array فارغاً، احذف الـ key كلياً

### 3. shared_attributes:
- dict حيث key = attribute.key
- value يعتمد على نوع الـ attribute:
  - fixed value: string/numeric/boolean/date
  - attributes with options: array of option UUIDs

### 4. images:
- يجب أن تحتوي على filenames المرفوعة (من signed-urls response)
- format: `<ISO-8601 timestamp>-<SHA-256 hash>`

### 5. signed-urls endpoint:
- `POST api/extensions/signed-urls` (بدون شرطة — "signed-urls" وليس "signed_urls")
- Request: `{"operation": "put_product_variant_media", "file_names": [...], "category_id": "..."}`
- Response: `[{"fileName": "...", "url": "..."}]`

### 6. ملاحظة مهمة من PDF:
- لا يجب على البوت ترجمة حقول title و description — الترجمة تتم من Backend Service
- يجب استخدام DeepSeek API لجميع عمليات الذكاء الاصطناعي

### 7. الحقول الافتراضية للـ variant:
- stock_count: 100 (default)
- visibility_status: "public"
- tax_percentage: null
- cost_price: null
- dimensions: null
