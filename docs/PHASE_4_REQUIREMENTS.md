# المرحلة الرابعة: تسجيل التجار + تحسين تجربة المستخدم (UX)
## TurkTextileHub Bot - Phase 4

---

## السياق الكامل للمشروع

**اسم المشروع:** TurkTextileHub Bot  
**الشركة:** KAYISOFT - إسطنبول، تركيا  
**الغرض:** بوت تليجرام B2B يربط موردي المنسوجات التركية بتجار الجملة  
**اللغات المدعومة:** العربية 🇸🇦، التركية 🇹🇷، الإنجليزية 🇬🇧  

---

## الملفات الموجودة حالياً (لا تعدّل عليها إلا ما هو مذكور)

```
bot/
├── main.py                          ← يحتاج تعديل
├── config.py                        ← لا تعدّل
├── states.py                        ← يحتاج إضافة
├── handlers/
│   ├── start_handler.py             ← يحتاج تعديل (تحسين UX)
│   └── supplier_handler.py          ← لا تعدّل
├── services/
│   ├── language_service.py          ← لا تعدّل
│   └── database_service.py         ← يحتاج إضافة دالة
└── translations/
    ├── ar.json                      ← يحتاج إضافة مفاتيح
    ├── tr.json                      ← يحتاج إضافة مفاتيح
    └── en.json                      ← يحتاج إضافة مفاتيح
```

---

## المهام المطلوبة

### المهمة 1: إنشاء جدول التجار في قاعدة البيانات

أضف دالة جديدة في `database_service.py` لحفظ بيانات التجار:

```python
def save_trader(trader_data: dict) -> bool:
    """يحفظ بيانات التاجر في جدول bot_trader_registrations"""
    # نقطة النهاية: /rest/v1/bot_trader_registrations
    # الأعمدة: telegram_id (text), full_name (text), phone (text), 
    #           country (text), product_interest (text), status (text DEFAULT 'pending')
    # نفس منطق save_supplier تماماً
```

```python
def check_trader_exists(telegram_id: str) -> bool:
    """يتحقق من وجود تاجر مسجل مسبقاً"""
    # نفس منطق check_supplier_exists تماماً لكن على جدول bot_trader_registrations
```

**ملاحظة:** الجدول `bot_trader_registrations` سيتم إنشاؤه في Supabase قبل تشغيل البوت.

---

### المهمة 2: إنشاء ملف `trader_handler.py` (جديد)

**المسار:** `bot/handlers/trader_handler.py`

**تدفق المحادثة (ConversationHandler):**

```
زر "تاجر" 
    ↓
[TRADER_FULL_NAME] ← "ما هو اسمك الكامل؟"
    ↓
[TRADER_PHONE] ← "ما هو رقم هاتفك؟ (مع رمز الدولة)"
    ↓
[TRADER_COUNTRY] ← "من أي دولة أنت؟"
    ↓
[TRADER_PRODUCT] ← InlineKeyboard بـ 4 أزرار:
    • 👕 ملابس جاهزة
    • 🧵 أقمشة خام
    • 👟 أحذية وإكسسوار
    • 📦 منتجات متنوعة
    ↓
[END] ← رسالة نجاح + أزرار رئيسية
```

**معالجات المطلوبة:**

```python
async def start_trader_registration(update, context):
    """يبدأ تسجيل التاجر عند الضغط على زر 'تاجر'"""
    # تحقق أولاً من check_trader_exists
    # إذا مسجل: أرسل رسالة "already_registered" وأنهِ المحادثة
    # إذا جديد: اسأل عن الاسم الكامل

async def received_trader_name(update, context):
    """يستقبل الاسم الكامل للتاجر"""
    # تحقق أن الاسم لا يقل عن حرفين
    # احفظ في context.user_data['trader_full_name']
    # اسأل عن رقم الهاتف

async def received_trader_phone(update, context):
    """يستقبل رقم هاتف التاجر"""
    # احفظ في context.user_data['trader_phone']
    # اسأل عن الدولة

async def received_trader_country(update, context):
    """يستقبل دولة التاجر"""
    # احفظ في context.user_data['trader_country']
    # أرسل InlineKeyboard لاختيار نوع المنتج

async def received_trader_product(update, context):
    """يستقبل نوع المنتج المفضل عبر InlineKeyboard"""
    # استقبل callback_data
    # احفظ جميع البيانات في Supabase عبر save_trader()
    # أرسل رسالة نجاح مع أزرار العودة للقائمة الرئيسية
    # أنهِ المحادثة

async def cancel_trader(update, context):
    """يلغي عملية التسجيل"""
```

