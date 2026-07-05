-- N3P trigger-proof condition-grain UNIQUE compatibility.
-- Artifact only. Execute only in an explicit schema migration gate.

BEGIN;

ALTER TABLE stock_action_confirmation_projection_metric
  DROP CONSTRAINT stock_action_confirmation_pro_projection_run_id_identity_ke_key;

CREATE UNIQUE INDEX stock_action_confirmation_projection_metric_legacy_object_minute_uidx
ON stock_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version
)
WHERE NOT COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

CREATE UNIQUE INDEX stock_action_confirmation_projection_metric_trigger_proof_condition_grain_uidx
ON stock_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version,
  (COALESCE(raw_json->>'direction', trace_json#>>'{higher_period_context_source,context_direction}', '')),
  (COALESCE(raw_json->>'signal_type', '')),
  (COALESCE(raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'original_condition_key', raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'source_condition_pool_id', trace_json#>>'{higher_period_context_source,source_condition_pool_id}', '')),
  (COALESCE(raw_json->>'source_minute_target_scope_id', trace_json#>>'{higher_period_context_source,source_minute_target_scope_id}', ''))
)
WHERE COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

ALTER TABLE index_action_confirmation_projection_metric
  DROP CONSTRAINT index_action_confirmation_pro_projection_run_id_identity_ke_key;

CREATE UNIQUE INDEX index_action_confirmation_projection_metric_legacy_object_minute_uidx
ON index_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version
)
WHERE NOT COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

CREATE UNIQUE INDEX index_action_confirmation_projection_metric_trigger_proof_condition_grain_uidx
ON index_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version,
  (COALESCE(raw_json->>'direction', trace_json#>>'{higher_period_context_source,context_direction}', '')),
  (COALESCE(raw_json->>'signal_type', '')),
  (COALESCE(raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'original_condition_key', raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'source_condition_pool_id', trace_json#>>'{higher_period_context_source,source_condition_pool_id}', '')),
  (COALESCE(raw_json->>'source_minute_target_scope_id', trace_json#>>'{higher_period_context_source,source_minute_target_scope_id}', ''))
)
WHERE COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

ALTER TABLE board_action_confirmation_projection_metric
  DROP CONSTRAINT board_action_confirmation_pro_projection_run_id_identity_ke_key;

CREATE UNIQUE INDEX board_action_confirmation_projection_metric_legacy_object_minute_uidx
ON board_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version
)
WHERE NOT COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

CREATE UNIQUE INDEX board_action_confirmation_projection_metric_trigger_proof_condition_grain_uidx
ON board_action_confirmation_projection_metric (
  projection_run_id,
  identity_key,
  trade_date,
  metric_minute_label,
  projection_schema_version,
  (COALESCE(raw_json->>'direction', trace_json#>>'{higher_period_context_source,context_direction}', '')),
  (COALESCE(raw_json->>'signal_type', '')),
  (COALESCE(raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'original_condition_key', raw_json->>'condition_key', '')),
  (COALESCE(raw_json->>'source_condition_pool_id', trace_json#>>'{higher_period_context_source,source_condition_pool_id}', '')),
  (COALESCE(raw_json->>'source_minute_target_scope_id', trace_json#>>'{higher_period_context_source,source_minute_target_scope_id}', ''))
)
WHERE COALESCE((
  raw_json->>'metric_role' = 'trigger_proof'
  AND raw_json->>'proof_consumer' = 'N4'
  AND raw_json->>'proof_owner' = 'N3'
  AND raw_json->>'not_n5_final_proof' = 'true'
  AND raw_json->>'action_confirmation_ready' = 'false'
), FALSE);

COMMIT;
