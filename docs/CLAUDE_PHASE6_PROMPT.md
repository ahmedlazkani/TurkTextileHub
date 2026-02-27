
# أمر المرحلة السادسة: إعادة هيكلة TurkTextileHub وإضافة المنتجات

مرحباً Claude،

ننتقل اليوم إلى المرحلة السادسة من مشروع بوت TurkTextileHub. هذه المرحلة تتضمن إعادة هيكلة كبيرة للكود، إكمال تدفقات التسجيل، وإضافة الميزة الأساسية الجديدة: إدارة المنتجات.

**مهمتك:** استلام الكود الحالي كاملاً، فهم المتطلبات الجديدة، وإعادة كتابة المشروع بالكامل حسب الهيكل الجديد مع إضافة الميزات المطلوبة. يجب أن يكون الكود نظيفاً، موثقاً، وقابلاً للتوسع.

---

## 1. الكود الحالي للمشروع (Current Codebase)

هذا هو الكود الكامل للمشروع حالياً. ادرسه جيداً قبل البدء.




### === ./__init__.py ===


```python
```


### === ./config.py ===


```python
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
```


### === ./handlers/__init__.py ===


```python
```


### === ./handlers/start_handler.py ===


```python
# ===================================================
# bot/handlers/start_handler.py
# معالج أمر /start - يعرض رسالة الترحيب وأزرار اختيار الدور
# المرحلة الرابعة: تحسين UX - أزرار محسّنة + send_chat_action + اسم المستخدم
# يدعم ثلاث لغات: العربية، التركية، الإنجليزية
# KAYISOFT - إسطنبول، تركيا
# ===================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.language_service import get_string


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج أمر /start الرئيسي - نسخة محسّنة بتجربة مستخدم أفضل.

    التحسينات في هذه المرحلة:
        - عرض اسم المستخدم من تليجرام في رسالة الترحيب
        - إظهار مؤشر "يكتب..." قبل الرد
        - ثلاثة أزرار في ثلاثة صفوف منفصلة (مورد، تاجر، تغيير اللغة)

    المعاملات:
        update: كائن التحديث من تليجرام
        context: سياق البوت
    """
    # ===================================================
    # إظهار مؤشر الكتابة لتحسين تجربة الانتظار
    # ===================================================
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # ===================================================
    # تحديد لغة المستخدم من إعدادات تليجرام
    # ===================================================
    user_language_code = update.effective_user.language_code or ""

    if user_language_code.startswith("tr"):
        lang = "tr"
    elif user_language_code.startswith("en"):
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة في بيانات المستخدم
    context.user_data["lang"] = lang

    # ===================================================
    # استخراج اسم المستخدم من تليجرام لرسالة ترحيب شخصية
    # ===================================================
    user = update.effective_user
    user_name = user.first_name or user.username or ""

    # ===================================================
    # بناء أزرار القائمة الرئيسية المحسّنة (3 صفوف)
    # كل زر في صف مستقل لسهولة الضغط على الشاشات الصغيرة
    # ===================================================
    keyboard = [
        # الصف الأول: تسجيل كمورد
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
            )
        ],
        # الصف الثاني: تسجيل كتاجر
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_trader_btn"),
                callback_data="trader"
            )
        ],
        # الصف الثالث: تغيير اللغة
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # ===================================================
    # تجميع رسالة الترحيب مع اسم المستخدم
    # ===================================================
    welcome_text = get_string(lang, "welcome")
    role_text = get_string(lang, "role_selection")

    # بناء رسالة الترحيب بدون اسم المستخدم
    welcome_message = f"{welcome_text}\n\n{role_text}"

    # إرسال رسالة الترحيب مع الأزرار المحسّنة
    await update.message.reply_text(
        text=welcome_message,
        reply_markup=reply_markup
    )


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يعرض قائمة اختيار اللغة عند الضغط على زر 'تغيير اللغة'.

    يُرسل رسالة جديدة مع ثلاثة أزرار: العربية، التركية، الإنجليزية.
    كل زر يغير لغة المستخدم عند الضغط عليه.

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت
    """
    query = update.callback_query

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # بناء أزرار اختيار اللغة (3 أزرار - كل لغة في صف)
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang_ar")
        ],
        [
            InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr")
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # تعديل الرسالة الحالية بعرض خيارات اللغة مع النص الصحيح
    await query.edit_message_text(
        text=get_string(lang, "select_language"),
        reply_markup=reply_markup
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    يضبط لغة المستخدم بناءً على اختياره ويعرض القائمة الرئيسية.

    يُستدعى عند الضغط على أحد أزرار اختيار اللغة (lang_ar, lang_tr, lang_en).

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت
    """
    query = update.callback_query

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # تحديد اللغة المختارة من callback_data
    # ===================================================
    callback = query.data  # lang_ar أو lang_tr أو lang_en

    if callback == "lang_tr":
        lang = "tr"
    elif callback == "lang_en":
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة الجديدة في بيانات المستخدم
    context.user_data["lang"] = lang

    # ===================================================
    # إظهار مؤشر الكتابة قبل تحديث القائمة
    # ===================================================
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.TYPING
    )

    # ===================================================
    # عرض القائمة الرئيسية بعد تغيير اللغة
    # ===================================================
    user = query.from_user
    user_name = user.first_name or user.username or ""

    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_trader_btn"),
                callback_data="trader"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = get_string(lang, "welcome")
    role_text = get_string(lang, "role_selection")

    # بناء رسالة الترحيب بدون اسم المستخدم
    welcome_message = f"{welcome_text}\n\n{role_text}"

    # تعديل الرسالة بالقائمة الرئيسية باللغة الجديدة
    await query.edit_message_text(
        text=welcome_message,
        reply_markup=reply_markup
    )
```


### === ./handlers/supplier_handler.py ===


