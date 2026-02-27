
# متطلبات المرحلة السادسة: إعادة الهيكلة وإدارة المنتجات

**المستند:** `PHASE_6_REQUIREMENTS.md`
**الإصدار:** 1.0
**التاريخ:** 27 فبراير 2026

## 1. الهدف الأساسي

إعادة هيكلة قاعدة الكود لتكون قابلة للتوسع، إكمال تدفقات تسجيل المستخدمين حسب الوثيقة، وبناء الميزات الأساسية لإدارة المنتجات (الإضافة والتصفح).

---

## 2. الهيكل الجديد للملفات (New File Structure)

يجب إعادة تنظيم الملفات لتصبح بالشكل التالي. هذا يتطلب نقل بعض الوظائف وإنشاء ملفات جديدة.

```
bot/
├── __init__.py
├── config.py
├── main.py
├── states.py
|
├── handlers/
│   ├── __init__.py
│   ├── admin_handler.py      # (فارغ حالياً، للمستقبل)
│   ├── browse_handler.py     # (جديد) تصفح المنتجات
│   ├── product_handler.py    # (جديد) إضافة وتعديل المنتجات
│   ├── start_handler.py      # (مُعدّل) إصلاح رسالة الترحيب
│   ├── supplier_handler.py   # (مُعدّل) تسجيل المورد فقط
│   └── trader_handler.py     # (مُعدّل) تسجيل التاجر فقط
|
├── services/
│   ├── __init__.py
│   ├── database_service.py   # (مُعدّل) إضافة دوال المنتجات
│   ├── language_service.py   # (مُعدّل) إضافة نصوص جديدة
│   └── notification_service.py # (لا تغيير)
|
└── translations/
    ├── ar.json               # (مُعدّل) نصوص جديدة
    ├── en.json               # (مُعدّل) نصوص جديدة
    └── tr.json               # (مُعدّل) نصوص جديدة
```

---

## 3. تحديثات قاعدة البيانات (Supabase Schema)

يجب تنفيذ أوامر SQL التالية في Supabase لإضافة الجداول والحقول الجديدة.

### 3.1. جدول المنتجات الجديد: `products`

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    price TEXT,
    images TEXT[] NOT NULL, -- مصفوفة من file_id الخاص بالصور
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- تفعيل RLS
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

-- سياسة: المورد يرى منتجاته فقط
CREATE POLICY "Suppliers can view their own products" ON products
FOR SELECT USING (supplier_id = (SELECT id FROM suppliers WHERE user_id = auth.uid()));

-- سياسة: المورد يضيف منتجات لنفسه فقط
CREATE POLICY "Suppliers can insert their own products" ON products
FOR INSERT WITH CHECK (supplier_id = (SELECT id FROM suppliers WHERE user_id = auth.uid()));

