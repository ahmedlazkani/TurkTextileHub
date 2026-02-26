# ===================================================
# bot/config.py
# إعدادات البوت - تحميل متغيرات البيئة والثوابت الأساسية
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import os
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# توكن البوت الرئيسي - مطلوب للتشغيل
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# إعدادات Supabase لقاعدة البيانات
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# معرّف تليجرام الخاص بالأدمن - لاستقبال إشعارات التسجيل الجديدة
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "5733520948"))

# التحقق من وجود التوكن - إذا كان فارغاً يتوقف البوت
if not BOT_TOKEN:
    raise ValueError(
        "❌ خطأ: متغير البيئة TELEGRAM_BOT_TOKEN غير موجود أو فارغ.\n"
        "الرجاء نسخ ملف .env.example إلى .env وإضافة التوكن الصحيح."
    )
