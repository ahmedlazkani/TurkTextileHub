# ===================================================
# bot/handlers/product_handler.py
# معالج إضافة المنتجات — ربط بـ KAYISOFT API
#
# التحديث: إعادة كتابة كاملة لدعم:
#   1. رفع الصور لـ MinIO عبر image_service
#   2. شجرة التصنيف الديناميكية من KAYISOFT API
#   3. إرسال المنتج لـ KAYISOFT بدلاً من Supabase مباشرة
#   4. fallback لـ Supabase إذا لم يكن KAYISOFT مضبوطاً
#
# التدفق الجديد:
#   /add_product ← الصور ← الفئة الرئيسية ← الفئة الفرعية
#   ← الكمية الدنيا ← معاينة ← نشر → KAYISOFT API
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, ConversationHandler

from bot import states
from bot.services import database_service, notification_service
from bot.services.language_service import get_string
from bot.services import kayisoft_api
from bot.services import image_service

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# ثوابت وبيانات ثابتة
# ──────────────────────────────────────────────────────────

# شجرة التصنيف الثابتة (fallback إذا لم يستجب KAYISOFT API)
# تُستبدل بالشجرة الديناميكية من API عند الإمكان
_FALLBACK_CATEGORIES = {
    "cat_abayas":  "Abayas",
    "cat_dresses": "Dresses",
    "cat_hijab":   "Hijab Clothing",
    "cat_sets":    "Sets",
    "cat_other":   "Other",
}


# ──────────────────────────────────────────────────────────
# دوال بناء لوحات المفاتيح
# ──────────────────────────────────────────────────────────

def _build_category_keyboard(lang: str, categories: dict = None) -> InlineKeyboardMarkup:
    """
    يبني لوحة مفاتيح اختيار الفئة الرئيسية.

    يستخدم الشجرة الديناميكية من KAYISOFT إذا توفرت،
    أو يرجع للفئات الثابتة كـ fallback.

    المدخلات:
        lang       (str) : رمز اللغة
        categories (dict): الفئات من KAYISOFT API أو None للـ fallback

    المخرجات:
        InlineKeyboardMarkup: لوحة مفاتيح الفئات
    """
    if categories:
        keyboard = [
            [InlineKeyboardButton(text=name, callback_data=f"kcat_{cat_id}")]
            for cat_id, name in list(categories.items())[:8]  # بحد أقصى 8 فئات
        ]
    else:
        keyboard = [
            [InlineKeyboardButton(text=get_string(lang, "category_abayas"), callback_data="cat_abayas")],
            [InlineKeyboardButton(text=get_string(lang, "category_dresses"), callback_data="cat_dresses")],
            [InlineKeyboardButton(text=get_string(lang, "category_hijab"),   callback_data="cat_hijab")],
            [InlineKeyboardButton(text=get_string(lang, "category_sets"),    callback_data="cat_sets")],
            [InlineKeyboardButton(text=get_string(lang, "category_other"),   callback_data="cat_other")],
        ]
    return InlineKeyboardMarkup(keyboard)


# ──────────────────────────────────────────────────────────
# جلب شجرة التصنيف من KAYISOFT API
# ──────────────────────────────────────────────────────────

def _fetch_kayisoft_categories() -> dict:
    """
    يجلب شجرة التصنيف الديناميكية من KAYISOFT API.

    المنطق:
        1. تحقق من cache في Supabase (مفتاح: kayisoft_categories)
        2. إذا لم يوجد، اجلب من KAYISOFT API
        3. احفظ في cache لمدة 6 ساعات
        4. إذا فشل، أعد قاموساً فارغاً (يستخدم الـ fallback)

    المخرجات:
        dict: {category_id: category_name} أو {} عند الفشل
    """
    # تحقق من cache
    cached = database_service.get_cache("kayisoft_categories")
    if cached and isinstance(cached, dict):
        logger.debug(f"💾 cache hit: kayisoft_categories ({len(cached)} فئة)")
        return cached

    # جلب من KAYISOFT API
    try:
        result = kayisoft_api._get("/api/seller/categories")
        if result and isinstance(result, list):
            categories = {
                str(cat.get("id")): cat.get("name") or cat.get("name_ar") or "فئة"
                for cat in result
                if cat.get("id")
            }
            if categories:
                database_service.set_cache("kayisoft_categories", categories, ttl_hours=6)
                logger.info(f"✅ تم جلب {len(categories)} فئة من KAYISOFT API")
                return categories
    except Exception as e:
        logger.warning(f"⚠️ فشل جلب فئات KAYISOFT: {e}")

    return {}


