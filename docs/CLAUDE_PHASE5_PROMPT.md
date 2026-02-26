# أمر Claude - المرحلة الخامسة (الأخيرة)

---

## الأمر

أنت مطوّر Python متخصص في بوتات تليجرام. أنت تعمل على مشروع **TurkTextileHub Bot** من شركة **KAYISOFT** - بوت B2B لتجار الجملة في قطاع المنسوجات التركية.

### حالة المشروع الحالية

المشروع مكتمل ويعمل بنجاح. البوت يدعم:
- تسجيل الموردين (يُحفظ في جدول `bot_registrations` في Supabase)
- تسجيل التجار (يُحفظ في جدول `bot_trader_registrations` في Supabase)
- دعم ثلاث لغات: العربية، التركية، الإنجليزية

### المهمة المطلوبة

أضف **نظام إشعارات فوري للأدمن** + **ملف إعداد Railway للنشر الدائم**.

---

### الملفات المطلوبة (4 ملفات فقط)

#### 1. `bot/services/notification_service.py` (ملف جديد)

أنشئ خدمة إشعارات بالمواصفات التالية:

```
- استيراد: requests, datetime, logging
- استيراد من config: TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_ID
- استخدام requests.post مباشرة لـ Telegram Bot API (لا python-telegram-bot)
- الرابط: https://api.telegram.org/bot{TOKEN}/sendMessage
```

**دالة `notify_new_supplier(supplier_data: dict) -> bool`:**
- ترسل رسالة HTML للأدمن عند تسجيل مورد جديد
- نص الرسالة:
```
🏭 <b>مورد جديد تسجّل!</b>

👤 <b>اسم الشركة:</b> {company_name}
🙋 <b>جهة الاتصال:</b> {contact_name}
📞 <b>الهاتف:</b> {phone}
🆔 <b>معرّف تليجرام:</b> {telegram_id}
📅 <b>وقت التسجيل:</b> {datetime}

⏳ الحالة: قيد المراجعة
```
- ترجع True عند النجاح، False عند الفشل
- try/except يمنع توقف البوت عند فشل الإشعار

**دالة `notify_new_trader(trader_data: dict) -> bool`:**
- نفس الآلية، نص الرسالة:
```
🛒 <b>تاجر جديد تسجّل!</b>

👤 <b>الاسم الكامل:</b> {full_name}
📞 <b>الهاتف:</b> {phone}
🌍 <b>الدولة:</b> {country}
🏷️ <b>اهتمامات المنتجات:</b> {product_interest}
🆔 <b>معرّف تليجرام:</b> {telegram_id}
📅 <b>وقت التسجيل:</b> {datetime}

⏳ الحالة: قيد المراجعة
```

---

#### 2. `bot/config.py` (معدّل)

أضف هذا السطر بعد `TELEGRAM_BOT_TOKEN`:
```python
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
```

أرسل الملف كاملاً مع الإضافة.

---

#### 3. `bot/handlers/supplier_handler.py` (معدّل)

في دالة `received_phone`، بعد `if saved:` مباشرة، أضف:
```python
# إرسال إشعار للأدمن بالتسجيل الجديد
from bot.services import notification_service
notification_service.notify_new_supplier(supplier_data)
```

أرسل الملف كاملاً مع الإضافة.

---

#### 4. `bot/handlers/trader_handler.py` (معدّل)

في دالة `received_trader_product`، بعد `if saved:` مباشرة، أضف:
```python
# إرسال إشعار للأدمن بالتسجيل الجديد
from bot.services import notification_service
notification_service.notify_new_trader(trader_data)
```

أرسل الملف كاملاً مع الإضافة.

---

#### 5. `railway.toml` (ملف جديد في جذر المشروع)

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m bot.main"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10
```

---

### معايير الجودة الإلزامية

1. **تعليقات بالعربية** في كل قسم من الكود
2. **Docstring بالعربية** لكل دالة
3. **try/except** في كل دالة في notification_service.py
4. الإشعار الفاشل **لا يوقف البوت** - يُسجّل الخطأ فقط بـ `logging.error`
5. استخدام `datetime.now().strftime("%Y-%m-%d %H:%M")` للوقت
6. **لا تضيف** أي ميزات غير مذكورة
7. **لا تعدّل** main.py أو database_service.py أو ملفات الترجمة أو start_handler.py

---

### البنية الحالية للمشروع (للمرجعية)

```
TurkTextileHub/
├── bot/
│   ├── main.py
│   ├── config.py
│   ├── states.py
│   ├── handlers/
│   │   ├── start_handler.py
│   │   ├── supplier_handler.py
│   │   └── trader_handler.py
│   ├── services/
│   │   ├── database_service.py
│   │   └── language_service.py
│   └── translations/
│       ├── ar.json
│       ├── tr.json
│       └── en.json
├── docs/
├── requirements.txt
└── railway.toml  ← جديد
```

---

### التسليم المطلوب

سلّم **5 ملفات كاملة** بدون اختصار:
1. `bot/services/notification_service.py`
2. `bot/config.py`
3. `bot/handlers/supplier_handler.py`
4. `bot/handlers/trader_handler.py`
5. `railway.toml`

كل ملف يجب أن يكون **كاملاً** من أول سطر إلى آخر سطر.
