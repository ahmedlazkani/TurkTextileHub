# متطلبات صفحات الهبوط الذكية (Smart Link Landing Pages)
## TopKap & TopGate — Deferred Deep Linking UX Specification

**إلى: فريق تطوير Kayisoft**
**من: فريق تطوير TopKap Telegram Bot**
**الإصدار: 1.0**

---

## المفهوم العام (Concept Overview)

عند ضغط أي مستخدم (مورد أو تاجر) على رابط Smart Link من قناة تيليغرام أو من البوت، يجب أن يمر بتجربة من مرحلتين:

**المرحلة 1 — صفحة الهبوط (Landing Page):**
تظهر صفحة ويب احترافية ومحفزة تعرض محتوى الرابط (منتج، ملف مورد، إلخ) مع زر تحميل التطبيق.

**المرحلة 2 — الانتقال الذكي (Deferred Deep Link):**
إذا كان التطبيق مثبتاً → يفتح التطبيق مباشرة على الصفحة المطلوبة.
إذا لم يكن مثبتاً → يوجه للمتجر (App Store / Google Play) حسب الجهاز، وبعد التثبيت يتذكر الوجهة ويفتحها فوراً.

---

## هيكل كل صفحة هبوط (Page Structure)

كل صفحة تتكون من:
1. **Header** — شعار TopKap أو TopGate + اسم التطبيق
2. **Hero Section** — محتوى الرابط (صورة المنتج أو صورة المورد)
3. **Motivational Message** — رسالة تحفيزية بلغة المستخدم (Auto-detect)
4. **CTA Button** — زر "افتح في التطبيق" أو "حمّل التطبيق"
5. **Store Badges** — App Store + Google Play
6. **Footer** — حقوق النشر + روابط الدعم

---

## الروابط والرسائل التفصيلية

---

### 🔗 رابط 1: صفحة المنتج
**URL:** `https://link.topkap.app/product/{product_id}`
**الجمهور:** التجار والمشترين (Buyers / Traders)
**السياق:** يُنشر في قنوات الموردين على تيليغرام مع كل منتج جديد

#### الرسائل التحفيزية (بالثلاث لغات)

**🇹🇷 التركية:**
> **Bu ürünü kaçırmayın!**
>
> Türkiye'nin en büyük toptan tekstil pazarında binlerce ürün sizi bekliyor.
> Fiyatları karşılaştırın, tedarikçilerle doğrudan iletişime geçin ve
> işletmenizi büyütün — hepsi tek uygulamada.
>
> 📦 **Ürünü görmek için TopGate'i açın**

**🇸🇦 العربية:**
> **لا تفوّت هذا المنتج!**
>
> آلاف المنتجات من أكبر سوق نسيج بالجملة في تركيا بانتظارك.
> قارن الأسعار، تواصل مع الموردين مباشرة، وطوّر تجارتك —
> كل ذلك في تطبيق واحد.
>
> 📦 **افتح TopGate لعرض المنتج**

**🇬🇧 الإنجليزية:**
> **Don't miss this product!**
>
> Thousands of products from Turkey's largest wholesale textile marketplace await you.
> Compare prices, contact suppliers directly, and grow your business —
> all in one app.
>
> 📦 **Open TopGate to view this product**

**نص زر CTA:**
- 🇹🇷 `Uygulamada Görüntüle` (عرض في التطبيق)
- 🇸🇦 `عرض في التطبيق`
- 🇬🇧 `View in App`

---

### 🔗 رابط 2: ملف المورد (Supplier Profile)
**URL:** `https://link.topkap.app/supplier/{supplier_id}`
**الجمهور:** التجار والمشترين (Buyers / Traders)
**السياق:** يُشارك من قِبل الموردين لجذب متابعين جدد

#### الرسائل التحفيزية

**🇹🇷 التركية:**
> **Güvenilir Türk Tedarikçiyle Tanışın!**
>
> Bu tedarikçi, TopKap'ın doğrulanmış tedarikçileri arasında yer almaktadır.
> Tüm ürün kataloğunu inceleyin, fiyat teklifleri alın ve
> uzun vadeli ticari ilişkiler kurun.
>
> ✅ **Doğrulanmış Tedarikçi** | 🌍 **180+ Ülkeye İhracat**