```python
# ===================================================
# bot/handlers/supplier_handler.py
# معالج محادثة متعدد الخطوات لتسجيل الموردين
# المرحلة الخامسة: إضافة إشعار الأدمن عند كل تسجيل ناجح
# يتعامل مع تدفق: اسم الشركة ← اسم جهة الاتصال ← رقم الهاتف
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service
from bot.services import notification_service
from bot.services.language_service import get_string

# سجل خاص بهذا المعالج
logger = logging.getLogger(__name__)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق تسجيل المورد عند الضغط على زر 'مورد'.

    الخطوات:
        1. استخراج لغة المستخدم من بيانات تليجرام وحفظها
        2. الرد على الزر لإزالة حالة التحميل
        3. تعديل الرسالة الأصلية برسالة بداية التسجيل
        4. إرسال سؤال اسم الشركة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت (يُستخدم لحفظ بيانات المستخدم)

    المُخرجات:
        int: states.COMPANY_NAME للانتقال إلى مرحلة استقبال اسم الشركة
    """
    query = update.callback_query

    # ===================================================
    # استخراج لغة المستخدم وتحديد اللغة المناسبة
    # ===================================================
    raw_lang = query.from_user.language_code or "ar"

    if raw_lang.startswith("tr"):
        lang = "tr"
    elif raw_lang.startswith("en"):
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة في بيانات المستخدم لاستخدامها في جميع الخطوات التالية
    context.user_data["lang"] = lang

    # الرد على الزر لإزالة حالة التحميل الدوارة في تليجرام
    await query.answer()

    # تعديل الرسالة الأصلية برسالة بداية التسجيل كمورد
    await query.edit_message_text(
        text=get_string(lang, "supplier_registration_start")
    )

    # إرسال سؤال اسم الشركة كرسالة جديدة
    await query.message.reply_text(
        text=get_string(lang, "prompt_company_name")
    )

    # الانتقال إلى مرحلة استقبال اسم الشركة
    return states.COMPANY_NAME


async def received_company_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم الشركة من المستخدم وينتقل لمرحلة اسم جهة الاتصال.

    الخطوات:
        1. قراءة النص المُرسل من المستخدم
        2. حفظ اسم الشركة في context.user_data
        3. إرسال سؤال اسم جهة الاتصال

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.CONTACT_NAME للانتقال إلى مرحلة اسم جهة الاتصال
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ اسم الشركة
    # ===================================================
    company_name = update.message.text
    context.user_data["company_name"] = company_name

    # إرسال سؤال اسم جهة الاتصال
    await update.message.reply_text(
        text=get_string(lang, "prompt_contact_name")
    )

    return states.CONTACT_NAME


async def received_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اسم جهة الاتصال وينتقل لمرحلة رقم الهاتف.

    الخطوات:
        1. قراءة النص المُرسل من المستخدم
        2. حفظ اسم جهة الاتصال في context.user_data
        3. إرسال سؤال رقم الهاتف

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.PHONE_NUMBER للانتقال إلى مرحلة رقم الهاتف
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ اسم جهة الاتصال
    # ===================================================
    contact_name = update.message.text
    context.user_data["contact_name"] = contact_name

    # إرسال سؤال رقم الهاتف مع مثال على الصيغة الصحيحة
    await update.message.reply_text(
        text=get_string(lang, "prompt_phone")
    )

    return states.PHONE_NUMBER


async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم الهاتف، يحفظ البيانات في Supabase، ويُرسل إشعاراً للأدمن.

    الخطوات:
        1. قراءة رقم الهاتف وحفظه
        2. تجميع بيانات المورد الكاملة
        3. التحقق من التسجيل المسبق
        4. حفظ البيانات في Supabase إذا كان المستخدم جديداً
        5. إرسال إشعار فوري للأدمن عند نجاح الحفظ
        6. إرسال الرسالة المناسبة للمستخدم وإنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ رقم الهاتف
    # ===================================================
    phone = update.message.text
    context.user_data["phone"] = phone

    # ===================================================
    # تجميع بيانات المورد الكاملة للحفظ في قاعدة البيانات
    # ===================================================
    supplier_data = {
        "telegram_id": str(update.effective_user.id),
        "company_name": context.user_data.get("company_name"),
        "contact_name": context.user_data.get("contact_name"),
        "phone": context.user_data.get("phone"),
    }

    # ===================================================
    # التحقق أولاً إذا كان المورد مسجلاً مسبقاً في Supabase
    # ===================================================
    already_exists = database_service.check_supplier_exists(supplier_data["telegram_id"])

    if already_exists:
        # إرسال رسالة أن المورد مسجل مسبقاً
        await update.message.reply_text(
            text=get_string(lang, "already_registered")
        )
    else:
        # ===================================================
        # حفظ بيانات المورد في قاعدة البيانات Supabase
        # ===================================================
        success = database_service.save_supplier(supplier_data)

        if success:
            logger.info(
                "تم حفظ بيانات المورد بنجاح: telegram_id=%s",
                supplier_data["telegram_id"]
            )
            # ===================================================
            # إرسال إشعار للأدمن بالتسجيل الجديد
            # الفشل لا يوقف البوت - يُسجَّل الخطأ فقط داخل الخدمة
            # ===================================================
            notification_service.notify_new_supplier(supplier_data)

            await update.message.reply_text(
                text=get_string(lang, "registration_success")
            )
        else:
            logger.error(
                "فشل حفظ بيانات المورد: telegram_id=%s",
                supplier_data["telegram_id"]
            )
            await update.message.reply_text(
                text=get_string(lang, "error_general")
            )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية التسجيل عند كتابة أمر /cancel.

    الخطوات:
        1. استرجاع اللغة المحفوظة
        2. إرسال رسالة إلغاء العملية
        3. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يُستدعى من CommandHandler)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    lang = context.user_data.get("lang", "ar")

    # إرسال رسالة الإلغاء مع إرشاد للبدء من جديد
    await update.message.reply_text(
        text=get_string(lang, "cancel")
    )

    return ConversationHandler.END
```


### === ./handlers/trader_handler.py ===


