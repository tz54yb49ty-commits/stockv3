-- N2 context enrichment row-level materialization schema rollback draft.
-- Scope: remove only the four tables introduced by 033.
-- Boundary: schema rollback is blocked if any materialization rows exist.

BEGIN;

DO $$
DECLARE
  v_existing_rows bigint := 0;
BEGIN
  IF to_regclass('public.stock_condition_context_enrichment') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM stock_condition_context_enrichment' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '033 rollback blocked: stock_condition_context_enrichment has % rows', v_existing_rows;
  END IF;

  IF to_regclass('public.index_condition_context_enrichment') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM index_condition_context_enrichment' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '033 rollback blocked: index_condition_context_enrichment has % rows', v_existing_rows;
  END IF;

  IF to_regclass('public.board_condition_context_enrichment') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM board_condition_context_enrichment' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '033 rollback blocked: board_condition_context_enrichment has % rows', v_existing_rows;
  END IF;

  IF to_regclass('public.common_condition_context_enrichment_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_condition_context_enrichment_run' INTO v_existing_rows;
  END IF;
  IF v_existing_rows > 0 THEN
    RAISE EXCEPTION '033 rollback blocked: common_condition_context_enrichment_run has % rows', v_existing_rows;
  END IF;
END $$;

DROP TABLE IF EXISTS board_condition_context_enrichment;
DROP TABLE IF EXISTS index_condition_context_enrichment;
DROP TABLE IF EXISTS stock_condition_context_enrichment;
DROP TABLE IF EXISTS common_condition_context_enrichment_run;

COMMIT;
