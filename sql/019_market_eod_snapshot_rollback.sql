-- N3-EOD 019 schema rollback draft.
-- Only safe before any EOD business rows exist.

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  SELECT
    COALESCE((SELECT count(*) FROM stock_eod_reconciliation_item), 0)
    + COALESCE((SELECT count(*) FROM index_eod_reconciliation_item), 0)
    + COALESCE((SELECT count(*) FROM board_eod_reconciliation_item), 0)
    + COALESCE((SELECT count(*) FROM stock_eod_snapshot), 0)
    + COALESCE((SELECT count(*) FROM index_eod_snapshot), 0)
    + COALESCE((SELECT count(*) FROM board_eod_snapshot), 0)
  INTO v_count;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing 019 schema rollback: EOD tables contain % rows. Run business rollback by eod_run_id first.', v_count;
  END IF;
END $$;

DROP TABLE IF EXISTS board_eod_reconciliation_item;
DROP TABLE IF EXISTS index_eod_reconciliation_item;
DROP TABLE IF EXISTS stock_eod_reconciliation_item;
DROP TABLE IF EXISTS board_eod_snapshot;
DROP TABLE IF EXISTS index_eod_snapshot;
DROP TABLE IF EXISTS stock_eod_snapshot;
