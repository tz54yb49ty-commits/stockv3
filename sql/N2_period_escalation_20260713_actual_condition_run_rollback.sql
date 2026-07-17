-- N2 period-escalation rollback artifact for the actual 20260713 condition run.
-- Target N2 run: condition_layer_20260710_source_20260710_for_20260713_v1
-- Upstream period bundle HEAD: a998a127
--
-- Historical evidence only (DO NOT MODIFY OR EXECUTE AS THIS ROLLBACK):
--   sql/N2_period_escalation_20260713_condition_run_rollback.sql
-- targets planned run condition_layer_20260710_to_20260713_20260713090000_execute,
-- which is not the actual target of this artifact.
--
-- Execute only after a dedicated rollback execute gate and exact authorization:
--   SET ashare_v3.allow_n2_condition_rollback_run_id =
--     'condition_layer_20260710_source_20260710_for_20260713_v1';
--
-- Scope and hard boundaries:
-- - Deletes only N2 rows owned by the exact target run.
-- - Preserves every other condition run and never changes active lineage.
-- - Never deletes N3/N4/N5/N6 facts, event infrastructure, or consumer state.
-- - Fails before N2 business-row mutation for any outbox/inbox/checkpoint or
--   downstream reference, including the known actual N4 context run.

BEGIN;

DO $authorization_guard$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260710_source_20260710_for_20260713_v1';
  v_allowed text :=
    current_setting('ashare_v3.allow_n2_condition_rollback_run_id', true);
BEGIN
  IF v_allowed IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback blocked: set ashare_v3.allow_n2_condition_rollback_run_id=% before mutation',
      v_run_id;
  END IF;
END
$authorization_guard$;

-- Transaction-local proof that rows of other condition runs remain unchanged.
CREATE TEMP TABLE _n2_period_escalation_20260713_actual_rollback_guard
ON COMMIT DROP AS
SELECT
  'condition_layer_20260710_source_20260710_for_20260713_v1'::text AS run_id,
  count(*)::bigint AS other_condition_run_count,
  md5(
    COALESCE(
      string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id),
      ''
    )
  ) AS other_condition_run_hash
FROM public.common_condition_run AS r
WHERE r.run_id <> 'condition_layer_20260710_source_20260710_for_20260713_v1';

DO $pre_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260710_source_20260710_for_20260713_v1';
  v_actual_n4_context_run_id CONSTANT text :=
    'trigger_context_snapshot_20260713_condition_layer_20260710_source_20260710_for_20260713_v1__atomic_rule_v1';
  v_count bigint;
  v_table text;
