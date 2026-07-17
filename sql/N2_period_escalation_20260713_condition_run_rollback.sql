-- N2 period-escalation condition-run rollback artifact.
-- Target run: condition_layer_20260710_to_20260713_20260713090000_execute
--
-- DO NOT EXECUTE without a dedicated rollback execute gate and explicit authorization:
--   SET ashare_v3.allow_n2_condition_rollback_run_id =
--     'condition_layer_20260710_to_20260713_20260713090000_execute';
--
-- Scope:
-- - Deletes only rows owned by the exact target N2 run.
-- - Uses the canonical N2 FULL_ROLLBACK_ORDER.
-- - Does not restore, supersede, or otherwise update any other condition run.
-- - Does not delete or update event infrastructure or N3/N4/N5/N6 rows.
-- - Fails before business-row mutation if event or downstream references exist.

BEGIN;

DO $authorization_guard$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260710_to_20260713_20260713090000_execute';
  v_allowed text :=
    current_setting('ashare_v3.allow_n2_condition_rollback_run_id', true);
BEGIN
  IF v_allowed IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback blocked: set ashare_v3.allow_n2_condition_rollback_run_id=% before mutation',
      v_run_id;
  END IF;
END
$authorization_guard$;

-- The snapshot is transaction-local and proves that no non-target
-- common_condition_run row changed during this rollback.
CREATE TEMP TABLE _n2_period_escalation_20260713_rollback_guard
ON COMMIT DROP AS
SELECT
  'condition_layer_20260710_to_20260713_20260713090000_execute'::text AS run_id,
  count(*)::bigint AS other_condition_run_count,
  md5(
    COALESCE(
      string_agg(
        md5(to_jsonb(r)::text),
        '' ORDER BY r.run_id
      ),
      ''
    )
  ) AS other_condition_run_hash
FROM common_condition_run AS r
WHERE r.run_id <>
  'condition_layer_20260710_to_20260713_20260713090000_execute';

DO $pre_mutation_guards$
DECLARE
  v_run_id text;
  v_count bigint;
  v_table text;
