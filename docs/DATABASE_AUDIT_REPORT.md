# تقرير تدقيق قاعدة البيانات - TurkTextileHub
**التاريخ:** 27 فبراير 2026  
**المُعِد:** مراجعة تقنية شاملة

---

## ملخص تنفيذي

بعد مراجعة شاملة لجميع نقاط تفاعل الكود مع Supabase، تم اكتشاف **4 مشاكل حرجة** و**3 مخاطر محتملة** تحتاج إلى معالجة فورية قبل الإطلاق.

---

## المشاكل الحرجة (يجب إصلاحها الآن)

### المشكلة 1: أعمدة مفقودة في `bot_registrations`
**الخطورة:** عالية - يمنع تسجيل الموردين بالكامل

| العمود المطلوب | النوع | السبب |
|---|---|---|
| `city` | TEXT | سؤال المدينة الجديد |
| `sales_telegram_id` | TEXT | موظف المبيعات |

**الحل:**
```sql
ALTER TABLE bot_registrations
ADD COLUMN IF NOT EXISTS city TEXT,
ADD COLUMN IF NOT EXISTS sales_telegram_id TEXT;
```

---

### المشكلة 2: عمود مفقود في `bot_trader_registrations`
**الخطورة:** عالية - يمنع اكتمال تسجيل التجار

| العمود المطلوب | النوع | السبب |
|---|---|---|
| `business_type` | TEXT | نوع النشاط التجاري |

**الحل:**
```sql
ALTER TABLE bot_trader_registrations
ADD COLUMN IF NOT EXISTS business_type TEXT;
```

---

### المشكلة 3: تعارض اسم العمود في جدول `suppliers`
**الخطورة:** عالية - يمنع عمل `/add_product` بالكامل

الكود يبحث عن المورد بـ `user_id`:
```python
# database_service.py السطر 124
url = f"{SUPABASE_URL}/rest/v1/suppliers?user_id=eq.{telegram_id}"
```

لكن جدول `bot_registrations` يستخدم `telegram_id` وليس `user_id`.  
**النتيجة:** `/add_product` لن يجد المورد أبداً وسيرفض كل الموردين.

**الحل الأول (موصى به):** إنشاء View في Supabase يربط الجدولين:
```sql
CREATE OR REPLACE VIEW suppliers AS
SELECT 
    id,
    telegram_id AS user_id,
    company_name,
    city,
    phone,
    status,
    created_at
FROM bot_registrations;
```

**الحل الثاني:** تعديل الكود ليستخدم `telegram_id` بدلاً من `user_id`:
```python
url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id,company_name"
```

---

### المشكلة 4: جدول `products` غير موجود
**الخطورة:** عالية - يمنع إضافة وتصفح المنتجات

**الحل:**
```sql
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL,
    category TEXT NOT NULL,
    price TEXT,
    images TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## المخاطر المحتملة (تحتاج انتباهاً)

### الخطر 1: لا يوجد تحقق من صحة رقم الهاتف
الكود يقبل أي نص كرقم هاتف دون التحقق من الصيغة. يمكن أن يُدخل المستخدم نصاً عشوائياً.

**التوصية:** إضافة regex بسيط في المرحلة القادمة:
```python
import re
if not re.match(r'^\+?[0-9]{8,15}$', phone):
    # طلب إعادة الإدخال
```

---

### الخطر 2: الصور تُحفظ كـ file_id فقط
`file_id` في تليجرام **مؤقت** - قد يتغير بعد فترة وتصبح الصور غير قابلة للعرض.

**التوصية:** في مرحلة لاحقة، رفع الصور إلى Supabase Storage أو S3 وحفظ الرابط الدائم.

---

### الخطر 3: لا يوجد Rate Limiting
مستخدم يمكنه إرسال آلاف الرسائل في ثانية واحدة مما قد يُبطئ البوت.

**التوصية:** إضافة حد أدنى بسيط في المرحلة القادمة.

---

## أمر SQL الشامل (نفّذه دفعة واحدة)

```sql
-- ===== إصلاح جميع المشاكل الحرجة =====

-- 1. إضافة أعمدة الموردين
ALTER TABLE bot_registrations
ADD COLUMN IF NOT EXISTS city TEXT,
ADD COLUMN IF NOT EXISTS sales_telegram_id TEXT;

-- 2. إضافة عمود نوع النشاط للتجار
ALTER TABLE bot_trader_registrations
ADD COLUMN IF NOT EXISTS business_type TEXT;

-- 3. إنشاء جدول المنتجات
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL,
    category TEXT NOT NULL,
    price TEXT,
    images TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. إصلاح مشكلة user_id في database_service
-- (يتطلب تعديل الكود - انظر المشكلة 3 أعلاه)
```

---

## الإجراء الموصى به

| الأولوية | الإجراء | الوقت المقدر |
|---|---|---|
| **فوري** | تنفيذ أمر SQL الشامل في Supabase | 2 دقيقة |
| **فوري** | إصلاح `user_id` → `telegram_id` في الكود | 5 دقائق |
| **قريباً** | إضافة التحقق من رقم الهاتف | مرحلة 7 |
| **مستقبلاً** | رفع الصور إلى Storage دائم | مرحلة 8+ |
