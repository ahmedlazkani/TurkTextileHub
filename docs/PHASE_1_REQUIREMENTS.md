# مواصفات المرحلة الأولى: الأساس والبنية التحتية للبوت

## نظرة عامة على المشروع

**اسم المشروع:** TurkTextileHub Bot  
**الغرض:** بوت تليجرام B2B يربط موردي المنسوجات التركية بتجار الجملة  
**الشركة:** KAYISOFT - إسطنبول، تركيا  
**اللغات المدعومة:** العربية (الافتراضية)، التركية، الإنجليزية

---

## هيكل الملفات المطلوب

```
TurkTextileHub/
├── bot/
│   ├── __init__.py              (ملف فارغ)
│   ├── main.py                  (نقطة الدخول الرئيسية)
│   ├── config.py                (إعدادات البوت)
│   ├── states.py                (ثوابت حالات المحادثة)
│   ├── handlers/
│   │   ├── __init__.py          (ملف فارغ)
│   │   └── start_handler.py     (معالج أمر /start)
│   ├── services/
│   │   ├── __init__.py          (ملف فارغ)
│   │   └── language_service.py  (خدمة اللغات)
│   └── translations/
│       ├── ar.json              (الترجمة العربية)
│       ├── tr.json              (الترجمة التركية)
│       └── en.json              (الترجمة الإنجليزية)
├── requirements.txt
├── .env.example
└── README.md
```

---

## المواصفات التفصيلية لكل ملف

### 1. `requirements.txt`
```
python-telegram-bot==20.7
python-dotenv==1.0.0
requests==2.31.0
```

### 2. `.env.example`
```
TELEGRAM_BOT_TOKEN=your_token_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here
```

### 3. `bot/config.py`
يقوم بالتالي:
- تحميل متغيرات البيئة من `.env`
- تعريف ثابت `BOT_TOKEN` يقرأ من `TELEGRAM_BOT_TOKEN`
- تعريف ثابت `SUPABASE_URL` يقرأ من `SUPABASE_URL`
- تعريف ثابت `SUPABASE_KEY` يقرأ من `SUPABASE_KEY`
- إذا كان `BOT_TOKEN` فارغاً، يطرح استثناء `ValueError` مع رسالة واضحة

### 4. `bot/states.py`
يعرّف ثوابت الأعداد الصحيحة لحالات المحادثة:
```python
COMPANY_NAME = 1
CONTACT_NAME = 2
PHONE_NUMBER = 3
```

### 5. `bot/services/language_service.py`
**الوظيفة:** تحميل ملفات الترجمة وإرجاع النصوص المترجمة.

**المتطلبات:**
- دالة `load_translations()` تقرأ ملفات `ar.json`, `tr.json`, `en.json` من مجلد `translations/` وتخزنها في قاموس
- دالة `get_string(lang: str, key: str) -> str` تُرجع النص المترجم للمفتاح المحدد باللغة المحددة
- إذا لم توجد اللغة أو المفتاح، ترجع النص العربي كاحتياطي
- إذا لم يوجد المفتاح في العربية أيضاً، ترجع المفتاح نفسه
- يتم تحميل الترجمات مرة واحدة عند استيراد الوحدة

### 6. ملفات الترجمة

**`bot/translations/ar.json`** (يجب أن يحتوي على المفاتيح التالية):
```json
{
  "welcome": "مرحباً بك في TurkTextileHub 🌟\nمنصة B2B لتجارة المنسوجات التركية",
  "role_selection": "اختر دورك:",
  "supplier": "🏭 مورد",
  "trader": "🛒 تاجر",
  "supplier_registration_start": "ممتاز! سنبدأ تسجيلك كمورد.\nهذا سيستغرق دقيقتين فقط.",
  "prompt_company_name": "ما هو اسم شركتك أو متجرك؟",
  "prompt_contact_name": "ما هو اسم الشخص المسؤول للتواصل؟",
  "prompt_phone": "ما هو رقم هاتفك (مع رمز الدولة)؟\nمثال: +905551234567",
  "registration_success": "✅ تم تسجيلك بنجاح كمورد!\nسنتواصل معك قريباً.",
  "cancel": "تم إلغاء العملية. اكتب /start للبدء من جديد.",
  "trader_coming_soon": "🛒 تسجيل التجار قادم قريباً!",
  "error_general": "حدث خطأ. الرجاء المحاولة مرة أخرى أو كتابة /start"
}
```