---

### المهمة 3: تحسين تجربة المستخدم (UX) في `start_handler.py`

**التحسينات المطلوبة:**

#### أ) إضافة رسالة ترحيب محسّنة
```
عند /start:
- أرسل أولاً: صورة أو GIF ترحيبي (اختياري - استخدم send_chat_action أولاً)
- ثم: رسالة الترحيب مع اسم المستخدم من تليجرام
- ثم: أزرار الاختيار
```

#### ب) استخدام `send_chat_action` قبل كل رد
```python
# قبل كل رسالة طويلة أو معالجة:
await context.bot.send_chat_action(
    chat_id=update.effective_chat.id,
    action="typing"
)
```
هذا يُظهر "يكتب..." للمستخدم أثناء المعالجة، مما يحسن تجربة الانتظار.

#### ج) تحسين أزرار القائمة الرئيسية
```python
# الأزرار الحالية:
# [🏭 مورد]  [🛒 تاجر]

# الأزرار المحسّنة (3 صفوف):
# [🏭 تسجيل كمورد]
# [🛒 تسجيل كتاجر]  
# [🌐 تغيير اللغة]
```

#### د) إضافة زر "تغيير اللغة" في القائمة الرئيسية
```python
async def change_language(update, context):
    """يعرض قائمة اختيار اللغة مرة أخرى"""
    # أرسل نفس رسالة اختيار اللغة من start_handler
    # مع 3 أزرار: العربية، التركية، الإنجليزية
```

---

### المهمة 4: تحديث `states.py`

أضف الحالات الجديدة:

```python
# حالات تسجيل التاجر
TRADER_FULL_NAME = 10
TRADER_PHONE = 11
TRADER_COUNTRY = 12
TRADER_PRODUCT = 13
```

---

### المهمة 5: تحديث `main.py`

أضف `trader_conv` ConversationHandler بنفس أسلوب `supplier_conv`:

```python
trader_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_trader_registration, pattern="^trader$")],
    states={
        TRADER_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_trader_name)],
        TRADER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_trader_phone)],
        TRADER_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_trader_country)],
        TRADER_PRODUCT: [CallbackQueryHandler(received_trader_product, pattern="^product_")],
    },
    fallbacks=[CommandHandler("cancel", cancel_trader)],
    per_message=False,
    per_chat=True,
    per_user=True,
)
```

**ترتيب تسجيل المعالجات في `setup_handlers`:**
```python
application.add_handler(start_handler)
application.add_handler(supplier_conv)
application.add_handler(trader_conv)      # ← جديد
application.add_handler(change_lang_handler)  # ← جديد
application.add_handler(error_handler)
```

---

### المهمة 6: تحديث ملفات الترجمة

أضف هذه المفاتيح لكل من `ar.json` و `tr.json` و `en.json`:

