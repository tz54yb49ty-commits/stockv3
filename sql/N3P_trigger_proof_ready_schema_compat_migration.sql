-- N3P trigger-proof ready CHECK compatibility patch.
-- Artifact only: do not execute without an explicit schema migration gate.

BEGIN;

ALTER TABLE stock_action_confirmation_projection_metric
  DROP CONSTRAINT stock_action_confirmation_projection_metric_check;
ALTER TABLE stock_action_confirmation_projection_metric
  ADD CONSTRAINT stock_action_confirmation_projection_metric_check CHECK (
    metric_ready = false
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_120m_body_high IS NOT NULL
      AND previous_120m_body_low IS NOT NULL
      AND previous_30m_body_high IS NOT NULL
      AND previous_30m_body_low IS NOT NULL
      AND previous_5m_body_high IS NOT NULL
      AND previous_5m_body_low IS NOT NULL
      AND previous_1m_body_high IS NOT NULL
      AND previous_1m_body_low IS NOT NULL
      AND current_1m_amount IS NOT NULL
      AND current_5m_virtual_amount IS NOT NULL
      AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
      AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
      AND previous_1m_period_source <> 'not_available'
      AND previous_5m_period_source <> 'not_available'
      AND previous_30m_period_source <> 'not_available'
      AND previous_120m_period_source <> 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        previous_1m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_5m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_30m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_120m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
    )
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_1m_period_source = 'not_available'
      AND previous_5m_period_source = 'not_available'
      AND previous_30m_period_source = 'not_available'
      AND previous_120m_period_source = 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND source_fact_ids->>'source_mode' = 'b1_source_returned_snapshot'
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        raw_json->>'metric_role' = 'trigger_proof'
        OR trace_json->>'metric_role' = 'trigger_proof'
      )
      AND (
        raw_json->>'proof_owner' = 'N3'
        OR trace_json->>'proof_owner' = 'N3'
      )
      AND (
        raw_json->>'proof_consumer' = 'N4'
        OR trace_json->>'proof_consumer' = 'N4'
      )
      AND (
        raw_json->>'not_n5_final_proof' = 'true'
        OR trace_json->>'not_n5_final_proof' = 'true'
      )
      AND (
        raw_json->>'action_confirmation_ready' = 'false'
        OR trace_json->>'action_confirmation_ready' = 'false'
      )
      AND (
        raw_json->>'previous_day_cumulative_source' = 'true'
        OR trace_json->>'previous_day_cumulative_source' = 'true'
      )
      AND jsonb_typeof(raw_json->'trigger_proof_segment_source_db_compat') = 'object'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'db_facing_value' = 'not_available'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'reason' = 'trigger_proof_does_not_use_action_confirmation_segments'
    )
);

ALTER TABLE index_action_confirmation_projection_metric
  DROP CONSTRAINT index_action_confirmation_projection_metric_check;
ALTER TABLE index_action_confirmation_projection_metric
  ADD CONSTRAINT index_action_confirmation_projection_metric_check CHECK (
    metric_ready = false
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_120m_body_high IS NOT NULL
      AND previous_120m_body_low IS NOT NULL
      AND previous_30m_body_high IS NOT NULL
      AND previous_30m_body_low IS NOT NULL
      AND previous_5m_body_high IS NOT NULL
      AND previous_5m_body_low IS NOT NULL
      AND previous_1m_body_high IS NOT NULL
      AND previous_1m_body_low IS NOT NULL
      AND current_1m_amount IS NOT NULL
      AND current_5m_virtual_amount IS NOT NULL
      AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
      AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
      AND previous_1m_period_source <> 'not_available'
      AND previous_5m_period_source <> 'not_available'
      AND previous_30m_period_source <> 'not_available'
      AND previous_120m_period_source <> 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        previous_1m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_5m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_30m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_120m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
    )
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_1m_period_source = 'not_available'
      AND previous_5m_period_source = 'not_available'
      AND previous_30m_period_source = 'not_available'
      AND previous_120m_period_source = 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND source_fact_ids->>'source_mode' = 'b1_source_returned_snapshot'
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        raw_json->>'metric_role' = 'trigger_proof'
        OR trace_json->>'metric_role' = 'trigger_proof'
      )
      AND (
        raw_json->>'proof_owner' = 'N3'
        OR trace_json->>'proof_owner' = 'N3'
      )
      AND (
        raw_json->>'proof_consumer' = 'N4'
        OR trace_json->>'proof_consumer' = 'N4'
      )
      AND (
        raw_json->>'not_n5_final_proof' = 'true'
        OR trace_json->>'not_n5_final_proof' = 'true'
      )
      AND (
        raw_json->>'action_confirmation_ready' = 'false'
        OR trace_json->>'action_confirmation_ready' = 'false'
      )
      AND (
        raw_json->>'previous_day_cumulative_source' = 'true'
        OR trace_json->>'previous_day_cumulative_source' = 'true'
      )
      AND jsonb_typeof(raw_json->'trigger_proof_segment_source_db_compat') = 'object'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'db_facing_value' = 'not_available'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'reason' = 'trigger_proof_does_not_use_action_confirmation_segments'
    )
);

