# TurkTextileHub Bot 🏭

بوت تليجرام B2B يربط موردي المنسوجات التركية بتجار الجملة.

**الشركة:** KAYISOFT - إسطنبول، تركيا

---

## المرحلة الأولى: الأساس والبنية التحتية

### الميزات
- استجابة لأمر `/start`
- رسالة ترحيب تلقائية بلغة المستخدم
- دعم 3 لغات: العربية (افتراضي)، التركية، الإنجليزية
- زرا اختيار الدور: مورد 🏭 أو تاجر 🛒

---

## التثبيت والتشغيل

### 1. تثبيت المتطلبات
```bash
pip install -r requirements.txt
```

### 2. إعداد متغيرات البيئة
```bash
cp .env.example .env
# ثم عدّل ملف .env وأضف التوكن الخاص بك
```

### 3. تشغيل البوت
```bash
python -m bot.main
```

---

## هيكل الملفات

```
TurkTextileHub/
├── bot/
│   ├── main.py              # نقطة الدخول الرئيسية
│   ├── config.py            # إعدادات البوت
│   ├── states.py            # ثوابت حالات المحادثة
│   ├── handlers/
│   │   └── start_handler.py # معالج أمر /start
│   ├── services/
│   │   └── language_service.py # خدمة اللغات
│   └── translations/
│       ├── ar.json          # الترجمة العربية
│       ├── tr.json          # الترجمة التركية
│       └── en.json          # الترجمة الإنجليزية
├── requirements.txt
├── .env.example
└── README.md
```

---

## متغيرات البيئة المطلوبة

| المتغير | الوصف |
|---------|-------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت من @BotFather |
| `SUPABASE_URL` | رابط قاعدة بيانات Supabase |
| `SUPABASE_KEY` | مفتاح API لـ Supabase |
