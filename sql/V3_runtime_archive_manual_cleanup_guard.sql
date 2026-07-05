BEGIN;

DO $$
DECLARE
  v_trade_date text := current_setting('ashare_v3.archive_cleanup_trade_date', true);
  v_expected_total bigint := 2444428;
  v_live_total bigint;
  v_blocking_count bigint;
  v_recent_trade_dates text[];
BEGIN
  IF current_setting('ashare_v3.allow_v3_runtime_archive_manual_cleanup', true) <> 'true' THEN
    RAISE EXCEPTION 'blocked: set ashare_v3.allow_v3_runtime_archive_manual_cleanup=true in a reviewed cleanup final gate';
  END IF;
  IF current_setting('ashare_v3.archive_manifest_verified', true) <> 'true' THEN
    RAISE EXCEPTION 'blocked: archive_manifest_verified must be true before hot runtime cleanup';
  END IF;
  IF current_setting('ashare_v3.archive_manifest_file_count', true) <> '52' THEN
    RAISE EXCEPTION 'blocked: archive_manifest_file_count must be 52 before 20260612 hot runtime cleanup';
  END IF;
  IF current_setting('ashare_v3.archive_manifest_total_rows', true) <> v_expected_total::text THEN
    RAISE EXCEPTION 'blocked: archive_manifest_total_rows must be % before 20260612 hot runtime cleanup', v_expected_total;
  END IF;
  IF v_trade_date <> '20260612' THEN
    RAISE EXCEPTION 'blocked: archive_cleanup_trade_date must be 20260612, got %', v_trade_date;
  END IF;

  -- today_plus_recent_5_trade_days retention guard. Recent hot runtime rows
  -- must remain local unless a separate final gate explicitly overrides this.
  SELECT array_agg(trade_date_text ORDER BY trade_date_text DESC) INTO v_recent_trade_dates
  FROM (
    SELECT trade_date::text AS trade_date_text
    FROM common_trade_calendar
    WHERE is_open = true
    ORDER BY trade_date DESC
    LIMIT 6
  ) recent_trade_dates;
  IF v_trade_date = ANY(coalesce(v_recent_trade_dates, ARRAY[]::text[]))
     AND current_setting('ashare_v3.allow_v3_runtime_archive_cleanup_recent_trade_date', true) <> 'true' THEN
    RAISE EXCEPTION 'blocked: % is in today_plus_recent_5_trade_days retention window: %',
      v_trade_date,
      v_recent_trade_dates;
  END IF;

  SELECT count(*) INTO v_blocking_count
  FROM common_event_outbox
  WHERE trade_date = v_trade_date
    AND status = 'delivering';
  IF v_blocking_count <> 0 THEN
    RAISE EXCEPTION 'blocked: delivering outbox rows exist for %: %', v_trade_date, v_blocking_count;
  END IF;

  SELECT count(*) INTO v_blocking_count
  FROM common_event_delivery_attempt d
  WHERE EXISTS (
    SELECT 1
    FROM common_event_outbox o
    WHERE o.event_id = d.event_id
      AND o.trade_date = v_trade_date
  );
  IF v_blocking_count <> 0 THEN
    RAISE EXCEPTION 'blocked: delivery attempt rows exist for %: %', v_trade_date, v_blocking_count;
  END IF;

  SELECT count(*) INTO v_blocking_count
  FROM user_projection_run
  WHERE source_action_run_id IN (
    SELECT run_id FROM common_action_run WHERE for_trade_date = v_trade_date
  );
  IF v_blocking_count <> 0 THEN
    RAISE EXCEPTION 'blocked: N6 user projection rows exist for %: %', v_trade_date, v_blocking_count;
  END IF;

  SELECT count(*) INTO v_blocking_count
  FROM common_position_state
  WHERE for_trade_date = v_trade_date;
  IF v_blocking_count <> 0 THEN
    RAISE EXCEPTION 'blocked: position state rows exist for %: %', v_trade_date, v_blocking_count;
  END IF;

  SELECT count(*) INTO v_blocking_count
  FROM common_position_event
  WHERE for_trade_date = v_trade_date;
  IF v_blocking_count <> 0 THEN
    RAISE EXCEPTION 'blocked: position event rows exist for %: %', v_trade_date, v_blocking_count;
  END IF;

  SELECT sum(row_count) INTO v_live_total
  FROM (
    SELECT count(*) AS row_count FROM common_market_data_run WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_market_data_quality_item WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_market_data_subscription_candidate WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_market_data_subscription WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_market_data_pull_plan WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_previous_day_minute_preload_status WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_previous_day_minute_preload_status WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_previous_day_minute_preload_status WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_realtime_daily_snapshot WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_realtime_daily_snapshot WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_realtime_daily_snapshot WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_minute_bar_1m WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_minute_bar_1m WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_minute_bar_1m WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_realtime_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_realtime_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_realtime_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_action_confirmation_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_action_confirmation_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_action_confirmation_projection_metric WHERE trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_trigger_run WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_trigger_quality_item WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_trigger_context_snapshot WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_trigger_context_snapshot WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_trigger_context_snapshot WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_trigger_state WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_trigger_match WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_action_run WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_action_quality_item WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM stock_action_fact WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM index_action_fact WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM board_action_fact WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_action_event WHERE for_trade_date = v_trade_date
    UNION ALL SELECT count(*) FROM common_event_outbox WHERE trade_date = v_trade_date AND source_layer = 'N3_market_data'
    UNION ALL SELECT count(*) FROM common_event_ledger WHERE trade_date = v_trade_date AND source_layer = 'N3_market_data'
    UNION ALL SELECT count(*)
      FROM common_event_inbox i
      WHERE i.source_layer = 'N3_market_data'
        AND EXISTS (
          SELECT 1 FROM common_event_outbox o
          WHERE o.event_id = i.event_id
            AND o.trade_date = v_trade_date
            AND o.source_layer = 'N3_market_data'
        )
    UNION ALL SELECT count(*)
      FROM common_event_delivery_attempt d
      WHERE EXISTS (
        SELECT 1 FROM common_event_outbox o
        WHERE o.event_id = d.event_id
          AND o.trade_date = v_trade_date
          AND o.source_layer = 'N3_market_data'
      )
    UNION ALL SELECT count(*) FROM common_event_consumer_checkpoint
      WHERE source_layer = 'N3_market_data'
        AND last_event_time::date = to_date(v_trade_date, 'YYYYMMDD')
    UNION ALL SELECT count(*) FROM common_event_outbox WHERE trade_date = v_trade_date AND source_layer = 'N4_trigger'
    UNION ALL SELECT count(*) FROM common_event_ledger WHERE trade_date = v_trade_date AND source_layer = 'N4_trigger'
    UNION ALL SELECT count(*)
      FROM common_event_inbox i
      WHERE i.source_layer = 'N4_trigger'
        AND EXISTS (
          SELECT 1 FROM common_event_outbox o
          WHERE o.event_id = i.event_id
            AND o.trade_date = v_trade_date
            AND o.source_layer = 'N4_trigger'
        )
    UNION ALL SELECT count(*)
      FROM common_event_delivery_attempt d
      WHERE EXISTS (
        SELECT 1 FROM common_event_outbox o
        WHERE o.event_id = d.event_id
          AND o.trade_date = v_trade_date
          AND o.source_layer = 'N4_trigger'
      )
    UNION ALL SELECT count(*) FROM common_event_consumer_checkpoint
      WHERE source_layer = 'N4_trigger'
        AND last_event_time::date = to_date(v_trade_date, 'YYYYMMDD')
    UNION ALL SELECT count(*) FROM common_event_outbox WHERE trade_date = v_trade_date AND source_layer = 'N5_action'
    UNION ALL SELECT count(*) FROM common_event_ledger WHERE trade_date = v_trade_date AND source_layer = 'N5_action'
    UNION ALL SELECT count(*)
      FROM common_event_inbox i
      WHERE i.source_layer = 'N5_action'
        AND EXISTS (
          SELECT 1 FROM common_event_outbox o
          WHERE o.event_id = i.event_id
            AND o.trade_date = v_trade_date
            AND o.source_layer = 'N5_action'
        )
    UNION ALL SELECT count(*)
      FROM common_event_delivery_attempt d
      WHERE EXISTS (
        SELECT 1 FROM common_event_outbox o
        WHERE o.event_id = d.event_id
          AND o.trade_date = v_trade_date
          AND o.source_layer = 'N5_action'
      )
    UNION ALL SELECT count(*) FROM common_event_consumer_checkpoint
      WHERE source_layer = 'N5_action'
        AND last_event_time::date = to_date(v_trade_date, 'YYYYMMDD')
    UNION ALL SELECT count(*) FROM user_projection_run
      WHERE source_action_run_id IN (
        SELECT run_id FROM common_action_run WHERE for_trade_date = v_trade_date
      )
    UNION ALL SELECT count(*) FROM user_signal_projection
      WHERE user_projection_run_id IN (
        SELECT user_projection_run_id FROM user_projection_run
        WHERE source_action_run_id IN (
          SELECT run_id FROM common_action_run WHERE for_trade_date = v_trade_date
        )
      )
    UNION ALL SELECT count(*) FROM user_signal_card
      WHERE user_projection_run_id IN (
        SELECT user_projection_run_id FROM user_projection_run
        WHERE source_action_run_id IN (
          SELECT run_id FROM common_action_run WHERE for_trade_date = v_trade_date
        )
      )
    UNION ALL SELECT count(*) FROM user_notification_queue
      WHERE user_projection_run_id IN (
        SELECT user_projection_run_id FROM user_projection_run
        WHERE source_action_run_id IN (
          SELECT run_id FROM common_action_run WHERE for_trade_date = v_trade_date
        )
      )
  ) AS archived_scope;

  IF v_live_total <> v_expected_total THEN
    RAISE EXCEPTION 'blocked: live archived-scope total rows % does not match verified manifest total %', v_live_total, v_expected_total;
  END IF;
