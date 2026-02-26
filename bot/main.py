# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import BOT_TOKEN
from bot.handlers import start_handler


# ===================================================
# إعداد نظام السجلات لمتابعة عمل البوت
# ===================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج الأخطاء العالمي - يعالج جميع الأخطاء التي تحدث أثناء تشغيل البوت.
    
    السلوك:
    - يتجاهل خطأ BadRequest الذي يحتوي على "Query is too old" (استعلامات الأزرار القديمة)
    - يسجل جميع الأخطاء الأخرى في السجلات
    
    المعاملات:
        update: كائن التحديث (قد يكون None في بعض الحالات)
        context: سياق البوت الذي يحتوي على معلومات الخطأ
    """
    # الحصول على الخطأ من السياق
    error = context.error
    
    # تجاهل خطأ "Query is too old" - يحدث عند الضغط على أزرار قديمة
    if isinstance(error, BadRequest) and "Query is too old" in str(error):
        logger.info("تم تجاهل استعلام قديم (Query is too old)")
        return
    
    # تسجيل جميع الأخطاء الأخرى مع تفاصيل كاملة
    logger.error(
        "حدث خطأ أثناء معالجة التحديث:",
        exc_info=context.error
    )


def main() -> None:
    """
    الدالة الرئيسية لتشغيل البوت.
    
    الخطوات:
    1. إنشاء كائن Application باستخدام التوكن
    2. تسجيل معالجات الأوامر
    3. تسجيل معالج الأخطاء
    4. تشغيل البوت بنظام polling
    """
    logger.info("🚀 جاري تشغيل بوت TurkTextileHub...")
    
    # إنشاء كائن Application - نقطة تحكم البوت الرئيسية
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ===================================================
    # تسجيل معالجات الأوامر
    # ===================================================
    
    # تسجيل معالج أمر /start
    application.add_handler(
        CommandHandler("start", start_handler.start)
    )
    
    # ===================================================
    # تسجيل معالج الأخطاء العالمي
    # ===================================================
    application.add_error_handler(error_handler)
    
    logger.info("✅ تم تسجيل جميع المعالجات بنجاح")
    logger.info("🔄 البوت يعمل الآن في وضع polling...")
    
    # تشغيل البوت - يظل يعمل حتى يتم إيقافه يدوياً
    application.run_polling()


# ===================================================
# نقطة الدخول - يتم التشغيل فقط عند تنفيذ الملف مباشرة
# ===================================================
if __name__ == "__main__":
    main()