```python
# ===================================================
# bot/handlers/trader_handler.py
# معالج محادثة متعدد الخطوات لتسجيل التجار
# المرحلة الخامسة: إضافة إشعار الأدمن عند كل تسجيل ناجح
# تدفق: الاسم الكامل ← رقم الهاتف ← الدولة ← نوع المنتج
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service
from bot.services import notification_service
from bot.services.language_service import get_string

# سجل خاص بهذا المعالج
logger = logging.getLogger(__name__)


async def start_trader_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تسجيل التاجر عند الضغط على زر 'تسجيل كتاجر'.

    الخطوات:
        1. استخراج لغة المستخدم وحفظها
        2. الرد على الزر لإزالة حالة التحميل
        3. التحقق إذا كان المستخدم مسجلاً مسبقاً كتاجر
        4. إذا جديد: تعديل الرسالة وإرسال سؤال الاسم الكامل
        5. إذا مسجل: إرسال رسالة تنبيه وإنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_FULL_NAME للانتقال لمرحلة الاسم، أو END إذا مسجل مسبقاً
    """
    query = update.callback_query

    # ===================================================
    # استخراج لغة المستخدم وتحديد اللغة المناسبة
    # ===================================================
    raw_lang = query.from_user.language_code or "ar"

    if raw_lang.startswith("tr"):
        lang = "tr"
    elif raw_lang.startswith("en"):
        lang = "en"
    else:
        lang = "ar"

    # حفظ اللغة في بيانات المستخدم لاستخدامها في جميع الخطوات التالية
    context.user_data["lang"] = lang

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # التحقق من أن المستخدم ليس مسجلاً مسبقاً كتاجر
    # ===================================================
    telegram_id = str(query.from_user.id)

    # إظهار مؤشر الكتابة أثناء التحقق من قاعدة البيانات
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action="typing"
    )

    already_exists = database_service.check_trader_exists(telegram_id)

    if already_exists:
        # إرسال رسالة أن المستخدم مسجل مسبقاً وإنهاء المحادثة
        await query.edit_message_text(
            text=get_string(lang, "already_registered")
        )
        return ConversationHandler.END

    # ===================================================
    # تعديل الرسالة الأصلية برسالة الترحيب بتسجيل التجار
    # ===================================================
    await query.edit_message_text(
        text=get_string(lang, "trader_welcome")
    )

    # إرسال سؤال الاسم الكامل كرسالة جديدة
    await query.message.reply_text(
        text=get_string(lang, "ask_trader_name")
    )

    # الانتقال إلى مرحلة استقبال الاسم الكامل
    return states.TRADER_FULL_NAME


async def received_trader_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل الاسم الكامل للتاجر ويتحقق من صحته.

    الخطوات:
        1. قراءة الاسم المُرسل والتحقق من أنه لا يقل عن حرفين
        2. حفظ الاسم في context.user_data
        3. إرسال سؤال رقم الهاتف

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_PHONE للانتقال لمرحلة الهاتف،
             أو نفس الحالة إذا كان الاسم غير صالح
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال الاسم والتحقق من صحته (لا يقل عن حرفين)
    # ===================================================
    full_name = update.message.text.strip()

    if len(full_name) < 2:
        # الاسم قصير جداً - إعادة السؤال
        await update.message.reply_text(
            text=get_string(lang, "ask_trader_name")
        )
        return states.TRADER_FULL_NAME

    # حفظ الاسم الكامل في بيانات المستخدم
    context.user_data["trader_full_name"] = full_name

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال رقم الهاتف
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_phone")
    )

    # الانتقال إلى مرحلة استقبال رقم الهاتف
    return states.TRADER_PHONE


async def received_trader_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل رقم هاتف التاجر وينتقل لمرحلة الدولة.

    الخطوات:
        1. قراءة رقم الهاتف المُرسل من المستخدم
        2. حفظه في context.user_data
        3. إرسال سؤال الدولة

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_COUNTRY للانتقال لمرحلة الدولة
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ رقم الهاتف
    # ===================================================
    phone = update.message.text.strip()
    context.user_data["trader_phone"] = phone

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال الدولة
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_country")
    )

    # الانتقال إلى مرحلة استقبال الدولة
    return states.TRADER_COUNTRY


async def received_trader_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل دولة التاجر ويعرض قائمة اختيار نوع المنتج.

    الخطوات:
        1. قراءة الدولة المُرسلة من المستخدم
        2. حفظها في context.user_data
        3. إرسال InlineKeyboard بأربعة خيارات لنوع المنتج

    المعاملات:
        update: كائن التحديث (يحتوي على message.text)
        context: سياق البوت

    المُخرجات:
        int: states.TRADER_PRODUCT للانتقال لمرحلة اختيار المنتج
    """
    lang = context.user_data.get("lang", "ar")

    # ===================================================
    # استقبال وحفظ الدولة
    # ===================================================
    country = update.message.text.strip()
    context.user_data["trader_country"] = country

    # ===================================================
    # بناء InlineKeyboard بأربعة أزرار لنوع المنتج
    # callback_data يُستخدم لاحقاً لتحديد الاختيار
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_ready"),
                callback_data="product_ready"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_fabric"),
                callback_data="product_fabric"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_shoes"),
                callback_data="product_shoes"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "product_misc"),
                callback_data="product_misc"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # إظهار مؤشر الكتابة قبل الرد
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # إرسال سؤال نوع المنتج مع الأزرار
    await update.message.reply_text(
        text=get_string(lang, "ask_trader_product"),
        reply_markup=reply_markup
    )

    # الانتقال إلى مرحلة استقبال اختيار المنتج
    return states.TRADER_PRODUCT


async def received_trader_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نوع المنتج عبر InlineKeyboard، يحفظ البيانات في Supabase، ويُرسل إشعاراً للأدمن.

    الخطوات:
        1. استقبال callback_data لمعرفة المنتج المختار
        2. الرد على الزر لإزالة حالة التحميل
        3. تجميع جميع بيانات التاجر وحفظها في Supabase
        4. إرسال إشعار فوري للأدمن عند نجاح الحفظ
        5. إرسال رسالة النجاح مع أزرار العودة للقائمة الرئيسية
        6. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يحتوي على callback_query)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    # الرد على الزر لإزالة حالة التحميل الدوارة
    await query.answer()

    # ===================================================
    # استقبال اختيار نوع المنتج من callback_data
    # ===================================================
    product_interest = query.data  # مثال: "product_ready"

    # إظهار مؤشر الكتابة أثناء الحفظ في قاعدة البيانات
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action="typing"
    )

    # ===================================================
    # تجميع جميع بيانات التاجر الكاملة
    # ===================================================
    trader_data = {
        "telegram_id": str(query.from_user.id),
        "full_name": context.user_data.get("trader_full_name"),
        "phone": context.user_data.get("trader_phone"),
        "country": context.user_data.get("trader_country"),
        "product_interest": product_interest,
    }

    # ===================================================
    # حفظ بيانات التاجر في Supabase
    # ===================================================
    success = database_service.save_trader(trader_data)

    # ===================================================
    # بناء أزرار العودة للقائمة الرئيسية بعد التسجيل
    # ===================================================
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_string(lang, "register_supplier_btn"),
                callback_data="supplier"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string(lang, "change_language"),
                callback_data="change_language"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if success:
        logger.info(
            "تم حفظ بيانات التاجر بنجاح: telegram_id=%s",
            trader_data["telegram_id"]
        )
        # ===================================================
        # إرسال إشعار للأدمن بالتسجيل الجديد
        # الفشل لا يوقف البوت - يُسجَّل الخطأ فقط داخل الخدمة
        # ===================================================
        notification_service.notify_new_trader(trader_data)

        # إرسال رسالة نجاح التسجيل مع أزرار العودة
        await query.edit_message_text(
            text=get_string(lang, "trader_success"),
            reply_markup=reply_markup
        )
    else:
        logger.error(
            "فشل حفظ بيانات التاجر: telegram_id=%s",
            trader_data["telegram_id"]
        )
        # إرسال رسالة الخطأ العامة مع أزرار العودة
        await query.edit_message_text(
            text=get_string(lang, "error_general"),
            reply_markup=reply_markup
        )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END


async def cancel_trader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية تسجيل التاجر عند كتابة أمر /cancel.

    الخطوات:
        1. استرجاع اللغة المحفوظة
        2. إرسال رسالة الإلغاء
        3. إنهاء المحادثة

    المعاملات:
        update: كائن التحديث (يُستدعى من CommandHandler)
        context: سياق البوت

    المُخرجات:
        int: ConversationHandler.END لإنهاء تدفق المحادثة
    """
    lang = context.user_data.get("lang", "ar")

    # إرسال رسالة الإلغاء مع إرشاد للبدء من جديد
    await update.message.reply_text(
        text=get_string(lang, "cancel")
    )

    # إنهاء تدفق المحادثة
    return ConversationHandler.END
```


### === ./main.py ===


