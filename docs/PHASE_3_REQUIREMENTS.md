# مواصفات المرحلة الثالثة: ربط قاعدة البيانات Supabase

## السياق

هيكل جدول `suppliers` الموجود فعلاً في Supabase (لا تُنشئ جدولاً جديداً):

| العمود | النوع | الوصف |
|---|---|---|
| `id` | uuid | مفتاح أساسي (تلقائي) |
| `user_id` | uuid | معرّف المستخدم (سنستخدمه لـ telegram_id) |
| `business_name` | varchar | اسم الشركة بالعربية |
| `business_name_tr` | varchar | اسم الشركة بالتركية (اختياري) |
| `city` | varchar | المدينة (اختياري) |
| `country` | varchar | الدولة (اختياري) |
| `whatsapp` | varchar | رقم الواتساب/الهاتف |
| `email` | varchar | البريد الإلكتروني (اختياري) |
| `description` | varchar | وصف الشركة (اختياري) |
| `verification_status` | varchar | حالة التحقق |
| `reputation_score` | integer | نقاط السمعة |
| `total_products` | integer | عدد المنتجات |
| `total_rfqs` | integer | عدد طلبات الأسعار |
| `created_at` | timestamp | تاريخ الإنشاء (تلقائي) |
| `updated_at` | timestamp | تاريخ التحديث (تلقائي) |

**ملاحظة:** لا يوجد عمود `telegram_id` منفصل. سنستخدم `user_id` لحفظ معرّف تليجرام كنص.

---

## الملفات المطلوب إنشاؤها في هذه المرحلة

### 1. `bot/services/database_service.py` (ملف جديد)

**الوظيفة:** خدمة قاعدة البيانات - التواصل مع Supabase عبر HTTP REST API مباشرة (بدون أي مكتبة خارجية إضافية، فقط `requests`).

**المتطلبات التفصيلية:**

#### الثوابت والإعداد:
```python
import requests
import logging
from bot.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

# رأس الطلبات المشتركة لجميع الاتصالات بـ Supabase
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}
```

#### الدوال المطلوبة:

**أ. `save_supplier(supplier_data: dict) -> bool`**
- نوع: دالة عادية (ليست async)
- تستقبل قاموساً يحتوي على بيانات المورد
- تُرسل طلب POST إلى `/rest/v1/suppliers`
- البيانات التي تُرسل إلى Supabase:
  ```python
  {
      "user_id": supplier_data.get("telegram_id"),   # نحفظ telegram_id في user_id
      "business_name": supplier_data.get("company_name"),
      "whatsapp": supplier_data.get("phone"),
      "verification_status": "pending",
      "reputation_score": 0,
      "total_products": 0,
      "total_rfqs": 0,
  }
  ```
- إذا كان رمز الاستجابة `201` → تُرجع `True` وتسجل رسالة نجاح
- إذا كان أي رمز آخر → تُرجع `False` وتسجل رسالة خطأ مع تفاصيل الاستجابة
- تعالج استثناءات `requests.exceptions.RequestException` وتُرجع `False`

**ب. `check_supplier_exists(telegram_id: str) -> bool`**
- نوع: دالة عادية (ليست async)
- تُرسل طلب GET إلى `/rest/v1/suppliers?user_id=eq.{telegram_id}&select=id`
- إذا كانت النتيجة قائمة غير فارغة → تُرجع `True`
- إذا كانت فارغة أو حدث خطأ → تُرجع `False`

---

### 2. تعديل `bot/handlers/supplier_handler.py` (تعديل على الملف الموجود)

**التعديل الوحيد المطلوب:** في دالة `received_phone` فقط.

**استبدل هذا الكود:**
```python
# طباعة البيانات في السجلات (مؤقتاً بدلاً من حفظها في قاعدة البيانات)
logger.info("📋 بيانات مورد جديد: %s", supplier_data)

# إرسال رسالة نجاح التسجيل للمستخدم
await update.message.reply_text(
    text=get_string(lang, "registration_success")
)
```

**بهذا الكود:**
```python
# استيراد خدمة قاعدة البيانات (يُضاف في أعلى الملف مع بقية الاستيرادات)
from bot.services import database_service

# التحقق أولاً إذا كان المورد مسجلاً مسبقاً
already_exists = database_service.check_supplier_exists(supplier_data["telegram_id"])

if already_exists:
    # إرسال رسالة أن المورد مسجل مسبقاً
    await update.message.reply_text(
        text=get_string(lang, "already_registered")
    )
else:
    # حفظ بيانات المورد في قاعدة البيانات
    success = database_service.save_supplier(supplier_data)
    
    if success:
        logger.info("✅ تم حفظ بيانات المورد بنجاح: telegram_id=%s", supplier_data["telegram_id"])
        await update.message.reply_text(
            text=get_string(lang, "registration_success")
        )
    else:
        logger.error("❌ فشل حفظ بيانات المورد: telegram_id=%s", supplier_data["telegram_id"])
        await update.message.reply_text(
            text=get_string(lang, "error_general")
        )
```

**ملاحظة:** أضف `from bot.services import database_service` في أعلى الملف مع بقية الاستيرادات.

---

### 3. تعديل ملفات الترجمة (إضافة مفتاح جديد)

أضف المفتاح `"already_registered"` لجميع ملفات الترجمة الثلاثة:

**`bot/translations/ar.json`** - أضف:
```json
"already_registered": "⚠️ أنت مسجل بالفعل كمورد في منصتنا."
```

**`bot/translations/tr.json`** - أضف:
```json
"already_registered": "⚠️ Zaten platformumuzda tedarikçi olarak kayıtlısınız."
```

**`bot/translations/en.json`** - أضف:
```json
"already_registered": "⚠️ You are already registered as a supplier on our platform."
```

---

## ملاحظات مهمة للمبرمج

1. **لا تستخدم `supabase-py`** - استخدم `requests` فقط للتواصل مع Supabase REST API
2. **`save_supplier` و `check_supplier_exists` ليستا async** - يتم استدعاؤهما من داخل دوال async لكنهما أنفسهما عاديتان
3. **لا تُنشئ جدولاً جديداً** - الجدول موجود بالفعل
4. **عمود `user_id`** هو الذي نستخدمه لحفظ `telegram_id` (كنص وليس UUID حقيقي)
5. **تأكد من معالجة الأخطاء** في جميع طلبات HTTP

---

## النتيجة المتوقعة

بعد تنفيذ هذه المرحلة:
1. عند إكمال المورد تسجيله → تُحفظ بياناته فعلياً في Supabase
2. إذا حاول نفس المستخدم التسجيل مرة ثانية → يظهر له رسالة "مسجل مسبقاً"
3. يمكن رؤية البيانات في لوحة Supabase تحت جدول `suppliers`

---

## الملفات التي يجب تسليمها

1. `bot/services/database_service.py` (ملف جديد كامل)
2. `bot/handlers/supplier_handler.py` (الملف المعدّل كاملاً)
3. `bot/translations/ar.json` (الملف المعدّل كاملاً)
4. `bot/translations/tr.json` (الملف المعدّل كاملاً)
5. `bot/translations/en.json` (الملف المعدّل كاملاً)

---

*هذا الملف أعده مساعد الذكاء الاصطناعي لإدارة المشروع. يُرجى تسليم الكود المنتج في ملفات منفصلة.*
