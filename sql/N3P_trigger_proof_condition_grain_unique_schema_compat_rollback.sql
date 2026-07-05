-- Rollback for N3P trigger-proof condition-grain UNIQUE compatibility.
-- Artifact only. Execute only in an explicit rollback gate.

BEGIN;

DROP INDEX IF EXISTS stock_action_confirmation_projection_metric_legacy_object_minut;
DROP INDEX IF EXISTS stock_action_confirmation_projection_metric_trigger_proof_condi;

ALTER TABLE stock_action_confirmation_projection_metric
  ADD CONSTRAINT stock_action_confirmation_pro_projection_run_id_identity_ke_key UNIQUE
  (projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version);

DROP INDEX IF EXISTS index_action_confirmation_projection_metric_legacy_object_minut;
DROP INDEX IF EXISTS index_action_confirmation_projection_metric_trigger_proof_condi;

ALTER TABLE index_action_confirmation_projection_metric
  ADD CONSTRAINT index_action_confirmation_pro_projection_run_id_identity_ke_key UNIQUE
  (projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version);

DROP INDEX IF EXISTS board_action_confirmation_projection_metric_legacy_object_minut;
DROP INDEX IF EXISTS board_action_confirmation_projection_metric_trigger_proof_condi;

ALTER TABLE board_action_confirmation_projection_metric
  ADD CONSTRAINT board_action_confirmation_pro_projection_run_id_identity_ke_key UNIQUE
  (projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version);

COMMIT;
