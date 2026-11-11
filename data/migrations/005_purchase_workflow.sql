CREATE TABLE business.purchase_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_id BIGINT NOT NULL REFERENCES business.users(id),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0 AND quantity <> 'NaN'::numeric),
    unit TEXT NOT NULL CHECK (length(trim(unit)) > 0),
    budget NUMERIC(18,2) CHECK (budget >= 0 AND budget <> 'NaN'::numeric),
    currency TEXT NOT NULL DEFAULT 'VND' CHECK (currency='VND'),
    budget_type TEXT NOT NULL CHECK (budget_type IN ('per_unit','total')),
    delivery_location TEXT NOT NULL,
    delivery_deadline DATE NOT NULL,
    additional_requirements TEXT NOT NULL DEFAULT '',
    source TEXT,
    product_id TEXT,
    contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    contact_phone TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK
        (status IN ('open','assigned','quoted','selected','connected','cancelled','closed_no_match')),
    selected_quote_id BIGINT,
    demo_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((source IS NULL AND product_id IS NULL) OR
        (source IS NOT NULL AND source=upper(trim(source)) AND length(source)>0
         AND product_id IS NOT NULL AND product_id=trim(product_id) AND length(product_id)>0))
);
CREATE INDEX purchase_requests_buyer_idx ON business.purchase_requests(buyer_id);
CREATE TABLE business.request_matches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES business.purchase_requests(id),
    supplier_id BIGINT NOT NULL REFERENCES business.suppliers(id),
    assigned_by BIGINT NOT NULL REFERENCES business.users(id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned','quoted','declined','selected')),
    decline_reason TEXT NOT NULL DEFAULT '',
    UNIQUE(request_id,supplier_id),
    UNIQUE(request_id,id)
);
CREATE TABLE business.request_quotes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES business.purchase_requests(id),
    match_id BIGINT NOT NULL,
    version INTEGER NOT NULL CHECK (version>0),
    quantity NUMERIC(18,3) NOT NULL CHECK (quantity>0 AND quantity <> 'NaN'::numeric),
    unit TEXT NOT NULL,
    unit_price NUMERIC(18,2) NOT NULL CHECK (unit_price>=0 AND unit_price <> 'NaN'::numeric),
    shipping_fee NUMERIC(18,2) CHECK (shipping_fee>=0 AND shipping_fee <> 'NaN'::numeric),
    total_amount NUMERIC(18,2) NOT NULL CHECK (total_amount>=0 AND total_amount <> 'NaN'::numeric),
    expected_delivery DATE NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    excluded_costs TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','selected')),
    created_by BIGINT NOT NULL REFERENCES business.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(request_id,match_id) REFERENCES business.request_matches(request_id,id),
    UNIQUE(match_id,version), UNIQUE(request_id,id),
    CHECK (total_amount=round(quantity*unit_price+coalesce(shipping_fee,0),2))
);
CREATE UNIQUE INDEX one_current_quote_per_match ON business.request_quotes(match_id) WHERE status='active';
CREATE UNIQUE INDEX one_selected_quote_per_request ON business.request_quotes(request_id) WHERE status='selected';
CREATE UNIQUE INDEX one_selected_match_per_request ON business.request_matches(request_id) WHERE status='selected';
ALTER TABLE business.purchase_requests ADD CONSTRAINT selected_quote_owns_request
    FOREIGN KEY(id,selected_quote_id) REFERENCES business.request_quotes(request_id,id);
CREATE TABLE business.request_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES business.purchase_requests(id),
    match_id BIGINT,
    actor_id BIGINT NOT NULL REFERENCES business.users(id),
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(request_id,match_id) REFERENCES business.request_matches(request_id,id)
);
REVOKE ALL ON business.purchase_requests,business.request_matches,business.request_quotes,business.request_events FROM PUBLIC;
