-- A-share monitor v3 ingestion-to-condition read-only source interface.
-- Boundary: exposes raw-ingestion active versions to the condition layer.
-- It does not create condition tables, compute conditions, or start workers.

BEGIN;

CREATE OR REPLACE VIEW common_condition_active_source_version_view AS
SELECT
  substring(scope_key FROM '([0-9]{8})$') AS source_trade_date,
  data_domain,
  data_type,
  source_version AS active_source_version,
  source_batch_id,
  activated_at,
  activated_by
FROM common_active_source_version
WHERE substring(scope_key FROM '([0-9]{8})$') IS NOT NULL;

COMMENT ON VIEW common_condition_active_source_version_view IS
'Read-only stable interface for the condition layer. Extracts source_trade_date from active source scope_key and exposes active source_version without leaking scope prefixes such as TDX: or A_STOCK:.';

COMMIT;
