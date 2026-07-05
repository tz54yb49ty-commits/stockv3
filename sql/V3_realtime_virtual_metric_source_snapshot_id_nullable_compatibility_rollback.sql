DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_realtime_virtual_metric_source_snapshot_id_nullable_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'source_snapshot_id nullable compatibility rollback blocked by default; set reviewed session flag after final gate approval';
  END IF;
END $$;

BEGIN;

DO $$
DECLARE
  null_refs bigint := 0;
BEGIN
  SELECT
    (SELECT count(*) FROM stock_action_confirmation_projection_metric WHERE source_snapshot_id IS NULL) +
    (SELECT count(*) FROM index_action_confirmation_projection_metric WHERE source_snapshot_id IS NULL) +
    (SELECT count(*) FROM board_action_confirmation_projection_metric WHERE source_snapshot_id IS NULL)
  INTO null_refs;

  IF null_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: source_snapshot_id IS NULL refs=%', null_refs;
  END IF;
END $$;

ALTER TABLE stock_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id SET NOT NULL;

ALTER TABLE index_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id SET NOT NULL;

ALTER TABLE board_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id SET NOT NULL;

COMMIT;
