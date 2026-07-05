-- N3 projection enrichment v4 row-level materialization schema rollback draft.
-- Scope: drop only the three additive N3 projection enrichment v4 tables.
-- Boundary: schema rollback hard-fails if any table contains rows.

BEGIN;

DO $$
DECLARE
  v_existing_rows bigint := 0;
BEGIN
  IF to_regclass('public.stock_projection_enrichment_v4_metric') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM stock_projection_enrichment_v4_metric' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '034 rollback blocked: stock_projection_enrichment_v4_metric has % rows', v_existing_rows;
  END IF;

  v_existing_rows := 0;
  IF to_regclass('public.index_projection_enrichment_v4_metric') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM index_projection_enrichment_v4_metric' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '034 rollback blocked: index_projection_enrichment_v4_metric has % rows', v_existing_rows;
  END IF;

  v_existing_rows := 0;
  IF to_regclass('public.board_projection_enrichment_v4_metric') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM board_projection_enrichment_v4_metric' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '034 rollback blocked: board_projection_enrichment_v4_metric has % rows', v_existing_rows;
  END IF;
END $$;

DROP TABLE IF EXISTS board_projection_enrichment_v4_metric;
DROP TABLE IF EXISTS index_projection_enrichment_v4_metric;
DROP TABLE IF EXISTS stock_projection_enrichment_v4_metric;

COMMIT;