**`bot/translations/tr.json`** (نفس المفاتيح بالتركية):
```json
{
  "welcome": "TurkTextileHub'a Hoş Geldiniz 🌟\nTürk tekstil ticareti için B2B platformu",
  "role_selection": "Rolünüzü seçin:",
  "supplier": "🏭 Tedarikçi",
  "trader": "🛒 Tüccar",
  "supplier_registration_start": "Harika! Tedarikçi olarak kaydınızı başlatıyoruz.\nBu sadece iki dakika sürecek.",
  "prompt_company_name": "Şirketinizin veya mağazanızın adı nedir?",
  "prompt_contact_name": "İletişim için sorumlu kişinin adı nedir?",
  "prompt_phone": "Telefon numaranız nedir (ülke kodu ile)?\nÖrnek: +905551234567",
  "registration_success": "✅ Tedarikçi olarak başarıyla kaydoldunuz!\nYakında sizinle iletişime geçeceğiz.",
  "cancel": "İşlem iptal edildi. Yeniden başlamak için /start yazın.",
  "trader_coming_soon": "🛒 Tüccar kaydı yakında geliyor!",
  "error_general": "Bir hata oluştu. Lütfen tekrar deneyin veya /start yazın."
}
```

**`bot/translations/en.json`** (نفس المفاتيح بالإنجليزية):
```json
{
  "welcome": "Welcome to TurkTextileHub 🌟\nB2B platform for Turkish textile trade",
  "role_selection": "Choose your role:",
  "supplier": "🏭 Supplier",
  "trader": "🛒 Trader",
  "supplier_registration_start": "Great! We'll start your registration as a supplier.\nThis will only take two minutes.",
  "prompt_company_name": "What is the name of your company or store?",
  "prompt_contact_name": "What is the name of the contact person?",
  "prompt_phone": "What is your phone number (with country code)?\nExample: +905551234567",
  "registration_success": "✅ You have been successfully registered as a supplier!\nWe will contact you soon.",
  "cancel": "Operation cancelled. Type /start to begin again.",
  "trader_coming_soon": "🛒 Trader registration coming soon!",
  "error_general": "An error occurred. Please try again or type /start."
}
```

### 7. `bot/handlers/start_handler.py`

**الوظيفة:** معالجة أمر `/start` وعرض أزرار اختيار الدور.

**المتطلبات:**
- دالة `start(update, context)` غير متزامنة (async)
- تحديد لغة المستخدم من `update.effective_user.language_code`
- إذا كانت اللغة `tr` تستخدم التركية، إذا كانت `en` تستخدم الإنجليزية، وإلا تستخدم العربية
- عرض رسالة الترحيب مع زرين inline:
  - زر "مورد/Supplier/Tedarikçi" بـ `callback_data='supplier'`
  - زر "تاجر/Trader/Tüccar" بـ `callback_data='trader'`
- استيراد `get_string` من `bot.services.language_service`

### 8. `bot/main.py`

**الوظيفة:** نقطة الدخول الرئيسية للبوت.

**المتطلبات:**
- إعداد نظام السجلات (logging) بمستوى INFO
- استيراد `BOT_TOKEN` من `bot.config`
- إنشاء `Application` باستخدام `Application.builder().token(BOT_TOKEN).build()`
- تسجيل `CommandHandler("start", start_handler.start)`
- **معالج الأخطاء العالمي:** دالة `error_handler(update, context)` تتجاهل خطأ `BadRequest` الذي يحتوي على "Query is too old" وتسجل جميع الأخطاء الأخرى
- تسجيل معالج الأخطاء باستخدام `application.add_error_handler(error_handler)`
- تشغيل البوت باستخدام `application.run_polling()`
- الكود الرئيسي داخل `if __name__ == "__main__":`

---

## ملاحظات مهمة للمبرمج (Claude/ChatGPT/Gemini)

1. **استخدم `python-telegram-bot` الإصدار 20.x** - هذا الإصدار يستخدم `async/await` بشكل كامل
2. **لا تضع أي منطق للمحادثة في هذه المرحلة** - فقط أمر `/start` والأزرار
3. **تأكد من أن جميع الدوال المعالجة `async`**
4. **استخدم `InlineKeyboardButton` و `InlineKeyboardMarkup`** للأزرار
5. **لا تضع `callback_data` handlers في هذه المرحلة** - فقط اعرض الأزرار
6. **الكود يجب أن يكون نظيفاً مع تعليقات توضيحية بالعربية**

---

## النتيجة المتوقعة

بعد تنفيذ هذه المرحلة، يجب أن يكون البوت قادراً على:
1. الاستجابة لأمر `/start`
2. عرض رسالة ترحيب بلغة المستخدم
3. عرض زرين: مورد وتاجر
4. تشغيل البوت بنجاح بدون أخطاء

---

*هذا الملف أعده مساعد الذكاء الاصطناعي لإدارة المشروع. يُرجى تسليم الكود المنتج في ملفات منفصلة لكل وحدة.*