BEGIN
  SELECT run_id INTO STRICT v_run_id
  FROM _n2_period_escalation_20260713_rollback_guard;

  IF v_run_id IS DISTINCT FROM
     'condition_layer_20260710_to_20260713_20260713090000_execute' THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback blocked: target run guard mismatch: %',
      v_run_id;
  END IF;

  -- Lock only the target run. This also prevents new FK-backed downstream
  -- references from racing the remaining guards and deletes.
  PERFORM 1
  FROM common_condition_run
  WHERE run_id = v_run_id
  FOR UPDATE;

  GET DIAGNOSTICS v_count = ROW_COUNT;
  IF v_count <> 1 THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback blocked: expected exactly one target common_condition_run row for %, found %',
      v_run_id,
      v_count;
  END IF;

  -- Event infrastructure is never modified by this artifact. Any reference,
  -- including delivered/delivering outbox state, blocks the rollback.
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_outbox AS t
      WHERE (t.source_run_id = $1 OR to_jsonb(t)::text LIKE $2)
        AND t.status IN ('delivered', 'delivering')
    $sql$
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 period-escalation rollback blocked: delivered/delivering outbox refs for % = %',
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
        'N2 period-escalation rollback blocked: outbox refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_inbox AS t
      WHERE t.source_run_id = $1 OR to_jsonb(t)::text LIKE $2
    $sql$
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 period-escalation rollback blocked: inbox refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_consumer_checkpoint AS t
      WHERE to_jsonb(t)::text LIKE $1
    $sql$
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 period-escalation rollback blocked: checkpoint refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;

  -- N3 lineage: subscription grain, pull plan, and market-data run are
  -- checked explicitly; candidate and quality rows are included as well.
  FOREACH v_table IN ARRAY ARRAY[
    'common_market_data_run',
    'common_market_data_quality_item',
    'common_market_data_subscription_candidate',
    'common_market_data_subscription',
    'common_market_data_pull_plan'
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
          'N2 period-escalation rollback blocked: N3 refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- N4 lineage: context localization, lifecycle state, and match facts.
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
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_table
      )
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 period-escalation rollback blocked: N4 refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- N5 lineage: canonical and compatibility action facts plus live tracking.
  FOREACH v_table IN ARRAY ARRAY[
    'common_action_run',
    'common_action_quality_item',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'common_action_event',
    'common_action_tracking_state',
    'common_action_confirmation',
    'common_position_state',
    'common_position_event',
    'common_risk_event'
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
          'N2 period-escalation rollback blocked: N5 refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- N6 lineage: both current projection/delivery names and MVP compatibility
  -- names are guarded. These rows are never removed by an N2 rollback.
  FOREACH v_table IN ARRAY ARRAY[
    'user_projection_run',
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
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_table
      )
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 period-escalation rollback blocked: N6 refs in % for % = %',
          v_table,
          v_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;

  -- A display-basis FK can preserve N2 lineage without embedding the run-id
  -- text in the N6 row, so guard it separately.
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
      FROM public.user_signal_projection
      WHERE source_condition_display_basis_id IN (
        SELECT stock_condition_display_basis_id
        FROM stock_condition_display_basis
        WHERE run_id = $1
        UNION ALL
        SELECT index_condition_display_basis_id
        FROM index_condition_display_basis
        WHERE run_id = $1
        UNION ALL
        SELECT board_condition_display_basis_id
        FROM board_condition_display_basis
        WHERE run_id = $1
      )
    $sql$
      INTO v_count
      USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 period-escalation rollback blocked: N6 display-basis refs for % = %',
        v_run_id,
        v_count;
    END IF;
  END IF;
END
$pre_mutation_guards$;

-- Canonical N2 FULL_ROLLBACK_ORDER begins here. Every predicate is bound to
-- the transaction-local exact run-id guard.
DELETE FROM stock_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM index_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM board_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DELETE FROM stock_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM board_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM index_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DELETE FROM board_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM index_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM stock_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DELETE FROM board_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM index_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM stock_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DELETE FROM board_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM index_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM stock_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DELETE FROM common_condition_quality_item
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);
DELETE FROM common_condition_run
WHERE run_id = (SELECT run_id FROM _n2_period_escalation_20260713_rollback_guard);

DO $post_mutation_guards$
DECLARE
  v_run_id text;
  v_count bigint;
  v_other_count_before bigint;
  v_other_count_after bigint;
  v_other_hash_before text;
  v_other_hash_after text;
  v_residual_count bigint;
BEGIN
  SELECT
    run_id,
    other_condition_run_count,
    other_condition_run_hash
  INTO STRICT
    v_run_id,
    v_other_count_before,
    v_other_hash_before
  FROM _n2_period_escalation_20260713_rollback_guard;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback failed: target common_condition_run still exists for %, count=%',
      v_run_id,
      v_count;
  END IF;

  SELECT
    count(*)::bigint,
    md5(
      COALESCE(
        string_agg(
          md5(to_jsonb(r)::text),
          '' ORDER BY r.run_id
        ),
        ''
      )
    )
  INTO v_other_count_after, v_other_hash_after
  FROM common_condition_run AS r
  WHERE r.run_id <> v_run_id;

  IF v_other_count_after IS DISTINCT FROM v_other_count_before
     OR v_other_hash_after IS DISTINCT FROM v_other_hash_before THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback failed: non-target common_condition_run rows changed (count %->%, hash %->%)',
      v_other_count_before,
      v_other_count_after,
      v_other_hash_before,
      v_other_hash_after;
  END IF;

  SELECT
      (SELECT count(*) FROM stock_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM index_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_condition_display_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM stock_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM index_minute_target_scope WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM index_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM stock_condition_pool WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM index_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM stock_condition_basis WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM index_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM stock_monitor_target WHERE source_version = v_run_id)
    + (SELECT count(*) FROM common_condition_quality_item WHERE run_id = v_run_id)
  INTO v_residual_count;

  IF v_residual_count <> 0 THEN
    RAISE EXCEPTION
      'N2 period-escalation rollback failed: target N2 child rows remain for %, count=%',
      v_run_id,
      v_residual_count;
  END IF;
END
$post_mutation_guards$;

COMMIT;
