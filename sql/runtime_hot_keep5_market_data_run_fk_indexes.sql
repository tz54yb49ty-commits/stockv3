-- Runtime hot keep-5 cleanup common_market_data_run child FK indexes.
-- Purpose: speed up common_market_data_run FK child lookups during old hot runtime cleanup.

CREATE INDEX IF NOT EXISTS idx_board_acpm_prev_day_run
  ON board_action_confirmation_projection_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_acpm_subscription_run
  ON board_action_confirmation_projection_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_board_acpm_today_minute_run
  ON board_action_confirmation_projection_metric (source_today_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_action_fact_market_data_run
  ON board_action_fact (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_board_c30_enrich_prev_day_run
  ON board_closed_30m_signal_enrichment (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_c30_enrich_subscription_run
  ON board_closed_30m_signal_enrichment (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_board_c30_summary_subscription_run
  ON board_closed_30m_summary (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_c3_run
  ON board_eod_snapshot (source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_board_proj_enrich_prev_day_run
  ON board_projection_enrichment_v4_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_proj_enrich_subscription_run
  ON board_projection_enrichment_v4_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_board_proj_enrich_today_minute_run
  ON board_projection_enrichment_v4_metric (source_today_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_hint_proj_prev_day_run
  ON board_realtime_hint_projection_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_hint_proj_subscription_run
  ON board_realtime_hint_projection_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_common_action_event_market_data_run
  ON common_action_event (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_common_position_event_market_data_run
  ON common_position_event (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_common_trigger_run_market_data_run
  ON common_trigger_run (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_index_acpm_prev_day_run
  ON index_action_confirmation_projection_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_acpm_subscription_run
  ON index_action_confirmation_projection_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_index_acpm_today_minute_run
  ON index_action_confirmation_projection_metric (source_today_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_action_fact_market_data_run
  ON index_action_fact (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_index_c30_enrich_prev_day_run
  ON index_closed_30m_signal_enrichment (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_c30_enrich_subscription_run
  ON index_closed_30m_signal_enrichment (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_index_c30_summary_subscription_run
  ON index_closed_30m_summary (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_c3_run
  ON index_eod_snapshot (source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_index_proj_enrich_prev_day_run
  ON index_projection_enrichment_v4_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_proj_enrich_subscription_run
  ON index_projection_enrichment_v4_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_index_proj_enrich_today_minute_run
  ON index_projection_enrichment_v4_metric (source_today_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_hint_proj_prev_day_run
  ON index_realtime_hint_projection_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_hint_proj_subscription_run
  ON index_realtime_hint_projection_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_acpm_prev_day_run
  ON stock_action_confirmation_projection_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_acpm_subscription_run
  ON stock_action_confirmation_projection_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_acpm_today_minute_run
  ON stock_action_confirmation_projection_metric (source_today_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_action_fact_market_data_run
  ON stock_action_fact (source_market_data_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_c30_enrich_prev_day_run
  ON stock_closed_30m_signal_enrichment (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_c30_enrich_subscription_run
  ON stock_closed_30m_signal_enrichment (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_c30_summary_subscription_run
  ON stock_closed_30m_summary (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_c3_run
  ON stock_eod_snapshot (source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_proj_enrich_prev_day_run
  ON stock_projection_enrichment_v4_metric (source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_proj_enrich_subscription_run
  ON stock_projection_enrichment_v4_metric (source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_proj_enrich_today_minute_run
  ON stock_projection_enrichment_v4_metric (source_today_minute_run_id);