```python
# ===================================================
# bot/main.py
# نقطة الدخول الرئيسية للبوت TurkTextileHub
# المرحلة الرابعة: إضافة ConversationHandler للتجار + معالج تغيير اللغة
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import states
from bot.config import BOT_TOKEN
from bot.handlers import start_handler, supplier_handler, trader_handler


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
    معالج الأخطاء العالمي - يعالج جميع الأخطاء أثناء تشغيل البوت.

    السلوك:
        - يتجاهل خطأ BadRequest الذي يحتوي على 'Query is too old'
        - يسجل جميع الأخطاء الأخرى في السجلات

    المعاملات:
        update: كائن التحديث (قد يكون None في بعض الحالات)
        context: سياق البوت الذي يحتوي على معلومات الخطأ
    """
    error = context.error

    # تجاهل خطأ الاستعلامات القديمة - يحدث عند الضغط على أزرار منتهية الصلاحية
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
        1. إنشاء كائن Application
        2. بناء ConversationHandler للموردين
        3. بناء ConversationHandler للتجار (جديد في المرحلة الرابعة)
        4. تسجيل المعالجات بالترتيب الصحيح
        5. تشغيل البوت بنظام polling
    """
    logger.info("جاري تشغيل بوت TurkTextileHub - المرحلة الرابعة...")

    # إنشاء كائن Application - نقطة تحكم البوت الرئيسية
    application = Application.builder().token(BOT_TOKEN).build()

    # ===================================================
    # ConversationHandler لتسجيل الموردين
    # per_message=False: مهم لتجنب التحذيرات مع CallbackQueryHandler
    # ===================================================
    supplier_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                supplier_handler.start_registration,
                pattern="^supplier$"
            )
        ],
        states={
            states.COMPANY_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_company_name
                )
            ],
            states.CONTACT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_contact_name
                )
            ],
            states.PHONE_NUMBER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    supplier_handler.received_phone
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", supplier_handler.cancel)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # ConversationHandler لتسجيل التجار (جديد - المرحلة الرابعة)
    # TRADER_PRODUCT يستخدم CallbackQueryHandler لأزرار الاختيار
    # ===================================================
    trader_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                trader_handler.start_trader_registration,
                pattern="^trader$"
            )
        ],
        states={
            # مرحلة استقبال الاسم الكامل
            states.TRADER_FULL_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_name
                )
            ],
            # مرحلة استقبال رقم الهاتف
            states.TRADER_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_phone
                )
            ],
            # مرحلة استقبال الدولة
            states.TRADER_COUNTRY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trader_handler.received_trader_country
                )
            ],
            # مرحلة اختيار نوع المنتج عبر InlineKeyboard
            states.TRADER_PRODUCT: [
                CallbackQueryHandler(
                    trader_handler.received_trader_product,
                    pattern="^product_(ready|fabric|shoes|misc)$"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", trader_handler.cancel_trader)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
    )

    # ===================================================
    # معالج تغيير اللغة (جديد - المرحلة الرابعة)
    # ===================================================
    change_lang_handler = CallbackQueryHandler(
        start_handler.change_language,
        pattern="^change_language$"
    )

    # معالج اختيار لغة محددة (ar/tr/en)
    set_lang_handler = CallbackQueryHandler(
        start_handler.set_language,
        pattern="^lang_(ar|tr|en)$"
    )

    # ===================================================
    # تسجيل المعالجات بالترتيب الصحيح - الترتيب مهم جداً
    # ConversationHandlers يجب أن تُسجَّل قبل أي CallbackQueryHandler منفصل
    # ===================================================

    # 1. معالج أمر /start
    application.add_handler(CommandHandler("start", start_handler.start))

    # 2. محادثة تسجيل الموردين
    application.add_handler(supplier_conv)

    # 3. محادثة تسجيل التجار (جديد)
    application.add_handler(trader_conv)

    # 4. معالج تغيير اللغة (جديد)
    application.add_handler(change_lang_handler)

    # 5. معالج اختيار لغة محددة (جديد)
    application.add_handler(set_lang_handler)

    # 6. معالج الأخطاء العالمي
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
```


### === ./services/__init__.py ===


```python
```


### === ./services/database_service.py ===


