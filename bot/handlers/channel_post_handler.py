"""
bot/handlers/channel_post_handler.py
معالج منشورات القناة — الخطوة 6

الوصف:
    يلتقط المنشورات من القنوات المربوطة تلقائياً، يحللها بـ OpenAI،
    ويرسل للمورد رسالة استئذان مع معاينة المنتج المستخرج.

المدخلات: تحديثات تليجرام من نوع channel_post
المخرجات: رسالة استئذان للمورد + حفظ في pending_posts
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from bot.services import database_service, ai_service, notification_service
from bot import config, states

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
# 1. المعالج الرئيسي — يلتقط كل منشور من القنوات المربوطة
# ══════════════════════════════════════════════════════

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    المدخلات: تحديث تليجرام يحتوي على channel_post (نص أو صورة أو فيديو)
    المخرجات: يحفظ المنشور في pending_posts ويرسل طلب موافقة للمورد
    المنطق:
        1. تحقق: هل update.channel_post موجود؟ (ليس update.message)
        2. استخرج channel_id = update.channel_post.chat.id
        3. استدع get_active_connection_by_channel_id — إذا لم تجد، تجاهل
        4. تحقق من rate limit — إذا تجاوز، أرسل تحذيراً للمورد وتجاهل
        5. تحقق من التكرار is_duplicate_post — إذا موجود، تجاهل
        6. استخرج: النص، الصور (file_ids)، الفيديو
        7. استدع ai_service.extract_product_data لاستخراج البيانات
        8. احفظ في pending_posts عبر database_service.save_pending_post
        9. أرسل رسالة الاستئذان للمورد عبر _send_approval_request
    """
    # 1. تحقق من وجود channel_post (ليس update.message)
    if not update.channel_post:
        logger.debug("تحديث بدون channel_post — تجاهل")
        return

    post = update.channel_post
    channel_id = post.chat.id          # 2. استخرج channel_id
    message_id = post.message_id

    logger.info(f"📬 منشور جديد | channel_id={channel_id} | message_id={message_id}")

    # 3. جلب الاتصال النشط للقناة
    try:
        connection = database_service.get_active_connection_by_channel_id(channel_id)
    except Exception as e:
        logger.error(f"❌ خطأ في جلب اتصال القناة {channel_id}: {e}")
        return

    if not connection:
        logger.debug(f"لا يوجد اتصال نشط للقناة {channel_id} — تجاهل")
        return

    supplier_id = connection["supplier_id"]

    # محاولة الحصول على telegram_id المورد من الاتصال أو من bot_registrations
    supplier_telegram_id = connection.get("supplier_telegram_id")
    if not supplier_telegram_id:
        try:
            supplier_info = database_service.get_supplier_by_id(supplier_id)
            if supplier_info:
                supplier_telegram_id = supplier_info.get("telegram_id")
        except Exception as e:
            logger.error(f"❌ خطأ في جلب telegram_id المورد {supplier_id}: {e}")
            return

    if not supplier_telegram_id:
        logger.error(f"❌ لا يمكن إيجاد telegram_id للمورد {supplier_id}")
        return

    # 4. تحقق من rate limit (10 منشورات/يوم)
    try:
        within_limit = database_service.check_rate_limit(supplier_id, max_posts=10)
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من rate limit للمورد {supplier_id}: {e}")
        within_limit = True  # السماح بالمرور عند خطأ التحقق

    if not within_limit:
        logger.warning(f"⚠️ المورد {supplier_id} تجاوز الحد اليومي للمنشورات")
        try:
            notification_service.notify_rate_limit_exceeded(
                supplier_telegram_id=supplier_telegram_id,
                lang="ar",
            )
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال تحذير rate limit: {e}")
        return

    # 5. تحقق من التكرار
    try:
        is_dup = database_service.is_duplicate_post(channel_id, message_id)
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من تكرار المنشور: {e}")
        is_dup = False

    if is_dup:
        logger.debug(f"🔁 منشور مكرر: channel_id={channel_id}, message_id={message_id} — تجاهل")
        return

    # 6. استخرج: النص، الصور (file_ids)، الفيديو
    raw_text = post.text or post.caption or ""
    image_file_ids = []
    video_url = None

    if post.photo:
        image_file_ids = [post.photo[-1].file_id]   # أعلى جودة
    elif post.document and post.document.mime_type and post.document.mime_type.startswith("image/"):
        image_file_ids = [post.document.file_id]

    if post.video:
        video_url = str(post.video.file_id)

    logger.info(
        f"محتوى: نص={len(raw_text)} حرف | صور={len(image_file_ids)} | فيديو={'نعم' if video_url else 'لا'}"
    )

    # 7. استخراج بيانات المنتج بـ AI
    try:
        extracted_data = ai_service.extract_product_data(
            raw_text=raw_text,
            image_count=len(image_file_ids),
        )
        logger.info(f"✅ AI استخرج: {extracted_data.get('title', 'غير محدد')}")
    except Exception as e:
        logger.error(f"❌ خطأ في AI: {e}")
        extracted_data = ai_service.get_default_product_data(raw_text)

    # 8. حفظ في pending_posts
    post_data = {
        "supplier_id": supplier_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "raw_text": raw_text,
        "image_urls": image_file_ids,
        "video_url": video_url,
        "extracted_data": extracted_data,
    }

    try:
        saved_post = database_service.save_pending_post(post_data)
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ pending_post: {e}")
        return

    if not saved_post:
        logger.error("❌ فشل حفظ pending_post — لا رد من قاعدة البيانات")
        return

    pending_post_id = saved_post["id"]
    logger.info(f"💾 تم حفظ pending_post: {pending_post_id}")

    # 9. إرسال رسالة الاستئذان للمورد
    try:
        await _send_approval_request(
            context=context,
            supplier_telegram_id=supplier_telegram_id,
            pending_post_id=pending_post_id,
            extracted_data=extracted_data,
            images=image_file_ids,
        )
        logger.info(f"📤 طلب موافقة أُرسل للمورد {supplier_telegram_id}")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال طلب الموافقة: {e}")


