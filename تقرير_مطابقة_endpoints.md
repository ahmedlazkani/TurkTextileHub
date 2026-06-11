# تقرير مطابقة ملف Endpoints مع كود البوت
**التاريخ:** 2026-06-11  
**المرجع:** TelegramBackendEndpoints(3).pdf  
**المشروع:** TurkTextileHub / TopKap Bot

---

## ملخص تنفيذي

| الحالة | العدد |
|--------|-------|
| ✅ يعمل بشكل صحيح | 7 |
| 🔴 مفقود / يحتاج تنفيذ | 2 |
| 🟡 يعمل جزئياً / يحتاج تحسين | 3 |

---

## أولاً: ما يعمل بشكل صحيح ✅

### 1. Headers الإلزامية
**المطلوب في الملف:**
```
Telegram-User-Id, Authorization: Bearer {token}, Platform: telegram, Accept-Language
```
**الحالة في الكود:** ✅ مُطبَّق بالكامل في `kayisoft_api.py` → `_headers()`

---

### 2. ربط الحساب (Connect)
**Endpoint:** `POST api/seller/telegram-bot/connect`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `connect_account()` + `start_handler.py`

---

### 3. تسجيل القناة (Create Channel)
**Endpoint:** `POST api/seller/telegram-bot/create-channel`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `create_channel()` + `channel_handler.py`

---

### 4. جلب التصنيفات (Categories)
**Endpoint:** `GET api/seller/categories?parent={id}`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `get_categories()` + `product_handler.py`

---

### 5. جلب خصائص الفئة (Attributes)
**Endpoint:** `GET api/seller/categories/{id}/attributes`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `get_attributes()` + `product_handler.py`

---

### 6. رفع الصور (Signed URLs)
**Endpoint:** `POST extensions/signed-urls`  
**المطلوب:** `operation: put_product_variant_media`, `file_names[]`, `category_id`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `get_signed_urls()`

---

### 7. نشر المنتج (Create Product)
**Endpoint:** `POST api/seller/products`  
**الحالة:** ✅ مُطبَّق في `kayisoft_api.py` → `create_product()` + `product_handler.py`  
**الهيكل:** name, product_no, category_id, shared_attributes, variants[] — كلها موجودة

---

## ثانياً: التعديلات البرتقالية الجديدة 🔴 (مفقودة — يجب تنفيذها)

### 🔴 التعديل 1: استخدام share_links من response في أزرار المنشور

**ما يقوله الملف (برتقالي):**
> "عند نجاح إضافة المنتج يرجع في الـ Response الـ Deep links التي سيستخدمها الـ Bot في أزرار المحادثة مع المورد وعرض المنتج الموجودين في المنشور الذي سينشره الـ Bot في قناة الـ Telegram"

**شكل الـ Response:**
```json
{
  "variants": [
    {
      "id": "variant-uuid",
      "share_links": {
        "details": "https://kayisoft.dynalinks.app/topgate/product-variant?id={variant_id}",
        "chat":    "https://kayisoft.dynalinks.app/topgate/start-chat-variant?id={variant_id}"
      }
    }
  ]
}
```

**الوضع الحالي في الكود:**
- البوت يستخرج فقط `product_id` و`seller_id` من الـ response
- أزرار المنشور تستخدم روابط قديمة مبنية يدوياً:
  - `https://topgate.app/product/{product_id}?supplier={supplier_id}&action=chat`
  - `https://topgate.app/supplier/{supplier_id}`

**المطلوب:**
1. استخراج `share_links` من أول variant في الـ response
2. استخدام `share_links.chat` لزر "تواصل عبر TopGate"
3. استخدام `share_links.details` لزر "عرض المنتج"
4. إذا لم تكن `share_links` موجودة → الرجوع للروابط القديمة كـ fallback

---

### 🔴 التعديل 2: تغيير نص زر "صفحة المورد" إلى "عرض المنتج"

**الوضع الحالي:**
```
زر 1: 💬 تواصل عبر TopGate  → _product_chat_url()
زر 2: 🛍️ صفحة المورد على TopGate → _supplier_page_url()
```

**المطلوب حسب الملف:**
```
زر 1: 💬 تواصل مع المورد  → share_links.chat
زر 2: 🛍️ عرض المنتج       → share_links.details
```

---

## ثالثاً: ما يعمل جزئياً 🟡 (يحتاج تحسين)

### 🟡 1. attrs_list للـ AI — الخصائص تُرسل كـ UUID بدلاً من اسم
**المشكلة:** `shared_attributes` تُرسل `option_id` (UUID) بدلاً من اسم الخيار للـ AI  
**السبب:** البحث عن `opt.get("id") == opt_id` لا يُطابق في بعض الحالات  
**التأثير:** البوست يكتب "غير محدد" للقماش والمقاس  
**الحالة:** تم تطبيق إصلاح جزئي — يحتاج تحقق

### 🟡 2. لغة البوست — خيارات اللغة في الفورم
**المشكلة:** checkboxes اللغة موجودة في الـ HTML لكنها مخفية  
**المطلوب:** إظهارها كـ UI واضح في أسفل الفورم  
**الحالة:** تم تطبيق إصلاح — يحتاج تحقق

### 🟡 3. titles و descriptions — يُرسل نص واحد بدلاً من array
**المطلوب حسب الملف:**
```json
"titles": [{"language": "ar", "text": "اسم المنتج"}]
"descriptions": [{"language": "ar", "text": "وصف المنتج"}]
```
**الوضع الحالي:** يُرسل كـ string مباشر أو array — يحتاج تحقق من الكود

---

## رابعاً: قائمة التنفيذ المطلوبة (مرتبة بالأولوية)

| الأولوية | المهمة | الملف المعني |
|----------|--------|--------------|
| 🔴 عالية | استخراج `share_links` من response وتمريرها لـ `_publish_to_channel` | `product_handler.py` |
| 🔴 عالية | تحديث `_build_channel_post` لاستخدام `share_links.chat` و`share_links.details` | `product_handler.py` |
| 🟡 متوسطة | إصلاح attrs_list للـ AI (UUID → اسم الخيار) | `product_handler.py` |
| 🟡 متوسطة | إظهار خيارات اللغة في الفورم | `product_form.html` |
| 🟡 منخفضة | التحقق من شكل titles/descriptions في payload | `product_handler.py` |

---

## الخلاصة

**التعديل الأهم والوحيد الجديد من الملف (البرتقالي):**  
استخدام `share_links` الواردة في response من `POST api/seller/products` بدلاً من بناء الروابط يدوياً. هذا يضمن أن أزرار المنشور تفتح الصفحة الصحيحة لكل variant بشكل مباشر.

**باقي الـ endpoints:** كلها مُطبَّقة بشكل صحيح في الكود الحالي.