```python
# ===================================================
# bot/services/database_service.py
# خدمة قاعدة البيانات - التواصل مع Supabase عبر REST API HTTP
# تستخدم مكتبة requests فقط بدون أي مكتبة خارجية إضافية
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

import requests

from bot.config import SUPABASE_KEY, SUPABASE_URL

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# ===================================================
# رأس الطلبات المشتركة لجميع الاتصالات بـ Supabase
# يتضمن مفتاح API والتفويض ونوع المحتوى
# ===================================================
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


# ===================================================
# دوال الموردين
# ===================================================

def save_supplier(supplier_data: dict) -> bool:
    """
    يحفظ بيانات المورد الجديد في جدول suppliers في Supabase.

    يُرسل طلب POST إلى REST API ويتحقق من نجاح العملية.
    لا يُنشئ جدولاً جديداً - الجدول موجود بالفعل في Supabase.

    ملاحظة: نحفظ telegram_id في عمود user_id لعدم وجود عمود مستقل له.

    المعاملات:
        supplier_data (dict): قاموس يحتوي على:
            - telegram_id: معرّف المستخدم في تليجرام
            - company_name: اسم الشركة أو المتجر
            - contact_name: اسم جهة الاتصال
            - phone: رقم الهاتف مع رمز الدولة

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح (رمز 201)، False في أي حالة أخرى
    """
    # بناء رابط نقطة النهاية لجدول bot_registrations
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations"

    # ===================================================
    # تجهيز البيانات المراد إرسالها إلى Supabase
    # جدول bot_registrations مخصص للبوت بدون قيود Foreign Key
    # ===================================================
    payload = {
        "telegram_id": supplier_data.get("telegram_id"),
        "company_name": supplier_data.get("company_name"),
        "contact_name": supplier_data.get("contact_name"),
        "phone": supplier_data.get("phone"),
        "status": "pending",
    }

    try:
        # إرسال طلب POST لحفظ بيانات المورد
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        # التحقق من نجاح العملية - Supabase يُرجع 201 عند الإنشاء الناجح
        if response.status_code == 201:
            logger.info(
                "✅ تم حفظ المورد في Supabase بنجاح: telegram_id=%s",
                supplier_data.get("telegram_id")
            )
            return True

        # تسجيل تفاصيل الخطأ في حال فشل الطلب
        logger.error(
            "❌ فشل حفظ المورد في Supabase: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء حفظ المورد: %s", str(e)
        )
        return False


def check_supplier_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود مورد مسجل مسبقاً باستخدام معرّف تليجرام.

    يُرسل طلب GET للبحث عن سجل يطابق telegram_id في جدول bot_registrations.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام (كنص)

    المُخرجات:
        bool: True إذا كان المورد مسجلاً بالفعل، False إذا لم يكن أو حدث خطأ
    """
    # ===================================================
    # بناء رابط الاستعلام مع فلتر telegram_id من جدول bot_registrations
    # نستخدم eq. لمطابقة القيمة الدقيقة وselect=id لتحميل أقل قدر من البيانات
    # ===================================================
    url = f"{SUPABASE_URL}/rest/v1/bot_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        # إرسال طلب GET للبحث عن المورد
        response = requests.get(url, headers=HEADERS, timeout=10)

        # التحقق من نجاح الطلب
        if response.status_code == 200:
            results = response.json()

            # إذا كانت القائمة غير فارغة فالمورد مسجل مسبقاً
            if results:
                logger.info(
                    "⚠️ المورد مسجل مسبقاً في Supabase: telegram_id=%s",
                    telegram_id
                )
                return True

            # القائمة فارغة - المورد غير مسجل
            return False

        # تسجيل خطأ في حال فشل الطلب والرجوع بـ False
        logger.error(
            "❌ خطأ في التحقق من وجود المورد: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء التحقق من المورد: %s", str(e)
        )
        return False


# ===================================================
# دوال التجار (المرحلة الرابعة)
# ===================================================

def save_trader(trader_data: dict) -> bool:
    """
    يحفظ بيانات التاجر الجديد في جدول bot_trader_registrations في Supabase.

    يُرسل طلب POST إلى REST API ويتحقق من نجاح العملية.
    الجدول bot_trader_registrations يجب أن يكون موجوداً مسبقاً في Supabase.

    المعاملات:
        trader_data (dict): قاموس يحتوي على:
            - telegram_id: معرّف المستخدم في تليجرام (text)
            - full_name: الاسم الكامل للتاجر (text)
            - phone: رقم الهاتف مع رمز الدولة (text)
            - country: دولة التاجر (text)
            - product_interest: نوع المنتج المفضل (text)

    المُخرجات:
        bool: True إذا تم الحفظ بنجاح (رمز 201)، False في أي حالة أخرى
    """
    # بناء رابط نقطة النهاية لجدول التجار
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations"

    # ===================================================
    # تجهيز البيانات المراد إرسالها إلى Supabase
    # status يُضبط على 'pending' تلقائياً للتجار الجدد
    # ===================================================
    payload = {
        "telegram_id": trader_data.get("telegram_id"),
        "full_name": trader_data.get("full_name"),
        "phone": trader_data.get("phone"),
        "country": trader_data.get("country"),
        "product_interest": trader_data.get("product_interest"),
        "status": "pending",
    }

    try:
        # إرسال طلب POST لحفظ بيانات التاجر
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

        # التحقق من نجاح العملية - Supabase يُرجع 201 عند الإنشاء الناجح
        if response.status_code == 201:
            logger.info(
                "✅ تم حفظ التاجر في Supabase بنجاح: telegram_id=%s",
                trader_data.get("telegram_id")
            )
            return True

        # تسجيل تفاصيل الخطأ في حال فشل الطلب
        logger.error(
            "❌ فشل حفظ التاجر في Supabase: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء حفظ التاجر: %s", str(e)
        )
        return False


def check_trader_exists(telegram_id: str) -> bool:
    """
    يتحقق من وجود تاجر مسجل مسبقاً باستخدام معرّف تليجرام.

    يُرسل طلب GET للبحث عن سجل في جدول bot_trader_registrations.

    المعاملات:
        telegram_id (str): معرّف المستخدم في تليجرام (كنص)

    المُخرجات:
        bool: True إذا كان التاجر مسجلاً بالفعل، False إذا لم يكن أو حدث خطأ
    """
    # بناء رابط الاستعلام مع فلتر telegram_id
    url = f"{SUPABASE_URL}/rest/v1/bot_trader_registrations?telegram_id=eq.{telegram_id}&select=id"

    try:
        # إرسال طلب GET للبحث عن التاجر
        response = requests.get(url, headers=HEADERS, timeout=10)

        # التحقق من نجاح الطلب
        if response.status_code == 200:
            results = response.json()

            # إذا كانت القائمة غير فارغة فالتاجر مسجل مسبقاً
            if results:
                logger.info(
                    "⚠️ التاجر مسجل مسبقاً في Supabase: telegram_id=%s",
                    telegram_id
                )
                return True

            # القائمة فارغة - التاجر غير مسجل
            return False

        # تسجيل خطأ في حال فشل الطلب
        logger.error(
            "❌ خطأ في التحقق من وجود التاجر: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال
        logger.error(
            "❌ خطأ في الاتصال بـ Supabase أثناء التحقق من التاجر: %s", str(e)
        )
        return False
```


### === ./services/language_service.py ===


```python
# ===================================================
# bot/services/language_service.py
# خدمة اللغات - تحميل ملفات الترجمة وإرجاع النصوص المترجمة
# تدعم: العربية (ar)، التركية (tr)، الإنجليزية (en)
# ===================================================

import json
import os

# المسار الكامل لمجلد الترجمات
_TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "translations")

# قاموس يخزن جميع الترجمات بعد التحميل
# الشكل: {"ar": {...}, "tr": {...}, "en": {...}}
_translations: dict = {}


def load_translations() -> dict:
    """
    تقرأ ملفات الترجمة الثلاثة وتخزنها في قاموس.
    يتم استدعاء هذه الدالة مرة واحدة عند استيراد الوحدة.
    
    المُخرجات:
        dict: قاموس يحتوي على جميع الترجمات مقسمة حسب اللغة
    """
    translations = {}
    
    # قائمة اللغات المدعومة مع أسماء ملفاتها
    supported_languages = ["ar", "tr", "en"]
    
    for lang in supported_languages:
        # بناء مسار ملف الترجمة
        file_path = os.path.join(_TRANSLATIONS_DIR, f"{lang}.json")
        
        try:
            # قراءة ملف JSON بترميز UTF-8 لدعم الأحرف العربية والتركية
            with open(file_path, "r", encoding="utf-8") as f:
                translations[lang] = json.load(f)
        except FileNotFoundError:
            # في حال عدم وجود الملف نسجل تحذيراً ونضع قاموساً فارغاً
            print(f"⚠️ تحذير: ملف الترجمة غير موجود: {file_path}")
            translations[lang] = {}
        except json.JSONDecodeError as e:
            # في حال وجود خطأ في صياغة JSON
            print(f"⚠️ تحذير: خطأ في قراءة ملف الترجمة {file_path}: {e}")
            translations[lang] = {}
    
    return translations


def get_string(lang: str, key: str) -> str:
    """
    ترجع النص المترجم للمفتاح المحدد باللغة المحددة.
    
    المعاملات:
        lang (str): رمز اللغة المطلوبة (ar, tr, en)
        key (str): مفتاح النص في ملف الترجمة
    
    المُخرجات:
        str: النص المترجم، أو النص العربي كاحتياطي، أو المفتاح نفسه
    
    منطق الاحتياطي:
        1. إذا وُجدت اللغة والمفتاح → يُرجع الترجمة المطلوبة
        2. إذا لم توجد اللغة أو المفتاح → يُرجع النص العربي
        3. إذا لم يوجد المفتاح في العربية أيضاً → يُرجع المفتاح نفسه
    """
    # البحث في اللغة المطلوبة أولاً
    if lang in _translations and key in _translations[lang]:
        return _translations[lang][key]
    
    # الاحتياطي: البحث في العربية
    if "ar" in _translations and key in _translations["ar"]:
        return _translations["ar"][key]
    
    # آخر احتياطي: إرجاع المفتاح نفسه إذا لم يوجد في أي لغة
    return key


# ===================================================
# تحميل الترجمات مرة واحدة عند استيراد الوحدة
# هذا يضمن عدم تكرار قراءة الملفات في كل طلب
# ===================================================
_translations = load_translations()
```


