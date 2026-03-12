# ===================================================
# bot/utils/channel_publisher.py
# أداة نشر المحتوى في قنوات تليجرام
#
# الوصف:
#   يتولى إرسال رسائل المنتجات المنسقة إلى قنوات تليجرام.
#   يدعم إرسال صور، فيديو، ومجموعات صور (media group).
#   يُستخدم من channel_post_handler عند نشر منتج معتمد.
#
# الاستخدام:
#   from bot.utils.channel_publisher import publish_product_to_channel
#   await publish_product_to_channel(bot, channel_id, product_data)
#
# KAYISOFT - إسطنبول، تركيا
# ===================================================

import logging
from typing import Optional

from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError, Forbidden, BadRequest

logger = logging.getLogger(__name__)

# الحد الأقصى للصور في مجموعة واحدة (قيد تليجرام)
_MAX_MEDIA_GROUP = 10

# الحد الأقصى لطول التسمية التوضيحية في تليجرام
_MAX_CAPTION_LENGTH = 1024


# ──────────────────────────────────────────────────────────
# دوال بناء نص المنتج
# ──────────────────────────────────────────────────────────

def _build_product_caption(product_data: dict, lang: str = "ar") -> str:
    """
    يبني نص التسمية التوضيحية للمنتج بالتنسيق المناسب للقناة.

    المعاملات:
        product_data (dict): بيانات المنتج — يحتوي على:
            - title       (str)      : عنوان المنتج بالعربية
            - title_en    (str)      : عنوان المنتج بالإنجليزية
            - category    (str)      : الفئة
            - price       (str|None) : السعر
            - currency    (str|None) : العملة
            - colors      (list)     : الألوان المتاحة
            - sizes       (list)     : المقاسات المتاحة
            - description (str|None) : وصف المنتج
        lang (str): لغة النص — ar|en|tr (افتراضي: ar)

    المُخرجات:
        str: نص منسق بـ HTML جاهز للنشر في القناة، بحد أقصى 1024 حرف.
    """
    title = product_data.get("title") or product_data.get("title_en") or "منتج جديد"
    category = product_data.get("category") or ""
    price = product_data.get("price")
    currency = product_data.get("currency") or ""
    colors = product_data.get("colors") or []
    sizes = product_data.get("sizes") or []
    description = product_data.get("description") or ""

    lines = [f"<b>{title}</b>"]

    if category:
        lines.append(f"📁 {category}")

    if description:
        # اقتصار الوصف على 200 حرف
        short_desc = description[:200] + ("..." if len(description) > 200 else "")
        lines.append(f"\n{short_desc}")

    if price:
        price_line = f"💰 {price}"
        if currency:
            price_line += f" {currency}"
        lines.append(price_line)

    if colors:
        colors_str = " · ".join(str(c) for c in colors[:5])  # بحد أقصى 5 ألوان
        lines.append(f"🎨 {colors_str}")

    if sizes:
        sizes_str = " · ".join(str(s) for s in sizes[:6])   # بحد أقصى 6 مقاسات
        lines.append(f"📐 {sizes_str}")

    lines.append("\n🛒 للاستفسار وطلب عرض السعر — تواصل معنا مباشرة")

    caption = "\n".join(lines)

    # اقتصار على الحد الأقصى لتليجرام
    if len(caption) > _MAX_CAPTION_LENGTH:
        caption = caption[:_MAX_CAPTION_LENGTH - 3] + "..."

    return caption


# ──────────────────────────────────────────────────────────
# الدالة الرئيسية للنشر
# ──────────────────────────────────────────────────────────

async def publish_product_to_channel(
    bot: Bot,
    channel_id: int,
    product_data: dict,
    lang: str = "ar",
) -> Optional[int]:
    """
    ينشر منتجاً في قناة تليجرام بالتنسيق المناسب.

    يختار تلقائياً بين:
    - media group: إذا كان هناك أكثر من صورة
    - صورة مفردة: إذا كانت هناك صورة واحدة
    - رسالة نصية: إذا لم تكن هناك صور

    المعاملات:
        bot          (Bot) : كائن البوت الرئيسي
        channel_id   (int) : معرّف القناة في تليجرام (رقم سالب)
        product_data (dict): بيانات المنتج المراد نشره
        lang         (str) : لغة النص — ar|en|tr

    المُخرجات:
        int | None: message_id للرسالة المنشورة عند النجاح، None عند الفشل.

    معالجة الأخطاء:
        - Forbidden: البوت ليس مشرفاً في القناة — يُسجَّل تحذير
        - BadRequest: بيانات غير صالحة — يُسجَّل خطأ
        - TelegramError: خطأ عام في تليجرام — يُسجَّل خطأ
    """
    caption = _build_product_caption(product_data, lang)
    image_urls: list = product_data.get("image_urls") or []

    logger.info(
        f"📢 نشر منتج في قناة {channel_id} | "
        f"صور={len(image_urls)} | "
        f"عنوان={product_data.get('title', 'غير محدد')!r}"
    )

    try:
        # الحالة 1: مجموعة صور (2+ صور)
        if len(image_urls) >= 2:
            return await _send_media_group(bot, channel_id, image_urls, caption)

        # الحالة 2: صورة واحدة
        if len(image_urls) == 1:
            return await _send_single_photo(bot, channel_id, image_urls[0], caption)

        # الحالة 3: رسالة نصية فقط (لا توجد صور)
        return await _send_text_only(bot, channel_id, caption)

    except Forbidden:
        logger.error(
            f"❌ البوت ليس مشرفاً في القناة {channel_id} أو تم حذفه — "
            f"يرجى التحقق من صلاحيات البوت"
        )
        return None

    except BadRequest as e:
        logger.error(f"❌ طلب غير صالح عند النشر في قناة {channel_id}: {e}")
        return None

    except TelegramError as e:
        logger.error(f"❌ خطأ تليجرام عند النشر في قناة {channel_id}: {e}")
        return None

    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع عند النشر في قناة {channel_id}: {e}")
        return None