BEGIN
  IF (SELECT run_id
      FROM _n2_period_escalation_20260713_actual_rollback_guard)
     IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback blocked: transaction target guard mismatch';
  END IF;

  SELECT count(*)
  INTO v_count
  FROM public.common_condition_run
  WHERE run_id = v_run_id;

  IF v_count <> 1 THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback blocked: expected exactly one common_condition_run row for %, found %',
      v_run_id,
      v_count;
  END IF;

  -- Lock only the exact target while all no-downstream-reference guards run.
  PERFORM 1
  FROM public.common_condition_run
  WHERE run_id = v_run_id
  FOR UPDATE;

  -- Any target outbox reference blocks. Delivered/delivering rows have a
  -- dedicated failure message because they are externally observable.
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_outbox AS t
      WHERE (t.source_run_id = $1 OR to_jsonb(t)::text LIKE $2)
        AND t.status IN ('delivering', 'delivered')
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: delivered/delivering outbox refs for % = %',
        v_run_id,
        v_count;
    END IF;

    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_outbox AS t
      WHERE t.source_run_id = $1 OR to_jsonb(t)::text LIKE $2
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: outbox refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  -- Inbox and checkpoint guards also follow event-id/outbox-id links, so a
  -- derived consumer reference cannot evade a payload-only run-id search.
  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_inbox AS i
        WHERE i.source_run_id = $1
           OR to_jsonb(i)::text LIKE $2
           OR i.event_id IN (
             SELECT o.event_id
             FROM public.common_event_outbox AS o
             WHERE o.source_run_id = $1 OR to_jsonb(o)::text LIKE $2
           )
      $sql$
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    ELSE
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_inbox AS i
        WHERE i.source_run_id = $1 OR to_jsonb(i)::text LIKE $2
      $sql$
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    END IF;

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: inbox refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_consumer_checkpoint AS c
        WHERE to_jsonb(c)::text LIKE $1
           OR c.last_event_id IN (
             SELECT o.event_id
             FROM public.common_event_outbox AS o
             WHERE o.source_run_id = $2 OR to_jsonb(o)::text LIKE $1
           )
           OR c.last_outbox_id IN (
             SELECT o.outbox_id
             FROM public.common_event_outbox AS o
             WHERE o.source_run_id = $2 OR to_jsonb(o)::text LIKE $1
           )
      $sql$
      INTO v_count
      USING '%' || v_run_id || '%', v_run_id;
    ELSE
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_consumer_checkpoint AS c
        WHERE to_jsonb(c)::text LIKE $1
      $sql$
      INTO v_count
      USING '%' || v_run_id || '%';
    END IF;

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: checkpoint refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_delivery_attempt') IS NOT NULL
     AND to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_delivery_attempt AS a
      WHERE a.event_id IN (
              SELECT o.event_id
              FROM public.common_event_outbox AS o
              WHERE o.source_run_id = $1 OR to_jsonb(o)::text LIKE $2
            )
         OR a.outbox_id IN (
              SELECT o.outbox_id
              FROM public.common_event_outbox AS o
              WHERE o.source_run_id = $1 OR to_jsonb(o)::text LIKE $2
            )
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: outbox delivery-attempt refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  -- Every known N3 lineage/fact table is a downstream hard-fail boundary.
  FOREACH v_table IN ARRAY ARRAY[
    'common_market_data_run',
    'common_market_data_quality_item',
    'common_market_data_subscription_candidate',
    'common_market_data_subscription',
    'common_market_data_pull_plan',
    'stock_realtime_daily_snapshot',
    'index_realtime_daily_snapshot',
    'board_realtime_daily_snapshot',
    'stock_minute_bar_1m',
    'index_minute_bar_1m',
    'board_minute_bar_1m',
    'stock_previous_day_minute_bar_1m',
    'index_previous_day_minute_bar_1m',
    'board_previous_day_minute_bar_1m',
    'stock_realtime_projection_metric',
    'index_realtime_projection_metric',
    'board_realtime_projection_metric',
    'stock_closed_30m_summary',
    'index_closed_30m_summary',
    'board_closed_30m_summary'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_table
      )
      INTO v_count
      USING '%' || v_run_id || '%';

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 actual-condition-run rollback blocked: N3 refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- The actual N4 context run is known to exist. Its presence, any N4 state,
  -- or any N4 match linked to this N2 run must fail before an N2 delete.
  FOREACH v_table IN ARRAY ARRAY[
    'common_trigger_run',
    'common_trigger_quality_item',
    'stock_trigger_context_snapshot',
    'index_trigger_context_snapshot',
    'board_trigger_context_snapshot',
    'common_trigger_state',
    'common_trigger_match'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table
      )
      INTO v_count
      USING '%' || v_run_id || '%', '%' || v_actual_n4_context_run_id || '%';

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 actual-condition-run rollback blocked: N4 context/state/match refs in % for N2 %, actual N4 context % = %',
          v_table,
          v_run_id,
          v_actual_n4_context_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- N5 action facts and tracking state may be linked by either the N2 run or
  -- the actual N4 context run; both links are rollback blockers.
  FOREACH v_table IN ARRAY ARRAY[
    'common_action_run',
    'common_action_quality_item',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'common_action_event',
    'common_action_tracking_state',
    'common_action_confirmation',
    'stock_action_confirmation_projection_metric',
    'index_action_confirmation_projection_metric',
    'board_action_confirmation_projection_metric',
    'common_position_state',
    'common_position_event',
    'common_risk_event'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table
      )
      INTO v_count
      USING '%' || v_run_id || '%', '%' || v_actual_n4_context_run_id || '%';

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 actual-condition-run rollback blocked: N5 action/tracking refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- N6 projections and compatibility projections are immutable downstream
  -- consumers for this rollback; any reference hard-fails.
  FOREACH v_table IN ARRAY ARRAY[
    'user_projection_run',
    'user_market_projection',
    'user_signal_projection',
    'user_signal_card',
    'user_signal_decision',
    'user_notification_queue',
    'user_card_projection',
    'user_voice_delivery',
    'user_voice_delivery_log',
    'user_device_ack',
    'sim_projection',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table
      )
      INTO v_count
      USING '%' || v_run_id || '%', '%' || v_actual_n4_context_run_id || '%';

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 actual-condition-run rollback blocked: N6 projection refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- Guard direct N6 display-basis foreign-key references even if a projection
  -- does not retain a textual source run-id.
  IF to_regclass('public.user_signal_projection') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_signal_projection'
         AND column_name = 'source_condition_display_basis_id'
     ) THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.user_signal_projection AS p
      WHERE p.source_condition_display_basis_id IN (
        SELECT stock_condition_display_basis_id
        FROM public.stock_condition_display_basis
        WHERE run_id = $1
        UNION ALL
        SELECT index_condition_display_basis_id
        FROM public.index_condition_display_basis
        WHERE run_id = $1
        UNION ALL
        SELECT board_condition_display_basis_id
        FROM public.board_condition_display_basis
        WHERE run_id = $1
      )
    $sql$
    INTO v_count
    USING v_run_id;

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 actual-condition-run rollback blocked: N6 display-basis refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;
END
$pre_mutation_guards$;

