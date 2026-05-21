# PDF API Findings — Images per Variant

## مراجعة PDF الرسمي (TelegramBackendEndpoints.pdf)

### الصفحة 3 — معلومات الفئة:
في response الفئة يوجد:
- `minimum_required_images`: 0
- `maximum_images`: 0
- `maximum_videos`: 0

**ملاحظة:** القيمة `0` تعني "بدون حد" أو "غير محدد" في هذا السياق — الـ API لا يفرض حداً صريحاً على عدد الصور.

### الصفحة 6 — Post Products:
في request body الـ variant:
```json
"images": [
  "2026-05-09T12:19:58.587Z-136a82a872029fda805f78fa313f8d0c386358871d180cef3346ba1b804bb7d9"
]
```
المثال يحتوي على صورة واحدة فقط، لكن هذا مجرد مثال وليس قيداً.

### الصفحة 8 — Response Body:
```json
"images": ["string"],
"videos": ["string"]
```
الـ response يُظهر `images` كـ array — لا يوجد حد مذكور.

### الخلاصة:
**الـ PDF الرسمي لا يذكر أي حد لعدد الصور في الـ variant.**
المشكلة التي لاحظها المستخدم (API يقبل صورة واحدة فقط) قد تكون:
1. قيد في Backend غير موثق
2. أو أن الكود الحالي يرسل صورة واحدة فقط رغم رفع أكثر

**التوصية:** مراجعة `_build_variants` في product_handler.py للتحقق من كيفية إضافة الصور للـ variant.