-- سياسة: السماح للجميع برؤية المنتجات النشطة
CREATE POLICY "Public can view active products" ON products
FOR SELECT USING (is_active = true);
```

### 3.2. تحديث جدول الموردين: `suppliers`

إضافة حقل `city` و `sales_telegram_id`.

```sql
ALTER TABLE suppliers
ADD COLUMN city TEXT,
ADD COLUMN sales_telegram_id BIGINT;
```

---

## 4. تعديلات على التدفقات الحالية

### 4.1. إصلاح رسالة الترحيب (`start_handler.py`)

**المشكلة:** رسالة الترحيب الحالية تعرض `"اختر دورك:"` كنص منفصل، مما يسبب ارتباكاً في الواجهة.

**الحل:** يجب دمج النص مع الأزرار في رسالة واحدة باستخدام `reply_markup`.

**الكود الحالي (خاطئ):**
```python
await update.message.reply_text(get_string("welcome", lang))
await update.message.reply_text(get_string("role_selection", lang), reply_markup=keyboard)
```

**الكود المطلوب (صحيح):**
```python
# رسالة واحدة فقط تجمع النص والأزرار
welcome_message = get_string("welcome", lang) + "\n\n" + get_string("role_selection", lang)
await update.message.reply_text(welcome_message, reply_markup=keyboard)
```

### 4.2. إكمال تسجيل المورد (`supplier_handler.py`)

يجب تعديل تدفق تسجيل المورد ليشمل سؤالين إضافيين حسب وثيقة المواصفات:

1.  **المدينة (City):** بعد سؤال "اسم المسؤول"، يجب سؤال المورد عن مدينته مع أزرار.
2.  **موظف المبيعات (Sales Rep):** بعد سؤال "الهاتف"، يجب سؤال المورد إذا كان لديه موظف مبيعات مخصص.

**التدفق الجديد:**
1.  `ask_company_name` (لا تغيير)
2.  `ask_contact_name` (لا تغيير)
3.  `ask_city` **(جديد):**
    *   النص: `"في أي مدينة يقع متجرك؟"`
    *   الأزرار: `[إسطنبول]`, `[بورصة]`, `[إزمير]`, `[أخرى]`
4.  `ask_phone` (لا تغيير)
5.  `ask_sales_rep` **(جديد):**
    *   النص: `"هل لديك موظف مبيعات مخصص لاستقبال الطلبات؟"`
    *   الأزرار: `[نعم، لدي]`, `[لا، سأستقبلها أنا]`
6.  `ask_sales_rep_username` **(جديد، فقط إذا كانت الإجابة "نعم"):**
    *   النص: `"أدخل يوزرنيم تليجرام الخاص به (مثال: @username)"`
7.  `finish_supplier_registration` (مُعدّل): يجب أن يحفظ الحقول الجديدة (`city`, `sales_telegram_id`) في قاعدة البيانات.

### 4.3. إكمال تسجيل التاجر (`trader_handler.py`)

**المشكلة:** السؤال الحالي هو "ما نوع المنتجات التي تهتم بها؟"، بينما الوثيقة تطلب "ما نوع نشاطك التجاري؟".

**الحل:** يجب تغيير السؤال والأزرار.

**التدفق الجديد:**
1.  `ask_trader_name` (لا تغيير)
2.  `ask_trader_phone` (لا تغيير)
3.  `ask_trader_country` (لا تغيير)
4.  `ask_business_type` **(تعديل كامل):**
    *   النص: `"ما هو نوع نشاطك التجاري؟"`
    *   الأزرار: `[متجر إلكتروني]`, `[محل ملابس]`, `[موزع]`, `[أخرى]`
5.  `finish_trader_registration` (مُعدّل): يجب أن يحفظ `business_type` بدلاً من `product_interest`.

---

## 5. الميزات الجديدة (New Features)

### 5.1. إضافة منتج جديد (`product_handler.py`)

هذا تدفق جديد بالكامل يسمح للموردين بإضافة منتجاتهم. يجب أن يكون مرناً وسهلاً.

**الأمر:** `/add_product`

**التدفق:**
1.  **`start_add_product`:**
    *   يستجيب لأمر `/add_product`.
    *   النص: `"لإضافة منتج جديد، أرسل لي صوره (من 1 إلى 5 صور دفعة واحدة)."`
    *   الحالة: `GETTING_IMAGES`

2.  **`get_images`:**
    *   يستقبل رسالة تحتوي على صورة واحدة أو أكثر.
    *   يحفظ `file_id` لكل صورة في `context.user_data['images']`.
    *   النص: `"رائع! الآن اختر فئة المنتج:"`
    *   الأزرار: `[عبايات]`, `[فساتين]`, `[ملابس محجبات]`, `[أطقم]`, `[أخرى]`
    *   الحالة: `GETTING_CATEGORY`

3.  **`get_category`:**
    *   يستقبل اختيار الفئة من الأزرار.
    *   يحفظ الفئة في `context.user_data['category']`.
    *   النص: `"أدخل السعر التقريبي للمنتج (اختياري). يمكنك كتابة نص مثل '10-12 دولار' أو 'حسب الكمية'."`
    *   الأزرار: `[تخطي]`
    *   الحالة: `GETTING_PRICE`

4.  **`get_price` (أو `skip_price`):**
    *   يستقبل نص السعر أو ضغطة زر "تخطي".
    *   يحفظ السعر في `context.user_data['price']`.
    *   **المعاينة:** يعرض للمورد رسالة معاينة تحتوي على:
        *   الصورة الأولى كـ `send_photo`.
        *   النص: `"== معاينة المنتج ==
