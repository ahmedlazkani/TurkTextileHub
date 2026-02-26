# ===================================================
# bot/handlers/start_handler.py
# معالج أمر /start - يعرض رسالة الترحيب وأزرار اختيار الدور
# يدعم ثلاث لغات: العربية، التركية، الإنجليزية
# ===================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.services.language_service import get_string


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start الرئيسي.
    
    يقوم بـ:
    1. تحديد لغة المستخدم من إعدادات تليجرام
    2. عرض رسالة ترحيب بلغة المستخدم
    3. عرض زرين inline لاختيار الدور (مورد أو تاجر)
    
    المعاملات:
        update: كائن التحديث من تليجرام
        context: سياق البوت
    """
    # تحديد لغة المستخدم من إعدادات تليجرام
    user_language_code = update.effective_user.language_code or ""
    
    # تحويل رمز اللغة إلى اللغة المدعومة
    # tr → تركية | en → إنجليزية | أي شيء آخر → عربية (الافتراضية)
    if user_language_code.startswith("tr"):
        lang = "tr"
    elif user_language_code.startswith("en"):
        lang = "en"
    else:
        lang = "ar"
    
    # بناء أزرار اختيار الدور (Inline Keyboard)
    keyboard = [
        [
            # زر المورد - callback_data='supplier'
            InlineKeyboardButton(
                text=get_string(lang, "supplier"),
                callback_data="supplier"
            ),
            # زر التاجر - callback_data='trader'
            InlineKeyboardButton(
                text=get_string(lang, "trader"),
                callback_data="trader"
            ),
        ]
    ]
    
    # إنشاء كائن لوحة المفاتيح
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # تجميع رسالة الترحيب مع عنوان اختيار الدور
    welcome_message = (
        f"{get_string(lang, 'welcome')}\n\n"
        f"{get_string(lang, 'role_selection')}"
    )
    
    # إرسال رسالة الترحيب مع الأزرار
    await update.message.reply_text(
        text=welcome_message,
        reply_markup=reply_markup
    )