ALTER TABLE board_action_confirmation_projection_metric
  DROP CONSTRAINT board_action_confirmation_projection_metric_check;
ALTER TABLE board_action_confirmation_projection_metric
  ADD CONSTRAINT board_action_confirmation_projection_metric_check CHECK (
    metric_ready = false
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_120m_body_high IS NOT NULL
      AND previous_120m_body_low IS NOT NULL
      AND previous_30m_body_high IS NOT NULL
      AND previous_30m_body_low IS NOT NULL
      AND previous_5m_body_high IS NOT NULL
      AND previous_5m_body_low IS NOT NULL
      AND previous_1m_body_high IS NOT NULL
      AND previous_1m_body_low IS NOT NULL
      AND current_1m_amount IS NOT NULL
      AND current_5m_virtual_amount IS NOT NULL
      AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
      AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
      AND previous_1m_period_source <> 'not_available'
      AND previous_5m_period_source <> 'not_available'
      AND previous_30m_period_source <> 'not_available'
      AND previous_120m_period_source <> 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        previous_1m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_5m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_30m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
      AND (
        previous_120m_period_source <> 'previous_trade_date_last_period'
        OR (
          jsonb_typeof(previous_day_minute_refs) = 'array'
          AND jsonb_array_length(previous_day_minute_refs) > 0
        )
      )
    )
    OR (
      metric_quality_status = 'passed'
      AND current_price IS NOT NULL
      AND current_price_time IS NOT NULL
      AND previous_1m_period_source = 'not_available'
      AND previous_5m_period_source = 'not_available'
      AND previous_30m_period_source = 'not_available'
      AND previous_120m_period_source = 'not_available'
      AND jsonb_typeof(source_fact_ids) = 'object'
      AND source_fact_ids <> '{}'::JSONB
      AND source_fact_ids->>'source_mode' = 'b1_source_returned_snapshot'
      AND jsonb_typeof(source_minute_refs) = 'array'
      AND jsonb_array_length(source_minute_refs) > 0
      AND (
        raw_json->>'metric_role' = 'trigger_proof'
        OR trace_json->>'metric_role' = 'trigger_proof'
      )
      AND (
        raw_json->>'proof_owner' = 'N3'
        OR trace_json->>'proof_owner' = 'N3'
      )
      AND (
        raw_json->>'proof_consumer' = 'N4'
        OR trace_json->>'proof_consumer' = 'N4'
      )
      AND (
        raw_json->>'not_n5_final_proof' = 'true'
        OR trace_json->>'not_n5_final_proof' = 'true'
      )
      AND (
        raw_json->>'action_confirmation_ready' = 'false'
        OR trace_json->>'action_confirmation_ready' = 'false'
      )
      AND (
        raw_json->>'previous_day_cumulative_source' = 'true'
        OR trace_json->>'previous_day_cumulative_source' = 'true'
      )
      AND jsonb_typeof(raw_json->'trigger_proof_segment_source_db_compat') = 'object'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'db_facing_value' = 'not_available'
      AND (raw_json->'trigger_proof_segment_source_db_compat')->>'reason' = 'trigger_proof_does_not_use_action_confirmation_segments'
    )
);

COMMIT;
