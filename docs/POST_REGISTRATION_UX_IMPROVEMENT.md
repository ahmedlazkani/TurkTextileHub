# متطلبات تحسين تجربة ما بعد التسجيل

**تاريخ:** 27 فبراير 2026

## 1. الهدف

تحسين تجربة المستخدم بعد إكمال التسجيل كمورد أو تاجر، من خلال توجيهه مباشرة لخطوات مفيدة ومحفزة بدلاً من تركه في فراغ.

## 2. المتطلبات الفنية

### أ. تعديل رسالة نجاح تسجيل المورد

**الملف:** `bot/handlers/supplier_handler.py`

**الدالة:** `_finish_supplier_registration`

**التغيير:**
1.  تغيير نص `registration_success` في ملفات الترجمة (ar.json, en.json, tr.json) ليصبح:
    *   **ar:** "✅ تم تسجيلك كمورد بنجاح!\n\n📦 الخطوة التالية: أضف منتجاتك الآن!"
    *   **en:** "✅ You have been successfully registered as a supplier!\n\n📦 Next step: Add your products now!"
    *   **tr:** "✅ Tedarikçi olarak başarıyla kaydoldunuz!\n\n📦 Sonraki adım: Ürünlerinizi şimdi ekleyin!"
2.  إضافة لوحة مفاتيح `InlineKeyboardMarkup` لرسالة النجاح تحتوي على زر واحد:
    *   **النص:** `➕ إضافة منتج الآن` (من ملف الترجمة)
    *   **callback_data:** `add_product_now`

### ب. تعديل رسالة نجاح تسجيل التاجر

**الملف:** `bot/handlers/trader_handler.py`

**الدالة:** `received_trader_business_type`

**التغيير:**
1.  تغيير نص `trader_success` في ملفات الترجمة ليصبح:
    *   **ar:** "✅ تم تسجيلك كتاجر بنجاح!\n\n🎯 ماذا يمكنك فعله الآن؟"
    *   **en:** "✅ You have been successfully registered as a trader!\n\n🎯 What can you do now?"
    *   **tr:** "✅ Tüccar olarak başarıyla kaydoldunuz!\n\n🎯 Şimdi ne yapabilirsiniz?"
2.  تغيير لوحة المفاتيح `InlineKeyboardMarkup` الحالية لتتضمن الأزرار التالية:
    *   **الزر 1:**
        *   **النص:** `🔍 تصفح المنتجات` (من ملف الترجمة)
        *   **callback_data:** `browse_products_now`
    *   **الزر 2:**
        *   **النص:** `📞 تواصل مع مورد` (من ملف الترجمة)
        *   **callback_data:** `contact_supplier`
    *   **الزر 3:**
        *   **النص:** `⭐ المنتجات المميزة` (من ملف الترجمة)
        *   **callback_data:** `featured_products`

### ج. إضافة معالجات للأزرار الجديدة

**الملف:** `bot/main.py`

**التغيير:**
1.  إضافة `CallbackQueryHandler` جديد في `main` function (خارج أي `ConversationHandler`) لمعالجة الأزرار الجديدة:
    *   `add_product_now`: يستدعي دالة `start_product_registration` من `product_handler`.
    *   `browse_products_now`: يستدعي دالة `start_browsing` من `browse_handler`.
    *   `contact_supplier` و `featured_products`: حالياً، فقط أرسل رسالة "قيد الإنشاء" (سيتم بناؤها في مرحلة لاحقة).

## 3. ملفات الترجمة (JSON)

يجب إضافة المفاتيح الجديدة التالية لملفات `ar.json`, `en.json`, `tr.json` مع ترجمتها المناسبة:

*   `add_product_now_btn`
*   `browse_products_btn`
*   `contact_supplier_btn`
*   `featured_products_btn`
*   `coming_soon`

