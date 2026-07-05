-- V3 20260612 realtime virtual metric previous_day_same_window_amount repair.
-- Scope: additive schema column plus scoped backfill for one N3 metric projection_run_id.
-- Do not execute without runtime_control final gate approval.
\set target_run_id 'action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1'

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair', true) <> 'true' THEN
    RAISE EXCEPTION 'previous_day_same_window_amount repair blocked by default; set reviewed session flag after runtime_control final gate approval';
  END IF;
END $$;

BEGIN;

SET LOCAL ashare_v3.repair_target_run_id = :'target_run_id';

-- expected total rows 100; stock/index/board=62/0/38
-- allow_reviewed_n4_refs:
--   This repair is a scoped N3 metric evidence backfill after stale N5 action_mark
--   rollback. Reviewed N4 trigger facts/outbox may already reference the target
--   metric run and must be preserved. N5/N6/user/sim/virtual refs remain
--   hard-fail blockers.
DO $$
DECLARE
  target_run_id text := current_setting('ashare_v3.repair_target_run_id');
  refs bigint := 0;
BEGIN
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_event_outbox
    WHERE (source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%')
      AND NOT (
        source_layer = 'N4_trigger'
        AND event_type IN ('TriggerMatched', 'TriggerStateChanged', 'TriggerPendingMarketData')
      );
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: non-reviewed common_event_outbox refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM common_event_inbox WHERE payload_json::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: common_event_inbox refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM common_event_consumer_checkpoint WHERE consumer_name::text LIKE '%' || target_run_id || '%' OR last_event_id::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: common_event_consumer_checkpoint refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_trigger_match
    WHERE row_to_json(common_trigger_match)::text LIKE '%' || target_run_id || '%';
    RAISE NOTICE 'reviewed_n4_trigger_refs common_trigger_match refs=% are preserved', refs;
  END IF;
  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM common_action_event WHERE row_to_json(common_action_event)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: common_action_event refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_signal_card WHERE row_to_json(user_signal_card)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_signal_card refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_notification_queue WHERE row_to_json(user_notification_queue)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_notification_queue refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_sim_order WHERE row_to_json(user_sim_order)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_sim_order refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_sim_trade WHERE row_to_json(user_sim_trade)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_sim_trade refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_sim_position WHERE row_to_json(user_sim_position)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_sim_position refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_account') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_account WHERE row_to_json(n6_virtual_account)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_account refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_order WHERE row_to_json(n6_virtual_order)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_order refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_trade WHERE row_to_json(n6_virtual_trade)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_trade refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_position WHERE row_to_json(n6_virtual_position)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_position refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_position_event WHERE row_to_json(n6_virtual_position_event)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_position_event refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM n6_virtual_pnl_snapshot WHERE row_to_json(n6_virtual_pnl_snapshot)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: n6_virtual_pnl_snapshot refs=%', refs; END IF;
  END IF;
  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    SELECT count(*) INTO refs FROM user_signal_projection WHERE row_to_json(user_signal_projection)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN RAISE EXCEPTION 'repair blocked: user_signal_projection refs=%', refs; END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM common_market_data_run WHERE run_id = target_run_id AND (downstream_layers_touched IS TRUE OR worker_started IS TRUE)) THEN
    RAISE EXCEPTION 'repair blocked: downstream_layers_touched or worker_started is true';
  END IF;
END $$;

ALTER TABLE stock_action_confirmation_projection_metric
  ADD COLUMN IF NOT EXISTS previous_day_same_window_amount NUMERIC;

