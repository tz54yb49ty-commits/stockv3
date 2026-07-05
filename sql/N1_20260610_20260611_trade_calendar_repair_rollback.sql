-- N1 trade calendar 20260610/20260611 repair rollback draft.
-- Scope:
--   trade_calendar_20260610_repair_v1 / SSE:20260610
--   trade_calendar_20260611_repair_v1 / SSE:20260611
-- This rollback does not touch daily facts, condition source, N2/N3/N4/N5/N6 facts,
-- outbox/inbox/checkpoint, workers, old system, delivery, sim, positions, or trading state.

BEGIN;

DO $$
DECLARE
  v_batch_ids text[] := ARRAY[
    'trade_calendar_20260610_repair_v1',
    'trade_calendar_20260611_repair_v1'
  ];
  v_source_versions text[] := ARRAY[
    'trade_calendar_20260610_repair_v1',
    'trade_calendar_20260611_repair_v1'
  ];
  v_scope_keys text[] := ARRAY[
    'SSE:20260610',
    'SSE:20260611'
  ];
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
BEGIN
  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = ANY(v_batch_ids)
     OR payload_json::text LIKE ANY(ARRAY[
       '%trade_calendar_20260610_repair_v1%',
       '%trade_calendar_20260611_repair_v1%',
       '%SSE:20260610%',
       '%SSE:20260611%'
     ]);

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = ANY(v_batch_ids)
     OR payload_json::text LIKE ANY(ARRAY[
       '%trade_calendar_20260610_repair_v1%',
       '%trade_calendar_20260611_repair_v1%',
       '%SSE:20260610%',
       '%SSE:20260611%'
     ])
     OR raw_json::text LIKE ANY(ARRAY[
       '%trade_calendar_20260610_repair_v1%',
       '%trade_calendar_20260611_repair_v1%',
       '%SSE:20260610%',
       '%SSE:20260611%'
     ]);

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ]);

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE source_versions::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ])
     OR raw_json::text LIKE ANY(ARRAY[
       '%trade_calendar_20260610_repair_v1%',
       '%trade_calendar_20260611_repair_v1%',
       '%SSE:20260610%',
       '%SSE:20260611%'
     ]);

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE raw_json::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ]);

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE raw_json::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ]);

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE raw_json::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ]);

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text LIKE ANY(ARRAY[
    '%trade_calendar_20260610_repair_v1%',
    '%trade_calendar_20260611_repair_v1%',
    '%SSE:20260610%',
    '%SSE:20260611%'
  ]);

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing 20260610/20260611 calendar repair rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND (
    (scope_key = 'SSE:20260610'
      AND source_batch_id = 'trade_calendar_20260610_repair_v1'
      AND source_version = 'trade_calendar_20260610_repair_v1')
    OR
    (scope_key = 'SSE:20260611'
      AND source_batch_id = 'trade_calendar_20260611_repair_v1'
      AND source_version = 'trade_calendar_20260611_repair_v1')
  );

DELETE FROM common_trade_calendar
WHERE (
    trade_date = '20260610'
    AND source_batch_id = 'trade_calendar_20260610_repair_v1'
    AND source_version = 'trade_calendar_20260610_repair_v1'
  )
  OR (
    trade_date = '20260611'
    AND source_batch_id = 'trade_calendar_20260611_repair_v1'
    AND source_version = 'trade_calendar_20260611_repair_v1'
  );

DELETE FROM common_quality_gate_result
WHERE (source_batch_id = 'trade_calendar_20260610_repair_v1'
       AND source_version = 'trade_calendar_20260610_repair_v1')
   OR (source_batch_id = 'trade_calendar_20260611_repair_v1'
       AND source_version = 'trade_calendar_20260611_repair_v1');

DELETE FROM common_ingest_batch
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND (
    (batch_id = 'trade_calendar_20260610_repair_v1'
      AND source_version = 'trade_calendar_20260610_repair_v1')
    OR
    (batch_id = 'trade_calendar_20260611_repair_v1'
      AND source_version = 'trade_calendar_20260611_repair_v1')
  );

COMMIT;