END $$;

-- N6 user projection scope; expected 0 rows for this archive.
DELETE FROM user_notification_queue
WHERE user_projection_run_id IN (
  SELECT user_projection_run_id
  FROM user_projection_run
  WHERE source_action_run_id IN (
    SELECT run_id FROM common_action_run
    WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  )
);

DELETE FROM user_signal_card
WHERE user_projection_run_id IN (
  SELECT user_projection_run_id
  FROM user_projection_run
  WHERE source_action_run_id IN (
    SELECT run_id FROM common_action_run
    WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  )
);

DELETE FROM user_signal_projection
WHERE user_projection_run_id IN (
  SELECT user_projection_run_id
  FROM user_projection_run
  WHERE source_action_run_id IN (
    SELECT run_id FROM common_action_run
    WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  )
);

DELETE FROM user_projection_run
WHERE source_action_run_id IN (
  SELECT run_id FROM common_action_run
  WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
);

-- N5 action layer.
DELETE FROM common_event_delivery_attempt d
WHERE EXISTS (
  SELECT 1 FROM common_event_outbox o
  WHERE o.event_id = d.event_id
    AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
    AND o.source_layer = 'N5_action'
);

DELETE FROM common_event_inbox i
WHERE i.source_layer = 'N5_action'
  AND EXISTS (
    SELECT 1 FROM common_event_outbox o
    WHERE o.event_id = i.event_id
      AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
      AND o.source_layer = 'N5_action'
  );