# ══════════════════════════════════════════════════════
# 2. بناء رسالة الاستئذان وإرسالها للمورد
# ══════════════════════════════════════════════════════

async def _send_approval_request(
    context: ContextTypes.DEFAULT_TYPE,
    supplier_telegram_id: int,
    pending_post_id: str,
    extracted_data: dict,
    images: list,
):
    """
    المدخلات:
        context             : سياق البوت
        supplier_telegram_id: معرف المورد في تليجرام
        pending_post_id     : UUID المنشور المعلق (string)
        extracted_data      : بيانات المنتج المستخرجة بـ AI
        images              : قائمة file_ids للصور
    المخرجات: يرسل رسالة الاستئذان مع أزرار inline للمورد
    المنطق:
        - يبني caption منسّق بالبيانات المستخرجة
        - يرسل مع الصورة الأولى إن وجدت، وإلا يرسل نصاً
        - الأزرار: نشر | تعديل | تجاهل
    """
    title       = extracted_data.get("title")       or "غير محدد"
    title_en    = extracted_data.get("title_en")    or "N/A"
    category    = extracted_data.get("category")    or "أخرى"
    price       = extracted_data.get("price")
    currency    = extracted_data.get("currency")    or ""
    colors      = extracted_data.get("colors")      or []
    sizes       = extracted_data.get("sizes")       or []
    moq         = extracted_data.get("minimum_order_quantity")
    description = extracted_data.get("description") or ""

    price_text  = f"{price} {currency}".strip() if price else "غير محدد"
    colors_text = "، ".join(colors) if colors else "غير محدد"
    sizes_text  = "، ".join(sizes)  if sizes  else "غير محدد"
    moq_text    = str(moq) if moq else "غير محدد"

    caption = (
        f"📦 منتج جديد من قناتك!\n\n"
        f"🏷 الاسم: {title}\n"
        f"🌍 الاسم (EN): {title_en}\n"
        f"📁 الفئة: {category}\n"
        f"💰 السعر: {price_text}\n"
        f"🎨 الألوان: {colors_text}\n"
        f"📐 المقاسات: {sizes_text}\n"
        f"📦 الحد الأدنى للطلب: {moq_text}\n\n"
        f"📝 الوصف:\n{description}\n\n"
        f"⏰ ستنتهي صلاحية هذا الطلب خلال 24 ساعة"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نشر المنتج",          callback_data=f"approve_post_{pending_post_id}"),
            InlineKeyboardButton("✏️ تعديل قبل النشر",    callback_data=f"edit_post_{pending_post_id}"),
        ],
        [
            InlineKeyboardButton("❌ تجاهل",               callback_data=f"reject_post_{pending_post_id}"),
        ],
    ])

    if images:
        await context.bot.send_photo(
            chat_id=supplier_telegram_id,
            photo=images[0],
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            chat_id=supplier_telegram_id,
            text=caption,
            reply_markup=keyboard,
        )


