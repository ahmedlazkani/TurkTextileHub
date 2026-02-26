# مواصفات المرحلة الثانية: تسجيل الموردين

## السياق

هذه المرحلة تبني على المرحلة الأولى. الكود الموجود حالياً:
- `bot/main.py` - نقطة الدخول الرئيسية (تم إنشاؤها في المرحلة الأولى)
- `bot/config.py` - الإعدادات
- `bot/states.py` - يحتوي على: `COMPANY_NAME=1`, `CONTACT_NAME=2`, `PHONE_NUMBER=3`
- `bot/services/language_service.py` - خدمة اللغات مع دالة `get_string(lang, key)`
- `bot/handlers/start_handler.py` - معالج `/start` مع زرين (supplier, trader)
- ملفات الترجمة تحتوي على المفاتيح: `supplier_registration_start`, `prompt_company_name`, `prompt_contact_name`, `prompt_phone`, `registration_success`, `cancel`, `trader_coming_soon`

---

## الملفات المطلوب إنشاؤها في هذه المرحلة

### 1. `bot/handlers/supplier_handler.py` (ملف جديد)

**الوظيفة:** معالج محادثة متعدد الخطوات لتسجيل الموردين.

**المتطلبات التفصيلية:**

#### الدوال المطلوبة:

**أ. `start_registration(update, context) -> int`**
- نوع: `async`
- يُستدعى عند الضغط على زر "مورد" (callback_data='supplier')
- يستخرج لغة المستخدم من `query.from_user.language_code`
- يحفظ اللغة في `context.user_data['lang']`
- يرد على الزر بـ `await query.answer()`
- يعدّل الرسالة الأصلية بـ `await query.edit_message_text(get_string(lang, 'supplier_registration_start'))`
- يرسل رسالة جديدة: `get_string(lang, 'prompt_company_name')`
- يُرجع `states.COMPANY_NAME`

**ب. `received_company_name(update, context) -> int`**
- نوع: `async`
- يستقبل اسم الشركة من `update.message.text`
- يحفظه في `context.user_data['company_name']`
- يرسل: `get_string(lang, 'prompt_contact_name')`
- يُرجع `states.CONTACT_NAME`

**ج. `received_contact_name(update, context) -> int`**
- نوع: `async`
- يستقبل اسم جهة الاتصال من `update.message.text`
- يحفظه في `context.user_data['contact_name']`
- يرسل: `get_string(lang, 'prompt_phone')`
- يُرجع `states.PHONE_NUMBER`

**د. `received_phone(update, context) -> int`**
- نوع: `async`
- يستقبل رقم الهاتف من `update.message.text`
- يحفظه في `context.user_data['phone']`
- يجمع بيانات المستخدم:
  ```python
  supplier_data = {
      'telegram_id': str(update.effective_user.id),
      'company_name': context.user_data.get('company_name'),
      'contact_name': context.user_data.get('contact_name'),
      'phone': context.user_data.get('phone'),
  }
  ```
- **مؤقتاً** يطبع البيانات في السجلات (logging.info) بدلاً من حفظها في قاعدة البيانات (سيتم ربط قاعدة البيانات في المرحلة الثالثة)
- يرسل: `get_string(lang, 'registration_success')`
- يُرجع `ConversationHandler.END`

**هـ. `cancel(update, context) -> int`**
- نوع: `async`
- يُستدعى عند كتابة `/cancel`
- يرسل: `get_string(lang, 'cancel')`
- يُرجع `ConversationHandler.END`

#### منطق اللغة في جميع الدوال:
```python
lang = context.user_data.get('lang', 'ar')
```

---

### 2. تعديل `bot/main.py` (تعديل على الملف الموجود)

**الإضافات المطلوبة:**

أ. استيراد المكتبات الإضافية:
```python
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from bot.handlers import supplier_handler
```

ب. إنشاء `ConversationHandler` للموردين وتسجيله:
```python
supplier_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(supplier_handler.start_registration, pattern='^supplier$')
    ],
    states={
        states.COMPANY_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_company_name)
        ],
        states.CONTACT_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_contact_name)
        ],
        states.PHONE_NUMBER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, supplier_handler.received_phone)
        ],
    },
    fallbacks=[CommandHandler("cancel", supplier_handler.cancel)],
    per_message=False,
    per_chat=True,
    per_user=True,
)
```

ج. إضافة معالج لزر "تاجر":
```python
async def trader_handler(update, context):
    query = update.callback_query
    await query.answer()
    lang = query.from_user.language_code or 'ar'
    if not lang.startswith(('tr', 'en')):
        lang = 'ar'
    elif lang.startswith('tr'):
        lang = 'tr'
    else:
        lang = 'en'
    await query.edit_message_text(get_string(lang, 'trader_coming_soon'))
```

د. ترتيب تسجيل المعالجات (مهم جداً - يجب أن يكون `supplier_conv` قبل أي `CallbackQueryHandler` منفصل):
```python
application.add_handler(CommandHandler("start", start_handler.start))
application.add_handler(supplier_conv)  # يجب أن يكون قبل trader
application.add_handler(CallbackQueryHandler(trader_handler, pattern='^trader$'))
application.add_error_handler(error_handler)
```

---

## ملاحظات مهمة للمبرمج

1. **`per_message=False`** في `ConversationHandler` - هذا مهم لتجنب التحذيرات
2. **لا تستخدم `per_message=True`** لأنه يتطلب أن يكون كل handler من نوع `CallbackQueryHandler`
3. **ترتيب المعالجات مهم جداً** - `supplier_conv` يجب أن يُسجَّل قبل أي handler آخر يتعامل مع callback
4. **احفظ اللغة في `context.user_data`** وليس في متغير محلي فقط
5. **لا تضف قاعدة بيانات في هذه المرحلة** - فقط اطبع البيانات في السجلات

---

## النتيجة المتوقعة

بعد تنفيذ هذه المرحلة، يجب أن يعمل البوت كالتالي:
1. المستخدم يكتب `/start` → يظهر زران
2. يضغط "مورد" → يبدأ تدفق التسجيل
3. يُدخل اسم الشركة → يُسأل عن اسم جهة الاتصال
4. يُدخل اسم جهة الاتصال → يُسأل عن رقم الهاتف
5. يُدخل رقم الهاتف → يظهر رسالة نجاح التسجيل
6. يضغط "تاجر" → يظهر رسالة "قادم قريباً"

---

## الملفات التي يجب تسليمها

1. `bot/handlers/supplier_handler.py` (ملف جديد كامل)
2. `bot/main.py` (الملف المعدّل كاملاً)

---

*هذا الملف أعده مساعد الذكاء الاصطناعي لإدارة المشروع. يُرجى تسليم الكود المنتج في ملفين منفصلين.*
