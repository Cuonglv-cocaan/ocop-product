-- Separate source namespaces allow equal SQLite IDs from distinct source files.
-- Old imported IDs belong to the reserved source "legacy-default".
ALTER TABLE business.leads ADD COLUMN legacy_sqlite_source TEXT;
UPDATE business.leads SET legacy_sqlite_source = 'legacy-default'
WHERE legacy_sqlite_id IS NOT NULL;
ALTER TABLE business.leads DROP CONSTRAINT leads_legacy_sqlite_id_key;
ALTER TABLE business.leads ADD CONSTRAINT leads_sqlite_source_id_key
    UNIQUE (legacy_sqlite_source, legacy_sqlite_id);
ALTER TABLE business.leads ADD CONSTRAINT leads_sqlite_identity_complete CHECK (
    (legacy_sqlite_source IS NULL AND legacy_sqlite_id IS NULL) OR
    (legacy_sqlite_source IS NOT NULL AND length(trim(legacy_sqlite_source)) > 0
     AND legacy_sqlite_id IS NOT NULL)
);
