-- ═══════════════════════════════════════════════════════════════════════════
-- Migration: 003_create_quote_requests.sql
-- TurkTextileHub — جدول طلبات عروض الأسعار (RFQ)
--
-- الوصف:
--   ينشئ جدول quote_requests الذي يخزّن طلبات عروض الأسعار التي
--   يرسلها التجار للموردين عبر بوت تليجرام.
--
-- العلاقات:
--   product_id  → products(id)         CASCADE DELETE
--   supplier_id → suppliers(id)        CASCADE DELETE
--   trader_id   → traders(telegram_id) CASCADE DELETE (bigint)
--
-- حالات الطلب (status):
--   pending   = طلب جديد لم يُرَد عليه بعد
--   answered  = المورد ردّ على الطلب
--   closed    = الطلب مُغلق (تم أو ملغى)
--
-- Row Level Security:
--   SELECT: متاح للجميع (لوحة التحكم تحتاج قراءة كل الطلبات)
--   INSERT: متاح لأي مستخدم مسجّل (auth.uid() IS NOT NULL)
--   UPDATE: متاح للمستخدمين المسجّلين (للمورد ليُحدِّث الحالة)
-- ═══════════════════════════════════════════════════════════════════════════

-- ── إنشاء الجدول ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.quote_requests (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    product_id    UUID        REFERENCES public.products(id)         ON DELETE CASCADE,
    supplier_id   UUID        REFERENCES public.suppliers(id)        ON DELETE CASCADE,
    trader_id     BIGINT      REFERENCES public.traders(telegram_id) ON DELETE CASCADE,
    quantity      TEXT,
    color         TEXT,
    size          TEXT,
    delivery_date TEXT,
    status        TEXT        DEFAULT 'pending' NOT NULL
                              CHECK (status IN ('pending', 'answered', 'closed')),
    created_at    TIMESTAMP WITH TIME ZONE
                              DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ── فهارس للبحث السريع ──────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quote_requests_supplier_id
    ON public.quote_requests(supplier_id);

CREATE INDEX IF NOT EXISTS idx_quote_requests_trader_id
    ON public.quote_requests(trader_id);

CREATE INDEX IF NOT EXISTS idx_quote_requests_product_id
    ON public.quote_requests(product_id);

CREATE INDEX IF NOT EXISTS idx_quote_requests_status
    ON public.quote_requests(status);

CREATE INDEX IF NOT EXISTS idx_quote_requests_created_at
    ON public.quote_requests(created_at DESC);

-- ── Row Level Security ───────────────────────────────────────────────────────
ALTER TABLE public.quote_requests ENABLE ROW LEVEL SECURITY;

-- قراءة: متاح للجميع (لوحة التحكم + المورد + التاجر)
CREATE POLICY "Allow public read access"
    ON public.quote_requests
    FOR SELECT
    USING (true);

-- إدراج: متاح لأي مستخدم مسجّل (البوت يعمل بـ service_role key لذا دائماً مسموح)
CREATE POLICY "Allow individual insert"
    ON public.quote_requests
    FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL);

-- تحديث: متاح لأي مستخدم مسجّل (المورد يُحدِّث status)
CREATE POLICY "Allow authenticated update"
    ON public.quote_requests
    FOR UPDATE
    USING (auth.uid() IS NOT NULL);

-- ── تعليق توضيحي على الجدول ─────────────────────────────────────────────────
COMMENT ON TABLE public.quote_requests IS
    'طلبات عروض الأسعار (RFQ) التي يرسلها التجار للموردين عبر بوت تليجرام';

COMMENT ON COLUMN public.quote_requests.status IS
    'حالة الطلب: pending = جديد، answered = تم الرد، closed = مغلق';

COMMENT ON COLUMN public.quote_requests.trader_id IS
    'Telegram ID للتاجر — مرجع لجدول traders(telegram_id)';
