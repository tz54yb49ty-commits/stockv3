-- Rollback draft for sql/016_market_closed_30m_summary_schema.sql.
-- Schema rollback only. Execute only after C2 business rows, if any, have
-- already been removed by c2_run_id from stock/index/board_closed_30m_summary.

DO $$
BEGIN
  IF to_regclass('public.stock_closed_30m_summary') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.stock_closed_30m_summary LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop stock_closed_30m_summary: table contains rows; run C2 business rollback by c2_run_id first';
  END IF;

  IF to_regclass('public.index_closed_30m_summary') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.index_closed_30m_summary LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop index_closed_30m_summary: table contains rows; run C2 business rollback by c2_run_id first';
  END IF;

  IF to_regclass('public.board_closed_30m_summary') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.board_closed_30m_summary LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop board_closed_30m_summary: table contains rows; run C2 business rollback by c2_run_id first';
  END IF;
END $$;

DROP TABLE IF EXISTS board_closed_30m_summary;
DROP TABLE IF EXISTS index_closed_30m_summary;
DROP TABLE IF EXISTS stock_closed_30m_summary;