WITH repair_values(identity_key, metric_minute_label, previous_day_same_window_amount) AS (
VALUES
    ('stock:SH:600162', '13:34', 231002047.0),
    ('stock:SH:600162', '13:41', 231002047.0),
    ('stock:SH:600498', '13:32', 1115525731.0),
    ('stock:SH:600596', '10:37', 120278867.0),
    ('stock:SH:601339', '10:16', 9649081.0),
    ('stock:SH:603039', '14:49', 135728210.0),
    ('stock:SH:603125', '10:41', 13300430.0),
    ('stock:SH:603125', '10:45', 13300430.0),
    ('stock:SH:603186', '10:48', 378806352.0),
    ('stock:SH:603268', '09:57', 296941531.0),
    ('stock:SH:603268', '10:41', 139368669.0),
    ('stock:SH:603268', '10:43', 139368669.0),
    ('stock:SH:603296', '10:21', 371700160.0),
    ('stock:SH:603379', '13:46', 97739616.0),
    ('stock:SH:603608', '13:11', 121896135.0),
    ('stock:SH:603608', '14:30', 51688188.0),
    ('stock:SH:603608', '14:52', 112025000.0),
    ('stock:SH:603733', '10:28', 54262382.0),
    ('stock:SH:603906', '13:26', 287640892.0),
    ('stock:SH:688147', '14:02', 146458219.0),
    ('stock:SH:688502', '13:39', 93076705.0),
    ('stock:SH:688507', '14:06', 186855881.0),
    ('stock:SH:688507', '14:19', 186855881.0),
    ('stock:SH:688507', '14:21', 186855881.0),
    ('stock:SH:688507', '14:25', 186855881.0),
    ('stock:SH:688507', '14:53', 327071987.0),
    ('stock:SH:688519', '10:27', 676028923.0),
    ('stock:SH:688559', '09:31', 260105848.0),
    ('stock:SH:688700', '10:17', 198808445.0),
    ('stock:SZ:000823', '10:41', 224958760.25),
    ('stock:SZ:000823', '10:45', 224958760.25),
    ('stock:SZ:000823', '10:48', 224958760.25),
    ('stock:SZ:002272', '11:16', 164301429.75),
    ('stock:SZ:002272', '11:21', 164301429.75),
    ('stock:SZ:002552', '10:12', 184698557.5),
    ('stock:SZ:002552', '10:20', 184698557.5),
    ('stock:SZ:002552', '10:28', 184698557.5),
    ('stock:SZ:002645', '10:48', 315471415.5),
    ('stock:SZ:002645', '10:57', 315471415.5),
    ('stock:SZ:002993', '09:52', 207325410.0),
    ('stock:SZ:002993', '09:55', 207325410.0),
    ('stock:SZ:002993', '10:56', 57669979.0),
    ('stock:SZ:002993', '10:59', 57669979.0),
    ('stock:SZ:300223', '11:02', 527463560.0),
    ('stock:SZ:300568', '14:02', 639145222.0),
    ('stock:SZ:300568', '14:06', 639145222.0),
    ('stock:SZ:300570', '10:20', 1290918018.0),
    ('stock:SZ:300570', '10:33', 881005116.0),
    ('stock:SZ:300706', '13:16', 328158112.375),
    ('stock:SZ:300706', '13:19', 328158112.375),
    ('stock:SZ:300706', '13:30', 328158112.375),
    ('stock:SZ:300776', '09:31', 755178309.0),
    ('stock:SZ:300811', '09:31', 559696676.0),
    ('stock:SZ:300811', '10:33', 216755083.0),
    ('stock:SZ:300811', '10:35', 216755083.0),
    ('stock:SZ:300811', '10:44', 216755083.0),
    ('stock:SZ:300814', '14:52', 258582128.0),
    ('stock:SZ:300814', '15:00', 258582128.0),
    ('stock:SZ:301086', '10:40', 107898518.75),
    ('stock:SZ:301297', '11:12', 56361800.0),
    ('stock:SZ:301526', '11:06', 389461627.5),
    ('stock:SZ:301526', '11:12', 389461627.5)
)
UPDATE stock_action_confirmation_projection_metric
SET previous_day_same_window_amount = repair_values.previous_day_same_window_amount,
    trace_json = COALESCE(trace_json, '{}'::jsonb) || jsonb_build_object(
      'previous_day_same_window_amount_repair', jsonb_build_object(
        'source', 'docs/V3_20260612_realtime_virtual_metric_writer_payload.json',
        'policy', 'n3_scoped_previous_day_same_window_amount_backfill',
        'review_required', 'runtime_control_final_gate'
      )
    )
FROM repair_values
WHERE projection_run_id = current_setting('ashare_v3.repair_target_run_id')
  AND stock_action_confirmation_projection_metric.identity_key = repair_values.identity_key
  AND stock_action_confirmation_projection_metric.metric_minute_label = repair_values.metric_minute_label;

DO $$
DECLARE
  target_run_id text := current_setting('ashare_v3.repair_target_run_id');
  repaired_count bigint := 0;
BEGIN
  SELECT count(*) INTO repaired_count FROM stock_action_confirmation_projection_metric WHERE projection_run_id = target_run_id AND previous_day_same_window_amount IS NOT NULL;
  IF repaired_count <> 62 THEN
    RAISE EXCEPTION 'repair blocked: stock_action_confirmation_projection_metric previous_day_same_window_amount rows expected 62, actual %', repaired_count;
  END IF;
END $$;

ALTER TABLE index_action_confirmation_projection_metric
  ADD COLUMN IF NOT EXISTS previous_day_same_window_amount NUMERIC;

WITH repair_values(identity_key, metric_minute_label, previous_day_same_window_amount) AS (
SELECT NULL::text AS identity_key, NULL::text AS metric_minute_label, NULL::numeric AS previous_day_same_window_amount WHERE false
)
UPDATE index_action_confirmation_projection_metric
SET previous_day_same_window_amount = repair_values.previous_day_same_window_amount,
    trace_json = COALESCE(trace_json, '{}'::jsonb) || jsonb_build_object(
      'previous_day_same_window_amount_repair', jsonb_build_object(
        'source', 'docs/V3_20260612_realtime_virtual_metric_writer_payload.json',
        'policy', 'n3_scoped_previous_day_same_window_amount_backfill',
        'review_required', 'runtime_control_final_gate'
      )
    )