الفئة: {category}
السعر: {price}

هل تريد نشر هذا المنتج؟"`
    *   الأزرار: `[✅ نعم، انشر الآن]`, `[❌ إلغاء]`
    *   الحالة: `CONFIRM_ADD_PRODUCT`

5.  **`finish_add_product`:**
    *   يستقبل ضغطة زر `✅ نعم، انشر الآن`.
    *   يجمع كل البيانات من `context.user_data`.
    *   يستدعي `database_service.add_product()` لحفظ المنتج في قاعدة البيانات.
    *   النص: `"✅ تم نشر منتجك بنجاح!"`
    *   ينهي المحادثة `ConversationHandler.END`.

### 5.2. تصفح المنتجات (`browse_handler.py`)

تدفق جديد يسمح للمشترين (التجار) بتصفح المنتجات المتاحة.

**الأمر:** `/browse`

**التدفق:**
1.  **`start_browse`:**
    *   يستجيب لأمر `/browse`.
    *   يستدعي `database_service.get_all_categories()` للحصول على الفئات المتاحة.
    *   النص: `"🔍 اختر فئة المنتجات التي تريد تصفحها:"`
    *   الأزرار: قائمة ديناميكية بالفئات المتاحة + زر `[عرض الكل]`.
    *   الحالة: `BROWSING_PRODUCTS`

2.  **`browse_products`:**
    *   يستقبل اختيار الفئة.
    *   يستدعي `database_service.get_products_by_category(category)`.
    *   **عرض المنتجات:** يعرض المنتجات بشكل تفاعلي (Pagination):
        *   يرسل أول منتج كرسالة (صورة + نص).
        *   النص: `الفئة: {category}
السعر: {price}
المورد: {supplier_name}`
        *   الأزرار: `[➡️ التالي]`, `[📋 طلب عرض سعر]`, `[🔙 العودة للفئات]`
    *   يحفظ قائمة المنتجات وفهرس المنتج الحالي في `context.user_data`.

3.  **`next_product` / `prev_product`:**
    *   يستجيب لضغط أزرار التنقل.
    *   يعدل الرسالة الحالية (`edit_message_media`, `edit_message_text`) لعرض المنتج التالي/السابق.

---

## 6. تحديثات ملفات الترجمة (`translations/*.json`)

يجب إضافة النصوص الجديدة المستخدمة في التدفقات أعلاه إلى ملفات الترجمة الثلاثة (ar, en, tr).

**مثال للنصوص الجديدة (بالعربية):**
*   `ask_city`: "في أي مدينة يقع متجرك؟"
*   `ask_sales_rep`: "هل لديك موظف مبيعات مخصص لاستقبال الطلبات؟"
*   `ask_sales_rep_username`: "أدخل يوزرنيم تليجرام الخاص به (مثال: @username)"
*   `ask_business_type`: "ما هو نوع نشاطك التجاري؟"
*   `add_product_start`: "لإضافة منتج جديد، أرسل لي صوره (من 1 إلى 5 صور دفعة واحدة)."
*   `add_product_get_category`: "رائع! الآن اختر فئة المنتج:"
*   `add_product_get_price`: "أدخل السعر التقريبي للمنتج (اختياري). يمكنك كتابة نص مثل '10-12 دولار' أو 'حسب الكمية'."
*   `add_product_confirm`: "== معاينة المنتج ==\nالفئة: {category}\nالسعر: {price}\n\nهل تريد نشر هذا المنتج؟"
*   `add_product_success`: "✅ تم نشر منتجك بنجاح!"
*   `browse_start`: "🔍 اختر فئة المنتجات التي تريد تصفحها:"
