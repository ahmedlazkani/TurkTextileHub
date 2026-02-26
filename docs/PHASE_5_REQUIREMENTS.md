# المرحلة الخامسة: إشعارات الأدمن + النشر الدائم على Railway

## نظرة عامة

هذه المرحلة الأخيرة تُضيف نظام إشعارات فوري للمدير (الأدمن) عند تسجيل أي مورد أو تاجر جديد، بالإضافة إلى ملف إعداد Railway للنشر الدائم.

---

## 1. الملفات التي يجب تسليمها (4 ملفات فقط)

| الملف | النوع | الوصف |
|---|---|---|
| `bot/services/notification_service.py` | جديد | خدمة إرسال الإشعارات للأدمن |
| `bot/handlers/supplier_handler.py` | معدّل | إضافة استدعاء الإشعار بعد الحفظ |
| `bot/handlers/trader_handler.py` | معدّل | إضافة استدعاء الإشعار بعد الحفظ |
| `railway.toml` | جديد | ملف إعداد النشر على Railway |

---

## 2. خدمة الإشعارات: `notification_service.py`

### الموقع
```
bot/services/notification_service.py
```

### المتغيرات المطلوبة من config.py
```python
from bot.config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_ID
```

### الدوال المطلوبة

#### `notify_new_supplier(supplier_data: dict) -> bool`
- ترسل رسالة للأدمن عند تسجيل مورد جديد
- تستخدم `requests.post` لـ Telegram Bot API مباشرة (لا تستخدم python-telegram-bot)
- الرابط: `https://api.telegram.org/bot{TOKEN}/sendMessage`
- المعاملات: `chat_id=ADMIN_TELEGRAM_ID`, `text=...`, `parse_mode="HTML"`
- ترجع `True` عند النجاح، `False` عند الفشل
- تعالج الأخطاء بـ `try/except` بدون إيقاف البوت

**نص الرسالة (HTML):**
```
🏭 <b>مورد جديد تسجّل!</b>

👤 <b>اسم الشركة:</b> {company_name}
🙋 <b>جهة الاتصال:</b> {contact_name}
📞 <b>الهاتف:</b> {phone}
🆔 <b>معرّف تليجرام:</b> {telegram_id}
📅 <b>وقت التسجيل:</b> {datetime}

⏳ الحالة: قيد المراجعة
```

#### `notify_new_trader(trader_data: dict) -> bool`
- ترسل رسالة للأدمن عند تسجيل تاجر جديد
- نفس الآلية أعلاه

**نص الرسالة (HTML):**
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

## 3. تعديل `supplier_handler.py`

### في دالة `received_phone` بعد سطر `save_supplier(supplier_data)` مباشرة:
```python
# إرسال إشعار للأدمن
from bot.services import notification_service
notification_service.notify_new_supplier(supplier_data)
```

**ملاحظة:** استدعاء الإشعار يجب أن يكون بعد التحقق من نجاح الحفظ فقط (داخل `if saved:`).

---

## 4. تعديل `trader_handler.py`

### في دالة `received_trader_product` بعد نجاح الحفظ:
```python
# إرسال إشعار للأدمن
from bot.services import notification_service
notification_service.notify_new_trader(trader_data)
```

**ملاحظة:** نفس الشرط - داخل `if saved:` فقط.

---

## 5. ملف `config.py` - إضافة متغير جديد

أضف هذا السطر في `bot/config.py` بعد `TELEGRAM_BOT_TOKEN`:
```python
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
```

---

## 6. ملف Railway: `railway.toml`

### الموقع: جذر المشروع
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m bot.main"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10
```

---

## 7. متغيرات البيئة المطلوبة في Railway

يجب أن يذكر Claude في ملاحظاته أن هذه المتغيرات يجب إضافتها في Railway:

| المتغير | القيمة |
|---|---|
| `TELEGRAM_BOT_TOKEN` | توكن البوت |
| `SUPABASE_URL` | رابط Supabase |
| `SUPABASE_KEY` | مفتاح Supabase |
| `ADMIN_TELEGRAM_ID` | معرّف تليجرام الخاص بك (رقم) |

---

## 8. معايير الجودة الإلزامية

1. كل دالة تحتوي على Docstring بالعربية
2. كل قسم مسبوق بتعليق توضيحي بالعربية
3. معالجة الأخطاء بـ `try/except` في كل دالة
4. الإشعار لا يوقف البوت إذا فشل (يُسجّل الخطأ فقط)
5. استخدام `datetime.now().strftime("%Y-%m-%d %H:%M")` للوقت
6. لا تضيف أي ميزات غير مذكورة

---

## 9. ملاحظات مهمة

- **لا تستخدم** `python-telegram-bot` في `notification_service.py` - استخدم `requests` فقط
- **لا تعدّل** `main.py` أو `database_service.py` أو ملفات الترجمة
- **لا تعدّل** `start_handler.py`
- الملفات المطلوبة هي 4 فقط كما محدد في الجدول أعلاه
