"""
update_translations_v31.py
Adds/updates translation keys for v3.1:
- why_topkap: Global value proposition with real market stats
- motivational messages (updated to global reach)
- onboarding_stats: Market numbers
- btn_why_topkap: New button
"""
import json
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "bot", "translations")

UPDATES = {
    "tr": {
        # ── Why TopKap — Global Value Proposition ──────────────────────────
        "why_topkap": (
            "💡 <b>Neden TopKap?</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌍 <b>Dünya Genelinde Alıcı Ağı</b>\n"
            "   Orta Doğu, Avrupa, Afrika, Orta Asya ve\n"
            "   dünyanın dört bir yanındaki alıcılara ulaşın.\n"
            "   <b>Sadece Arap alıcılar değil — tüm dünya!</b>\n\n"
            "📦 <b>Kolay Ürün Yönetimi</b>\n"
            "   Ürünlerinizi dakikalar içinde ekleyin,\n"
            "   düzenleyin ve binlerce alıcıya yayınlayın.\n\n"
            "📢 <b>Otomatik Telegram Kanalı Yayını</b>\n"
            "   Ürünleriniz otomatik olarak kanalınıza\n"
            "   profesyonel formatta paylaşılır.\n\n"
            "🌐 <b>Çok Dilli Platform</b>\n"
            "   Türkçe, Arapça, İngilizce — 3 dilde\n"
            "   global alıcılara ulaşın.\n\n"
            "📊 <b>Gerçek Zamanlı Analitik</b>\n"
            "   Ürün görüntülenmeleri, tıklamalar ve\n"
            "   satış verilerini anlık takip edin.\n\n"
            "🔗 <b>TopKap & TopGate Ekosistemi</b>\n"
            "   İki güçlü platformda tek hesap —\n"
            "   maksimum görünürlük, minimum çaba.\n\n"
            "💎 <b>Premium Tedarikçi Desteği</b>\n"
            "   7/24 Türkçe destek ekibi her zaman yanınızda.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 <b>Türkiye'nin #1 Tekstil B2B Platformu</b>"
        ),
        # ── Onboarding Stats ───────────────────────────────────────────────
        "onboarding_stats": (
            "📈 <b>TopKap Rakamlarla</b>\n\n"
            "🌍 <b>180+</b> ülkeden alıcı erişimi\n"
            "🏭 <b>1.000+</b> Türk tekstil tedarikçisi\n"
            "📦 <b>50.000+</b> ürün kataloğu\n"
            "📢 <b>500+</b> aktif Telegram kanalı\n"
            "💰 Türkiye tekstil ihracatı: <b>$22 Milyar/yıl</b>\n\n"
            "⚡ <i>Siz de bu büyümenin parçası olun!</i>"
        ),
        # ── Updated motivational messages ─────────────────────────────────
        "motivational_1": "🌍 <b>Dünyaya açılan kapı: TopKap!</b>",
        "motivational_2": "🚀 <b>180+ ülkeden alıcıya ulaşın — TopKap ile!</b>",
        "motivational_3": "🏆 <b>Türkiye'nin #1 tekstil B2B platformu!</b>",
        "motivational_4": "💼 <b>Ürünlerinizi dünyaya taşıyın — TopKap!</b>",
        "motivational_5": "✨ <b>1.000+ tedarikçinin güvendiği platform!</b>",
        # ── Button ────────────────────────────────────────────────────────
        "btn_why_topkap": "💡 Neden TopKap?",
        # ── Updated welcome ───────────────────────────────────────────────
        "welcome_message": (
            "🇹🇷 <b>TopKap'a Hoş Geldiniz!</b>\n\n"
            "Türkiye'nin Toptan Tekstil Merkezi.\n"
            "Ürünlerinizi ekleyin, <b>180+ ülkeden</b> alıcılara ulaşın.\n\n"
            "🌍 Lütfen dilinizi seçin:"
        ),
        # ── Updated main menu ─────────────────────────────────────────────
        "main_menu_supplier": (
            "🛍️ <b>Tedarikçi Paneli</b>\n\n"
            "Aşağıdaki menüden bir işlem seçin:\n\n"
            "➕ <b>Ürün Ekle</b> — Yeni ürün ekleyin ve yayınlayın\n"
            "📦 <b>Ürünlerim</b> — Mevcut ürünlerinizi yönetin\n"
            "📊 <b>İstatistikler</b> — Satış ve görüntülenme raporları\n"
            "🔗 <b>Kanal Yönetimi</b> — Telegram kanalınızı bağlayın\n"
            "⚙️ <b>Ayarlar</b> — Dil ve hesap ayarları\n"
            "💡 <b>Neden TopKap?</b> — Platformun avantajlarını keşfedin\n"
            "❓ <b>Yardım</b> — Adım adım kullanım kılavuzu"
        ),
    },

    "ar": {
        # ── Why TopKap ────────────────────────────────────────────────────
        "why_topkap": (
            "💡 <b>لماذا TopKap؟</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌍 <b>شبكة مشترين عالمية</b>\n"
            "   تواصل مع مشترين من الشرق الأوسط، أوروبا،\n"
            "   أفريقيا، آسيا الوسطى وأكثر من 180 دولة.\n"
            "   <b>ليس العرب فقط — العالم بأكمله!</b>\n\n"
            "📦 <b>إدارة منتجات سهلة</b>\n"
            "   أضف منتجاتك في دقائق وانشرها\n"
            "   لآلاف المشترين حول العالم.\n\n"
            "📢 <b>نشر تلقائي على قناة تيليغرام</b>\n"
            "   تُنشر منتجاتك تلقائياً على قناتك\n"
            "   بتنسيق احترافي.\n\n"
            "🌐 <b>منصة متعددة اللغات</b>\n"
            "   التركية، العربية، الإنجليزية — تواصل\n"
            "   مع مشترين عالميين بلغتهم.\n\n"
            "📊 <b>تحليلات فورية</b>\n"
            "   تابع مشاهدات المنتجات، النقرات\n"
            "   وبيانات المبيعات في الوقت الفعلي.\n\n"
            "🔗 <b>نظام TopKap و TopGate</b>\n"
            "   حساب واحد على منصتين قويتين —\n"
            "   أقصى ظهور بأقل جهد.\n\n"
            "💎 <b>دعم موردين متميز</b>\n"
            "   فريق دعم متاح 7/24 بلغتك.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 <b>منصة B2B النسيجية الأولى في تركيا</b>"
        ),
        # ── Onboarding Stats ───────────────────────────────────────────────
        "onboarding_stats": (
            "📈 <b>TopKap بالأرقام</b>\n\n"
            "🌍 <b>180+</b> دولة وصول للمشترين\n"
            "🏭 <b>1,000+</b> مورد نسيج تركي\n"
            "📦 <b>50,000+</b> منتج في الكتالوج\n"
            "📢 <b>500+</b> قناة تيليغرام نشطة\n"
            "💰 صادرات النسيج التركي: <b>22 مليار دولار/سنة</b>\n\n"
            "⚡ <i>كن جزءاً من هذا النمو!</i>"
        ),
        # ── Updated motivational messages ─────────────────────────────────
        "motivational_1": "🌍 <b>بوابتك للعالم: TopKap!</b>",
        "motivational_2": "🚀 <b>تواصل مع مشترين من 180+ دولة — مع TopKap!</b>",
        "motivational_3": "🏆 <b>منصة B2B النسيجية الأولى في تركيا!</b>",
        "motivational_4": "💼 <b>خذ منتجاتك للعالم — TopKap!</b>",
        "motivational_5": "✨ <b>المنصة التي يثق بها أكثر من 1,000 مورد!</b>",
        # ── Button ────────────────────────────────────────────────────────
        "btn_why_topkap": "💡 لماذا TopKap؟",
        # ── Updated welcome ───────────────────────────────────────────────
        "welcome_message": (
            "🇹🇷 <b>مرحباً بك في TopKap!</b>\n\n"
            "مركز النسيج التركي بالجملة.\n"
            "أضف منتجاتك، تواصل مع مشترين من <b>180+ دولة</b>.\n\n"
            "🌍 يرجى اختيار لغتك:"
        ),
        # ── Updated main menu ─────────────────────────────────────────────
        "main_menu_supplier": (
            "🛍️ <b>لوحة المورد</b>\n\n"
            "اختر إجراءً من القائمة أدناه:\n\n"
            "➕ <b>إضافة منتج</b> — أضف منتجاً جديداً وانشره\n"
            "📦 <b>منتجاتي</b> — إدارة منتجاتك الحالية\n"
            "📊 <b>الإحصائيات</b> — تقارير المبيعات والمشاهدات\n"
            "🔗 <b>إدارة القناة</b> — ربط قناتك على تيليغرام\n"
            "⚙️ <b>الإعدادات</b> — إعدادات اللغة والحساب\n"
            "💡 <b>لماذا TopKap؟</b> — اكتشف مزايا المنصة\n"
            "❓ <b>المساعدة</b> — دليل الاستخدام خطوة بخطوة"
        ),
    },

    "en": {
        # ── Why TopKap ────────────────────────────────────────────────────
        "why_topkap": (
            "💡 <b>Why TopKap?</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌍 <b>Global Buyer Network</b>\n"
            "   Connect with buyers from the Middle East, Europe,\n"
            "   Africa, Central Asia and 180+ countries worldwide.\n"
            "   <b>Not just Arab buyers — the entire world!</b>\n\n"
            "📦 <b>Easy Product Management</b>\n"
            "   Add your products in minutes and publish\n"
            "   them to thousands of global buyers.\n\n"
            "📢 <b>Automatic Telegram Channel Publishing</b>\n"
            "   Your products are automatically shared\n"
            "   to your channel in a professional format.\n\n"
            "🌐 <b>Multilingual Platform</b>\n"
            "   Turkish, Arabic, English — reach global\n"
            "   buyers in their own language.\n\n"
            "📊 <b>Real-Time Analytics</b>\n"
            "   Track product views, clicks and\n"
            "   sales data in real time.\n\n"
            "🔗 <b>TopKap & TopGate Ecosystem</b>\n"
            "   One account on two powerful platforms —\n"
            "   maximum visibility, minimum effort.\n\n"
            "💎 <b>Premium Supplier Support</b>\n"
            "   24/7 support team always by your side.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 <b>Turkey's #1 Textile B2B Platform</b>"
        ),
        # ── Onboarding Stats ───────────────────────────────────────────────
        "onboarding_stats": (
            "📈 <b>TopKap by the Numbers</b>\n\n"
            "🌍 <b>180+</b> countries with buyer access\n"
            "🏭 <b>1,000+</b> Turkish textile suppliers\n"
            "📦 <b>50,000+</b> product catalog\n"
            "📢 <b>500+</b> active Telegram channels\n"
            "💰 Turkish textile exports: <b>$22 Billion/year</b>\n\n"
            "⚡ <i>Be part of this growth!</i>"
        ),
        # ── Updated motivational messages ─────────────────────────────────
        "motivational_1": "🌍 <b>Your gateway to the world: TopKap!</b>",
        "motivational_2": "🚀 <b>Reach buyers from 180+ countries — with TopKap!</b>",
        "motivational_3": "🏆 <b>Turkey's #1 Textile B2B Platform!</b>",
        "motivational_4": "💼 <b>Take your products global — TopKap!</b>",
        "motivational_5": "✨ <b>Trusted by 1,000+ suppliers worldwide!</b>",
        # ── Button ────────────────────────────────────────────────────────
        "btn_why_topkap": "💡 Why TopKap?",
        # ── Updated welcome ───────────────────────────────────────────────
        "welcome_message": (
            "🇹🇷 <b>Welcome to TopKap!</b>\n\n"
            "Turkey's Wholesale Textile Hub.\n"
            "Add your products, reach buyers from <b>180+ countries</b>.\n\n"
            "🌍 Please select your language:"
        ),
        # ── Updated main menu ─────────────────────────────────────────────
        "main_menu_supplier": (
            "🛍️ <b>Supplier Dashboard</b>\n\n"
            "Select an action from the menu below:\n\n"
            "➕ <b>Add Product</b> — Add a new product and publish it\n"
            "📦 <b>My Products</b> — Manage your existing products\n"
            "📊 <b>Statistics</b> — Sales and view reports\n"
            "🔗 <b>Channel Management</b> — Connect your Telegram channel\n"
            "⚙️ <b>Settings</b> — Language and account settings\n"
            "💡 <b>Why TopKap?</b> — Discover platform advantages\n"
            "❓ <b>Help</b> — Step-by-step usage guide"
        ),
    },
}


def update_translations():
    for lang, updates in UPDATES.items():
        path = os.path.join(BASE, f"{lang}.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.update(updates)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {lang}.json — {len(updates)} keys updated/added")


if __name__ == "__main__":
    update_translations()
    print("\n🎉 All translation files updated for v3.1!")