DELETE FROM common_event_consumer_checkpoint
WHERE source_layer = 'N5_action'
  AND last_event_time::date = to_date(current_setting('ashare_v3.archive_cleanup_trade_date', true), 'YYYYMMDD');

DELETE FROM common_event_ledger
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N5_action';

DELETE FROM common_event_outbox
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N5_action';

DELETE FROM common_action_event
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_action_fact
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_action_fact
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_action_fact
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_action_quality_item
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_action_run
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

-- N4 trigger layer.
DELETE FROM common_event_delivery_attempt d
WHERE EXISTS (
  SELECT 1 FROM common_event_outbox o
  WHERE o.event_id = d.event_id
    AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
    AND o.source_layer = 'N4_trigger'
);

DELETE FROM common_event_inbox i
WHERE i.source_layer = 'N4_trigger'
  AND EXISTS (
    SELECT 1 FROM common_event_outbox o
    WHERE o.event_id = i.event_id
      AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
      AND o.source_layer = 'N4_trigger'
  );

DELETE FROM common_event_consumer_checkpoint
WHERE source_layer = 'N4_trigger'
  AND last_event_time::date = to_date(current_setting('ashare_v3.archive_cleanup_trade_date', true), 'YYYYMMDD');

DELETE FROM common_event_ledger
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N4_trigger';

DELETE FROM common_event_outbox
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N4_trigger';

DELETE FROM common_trigger_match
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_trigger_state
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_trigger_context_snapshot
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_trigger_context_snapshot
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_trigger_context_snapshot
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_trigger_quality_item
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_trigger_run
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

-- N3 market-data layer.
DELETE FROM common_event_delivery_attempt d
WHERE EXISTS (
  SELECT 1 FROM common_event_outbox o
  WHERE o.event_id = d.event_id
    AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
    AND o.source_layer = 'N3_market_data'
);

DELETE FROM common_event_inbox i
WHERE i.source_layer = 'N3_market_data'
  AND EXISTS (
    SELECT 1 FROM common_event_outbox o
    WHERE o.event_id = i.event_id
      AND o.trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
      AND o.source_layer = 'N3_market_data'
  );

DELETE FROM common_event_consumer_checkpoint
WHERE source_layer = 'N3_market_data'
  AND last_event_time::date = to_date(current_setting('ashare_v3.archive_cleanup_trade_date', true), 'YYYYMMDD');

DELETE FROM common_event_ledger
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N3_market_data';

DELETE FROM common_event_outbox
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true)
  AND source_layer = 'N3_market_data';

DELETE FROM stock_action_confirmation_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_action_confirmation_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_action_confirmation_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_realtime_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_realtime_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_realtime_projection_metric
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_minute_bar_1m
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_minute_bar_1m
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_minute_bar_1m
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_previous_day_minute_preload_status
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_previous_day_minute_preload_status
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_previous_day_minute_preload_status
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM stock_realtime_daily_snapshot
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM index_realtime_daily_snapshot
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM board_realtime_daily_snapshot
WHERE trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

-- N3 lineage metadata retained.
-- common_market_data_subscription has high-fanout ON DELETE SET NULL references
-- from minute/snapshot tables. Deleting it in the first cleanup pass can trigger
-- multi-hour child-table updates. Keep run/subscription/pull_plan lineage in the
-- hot DB until a dedicated metadata-retention cleanup gate reviews FK impact.
DELETE FROM common_market_data_subscription_candidate
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

DELETE FROM common_market_data_quality_item
WHERE for_trade_date = current_setting('ashare_v3.archive_cleanup_trade_date', true);

COMMIT;