# ══════════════════════════════════════════════════════
# 3. معالج الموافقة على المنشور
# ══════════════════════════════════════════════════════

async def handle_post_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    المدخلات: callback_query تبدأ بـ approve_post_
    المخرجات: ينشر المنتج في جدول products ويحدّث حالة pending_post إلى approved
    المنطق:
        1. استخرج pending_post_id من callback_data (يُعامَل كـ string)
        2. جلب pending_post من قاعدة البيانات
        3. استدع publish_product_from_pending — ينشئ سجلاً في جدول products
        4. حدّث حالة pending_post إلى approved
        5. عدّل الرسالة: أضف ✅ "تم نشر المنتج بنجاح!"
        6. أرسل إشعاراً للأدمن
    """
    query = update.callback_query
    await query.answer()

    # 1. استخرج pending_post_id (UUID كـ string)
    pending_post_id = query.data.replace("approve_post_", "", 1)
    logger.info(f"✅ طلب موافقة على المنشور: {pending_post_id}")

    # 2. جلب pending_post
    try:
        pending_post = database_service.get_pending_post(pending_post_id)
    except Exception as e:
        logger.error(f"❌ خطأ في جلب pending_post {pending_post_id}: {e}")
        await _edit_message(query, suffix="\n\n⚠️ حدث خطأ، يرجى المحاولة لاحقاً")
        return

    if not pending_post:
        logger.warning(f"⚠️ pending_post {pending_post_id} غير موجود")
        await _edit_message(query, suffix="\n\n❌ المنشور غير موجود أو انتهت صلاحيته")
        return

    # 3. نشر المنتج في جدول products
    try:
        database_service.publish_product_from_pending(pending_post_id)
        logger.info(f"🛍 تم نشر المنتج من المنشور {pending_post_id}")
    except Exception as e:
        logger.error(f"❌ خطأ في نشر المنتج من {pending_post_id}: {e}")
        await _edit_message(query, suffix="\n\n⚠️ حدث خطأ أثناء النشر")
        return

    # 4. حدّث حالة pending_post إلى approved
    try:
        database_service.update_pending_post_status(pending_post_id, "approved")
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث حالة المنشور {pending_post_id}: {e}")

    # 5. عدّل الرسالة: أضف ✅ "تم نشر المنتج بنجاح!"
    await _edit_message(query, suffix="\n\n✅ تم نشر المنتج بنجاح في الكتالوج!", remove_keyboard=True)

    # 6. أرسل إشعاراً للأدمن
    try:
        supplier_info = database_service.get_supplier_by_id(pending_post["supplier_id"])
        supplier_name = supplier_info.get("company_name", "مورد") if supplier_info else "مورد"
        product_title = (pending_post.get("extracted_data") or {}).get("title", "منتج جديد")
        notification_service.notify_channel_post_approved(
            admin_id=config.ADMIN_TELEGRAM_ID,
            supplier_name=supplier_name,
            product_title=product_title,
        )
    except Exception as e:
        logger.error(f"❌ خطأ في إشعار الأدمن: {e}")


# ══════════════════════════════════════════════════════
# 4. معالج رفض المنشور
# ══════════════════════════════════════════════════════

async def handle_post_rejection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    المدخلات: callback_query تبدأ بـ reject_post_
    المخرجات: يحدّث حالة pending_post إلى rejected ويعدّل الرسالة
    المنطق:
        1. حدّث حالة pending_post إلى rejected
        2. عدّل الرسالة: أضف ❌ "تم تجاهل المنشور"
    """
    query = update.callback_query
    await query.answer()

    # 1. حدّث الحالة إلى rejected
    pending_post_id = query.data.replace("reject_post_", "", 1)
    logger.info(f"❌ رفض المنشور: {pending_post_id}")

    try:
        database_service.update_pending_post_status(pending_post_id, "rejected")
    except Exception as e:
        logger.error(f"❌ خطأ في رفض المنشور {pending_post_id}: {e}")

    # 2. عدّل الرسالة: أضف ❌ "تم تجاهل المنشور"
    await _edit_message(query, suffix="\n\n❌ تم تجاهل المنشور", remove_keyboard=True)


