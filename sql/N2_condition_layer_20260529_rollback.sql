-- Rollback draft for N2 20260529 -> 20260601 condition layer run.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   Delete only condition_layer_20260529_source_20260529_v1 rows.
--   No previous 20260529 -> 20260601 active run is restored by this rollback.
--
-- Boundary:
--   Does not touch N1 source_version.
--   Does not touch common_event_outbox / common_event_inbox / common_event_consumer_checkpoint.
--   Does not touch N3/N4/N5/N6 business rows.
--   Blocks if condition_layer_20260529_source_20260529_v1 already has downstream N3/N4/N5/N6 references.

BEGIN;

DO $$
DECLARE
  rollback_run_id text := 'condition_layer_20260529_source_20260529_v1';
  downstream_refs bigint := 0;
BEGIN
  SELECT
      COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = rollback_run_id OR user_projection_run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((
        SELECT count(*)
        FROM user_signal_projection
        WHERE source_condition_display_run_id = rollback_run_id
           OR source_condition_display_basis_id IN (
                SELECT stock_condition_display_basis_id FROM stock_condition_display_basis WHERE run_id = rollback_run_id
                UNION ALL
                SELECT index_condition_display_basis_id FROM index_condition_display_basis WHERE run_id = rollback_run_id
                UNION ALL
                SELECT board_condition_display_basis_id FROM board_condition_display_basis WHERE run_id = rollback_run_id
           )
      ), 0)
  INTO downstream_refs;

  IF downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream N3/N4/N5/N6 refs exist for % (% rows)', rollback_run_id, downstream_refs;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v1';

DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v1';

DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v1';

DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v1';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260529_source_20260529_v1';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260529_source_20260529_v1';

COMMIT;