**🇸🇦 العربية:**
> **تعرّف على مورد تركي موثوق!**
>
> هذا المورد من بين الموردين المعتمدين على منصة TopKap.
> استعرض كامل كتالوج منتجاته، احصل على عروض أسعار، وابنِ
> علاقات تجارية طويلة الأمد.
>
> ✅ **مورد معتمد** | 🌍 **تصدير لـ 180+ دولة**

**🇬🇧 الإنجليزية:**
> **Meet a Verified Turkish Supplier!**
>
> This supplier is among TopKap's verified and trusted suppliers.
> Browse their full product catalog, request price quotes, and
> build long-term business relationships.
>
> ✅ **Verified Supplier** | 🌍 **Exporting to 180+ Countries**

**نص زر CTA:**
- 🇹🇷 `Tedarikçiyi İncele` (استعرض المورد)
- 🇸🇦 `استعرض ملف المورد`
- 🇬🇧 `View Supplier Profile`

---

### 🔗 رابط 3: فتح محادثة مع المورد (Chat with Supplier)
**URL:** `https://link.topkap.app/chat/{supplier_id}`
**الجمهور:** التجار والمشترين
**السياق:** زر "تواصل مع المورد" في منشورات المنتجات

#### الرسائل التحفيزية

**🇹🇷 التركية:**
> **Tedarikçiyle Doğrudan Konuşun!**
>
> Aracı yok, komisyon yok — sadece siz ve tedarikçi.
> Fiyat müzakeresi yapın, özel teklifler alın ve
> siparişlerinizi güvenle verin.
>
> 💬 **Şimdi mesaj gönderin — ücretsiz!**

**🇸🇦 العربية:**
> **تواصل مع المورد مباشرة!**
>
> بدون وسيط، بدون عمولة — أنت والمورد فقط.
> فاوض على الأسعار، احصل على عروض خاصة، وأرسل
> طلباتك بثقة تامة.
>
> 💬 **أرسل رسالة الآن — مجاناً!**

**🇬🇧 الإنجليزية:**
> **Chat Directly with the Supplier!**
>
> No middlemen, no commissions — just you and the supplier.
> Negotiate prices, get exclusive offers, and place your
> orders with full confidence.
>
> 💬 **Send a message now — it's free!**

**نص زر CTA:**
- 🇹🇷 `Şimdi Mesaj Gönder` (أرسل رسالة الآن)
- 🇸🇦 `تواصل الآن`
- 🇬🇧 `Chat Now`

---

### 🔗 رابط 4: إحصائيات المورد (Seller Statistics)
**URL:** `https://link.topkap.app/seller/statistics`
**الجمهور:** الموردون (Suppliers)
**السياق:** زر "الإحصائيات" في لوحة تحكم البوت

#### الرسائل التحفيزية

**🇹🇷 التركية:**
> **İşletmenizin Nabzını Tutun!**
>
> Gerçek zamanlı satış raporları, ürün görüntülenme istatistikleri
> ve kanal performans analizleri — hepsi tek ekranda.
> Veriye dayalı kararlar alın ve rakiplerinizin önüne geçin.
>
> 📊 **İstatistiklerinizi görmek için TopKap'ı açın**

**🇸🇦 العربية:**
> **راقب نبض تجارتك!**
>
> تقارير مبيعات فورية، إحصائيات مشاهدات المنتجات
> وتحليل أداء قناتك — كل ذلك في شاشة واحدة.
> اتخذ قرارات مبنية على البيانات وتفوّق على منافسيك.
>
> 📊 **افتح TopKap لعرض إحصائياتك**

**🇬🇧 الإنجليزية:**
> **Monitor Your Business Pulse!**
>
> Real-time sales reports, product view statistics,
> and channel performance analytics — all on one screen.
> Make data-driven decisions and stay ahead of the competition.
>
> 📊 **Open TopKap to view your statistics**

**نص زر CTA:**
- 🇹🇷 `İstatistikleri Gör` (عرض الإحصائيات)
- 🇸🇦 `عرض الإحصائيات`
- 🇬🇧 `View Statistics`

---

### 🔗 رابط 5: اشتراك المورد (Seller Subscription)
**URL:** `https://link.topkap.app/seller/subscription`
**الجمهور:** الموردون (Suppliers)
**السياق:** زر "اشتراكي" في لوحة تحكم البوت

#### الرسائل التحفيزية