# ══════════════════════════════════════════════════════
# 5. معالج تعديل المنشور — يبدأ ConversationHandler
# ══════════════════════════════════════════════════════

async def handle_post_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: callback_query تبدأ بـ edit_post_
    المخرجات: يعرض قائمة ما يمكن تعديله ويعيد حالة EDIT_POST_TITLE_AR
    المنطق:
        - يخزّن pending_post_id في context.user_data
        - يعرض أزرار اختيار الحقل المراد تعديله
    """
    query = update.callback_query
    await query.answer()

    pending_post_id = query.data.replace("edit_post_", "", 1)
    context.user_data["editing_post_id"] = pending_post_id
    logger.info(f"✏️ بدء تعديل المنشور: {pending_post_id}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تعديل الاسم العربي",      callback_data="edit_field_title_ar")],
        [InlineKeyboardButton("✏️ تعديل الاسم الإنجليزي",  callback_data="edit_field_title_en")],
        [InlineKeyboardButton("💰 تعديل السعر",             callback_data="edit_field_price")],
        [InlineKeyboardButton("📁 تغيير الفئة",             callback_data="edit_field_category")],
        [InlineKeyboardButton("✅ نشر كما هو",              callback_data=f"approve_post_{pending_post_id}")],
    ])

    await _edit_message(query, suffix="\n\n✏️ ماذا تريد تعديله؟", keyboard=keyboard)
    return states.EDIT_POST_TITLE_AR


async def handle_edit_field_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: callback_query لاختيار حقل التعديل (edit_field_*)
    المخرجات: يطلب القيمة الجديدة من المورد ويعيد حالة الانتظار المناسبة
    المنطق:
        - يحدد الحقل المراد تعديله
        - يرسل رسالة طلب الإدخال
        - يعيد الحالة المناسبة لـ ConversationHandler
    """
    query = update.callback_query
    await query.answer()
    field = query.data
    context.user_data["editing_field"] = field

    prompts = {
        "edit_field_title_ar":  ("أرسل الاسم العربي الجديد للمنتج:",          states.EDIT_POST_TITLE_AR),
        "edit_field_title_en":  ("Send the new English product name:",          states.EDIT_POST_TITLE_EN),
        "edit_field_price":     ("أرسل السعر الجديد (رقم فقط):",               states.EDIT_POST_PRICE),
        "edit_field_category":  ("أرسل الفئة الجديدة (abayas|dresses|hijab|sets|other):", states.EDIT_POST_CATEGORY),
    }

    prompt_text, next_state = prompts.get(field, ("أرسل القيمة الجديدة:", states.EDIT_POST_TITLE_AR))

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await context.bot.send_message(chat_id=query.from_user.id, text=prompt_text)
    return next_state