### === ./services/notification_service.py ===


```python
# ===================================================
# bot/services/notification_service.py
# خدمة الإشعارات الفورية للأدمن عبر Telegram Bot API مباشرة
# تُرسل إشعاراً فورياً لكل تسجيل جديد (مورد أو تاجر)
# تستخدم requests مباشرة بدون python-telegram-bot
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from datetime import datetime

import requests

from bot.config import BOT_TOKEN, ADMIN_TELEGRAM_ID

# سجل خاص بهذه الخدمة
logger = logging.getLogger(__name__)

# ===================================================
# رابط Telegram Bot API لإرسال الرسائل
# يُستخدم مباشرة بدون أي مكتبة وسيطة
# ===================================================
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def _send_admin_message(text: str) -> bool:
    """
    دالة داخلية مساعدة: ترسل رسالة نصية HTML للأدمن عبر Telegram API.

    تُستخدم من قِبل notify_new_supplier و notify_new_trader.
    الإشعار الفاشل لا يوقف البوت - يُسجَّل الخطأ فقط.

    المعاملات:
        text (str): نص الرسالة بصيغة HTML

    المُخرجات:
        bool: True إذا وصلت الرسالة بنجاح، False في أي حالة أخرى
    """
    # التحقق من أن معرف الأدمن مضبوط قبل المحاولة
    if not ADMIN_TELEGRAM_ID:
        logger.warning("⚠️ ADMIN_TELEGRAM_ID غير مضبوط - تم تخطي إشعار الأدمن")
        return False

    # ===================================================
    # تجهيز جسم الطلب بصيغة JSON
    # parse_mode=HTML لتفعيل التنسيق (Bold, Italic...)
    # ===================================================
    payload = {
        "chat_id": ADMIN_TELEGRAM_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        # إرسال الطلب مع timeout لتجنب التعليق اللانهائي
        response = requests.post(TELEGRAM_API_URL, json=payload, timeout=10)

        # التحقق من نجاح الإرسال
        if response.status_code == 200:
            logger.info("✅ تم إرسال الإشعار للأدمن بنجاح")
            return True

        # تسجيل تفاصيل الخطأ دون إيقاف البوت
        logger.error(
            "❌ فشل إرسال الإشعار للأدمن: status=%d, response=%s",
            response.status_code,
            response.text
        )
        return False

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الشبكة والاتصال - لا تُوقف البوت
        logger.error("❌ خطأ في الاتصال بـ Telegram API عند إرسال الإشعار: %s", str(e))
        return False


def notify_new_supplier(supplier_data: dict) -> bool:
    """
    يُرسل إشعاراً فورياً للأدمن عند تسجيل مورد جديد.

    يُنسّق رسالة HTML بتفاصيل المورد ويُرسلها لمعرّف الأدمن المضبوط.
    في حال الفشل يُسجَّل الخطأ فقط دون إيقاف البوت.

    المعاملات:
        supplier_data (dict): قاموس يحتوي على:
            - company_name: اسم الشركة أو المتجر
            - contact_name: اسم جهة الاتصال
            - phone: رقم الهاتف
            - telegram_id: معرّف تليجرام

    المُخرجات:
        bool: True عند نجاح الإرسال، False عند الفشل
    """
    # ===================================================
    # تجهيز الوقت الحالي بصيغة موحدة للتقارير
    # ===================================================
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ===================================================
    # بناء نص الرسالة بصيغة HTML مع إيموجي توضيحية
    # ===================================================
    message_text = (
        "🏭 <b>مورد جديد تسجّل!</b>\n\n"
        f"👤 <b>اسم الشركة:</b> {supplier_data.get('company_name', 'غير محدد')}\n"
        f"🙋 <b>جهة الاتصال:</b> {supplier_data.get('contact_name', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {supplier_data.get('phone', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {supplier_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    # إرسال الرسالة عبر الدالة المساعدة المشتركة
    return _send_admin_message(message_text)


def notify_new_trader(trader_data: dict) -> bool:
    """
    يُرسل إشعاراً فورياً للأدمن عند تسجيل تاجر جديد.

    يُنسّق رسالة HTML بتفاصيل التاجر ويُرسلها لمعرّف الأدمن المضبوط.
    في حال الفشل يُسجَّل الخطأ فقط دون إيقاف البوت.

    المعاملات:
        trader_data (dict): قاموس يحتوي على:
            - full_name: الاسم الكامل للتاجر
            - phone: رقم الهاتف
            - country: الدولة
            - product_interest: نوع المنتج المفضل
            - telegram_id: معرّف تليجرام

    المُخرجات:
        bool: True عند نجاح الإرسال، False عند الفشل
    """
    # ===================================================
    # تجهيز الوقت الحالي بصيغة موحدة للتقارير
    # ===================================================
    registration_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ===================================================
    # بناء نص الرسالة بصيغة HTML مع إيموجي توضيحية
    # ===================================================
    message_text = (
        "🛒 <b>تاجر جديد تسجّل!</b>\n\n"
        f"👤 <b>الاسم الكامل:</b> {trader_data.get('full_name', 'غير محدد')}\n"
        f"📞 <b>الهاتف:</b> {trader_data.get('phone', 'غير محدد')}\n"
        f"🌍 <b>الدولة:</b> {trader_data.get('country', 'غير محدد')}\n"
        f"🏷 <b>اهتمامات المنتجات:</b> {trader_data.get('product_interest', 'غير محدد')}\n"
        f"🆔 <b>معرّف تليجرام:</b> {trader_data.get('telegram_id', 'غير محدد')}\n"
        f"📅 <b>وقت التسجيل:</b> {registration_time}\n\n"
        "⏳ الحالة: قيد المراجعة"
    )

    # إرسال الرسالة عبر الدالة المساعدة المشتركة
    return _send_admin_message(message_text)
```


### === ./states.py ===


