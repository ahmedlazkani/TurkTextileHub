"""
scripts/update_translations_v40.py
====================================
Adds new translation keys for v4.0:
  - btn_share_topgate
  - topgate_share_message
  - add_product_loading_categories
  - add_product_categories_error
  - add_product_select_category
  - add_product_select_subcategory
  - add_product_fill_form
  - add_product_ai_processing
  - add_product_upload_images
  - add_product_confirm
  - add_product_upload_more
  - add_product_cancelled
  - add_product_publishing
  - add_product_success
  - add_product_channel_published
  - add_product_no_channel
  - add_product_api_error
  - btn_confirm_publish
  - btn_add_more_images
  - btn_cancel
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANS_DIR = os.path.join(BASE_DIR, "bot", "translations")

NEW_KEYS = {
    "tr": {
        # TopGate sharing
        "btn_share_topgate": "🌐 TopGate Profilimi Paylaş",
        "topgate_share_message": (
            "🌐 <b>TopGate'de Beni Takip Edin!</b>\n\n"
            "Türkiye'nin en kaliteli toptan tekstil ürünlerini keşfedin.\n"
            "Binlerce ürün, rekabetçi fiyatlar, güvenilir teslimat.\n\n"
            "📲 <b>TopGate uygulamasını indirin ve profilimi takip edin:</b>\n"
            "{supplier_url}\n\n"
            "🏭 <i>TopKap × TopGate — Türkiye'nin Toptan Tekstil Merkezi</i>"
        ),
        # Product flow
        "add_product_loading_categories": "⏳ Kategoriler yükleniyor...",
        "add_product_categories_error": (
            "❌ <b>Kategoriler yüklenemedi.</b>\n\n"
            "Lütfen birkaç dakika sonra tekrar deneyin veya destek ekibiyle iletişime geçin."
        ),
        "add_product_select_category": (
            "📂 <b>Ürün Kategorisi Seçin</b>\n\n"
            "Ürününüzün ana kategorisini seçin:"
        ),
        "add_product_select_subcategory": (
            "📁 <b>Alt Kategori Seçin</b>\n\n"
            "Ürününüzün alt kategorisini seçin:"
        ),
        "add_product_fill_form": (
            "📝 <b>Ürün Bilgilerini Girin</b>\n\n"
            "Aşağıdaki bilgileri içeren bir mesaj gönderin:\n\n"
            "• <b>Ürün adı</b>\n"
            "• <b>Fiyat</b> (₺ cinsinden)\n"
            "• <b>Minimum sipariş miktarı</b>\n"
            "• <b>Açıklama</b> (renk, beden, kumaş, vb.)\n\n"
            "<i>Örnek: Pamuklu erkek gömlek, beyaz ve mavi, S-XXL beden, "
            "adet fiyatı 85₺, minimum 12 adet</i>"
        ),
        "add_product_ai_processing": "🤖 <b>Yapay zeka bilgileri işliyor...</b>",
        "add_product_upload_images": (
            "📸 <b>Ürün Fotoğrafları</b>\n\n"
            "Ürün fotoğraflarını gönderin (en fazla 10 fotoğraf).\n"
            "İlk fotoğrafı gönderdikten sonra yayınlama seçenekleri görünecektir."
        ),
        "add_product_confirm": (
            "✅ <b>{count} fotoğraf yüklendi.</b>\n\n"
            "Ne yapmak istersiniz?"
        ),
        "add_product_upload_more": (
            "📸 Daha fazla fotoğraf gönderin.\n"
            "Bitirdiğinizde 'Şimdi Yayınla' butonuna basın."
        ),
        "add_product_cancelled": "❌ Ürün ekleme iptal edildi.",
        "add_product_publishing": (
            "🚀 <b>Ürün yayınlanıyor...</b>\n\n"
            "• Fotoğraflar yükleniyor...\n"
            "• TopKap'a kaydediliyor...\n"
            "• Kanala gönderiliyor...\n\n"
            "<i>Bu işlem birkaç saniye sürebilir.</i>"
        ),
        "add_product_success": (
            "🎉 <b>Ürün başarıyla yayınlandı!</b>\n\n"
            "Ürününüz artık TopKap ve TopGate'de görünür durumda."
        ),
        "add_product_channel_published": (
            "📢 <b>Kanalınıza da gönderildi!</b>\n"
            "Takipçileriniz ürününüzü görebilir."
        ),
        "add_product_no_channel": (
            "⚠️ <b>Kanal bağlı değil.</b>\n"
            "Telegram kanalınıza da yayınlamak için 'Kanal Yönetimi' bölümünden kanalınızı bağlayın."
        ),
        "add_product_api_error": (
            "❌ <b>Ürün kaydedilemedi.</b>\n\n"
            "Sunucu hatası oluştu. Lütfen tekrar deneyin."
        ),
        "btn_confirm_publish": "🚀 Şimdi Yayınla",
        "btn_add_more_images": "📸 Daha Fazla Fotoğraf Ekle ({count} yüklendi)",
        "btn_cancel": "❌ İptal",
    },

    "ar": {
        # TopGate sharing
        "btn_share_topgate": "🌐 شارك ملفي على TopGate",
        "topgate_share_message": (
            "🌐 <b>تابعني على TopGate!</b>\n\n"
            "اكتشف أفضل منتجات النسيج التركي بالجملة.\n"
            "آلاف المنتجات، أسعار تنافسية، شحن لجميع دول العالم.\n\n"
            "📲 <b>حمّل تطبيق TopGate وتابع صفحتي:</b>\n"
            "{supplier_url}\n\n"
            "🏭 <i>TopKap × TopGate — مركز النسيج التركي بالجملة</i>"
        ),
        # Product flow
        "add_product_loading_categories": "⏳ جاري تحميل الفئات...",
        "add_product_categories_error": (
            "❌ <b>تعذّر تحميل الفئات.</b>\n\n"
            "يرجى المحاولة مرة أخرى بعد قليل أو التواصل مع فريق الدعم."
        ),
        "add_product_select_category": (
            "📂 <b>اختر فئة المنتج</b>\n\n"
            "اختر الفئة الرئيسية لمنتجك:"
        ),
        "add_product_select_subcategory": (
            "📁 <b>اختر الفئة الفرعية</b>\n\n"
            "اختر الفئة الفرعية لمنتجك:"
        ),
        "add_product_fill_form": (
            "📝 <b>أدخل بيانات المنتج</b>\n\n"
            "أرسل رسالة تحتوي على:\n\n"
            "• <b>اسم المنتج</b>\n"
            "• <b>السعر</b> (بالليرة التركية ₺)\n"
            "• <b>الحد الأدنى للطلب</b>\n"
            "• <b>الوصف</b> (اللون، المقاس، القماش، إلخ)\n\n"
            "<i>مثال: قميص قطني رجالي، أبيض وأزرق، مقاسات S-XXL، "
            "سعر القطعة 85₺، الحد الأدنى 12 قطعة</i>"
        ),
        "add_product_ai_processing": "🤖 <b>الذكاء الاصطناعي يعالج البيانات...</b>",
        "add_product_upload_images": (
            "📸 <b>صور المنتج</b>\n\n"
            "أرسل صور المنتج (حتى 10 صور).\n"
            "بعد إرسال أول صورة ستظهر خيارات النشر."
        ),
        "add_product_confirm": (
            "✅ <b>تم رفع {count} صورة.</b>\n\n"
            "ماذا تريد أن تفعل؟"
        ),
        "add_product_upload_more": (
            "📸 أرسل المزيد من الصور.\n"
            "عند الانتهاء اضغط 'انشر الآن'."
        ),
        "add_product_cancelled": "❌ تم إلغاء إضافة المنتج.",
        "add_product_publishing": (
            "🚀 <b>جاري نشر المنتج...</b>\n\n"
            "• رفع الصور...\n"
            "• الحفظ على TopKap...\n"
            "• الإرسال للقناة...\n\n"
            "<i>قد تستغرق هذه العملية بضع ثوانٍ.</i>"
        ),
        "add_product_success": (
            "🎉 <b>تم نشر المنتج بنجاح!</b>\n\n"
            "منتجك الآن ظاهر على TopKap وTopGate."
        ),
        "add_product_channel_published": (
            "📢 <b>تم النشر على قناتك أيضاً!</b>\n"
            "يمكن لمتابعيك رؤية منتجك الآن."
        ),
        "add_product_no_channel": (
            "⚠️ <b>لا توجد قناة مربوطة.</b>\n"
            "للنشر على قناتك في تيليغرام، اربط قناتك من قسم 'إدارة القناة'."
        ),
        "add_product_api_error": (
            "❌ <b>تعذّر حفظ المنتج.</b>\n\n"
            "حدث خطأ في الخادم. يرجى المحاولة مرة أخرى."
        ),
        "btn_confirm_publish": "🚀 انشر الآن",
        "btn_add_more_images": "📸 أضف المزيد من الصور ({count} مرفوعة)",
        "btn_cancel": "❌ إلغاء",
    },

    "en": {
        # TopGate sharing
        "btn_share_topgate": "🌐 Share My TopGate Profile",
        "topgate_share_message": (
            "🌐 <b>Follow me on TopGate!</b>\n\n"
            "Discover the finest Turkish wholesale textile products.\n"
            "Thousands of products, competitive prices, worldwide shipping.\n\n"
            "📲 <b>Download TopGate and follow my profile:</b>\n"
            "{supplier_url}\n\n"
            "🏭 <i>TopKap × TopGate — Turkey's Wholesale Textile Hub</i>"
        ),
        # Product flow
        "add_product_loading_categories": "⏳ Loading categories...",
        "add_product_categories_error": (
            "❌ <b>Failed to load categories.</b>\n\n"
            "Please try again in a few minutes or contact support."
        ),
        "add_product_select_category": (
            "📂 <b>Select Product Category</b>\n\n"
            "Choose the main category for your product:"
        ),
        "add_product_select_subcategory": (
            "📁 <b>Select Subcategory</b>\n\n"
            "Choose the subcategory for your product:"
        ),
        "add_product_fill_form": (
            "📝 <b>Enter Product Details</b>\n\n"
            "Send a message containing:\n\n"
            "• <b>Product name</b>\n"
            "• <b>Price</b> (in Turkish Lira ₺)\n"
            "• <b>Minimum order quantity</b>\n"
            "• <b>Description</b> (color, size, fabric, etc.)\n\n"
            "<i>Example: Cotton men's shirt, white and blue, sizes S-XXL, "
            "unit price 85₺, minimum 12 pcs</i>"
        ),
        "add_product_ai_processing": "🤖 <b>AI is processing your data...</b>",
        "add_product_upload_images": (
            "📸 <b>Product Images</b>\n\n"
            "Send product images (up to 10 photos).\n"
            "Publishing options will appear after the first image."
        ),
        "add_product_confirm": (
            "✅ <b>{count} image(s) uploaded.</b>\n\n"
            "What would you like to do?"
        ),
        "add_product_upload_more": (
            "📸 Send more images.\n"
            "When done, press 'Publish Now'."
        ),
        "add_product_cancelled": "❌ Product addition cancelled.",
        "add_product_publishing": (
            "🚀 <b>Publishing product...</b>\n\n"
            "• Uploading images...\n"
            "• Saving to TopKap...\n"
            "• Sending to channel...\n\n"
            "<i>This may take a few seconds.</i>"
        ),
        "add_product_success": (
            "🎉 <b>Product published successfully!</b>\n\n"
            "Your product is now visible on TopKap and TopGate."
        ),
        "add_product_channel_published": (
            "📢 <b>Also posted to your channel!</b>\n"
            "Your followers can now see your product."
        ),
        "add_product_no_channel": (
            "⚠️ <b>No channel connected.</b>\n"
            "To publish to your Telegram channel, connect it from 'Channel Management'."
        ),
        "add_product_api_error": (
            "❌ <b>Failed to save product.</b>\n\n"
            "A server error occurred. Please try again."
        ),
        "btn_confirm_publish": "🚀 Publish Now",
        "btn_add_more_images": "📸 Add More Images ({count} uploaded)",
        "btn_cancel": "❌ Cancel",
    },
}


def update_translations():
    for lang, new_keys in NEW_KEYS.items():
        filepath = os.path.join(TRANS_DIR, f"{lang}.json")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        updated = 0
        for key, value in new_keys.items():
            if key not in data:
                data[key] = value
                updated += 1
            else:
                # Update existing key to new value
                data[key] = value
                updated += 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ {lang}.json — {updated} keys updated")


if __name__ == "__main__":
    update_translations()
    print("\n✅ All translation files updated for v4.0")