async def handle_edit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: نص من المورد يحتوي على القيمة الجديدة للحقل المحدد
    المخرجات: يحدّث extracted_data في pending_post، ينشر المنتج، ينهي المحادثة
    المنطق:
        1. استخرج الحقل والقيمة الجديدة
        2. حدّث extracted_data في pending_post
        3. انشر المنتج (publish_product_from_pending)
        4. حدّث حالة pending_post إلى approved
        5. أرسل تأكيداً للمورد
        6. أنهِ ConversationHandler
    """
    new_value       = update.message.text.strip()
    field           = context.user_data.get("editing_field", "")
    pending_post_id = context.user_data.get("editing_post_id", "")

    field_map = {
        "edit_field_title_ar":  "title",
        "edit_field_title_en":  "title_en",
        "edit_field_price":     "price",
        "edit_field_category":  "category",
    }
    data_key = field_map.get(field)

    # 2. حدّث extracted_data
    if data_key and pending_post_id:
        try:
            post = database_service.get_pending_post(pending_post_id)
            if post:
                extracted = post.get("extracted_data") or {}
                extracted[data_key] = new_value
                database_service.update_pending_post_extracted_data(pending_post_id, extracted)
                logger.info(f"✏️ تم تحديث {data_key}={new_value} في المنشور {pending_post_id}")
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث extracted_data: {e}")

    # 3-4. نشر المنتج وتحديث الحالة
    try:
        database_service.publish_product_from_pending(pending_post_id)
        database_service.update_pending_post_status(pending_post_id, "approved")
        logger.info(f"✅ تم نشر المنتج بعد التعديل: {pending_post_id}")
        await update.message.reply_text("✅ تم حفظ التعديلات ونشر المنتج!")
    except Exception as e:
        logger.error(f"❌ خطأ في نشر المنتج بعد التعديل: {e}")
        await update.message.reply_text("⚠️ حدث خطأ أثناء النشر، يرجى المحاولة لاحقاً.")

    # مسح user_data
    context.user_data.pop("editing_post_id", None)
    context.user_data.pop("editing_field",   None)
    return ConversationHandler.END


async def handle_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    المدخلات: أمر /cancel أو أي رسالة خارج السياق
    المخرجات: إنهاء ConversationHandler ومسح user_data
    المنطق: ينهي تدفق التعديل بشكل نظيف
    """
    context.user_data.pop("editing_post_id", None)
    context.user_data.pop("editing_field",   None)
    if update.message:
        await update.message.reply_text("تم إلغاء التعديل.")
    logger.info("تم إلغاء تعديل المنشور")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════
# 6. ConversationHandler لتعديل المنشور
# ══════════════════════════════════════════════════════

def get_post_edit_conversation_handler() -> ConversationHandler:
    """
    المدخلات: لا يوجد
    المخرجات: ConversationHandler جاهز للتسجيل في main.py
    المنطق:
        - entry_point: edit_post_* callback
        - الحالات: اختيار الحقل → إدخال القيمة → نشر
        - fallback: /cancel أو أي أمر
    """
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_post_edit, pattern="^edit_post_"),
        ],
        states={
            states.EDIT_POST_TITLE_AR: [
                CallbackQueryHandler(handle_edit_field_selection, pattern="^edit_field_"),
                CallbackQueryHandler(handle_post_approval,        pattern="^approve_post_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND,   handle_edit_text_input),
            ],
            states.EDIT_POST_TITLE_EN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,   handle_edit_text_input),
            ],
            states.EDIT_POST_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,   handle_edit_text_input),
            ],
            states.EDIT_POST_CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,   handle_edit_text_input),
            ],
        },
        fallbacks=[
            MessageHandler(filters.COMMAND, handle_edit_cancel),
        ],
        per_message=False,
    )


# ══════════════════════════════════════════════════════
# مساعد داخلي: تعديل الرسالة (caption أو text)
# ══════════════════════════════════════════════════════

async def _edit_message(
    query,
    suffix: str = "",
    keyboard=None,
    remove_keyboard: bool = False,
):
    """
    المدخلات:
        query          : CallbackQuery
        suffix         : نص يُضاف لنهاية الرسالة الحالية
        keyboard       : InlineKeyboardMarkup جديد (اختياري)
        remove_keyboard: True لإزالة الأزرار
    المخرجات: يعدّل caption أو text الرسالة
    المنطق: يتعامل مع رسائل الصور (caption) والنصوص (text) بنفس الطريقة
    """
    reply_markup = None if remove_keyboard else keyboard
    try:
        if query.message.caption is not None:
            original = query.message.caption or ""
            await query.edit_message_caption(
                caption=original + suffix,
                reply_markup=reply_markup,
            )
        else:
            original = query.message.text or ""
            await query.edit_message_text(
                text=original + suffix,
                reply_markup=reply_markup,
            )
    except Exception as e:
        logger.error(f"❌ خطأ في تعديل الرسالة: {e}")