```python
# ===================================================
# bot/states.py
# ثوابت حالات المحادثة - تُستخدم في ConversationHandler
# كل رقم يمثل مرحلة من مراحل التسجيل
# KAYISOFT - إسطنبول، تركيا
# ===================================================

# ===================================================
# حالات تسجيل الموردين (المرحلة 1-3)
# ===================================================

# مرحلة إدخال اسم الشركة أو المتجر
COMPANY_NAME = 1

# مرحلة إدخال اسم الشخص المسؤول للتواصل
CONTACT_NAME = 2

# مرحلة إدخال رقم الهاتف مع رمز الدولة
PHONE_NUMBER = 3

# ===================================================
# حالات تسجيل التجار (المرحلة الرابعة)
# الأرقام تبدأ من 10 لتجنب التعارض مع حالات الموردين
# ===================================================

# مرحلة إدخال الاسم الكامل للتاجر
TRADER_FULL_NAME = 10

# مرحلة إدخال رقم هاتف التاجر
TRADER_PHONE = 11

# مرحلة إدخال دولة التاجر
TRADER_COUNTRY = 12

# مرحلة اختيار نوع المنتج المفضل عبر InlineKeyboard
TRADER_PRODUCT = 13
```


---

## 2. المتطلبات الفنية التفصيلية للمرحلة السادسة

الآن، هذه هي المتطلبات الكاملة. اتبعها بدقة.


# متطلبات المرحلة السادسة: إعادة الهيكلة وإدارة المنتجات

**المستند:** `PHASE_6_REQUIREMENTS.md`
**الإصدار:** 1.0
**التاريخ:** 27 فبراير 2026

## 1. الهدف الأساسي

إعادة هيكلة قاعدة الكود لتكون قابلة للتوسع، إكمال تدفقات تسجيل المستخدمين حسب الوثيقة، وبناء الميزات الأساسية لإدارة المنتجات (الإضافة والتصفح).

---

## 2. الهيكل الجديد للملفات (New File Structure)

يجب إعادة تنظيم الملفات لتصبح بالشكل التالي. هذا يتطلب نقل بعض الوظائف وإنشاء ملفات جديدة.

```
bot/
├── __init__.py
├── config.py
├── main.py
├── states.py
|
├── handlers/
│   ├── __init__.py
│   ├── admin_handler.py      # (فارغ حالياً، للمستقبل)
│   ├── browse_handler.py     # (جديد) تصفح المنتجات
│   ├── product_handler.py    # (جديد) إضافة وتعديل المنتجات
│   ├── start_handler.py      # (مُعدّل) إصلاح رسالة الترحيب
│   ├── supplier_handler.py   # (مُعدّل) تسجيل المورد فقط
│   └── trader_handler.py     # (مُعدّل) تسجيل التاجر فقط
|
├── services/
│   ├── __init__.py
│   ├── database_service.py   # (مُعدّل) إضافة دوال المنتجات
│   ├── language_service.py   # (مُعدّل) إضافة نصوص جديدة
│   └── notification_service.py # (لا تغيير)
|
└── translations/
    ├── ar.json               # (مُعدّل) نصوص جديدة
    ├── en.json               # (مُعدّل) نصوص جديدة
    └── tr.json               # (مُعدّل) نصوص جديدة
```

---

## 3. تحديثات قاعدة البيانات (Supabase Schema)

يجب تنفيذ أوامر SQL التالية في Supabase لإضافة الجداول والحقول الجديدة.

### 3.1. جدول المنتجات الجديد: `products`

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    price TEXT,
    images TEXT[] NOT NULL, -- مصفوفة من file_id الخاص بالصور
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- تفعيل RLS
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

-- سياسة: المورد يرى منتجاته فقط
CREATE POLICY "Suppliers can view their own products" ON products
FOR SELECT USING (supplier_id = (SELECT id FROM suppliers WHERE user_id = auth.uid()));

-- سياسة: المورد يضيف منتجات لنفسه فقط
CREATE POLICY "Suppliers can insert their own products" ON products
FOR INSERT WITH CHECK (supplier_id = (SELECT id FROM suppliers WHERE user_id = auth.uid()));

-- سياسة: السماح للجميع برؤية المنتجات النشطة
CREATE POLICY "Public can view active products" ON products
FOR SELECT USING (is_active = true);
```

### 3.2. تحديث جدول الموردين: `suppliers`

إضافة حقل `city` و `sales_telegram_id`.

```sql
ALTER TABLE suppliers
ADD COLUMN city TEXT,
ADD COLUMN sales_telegram_id BIGINT;
```

---

## 4. تعديلات على التدفقات الحالية

### 4.1. إصلاح رسالة الترحيب (`start_handler.py`)

**المشكلة:** رسالة الترحيب الحالية تعرض `"اختر دورك:"` كنص منفصل، مما يسبب ارتباكاً في الواجهة.

**الحل:** يجب دمج النص مع الأزرار في رسالة واحدة باستخدام `reply_markup`.

**الكود الحالي (خاطئ):**
```python
await update.message.reply_text(get_string("welcome", lang))
await update.message.reply_text(get_string("role_selection", lang), reply_markup=keyboard)
```

**الكود المطلوب (صحيح):**
```python
# رسالة واحدة فقط تجمع النص والأزرار
welcome_message = get_string("welcome", lang) + "\n\n" + get_string("role_selection", lang)
await update.message.reply_text(welcome_message, reply_markup=keyboard)
```

### 4.2. إكمال تسجيل المورد (`supplier_handler.py`)

يجب تعديل تدفق تسجيل المورد ليشمل سؤالين إضافيين حسب وثيقة المواصفات:

1.  **المدينة (City):** بعد سؤال "اسم المسؤول"، يجب سؤال المورد عن مدينته مع أزرار.
2.  **موظف المبيعات (Sales Rep):** بعد سؤال "الهاتف"، يجب سؤال المورد إذا كان لديه موظف مبيعات مخصص.

**التدفق الجديد:**
1.  `ask_company_name` (لا تغيير)
2.  `ask_contact_name` (لا تغيير)
3.  `ask_city` **(جديد):**
    *   النص: `"في أي مدينة يقع متجرك؟"`
    *   الأزرار: `[إسطنبول]`, `[بورصة]`, `[إزمير]`, `[أخرى]`
4.  `ask_phone` (لا تغيير)
5.  `ask_sales_rep` **(جديد):**
    *   النص: `"هل لديك موظف مبيعات مخصص لاستقبال الطلبات؟"`
    *   الأزرار: `[نعم، لدي]`, `[لا، سأستقبلها أنا]`
6.  `ask_sales_rep_username` **(جديد، فقط إذا كانت الإجابة "نعم"):**
    *   النص: `"أدخل يوزرنيم تليجرام الخاص به (مثال: @username)"`
7.  `finish_supplier_registration` (مُعدّل): يجب أن يحفظ الحقول الجديدة (`city`, `sales_telegram_id`) في قاعدة البيانات.

### 4.3. إكمال تسجيل التاجر (`trader_handler.py`)

**المشكلة:** السؤال الحالي هو "ما نوع المنتجات التي تهتم بها؟"، بينما الوثيقة تطلب "ما نوع نشاطك التجاري؟".

**الحل:** يجب تغيير السؤال والأزرار.

**التدفق الجديد:**
1.  `ask_trader_name` (لا تغيير)
2.  `ask_trader_phone` (لا تغيير)
3.  `ask_trader_country` (لا تغيير)
4.  `ask_business_type` **(تعديل كامل):**
    *   النص: `"ما هو نوع نشاطك التجاري؟"`
    *   الأزرار: `[متجر إلكتروني]`, `[محل ملابس]`, `[موزع]`, `[أخرى]`
5.  `finish_trader_registration` (مُعدّل): يجب أن يحفظ `business_type` بدلاً من `product_interest`.

---

## 5. الميزات الجديدة (New Features)

### 5.1. إضافة منتج جديد (`product_handler.py`)

هذا تدفق جديد بالكامل يسمح للموردين بإضافة منتجاتهم. يجب أن يكون مرناً وسهلاً.

**الأمر:** `/add_product`

**التدفق:**
1.  **`start_add_product`:**
    *   يستجيب لأمر `/add_product`.
    *   النص: `"لإضافة منتج جديد، أرسل لي صوره (من 1 إلى 5 صور دفعة واحدة)."`
    *   الحالة: `GETTING_IMAGES`

2.  **`get_images`:**
    *   يستقبل رسالة تحتوي على صورة واحدة أو أكثر.
    *   يحفظ `file_id` لكل صورة في `context.user_data['images']`.
    *   النص: `"رائع! الآن اختر فئة المنتج:"`
    *   الأزرار: `[عبايات]`, `[فساتين]`, `[ملابس محجبات]`, `[أطقم]`, `[أخرى]`
    *   الحالة: `GETTING_CATEGORY`

3.  **`get_category`:**
    *   يستقبل اختيار الفئة من الأزرار.
    *   يحفظ الفئة في `context.user_data['category']`.
    *   النص: `"أدخل السعر التقريبي للمنتج (اختياري). يمكنك كتابة نص مثل '10-12 دولار' أو 'حسب الكمية'."`
    *   الأزرار: `[تخطي]`
    *   الحالة: `GETTING_PRICE`

4.  **`get_price` (أو `skip_price`):**
    *   يستقبل نص السعر أو ضغطة زر "تخطي".
    *   يحفظ السعر في `context.user_data['price']`.
    *   **المعاينة:** يعرض للمورد رسالة معاينة تحتوي على:
        *   الصورة الأولى كـ `send_photo`.
        *   النص: `"== معاينة المنتج ==