**ar.json:**
```json
"trader_welcome": "🛒 أهلاً بك في تسجيل التجار!\n\nسنحتاج بعض المعلومات للتواصل معك.",
"ask_trader_name": "👤 ما هو اسمك الكامل؟",
"ask_trader_phone": "📱 ما هو رقم هاتفك؟\n\nمثال: +905551234567",
"ask_trader_country": "🌍 من أي دولة أنت؟\n\nمثال: السعودية، الإمارات، مصر...",
"ask_trader_product": "📦 ما نوع المنتجات التي تهتم بها؟\n\nاختر من القائمة:",
"product_ready": "👕 ملابس جاهزة",
"product_fabric": "🧵 أقمشة خام",
"product_shoes": "👟 أحذية وإكسسوار",
"product_misc": "📦 منتجات متنوعة",
"trader_success": "✅ تم تسجيلك بنجاح كتاجر!\n\nسيتواصل معك فريقنا قريباً لعرض أفضل الموردين المناسبين لك.",
"change_language": "🌐 تغيير اللغة",
"register_supplier_btn": "🏭 تسجيل كمورد",
"register_trader_btn": "🛒 تسجيل كتاجر",
"typing_indicator": "⏳ جاري المعالجة..."
```

**tr.json:** (نفس المفاتيح بالتركية)
```json
"trader_welcome": "🛒 Tüccar kaydına hoş geldiniz!\n\nSizinle iletişime geçebilmemiz için birkaç bilgiye ihtiyacımız var.",
"ask_trader_name": "👤 Tam adınız nedir?",
"ask_trader_phone": "📱 Telefon numaranız nedir?\n\nÖrnek: +905551234567",
"ask_trader_country": "🌍 Hangi ülkedensiniz?\n\nÖrnek: Suudi Arabistan, BAE, Mısır...",
"ask_trader_product": "📦 Hangi tür ürünlerle ilgileniyorsunuz?\n\nListeden seçin:",
"product_ready": "👕 Hazır giyim",
"product_fabric": "🧵 Ham kumaş",
"product_shoes": "👟 Ayakkabı ve aksesuar",
"product_misc": "📦 Çeşitli ürünler",
"trader_success": "✅ Tüccar olarak başarıyla kaydoldunuz!\n\nEkibimiz size uygun tedarikçileri sunmak için yakında iletişime geçecek.",
"change_language": "🌐 Dil değiştir",
"register_supplier_btn": "🏭 Tedarikçi olarak kaydol",
"register_trader_btn": "🛒 Tüccar olarak kaydol",
"typing_indicator": "⏳ İşleniyor..."
```

**en.json:** (نفس المفاتيح بالإنجليزية)
```json
"trader_welcome": "🛒 Welcome to trader registration!\n\nWe need some information to get in touch with you.",
"ask_trader_name": "👤 What is your full name?",
"ask_trader_phone": "📱 What is your phone number?\n\nExample: +905551234567",
"ask_trader_country": "🌍 Which country are you from?\n\nExample: Saudi Arabia, UAE, Egypt...",
"ask_trader_product": "📦 What type of products are you interested in?\n\nChoose from the list:",
"product_ready": "👕 Ready-made clothing",
"product_fabric": "🧵 Raw fabric",
"product_shoes": "👟 Shoes & accessories",
"product_misc": "📦 Miscellaneous products",
"trader_success": "✅ You have been successfully registered as a trader!\n\nOur team will contact you soon with the best suppliers for you.",
"change_language": "🌐 Change language",
"register_supplier_btn": "🏭 Register as supplier",
"register_trader_btn": "🛒 Register as trader",
"typing_indicator": "⏳ Processing..."
```

---

## الملفات التي يجب تسليمها (6 ملفات فقط)

| الملف | النوع |
|---|---|
| `bot/handlers/trader_handler.py` | جديد |
| `bot/handlers/start_handler.py` | معدّل |
| `bot/services/database_service.py` | معدّل (إضافة دالتين) |
| `bot/states.py` | معدّل (إضافة 4 حالات) |
| `bot/main.py` | معدّل |
| `bot/translations/ar.json` + `tr.json` + `en.json` | معدّلة |

---

## معايير الجودة الإلزامية

1. كل دالة تحتوي على Docstring بالعربية
2. كل قسم مسبوق بتعليق توضيحي بالعربية
3. استخدام `send_chat_action` قبل كل رد يستغرق وقتاً
4. التحقق من صحة المدخلات (الاسم لا يقل عن حرفين)
5. معالجة جميع الأخطاء بـ try/except
6. لا تضيف أي ميزات غير مذكورة
