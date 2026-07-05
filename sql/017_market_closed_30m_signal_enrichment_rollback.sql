-- Rollback draft for sql/017_market_closed_30m_signal_enrichment_schema.sql.
-- Schema rollback is allowed only while the three enrichment tables are empty.

DO $$
BEGIN
  IF to_regclass('public.stock_closed_30m_signal_enrichment') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.stock_closed_30m_signal_enrichment LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop stock_closed_30m_signal_enrichment: table contains rows; clear C2B business rows first';
  END IF;

  IF to_regclass('public.index_closed_30m_signal_enrichment') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.index_closed_30m_signal_enrichment LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop index_closed_30m_signal_enrichment: table contains rows; clear C2B business rows first';
  END IF;

  IF to_regclass('public.board_closed_30m_signal_enrichment') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.board_closed_30m_signal_enrichment LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop board_closed_30m_signal_enrichment: table contains rows; clear C2B business rows first';
  END IF;
END $$;

DROP TABLE IF EXISTS board_closed_30m_signal_enrichment;
DROP TABLE IF EXISTS index_closed_30m_signal_enrichment;
DROP TABLE IF EXISTS stock_closed_30m_signal_enrichment;