**🇹🇷 التركية:**
> **İşletmenizi Bir Üst Seviyeye Taşıyın!**
>
> Premium üyelikle daha fazla ürün listeleyin, öncelikli sıralamada
> görünün ve özel müşteri desteğinden yararlanın.
> Türkiye'nin en büyük tekstil pazarında öne çıkın.
>
> 💎 **Premium'a geçin — ilk ay ücretsiz!**

**🇸🇦 العربية:**
> **ارتقِ بتجارتك لمستوى أعلى!**
>
> مع العضوية المميزة، أضف منتجات أكثر، احتل مراتب أعلى في
> نتائج البحث، واستفد من دعم عملاء ذي أولوية.
> تميّز في أكبر سوق نسيج في تركيا.
>
> 💎 **انتقل إلى Premium — الشهر الأول مجاناً!**

**🇬🇧 الإنجليزية:**
> **Take Your Business to the Next Level!**
>
> With a Premium membership, list more products, rank higher in
> search results, and enjoy priority customer support.
> Stand out in Turkey's largest textile marketplace.
>
> 💎 **Upgrade to Premium — first month free!**

**نص زر CTA:**
- 🇹🇷 `Premium'a Geç` (الترقية إلى Premium)
- 🇸🇦 `ترقية إلى Premium`
- 🇬🇧 `Upgrade to Premium`

---

## المتطلبات التقنية للصفحات (Technical Requirements)

### 1. اكتشاف اللغة التلقائي (Auto Language Detection)
يجب أن تكتشف الصفحة لغة المستخدم تلقائياً من:
- `Accept-Language` HTTP header (الأولوية الأولى)
- معامل URL: `?lang=ar` أو `?lang=tr` أو `?lang=en` (الأولوية الثانية)
- الاحتياطي الافتراضي: التركية (`tr`)

### 2. اكتشاف الجهاز (Device Detection)
يجب أن تكتشف الصفحة نوع الجهاز من `User-Agent` وتوجه زر التحميل:
- **iOS (iPhone/iPad):** رابط App Store
- **Android:** رابط Google Play
- **Desktop/Unknown:** عرض كلا الزرين (App Store + Google Play)

### 3. الـ Deferred Deep Link SDK
يجب دمج SDK الخاص بخدمة الروابط (AppsFlyer أو Branch.io) في:
- صفحة الهبوط (لتسجيل نية المستخدم قبل التثبيت)
- التطبيق نفسه (لاسترداد النية بعد التثبيت والتوجيه للصفحة الصحيحة)

### 4. Open Graph Tags (للمشاركة الاجتماعية)
يجب أن تحتوي كل صفحة على:
```html
<meta property="og:title"       content="[اسم المنتج / المورد]" />
<meta property="og:description" content="[الرسالة التحفيزية المختصرة]" />
<meta property="og:image"       content="[صورة المنتج / المورد]" />
<meta property="og:url"         content="[الرابط الكامل]" />
```
هذا يجعل الرابط يظهر بمعاينة جميلة (Preview Card) عند مشاركته في تيليغرام وواتساب.

### 5. معايير الأداء (Performance Standards)
- **وقت التحميل:** أقل من 2 ثانية على الشبكات المتوسطة (3G)
- **الحجم:** أقل من 200KB لكل صفحة
- **التصميم:** Responsive — يعمل على جميع أحجام الشاشات

---

## ملخص جدول الروابط والرسائل

| الرابط | الجمهور | الرسالة الرئيسية (عربي) | نص زر CTA (عربي) |
|---|---|---|---|
| `/product/{id}` | تجار / مشترين | لا تفوّت هذا المنتج! | عرض في التطبيق |
| `/supplier/{id}` | تجار / مشترين | تعرّف على مورد تركي موثوق! | استعرض ملف المورد |
| `/chat/{id}` | تجار / مشترين | تواصل مع المورد مباشرة! | تواصل الآن |
| `/seller/statistics` | موردون | راقب نبض تجارتك! | عرض الإحصائيات |
| `/seller/subscription` | موردون | ارتقِ بتجارتك لمستوى أعلى! | ترقية إلى Premium |

---

نحن جاهزون لمراجعة التصاميم المقترحة وتقديم أي ملاحظات تقنية إضافية.
هذه المتطلبات قابلة للتعديل بناءً على إمكانيات الـ SDK المختار من طرفكم.