# ──────────────────────────────────────────────────────────
# دوال الإرسال الداخلية
# ──────────────────────────────────────────────────────────

async def _send_media_group(
    bot: Bot,
    channel_id: int,
    image_urls: list,
    caption: str,
) -> Optional[int]:
    """
    دالة داخلية: ترسل مجموعة صور (media group) مع التسمية التوضيحية.

    المعاملات:
        bot        (Bot)  : كائن البوت
        channel_id (int)  : معرّف القناة
        image_urls (list) : قائمة file_ids للصور
        caption    (str)  : التسمية التوضيحية (HTML)

    المُخرجات:
        int | None: message_id للرسالة الأولى في المجموعة، أو None عند الفشل.
    """
    # بناء قائمة InputMediaPhoto (بحد أقصى _MAX_MEDIA_GROUP)
    media_list = []
    for idx, file_id in enumerate(image_urls[:_MAX_MEDIA_GROUP]):
        media_list.append(
            InputMediaPhoto(
                media=file_id,
                # التسمية التوضيحية على الصورة الأولى فقط (قيد تليجرام)
                caption=caption if idx == 0 else None,
                parse_mode="HTML" if idx == 0 else None,
            )
        )

    messages = await bot.send_media_group(
        chat_id=channel_id,
        media=media_list,
    )

    if messages:
        message_id = messages[0].message_id
        logger.info(f"✅ media group منشور في {channel_id} | message_id={message_id}")
        return message_id

    return None


async def _send_single_photo(
    bot: Bot,
    channel_id: int,
    file_id: str,
    caption: str,
) -> Optional[int]:
    """
    دالة داخلية: ترسل صورة مفردة مع التسمية التوضيحية.

    المعاملات:
        bot        (Bot) : كائن البوت
        channel_id (int) : معرّف القناة
        file_id    (str) : file_id الصورة
        caption    (str) : التسمية التوضيحية (HTML)

    المُخرجات:
        int | None: message_id الرسالة، أو None عند الفشل.
    """
    message = await bot.send_photo(
        chat_id=channel_id,
        photo=file_id,
        caption=caption,
        parse_mode="HTML",
    )
    logger.info(f"✅ صورة منشورة في {channel_id} | message_id={message.message_id}")
    return message.message_id


async def _send_text_only(
    bot: Bot,
    channel_id: int,
    text: str,
) -> Optional[int]:
    """
    دالة داخلية: ترسل رسالة نصية فقط (بدون صور).

    المعاملات:
        bot        (Bot) : كائن البوت
        channel_id (int) : معرّف القناة
        text       (str) : نص الرسالة (HTML)

    المُخرجات:
        int | None: message_id الرسالة، أو None عند الفشل.
    """
    message = await bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode="HTML",
    )
    logger.info(f"✅ رسالة نصية منشورة في {channel_id} | message_id={message.message_id}")
    return message.message_id


# ──────────────────────────────────────────────────────────
# دالة النشر إلى قنوات متعددة
# ──────────────────────────────────────────────────────────

async def publish_to_multiple_channels(
    bot: Bot,
    channel_ids: list[int],
    product_data: dict,
    lang: str = "ar",
) -> dict[int, Optional[int]]:
    """
    ينشر منتجاً في عدة قنوات في آنٍ واحد.

    المعاملات:
        bot         (Bot)      : كائن البوت
        channel_ids (list[int]): قائمة معرّفات القنوات
        product_data (dict)    : بيانات المنتج
        lang        (str)      : لغة النص

    المُخرجات:
        dict[int, int | None]: قاموس {channel_id: message_id | None}
        يحتوي على نتيجة النشر لكل قناة على حدة.

    الملاحظة:
        يستمر في النشر حتى عند فشل قناة واحدة ولا يوقف باقي القنوات.
    """
    results: dict[int, Optional[int]] = {}

    for channel_id in channel_ids:
        try:
            message_id = await publish_product_to_channel(
                bot=bot,
                channel_id=channel_id,
                product_data=product_data,
                lang=lang,
            )
            results[channel_id] = message_id
        except Exception as e:
            logger.error(f"❌ فشل النشر في قناة {channel_id}: {e}")
            results[channel_id] = None

    successful = sum(1 for v in results.values() if v is not None)
    logger.info(
        f"📢 نتائج النشر: {successful}/{len(channel_ids)} قناة ناجحة"
    )

    return results
