-- =====================================================
-- إنشاء جدول quote_requests لميزة RFQ
-- TurkTextileHub - نسخة مُصحَّحة (UUID متوافقة)
-- =====================================================

CREATE TABLE IF NOT EXISTS quote_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- المنتج المطلوب (UUID يتوافق مع جدول products)
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,

    -- المورد (UUID يتوافق مع جدول bot_registrations)
    supplier_id     UUID NOT NULL REFERENCES bot_registrations(id) ON DELETE CASCADE,

    -- معرّف التاجر على تيليجرام (BIGINT لأن Telegram IDs أرقام كبيرة)
    trader_id       BIGINT NOT NULL,

    -- تفاصيل الطلب (جميعها اختيارية - التاجر يمكنه التخطي)
    quantity        TEXT,
    color           TEXT,
    size            TEXT,
    delivery_date   TEXT,
    notes           TEXT,

    -- حالة الطلب
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'viewed', 'responded', 'closed')),

    -- التوقيتات
    request_time    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- فهارس للبحث السريع
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_qr_product_id   ON quote_requests(product_id);
CREATE INDEX IF NOT EXISTS idx_qr_supplier_id  ON quote_requests(supplier_id);
CREATE INDEX IF NOT EXISTS idx_qr_trader_id    ON quote_requests(trader_id);
CREATE INDEX IF NOT EXISTS idx_qr_status       ON quote_requests(status);

-- =====================================================
-- تعليق توضيحي على الجدول
-- =====================================================
COMMENT ON TABLE quote_requests IS 'طلبات عروض الأسعار من التجار للموردين - ميزة RFQ';

-- =====================================================
-- دالة تحديث updated_at تلقائياً
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_quote_requests_updated_at
    BEFORE UPDATE ON quote_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
