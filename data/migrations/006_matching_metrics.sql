-- Explicit supplier declarations only. Never parse legacy descriptions/catalog prices.
ALTER TABLE business.supplier_products
    ADD COLUMN category TEXT NOT NULL DEFAULT '',
    ADD COLUMN service_regions TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN preparation_days INTEGER CHECK (preparation_days >= 0),
    ADD COLUMN reference_price NUMERIC(18,2) CHECK
        (reference_price >= 0 AND reference_price <> 'NaN'::numeric),
    ADD COLUMN reference_price_unit TEXT NOT NULL DEFAULT '',
    ADD CONSTRAINT reference_price_requires_unit CHECK
        (reference_price IS NULL OR length(trim(reference_price_unit)) > 0);
-- Reference price is VND per declared unit, excludes unconfirmed shipping/taxes.
ALTER TABLE business.purchase_requests
    ADD COLUMN delivery_region TEXT NOT NULL DEFAULT '',
    ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE business.purchase_requests SET is_demo=TRUE WHERE demo_key IS NOT NULL;
ALTER TABLE business.request_matches
    ADD COLUMN rule_version TEXT,
    ADD COLUMN matching_snapshot JSONB;
CREATE INDEX request_events_match_type_idx ON business.request_events(match_id,event_type,created_at);
CREATE INDEX purchase_requests_created_idx ON business.purchase_requests(created_at);