FROM repair_values
WHERE projection_run_id = current_setting('ashare_v3.repair_target_run_id')
  AND index_action_confirmation_projection_metric.identity_key = repair_values.identity_key
  AND index_action_confirmation_projection_metric.metric_minute_label = repair_values.metric_minute_label;

DO $$
DECLARE
  target_run_id text := current_setting('ashare_v3.repair_target_run_id');
  repaired_count bigint := 0;
BEGIN
  SELECT count(*) INTO repaired_count FROM index_action_confirmation_projection_metric WHERE projection_run_id = target_run_id AND previous_day_same_window_amount IS NOT NULL;
  IF repaired_count <> 0 THEN
    RAISE EXCEPTION 'repair blocked: index_action_confirmation_projection_metric previous_day_same_window_amount rows expected 0, actual %', repaired_count;
  END IF;
END $$;

ALTER TABLE board_action_confirmation_projection_metric
  ADD COLUMN IF NOT EXISTS previous_day_same_window_amount NUMERIC;

WITH repair_values(identity_key, metric_minute_label, previous_day_same_window_amount) AS (
VALUES
    ('board:TDX:881002', '09:31', 4711877524.0),
    ('board:TDX:881002', '09:33', 4711877524.0),
    ('board:TDX:881002', '09:37', 4711877524.0),
    ('board:TDX:881002', '09:42', 4711877524.0),
    ('board:TDX:881002', '10:06', 1571158744.0),
    ('board:TDX:881002', '10:10', 1571158744.0),
    ('board:TDX:881002', '10:15', 1571158744.0),
    ('board:TDX:881002', '10:36', 1464618130.0),
    ('board:TDX:881002', '10:45', 1464618130.0),
    ('board:TDX:881087', '10:44', 2567073184.0),
    ('board:TDX:881087', '10:46', 2567073184.0),
    ('board:TDX:881087', '10:56', 2567073184.0),
    ('board:TDX:881087', '11:00', 2567073184.0),
    ('board:TDX:881111', '09:31', 1798749118.0),
    ('board:TDX:881111', '09:35', 1798749118.0),
    ('board:TDX:881111', '09:40', 1798749118.0),
    ('board:TDX:881136', '09:32', 1163051694.0),
    ('board:TDX:881215', '09:31', 805316982.0),
    ('board:TDX:881215', '10:50', 543335903.0),
    ('board:TDX:881215', '10:53', 543335903.0),
    ('board:TDX:881215', '10:55', 543335903.0),
    ('board:TDX:881215', '10:59', 543335903.0),
    ('board:TDX:881275', '09:31', 17532576976.0),
    ('board:TDX:881344', '14:47', 663005079.0),
    ('board:TDX:881389', '09:31', 2583306188.0),
    ('board:TDX:881389', '14:34', 1197064120.0),
    ('board:TDX:881389', '14:39', 1197064120.0),
    ('board:TDX:881416', '13:09', 231049869.0),
    ('board:TDX:881416', '13:27', 231049869.0),
    ('board:TDX:881416', '13:30', 231049869.0),
    ('board:TDX:881416', '13:36', 220035528.0),
    ('board:TDX:881416', '13:49', 220035528.0),
    ('board:TDX:881416', '13:52', 220035528.0),
    ('board:TDX:881416', '13:53', 220035528.0),
    ('board:TDX:881416', '14:11', 221359072.0),
    ('board:TDX:881470', '10:49', 778949294.0),
    ('board:TDX:881470', '10:57', 778949294.0),
    ('board:TDX:881471', '09:31', 4326673236.0)
)
UPDATE board_action_confirmation_projection_metric
SET previous_day_same_window_amount = repair_values.previous_day_same_window_amount,
    trace_json = COALESCE(trace_json, '{}'::jsonb) || jsonb_build_object(
      'previous_day_same_window_amount_repair', jsonb_build_object(
        'source', 'docs/V3_20260612_realtime_virtual_metric_writer_payload.json',
        'policy', 'n3_scoped_previous_day_same_window_amount_backfill',
        'review_required', 'runtime_control_final_gate'
      )
    )
FROM repair_values
WHERE projection_run_id = current_setting('ashare_v3.repair_target_run_id')
  AND board_action_confirmation_projection_metric.identity_key = repair_values.identity_key
  AND board_action_confirmation_projection_metric.metric_minute_label = repair_values.metric_minute_label;

DO $$
DECLARE
  target_run_id text := current_setting('ashare_v3.repair_target_run_id');
  repaired_count bigint := 0;
BEGIN
  SELECT count(*) INTO repaired_count FROM board_action_confirmation_projection_metric WHERE projection_run_id = target_run_id AND previous_day_same_window_amount IS NOT NULL;
  IF repaired_count <> 38 THEN
    RAISE EXCEPTION 'repair blocked: board_action_confirmation_projection_metric previous_day_same_window_amount rows expected 38, actual %', repaired_count;
  END IF;
END $$;

COMMIT;