# ──────────────────────────────────────────────────────────
# نقطة الدخول: /add_product
# ──────────────────────────────────────────────────────────

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق إضافة منتج عند كتابة /add_product.

    يتحقق من تسجيل المورد وموافقته قبل البدء.

    المدخلات:
        update  (Update)              : تحديث تليجرام
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.GETTING_IMAGES إذا مورد معتمد، ConversationHandler.END إذا لم يكن
    """
    lang = context.user_data.get("lang", "ar")
    telegram_id = str(update.effective_user.id)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    # التحقق من تسجيل المورد
    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if not supplier:
        await update.message.reply_text(text=get_string(lang, "not_registered_supplier"))
        return ConversationHandler.END

    if supplier.get("status") != "approved":
        await update.message.reply_text(
            "⏳ حسابكم قيد المراجعة. سيتم إشعاركم عند الموافقة."
        )
        return ConversationHandler.END

    # تهيئة بيانات الجلسة
    context.user_data["supplier_id"]   = supplier.get("id")
    context.user_data["supplier_name"] = supplier.get("company_name", "")
    context.user_data["telegram_id"]   = telegram_id
    context.user_data["images"]        = []  # file_ids من تليجرام
    context.user_data["image_urls"]    = []  # روابط MinIO بعد الرفع

    await update.message.reply_text(text=get_string(lang, "add_product_start"))
    return states.GETTING_IMAGES


async def start_add_product_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ تدفق إضافة منتج عند الضغط على زر 'إضافة منتج جديد'.

    المدخلات:
        update  (Update)              : تحديث تليجرام (callback_query)
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.GETTING_IMAGES أو ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    telegram_id = str(query.from_user.id)

    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    supplier = database_service.get_supplier_by_telegram_id(telegram_id)
    if not supplier:
        await query.answer(text=get_string(lang, "not_registered_supplier"), show_alert=True)
        return ConversationHandler.END

    if supplier.get("status") != "approved":
        await query.answer("⏳ حسابكم قيد المراجعة", show_alert=True)
        return ConversationHandler.END

    context.user_data["supplier_id"]   = supplier.get("id")
    context.user_data["supplier_name"] = supplier.get("company_name", "")
    context.user_data["telegram_id"]   = telegram_id
    context.user_data["images"]        = []
    context.user_data["image_urls"]    = []

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=get_string(lang, "add_product_start"),
    )
    return states.GETTING_IMAGES


# ──────────────────────────────────────────────────────────
# استقبال الصور
# ──────────────────────────────────────────────────────────

async def get_images(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل صور المنتج ويحفظ file_id لكل صورة.

    يقبل حتى 5 صور. بعد أول صورة يطلب الفئة مباشرة.

    المدخلات:
        update  (Update)              : تحديث تليجرام
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.GETTING_CATEGORY بعد استقبال الصورة
    """
    lang = context.user_data.get("lang", "ar")

    if not update.message.photo:
        await update.message.reply_text(text=get_string(lang, "add_product_no_images"))
        return states.GETTING_IMAGES

    # جلب أعلى جودة للصورة
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # إضافة للقائمة (بحد أقصى 5)
    images = context.user_data.get("images", [])
    if len(images) < 5:
        images.append(file_id)
        context.user_data["images"] = images

    logger.info(
        "📸 صورة %d/%d مُستقبَلة | supplier=%s",
        len(images), 5, context.user_data.get("supplier_id")
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    # جلب الفئات من KAYISOFT (ديناميكي)
    categories = _fetch_kayisoft_categories()

    await update.message.reply_text(
        text=get_string(lang, "add_product_get_category"),
        reply_markup=_build_category_keyboard(lang, categories if categories else None),
    )
    return states.GETTING_CATEGORY


# ──────────────────────────────────────────────────────────
# اختيار الفئة
# ──────────────────────────────────────────────────────────

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل اختيار الفئة (من الشجرة الديناميكية أو الثابتة) ويطلب السعر.

    المدخلات:
        update  (Update)              : تحديث تليجرام (callback_query)
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.GETTING_PRICE
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()

    data = query.data

    # فئة KAYISOFT ديناميكية: kcat_{id}
    if data.startswith("kcat_"):
        category_id = data.replace("kcat_", "")
        # جلب الاسم من الـ cache
        categories = _fetch_kayisoft_categories()
        category_name = categories.get(category_id, "Other")
        context.user_data["category"]    = category_name
        context.user_data["category_id"] = category_id
    else:
        # فئة ثابتة (fallback)
        category_name = _FALLBACK_CATEGORIES.get(data, "Other")
        context.user_data["category"]    = category_name
        context.user_data["category_id"] = None

    # طلب السعر مع زر التخطي
    keyboard = [[
        InlineKeyboardButton(
            text=get_string(lang, "skip_btn"),
            callback_data="price_skip"
        )
    ]]

    await query.edit_message_text(
        text=get_string(lang, "add_product_get_price"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return states.GETTING_PRICE


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل نص السعر ويعرض معاينة المنتج.

    المدخلات:
        update  (Update)              : تحديث تليجرام
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    lang = context.user_data.get("lang", "ar")
    context.user_data["price"] = update.message.text.strip()
    return await _show_product_preview(update.message, context, lang)


async def skip_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يتجاوز إدخال السعر ويعرض معاينة المنتج.

    المدخلات:
        update  (Update)              : تحديث تليجرام (callback_query)
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")
    await query.answer()
    context.user_data["price"] = None
    return await _show_product_preview(query.message, context, lang)


# ──────────────────────────────────────────────────────────
# معاينة المنتج
# ──────────────────────────────────────────────────────────

async def _show_product_preview(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    """
    دالة داخلية: تعرض معاينة المنتج قبل النشر.

    المنطق:
        - ترسل أول صورة مع نص المعاينة
        - أزرار التأكيد والإلغاء

    المدخلات:
        message: كائن الرسالة أو الاستجابة
        context: سياق البوت
        lang   : رمز اللغة

    المخرجات:
        int: states.CONFIRM_ADD_PRODUCT
    """
    category = context.user_data.get("category", "Other")
    price    = context.user_data.get("price") or "—"
    images   = context.user_data.get("images", [])

    preview_text = get_string(lang, "add_product_confirm").format(
        category=category,
        price=price,
    )

    keyboard = [
        [InlineKeyboardButton(text=get_string(lang, "publish_btn"),  callback_data="product_confirm_yes")],
        [InlineKeyboardButton(text=get_string(lang, "cancel_btn"),   callback_data="product_confirm_no")],
    ]

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    if images:
        await context.bot.send_photo(
            chat_id=message.chat_id,
            photo=images[0],
            caption=preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return states.CONFIRM_ADD_PRODUCT


# ──────────────────────────────────────────────────────────
# تأكيد النشر — القلب الرئيسي
# ──────────────────────────────────────────────────────────

async def finish_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يستقبل تأكيد النشر ويرفع الصور ثم يرسل المنتج لـ KAYISOFT API.

    المنطق الكامل:
        1. رفع الصور إلى MinIO عبر image_service
        2. إرسال المنتج لـ KAYISOFT API (submit_product)
        3. fallback: حفظ في Supabase مباشرة إذا فشل KAYISOFT
        4. إشعار الأدمن بالمنتج الجديد
        5. مسح بيانات الجلسة

    المدخلات:
        update  (Update)              : تحديث تليجرام (callback_query)
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: ConversationHandler.END
    """
    query = update.callback_query
    lang = context.user_data.get("lang", "ar")

    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    telegram_id  = context.user_data.get("telegram_id")
    supplier_id  = context.user_data.get("supplier_id")
    category     = context.user_data.get("category")
    category_id  = context.user_data.get("category_id")
    price        = context.user_data.get("price")
    file_ids     = context.user_data.get("images", [])

    # 1. رفع الصور إلى MinIO
    image_urls = []
    if file_ids:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
        image_urls = image_service.upload_multiple_photos(file_ids)
        if not image_urls:
            # إذا فشل الرفع، نستمر بدون صور
            logger.warning("⚠️ فشل رفع الصور — سيُحفظ المنتج بدون صور")

    # 2. بناء بيانات المنتج
    product_data = {
        "telegram_id":   telegram_id,
        "supplier_id":   supplier_id,
        "category":      category,
        "category_id":   category_id,
        "price":         price,
        "images":        file_ids,      # file_ids للـ legacy
        "image_urls":    image_urls,    # روابط MinIO للـ KAYISOFT
    }

    success = False

    # 3. محاولة الإرسال لـ KAYISOFT API أولاً
    kayisoft_result = kayisoft_api.submit_product(product_data)
    if kayisoft_result:
        logger.info("✅ تم إرسال المنتج لـ KAYISOFT API: %s", telegram_id)
        success = True
    else:
        # 4. fallback: حفظ مباشر في Supabase
        logger.warning("⚠️ KAYISOFT API غير متاح — fallback إلى Supabase")
        supabase_data = {**product_data, "images": image_urls or file_ids}
        success = database_service.add_product(supabase_data)
        if success:
            logger.info("✅ تم حفظ المنتج في Supabase مباشرة: %s", telegram_id)

    if success:
        # 5. إشعار الأدمن
        supplier_info = {"company_name": context.user_data.get("supplier_name", "غير محدد")}
        notification_service.notify_new_product(supplier_info, product_data)

        try:
            await query.edit_message_caption(caption=get_string(lang, "add_product_success"))
        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=get_string(lang, "add_product_success"),
            )
    else:
        logger.error("❌ فشل حفظ المنتج لكلا المسارين: telegram_id=%s", telegram_id)
        try:
            await query.edit_message_caption(caption=get_string(lang, "error_general"))
        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=get_string(lang, "error_general"),
            )

    # 6. مسح بيانات الجلسة
    for key in ["images", "image_urls", "category", "category_id", "price", "supplier_id"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END


# ──────────────────────────────────────────────────────────
# إلغاء العملية
# ──────────────────────────────────────────────────────────

async def cancel_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يُلغي عملية إضافة المنتج من زر الإلغاء أو أمر /cancel.

    المدخلات:
        update  (Update)              : تحديث تليجرام
        context (ContextTypes.DEFAULT): سياق البوت

    المخرجات:
        int: ConversationHandler.END
    """
    lang = context.user_data.get("lang", "ar")

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_caption(
                caption=get_string(lang, "cancel")
            )
        except Exception:
            await update.callback_query.edit_message_text(
                text=get_string(lang, "cancel")
            )
    else:
        await update.message.reply_text(text=get_string(lang, "cancel"))

    # مسح بيانات المنتج
    for key in ["images", "image_urls", "category", "category_id", "price", "supplier_id"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END