-- Canonical N2 FULL_ROLLBACK_ORDER. Every mutation predicates on the exact
-- transaction-local target run; no active-lineage status is updated.
DELETE FROM public.stock_condition_display_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.index_condition_display_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.board_condition_display_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DELETE FROM public.stock_minute_target_scope
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.board_minute_target_scope
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.index_minute_target_scope
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DELETE FROM public.board_condition_pool
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.index_condition_pool
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.stock_condition_pool
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DELETE FROM public.board_condition_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.index_condition_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.stock_condition_basis
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DELETE FROM public.board_monitor_target
WHERE source_version = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.index_monitor_target
WHERE source_version = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.stock_monitor_target
WHERE source_version = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DELETE FROM public.common_condition_quality_item
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);
DELETE FROM public.common_condition_run
WHERE run_id = (
  SELECT run_id FROM _n2_period_escalation_20260713_actual_rollback_guard
);

DO $post_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260710_source_20260710_for_20260713_v1';
  v_count bigint;
  v_other_count_before bigint;
  v_other_count_after bigint;
  v_other_hash_before text;
  v_other_hash_after text;
  v_residual_count bigint;
BEGIN
  SELECT
    other_condition_run_count,
    other_condition_run_hash
  INTO STRICT
    v_other_count_before,
    v_other_hash_before
  FROM _n2_period_escalation_20260713_actual_rollback_guard;

  SELECT count(*)
  INTO v_count
  FROM public.common_condition_run
  WHERE run_id = v_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback failed: target common_condition_run remains for %, count=%',
      v_run_id,
      v_count;
  END IF;

  SELECT
    count(*)::bigint,
    md5(
      COALESCE(
        string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id),
        ''
      )
    )
  INTO v_other_count_after, v_other_hash_after
  FROM public.common_condition_run AS r
  WHERE r.run_id <> v_run_id;

  IF v_other_count_after IS DISTINCT FROM v_other_count_before
     OR v_other_hash_after IS DISTINCT FROM v_other_hash_before THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback failed: another common_condition_run changed (count %->%, hash %->%)',
      v_other_count_before,
      v_other_count_after,
      v_other_hash_before,
      v_other_hash_after;
  END IF;

  SELECT
      (SELECT count(*) FROM public.stock_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.index_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.stock_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.index_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.index_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.stock_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.index_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.stock_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM public.index_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM public.stock_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM public.common_condition_quality_item WHERE run_id = v_run_id)
  INTO v_residual_count;

  IF v_residual_count <> 0 THEN
    RAISE EXCEPTION
      'N2 actual-condition-run rollback failed: target N2 child rows remain for %, count=%',
      v_run_id,
      v_residual_count;
  END IF;
END
$post_mutation_guards$;

COMMIT;
