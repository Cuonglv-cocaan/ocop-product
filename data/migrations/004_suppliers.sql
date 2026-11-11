CREATE TABLE business.suppliers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    entity_type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    province TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    delivery_areas TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','suspended')),
    created_by BIGINT NOT NULL REFERENCES business.users(id),
    reviewed_by BIGINT REFERENCES business.users(id),
    reviewed_at TIMESTAMPTZ,
    rejection_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    demo_key TEXT UNIQUE,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE business.supplier_members (
    supplier_id BIGINT NOT NULL REFERENCES business.suppliers(id),
    user_id BIGINT NOT NULL REFERENCES business.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (supplier_id,user_id)
);
CREATE INDEX supplier_members_user_idx ON business.supplier_members(user_id);
CREATE INDEX suppliers_status_idx ON business.suppliers(status);
CREATE TABLE business.supplier_products (
    supplier_id BIGINT NOT NULL REFERENCES business.suppliers(id),
    source TEXT NOT NULL CHECK (length(source)>0 AND source=upper(trim(source))),
    product_id TEXT NOT NULL CHECK (length(product_id)>0 AND product_id=trim(product_id)),
    minimum_order NUMERIC CHECK (minimum_order > 0),
    unit TEXT NOT NULL DEFAULT '',
    preparation_time TEXT NOT NULL DEFAULT '',
    capacity_description TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (supplier_id,source,product_id)
);
-- Product keys reference the separate DuckDB catalog in application code only.
REVOKE ALL ON business.suppliers,business.supplier_members,business.supplier_products FROM PUBLIC;