الفئة: {category}
السعر: {price}

هل تريد نشر هذا المنتج؟"`
    *   الأزرار: `[✅ نعم، انشر الآن]`, `[❌ إلغاء]`
    *   الحالة: `CONFIRM_ADD_PRODUCT`

5.  **`finish_add_product`:**
    *   يستقبل ضغطة زر `✅ نعم، انشر الآن`.
    *   يجمع كل البيانات من `context.user_data`.
    *   يستدعي `database_service.add_product()` لحفظ المنتج في قاعدة البيانات.
    *   النص: `"✅ تم نشر منتجك بنجاح!"`
    *   ينهي المحادثة `ConversationHandler.END`.

### 5.2. تصفح المنتجات (`browse_handler.py`)

تدفق جديد يسمح للمشترين (التجار) بتصفح المنتجات المتاحة.

**الأمر:** `/browse`

**التدفق:**
1.  **`start_browse`:**
    *   يستجيب لأمر `/browse`.
    *   يستدعي `database_service.get_all_categories()` للحصول على الفئات المتاحة.
    *   النص: `"🔍 اختر فئة المنتجات التي تريد تصفحها:"`
    *   الأزرار: قائمة ديناميكية بالفئات المتاحة + زر `[عرض الكل]`.
    *   الحالة: `BROWSING_PRODUCTS`

2.  **`browse_products`:**
    *   يستقبل اختيار الفئة.
    *   يستدعي `database_service.get_products_by_category(category)`.
    *   **عرض المنتجات:** يعرض المنتجات بشكل تفاعلي (Pagination):
        *   يرسل أول منتج كرسالة (صورة + نص).
        *   النص: `الفئة: {category}
السعر: {price}
المورد: {supplier_name}`
        *   الأزرار: `[➡️ التالي]`, `[📋 طلب عرض سعر]`, `[🔙 العودة للفئات]`
    *   يحفظ قائمة المنتجات وفهرس المنتج الحالي في `context.user_data`.

3.  **`next_product` / `prev_product`:**
    *   يستجيب لضغط أزرار التنقل.
    *   يعدل الرسالة الحالية (`edit_message_media`, `edit_message_text`) لعرض المنتج التالي/السابق.

---

## 6. تحديثات ملفات الترجمة (`translations/*.json`)

يجب إضافة النصوص الجديدة المستخدمة في التدفقات أعلاه إلى ملفات الترجمة الثلاثة (ar, en, tr).

**مثال للنصوص الجديدة (بالعربية):**
*   `ask_city`: "في أي مدينة يقع متجرك؟"
*   `ask_sales_rep`: "هل لديك موظف مبيعات مخصص لاستقبال الطلبات؟"
*   `ask_sales_rep_username`: "أدخل يوزرنيم تليجرام الخاص به (مثال: @username)"
*   `ask_business_type`: "ما هو نوع نشاطك التجاري؟"
*   `add_product_start`: "لإضافة منتج جديد، أرسل لي صوره (من 1 إلى 5 صور دفعة واحدة)."
*   `add_product_get_category`: "رائع! الآن اختر فئة المنتج:"
*   `add_product_get_price`: "أدخل السعر التقريبي للمنتج (اختياري). يمكنك كتابة نص مثل '10-12 دولار' أو 'حسب الكمية'."
*   `add_product_confirm`: "== معاينة المنتج ==\nالفئة: {category}\nالسعر: {price}\n\nهل تريد نشر هذا المنتج؟"
*   `add_product_success`: "✅ تم نشر منتجك بنجاح!"
*   `browse_start`: "🔍 اختر فئة المنتجات التي تريد تصفحها:"


---

## 3. المخرجات المطلوبة (Deliverables)

أريد منك أن تسلمني **الكود الكامل للمشروع بعد إعادة الهيكلة**.

**لا تسلمني الملفات بشكل منفصل**، بل سلمني الكود الكامل لكل ملف، ملف تلو الآخر، بالترتيب التالي:

1.  `bot/config.py`
2.  `bot/states.py`
3.  `bot/translations/ar.json`
4.  `bot/translations/en.json`
5.  `bot/translations/tr.json`
6.  `bot/services/database_service.py`
7.  `bot/services/language_service.py`
8.  `bot/handlers/start_handler.py`
9.  `bot/handlers/supplier_handler.py`
10. `bot/handlers/trader_handler.py`
11. `bot/handlers/product_handler.py`
12. `bot/handlers/browse_handler.py`
13. `bot/main.py`

تأكد من أن الكود نظيف، موثق جيداً، ويتبع أفضل الممارسات في `python-telegram-bot`.

شكراً لك!
