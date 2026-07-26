-- N2 directional-incremental context rollback artifact for one exact planned run.
-- Target N2 run: condition_layer_20260714_source_20260714_for_20260715_v1
-- Feature commit: 12c88a0be1f32f382f6c2c5d1af47b48297e482f
--
-- Historical N2 rollback artifacts for other date pairs are immutable evidence.
-- They do not authorize, constrain, or replace this artifact.
--
-- DO NOT EXECUTE without a dedicated rollback execute gate and both exact
-- transaction settings below:
--   SET ashare_v3.allow_n2_condition_rollback_run_id =
--     'condition_layer_20260714_source_20260714_for_20260715_v1';
--   SET ashare_v3.allow_n2_condition_rollback_artifact =
--     'N2_condition_layer_20260714_source_20260714_for_20260715_directional_incremental_v1_rollback.sql';
--
-- This artifact deletes only canonical N2 rows owned by the target run. It
-- never restores, updates, supersedes, or deletes another date pair's lineage.
-- Any event, downstream, or foreign-key reference blocks before an N2 business
-- row is deleted.

BEGIN;

DO $authorization_guard$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260714_source_20260714_for_20260715_v1';
  v_artifact_id CONSTANT text :=
    'N2_condition_layer_20260714_source_20260714_for_20260715_directional_incremental_v1_rollback.sql';
  v_allowed_run_id text :=
    current_setting('ashare_v3.allow_n2_condition_rollback_run_id', true);
  v_allowed_artifact text :=
    current_setting('ashare_v3.allow_n2_condition_rollback_artifact', true);
BEGIN
  IF v_allowed_run_id IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION
      'N2 directional-incremental rollback blocked: set ashare_v3.allow_n2_condition_rollback_run_id=% before mutation',
      v_run_id;
  END IF;

  IF v_allowed_artifact IS DISTINCT FROM v_artifact_id THEN
    RAISE EXCEPTION
      'N2 directional-incremental rollback blocked: set ashare_v3.allow_n2_condition_rollback_artifact=% before mutation',
      v_artifact_id;
  END IF;
END
$authorization_guard$;

DO $pre_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260714_source_20260714_for_20260715_v1';
  v_count bigint;
  v_table text;
  v_parent_table text;
  v_parent_filter_column text;
  v_fk_schema text;
  v_fk_table text;
  v_fk_column text;
  v_parent_column text;
  v_n2_owned_tables CONSTANT text[] := ARRAY[
    'common_condition_quality_item',
    'stock_monitor_target', 'index_monitor_target', 'board_monitor_target',
    'stock_condition_basis', 'index_condition_basis', 'board_condition_basis',
    'stock_condition_pool', 'index_condition_pool', 'board_condition_pool',
    'stock_minute_target_scope', 'index_minute_target_scope', 'board_minute_target_scope',
    'stock_condition_display_basis', 'index_condition_display_basis', 'board_condition_display_basis'
  ];
BEGIN
  SELECT count(*)
  INTO v_count
  FROM public.common_condition_run
  WHERE run_id = v_run_id;

  IF v_count <> 1 THEN
    RAISE EXCEPTION
      'N2 directional-incremental rollback blocked: expected exactly one target common_condition_run row for %, found %',
      v_run_id,
      v_count;
  END IF;

  -- Lock only the exact target while all no-reference guards run.
  PERFORM 1
  FROM public.common_condition_run
  WHERE run_id = v_run_id
  FOR UPDATE;

  -- Event infrastructure is immutable to N2 rollback. Delivered/delivering
  -- rows receive a dedicated blocker because they are externally observable.
  IF to_regclass('public.common_event_ledger') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_ledger AS e
      WHERE e.source_run_id = $1 OR to_jsonb(e)::text LIKE $2
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 directional-incremental rollback blocked: event-ledger refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_outbox AS o
      WHERE (o.source_run_id = $1 OR to_jsonb(o)::text LIKE $2)
        AND o.status IN ('delivering', 'delivered')
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 directional-incremental rollback blocked: delivered/delivering outbox refs for % = %',
        v_run_id, v_count;
    END IF;

    EXECUTE $sql$
      SELECT count(*)
      FROM public.common_event_outbox AS o
      WHERE o.source_run_id = $1 OR to_jsonb(o)::text LIKE $2
    $sql$
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 directional-incremental rollback blocked: outbox refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

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
        'N2 directional-incremental rollback blocked: inbox refs for % = %',
        v_run_id, v_count;
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
        'N2 directional-incremental rollback blocked: checkpoint refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_delivery_attempt') IS NOT NULL THEN
    IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_delivery_attempt AS a
        WHERE to_jsonb(a)::text LIKE $2
           OR a.event_id IN (
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
    ELSE
      EXECUTE $sql$
        SELECT count(*)
        FROM public.common_event_delivery_attempt AS a
        WHERE to_jsonb(a)::text LIKE $1
      $sql$
      INTO v_count
      USING '%' || v_run_id || '%';
    END IF;

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 directional-incremental rollback blocked: delivery-attempt refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

  -- N3: every known subscription, fact, preload, projection, and summary
  -- table is an immutable downstream boundary.
  FOREACH v_table IN ARRAY ARRAY[
    'common_market_data_run',
    'common_market_data_quality_item',
    'common_market_data_subscription_candidate',
    'common_market_data_subscription',
    'common_market_data_pull_plan',
    'stock_previous_day_minute_preload_status',
    'index_previous_day_minute_preload_status',
    'board_previous_day_minute_preload_status',
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
    'board_closed_30m_summary',
    'stock_closed_30m_signal_enrichment',
    'index_closed_30m_signal_enrichment',
    'board_closed_30m_signal_enrichment',
    'stock_eod_snapshot',
    'index_eod_snapshot',
    'board_eod_snapshot'
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
          'N2 directional-incremental rollback blocked: N3 refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- N4 context localization, state, match, and replay artifacts must all be
  -- absent. N2 never deletes or changes these downstream rows.
  FOREACH v_table IN ARRAY ARRAY[
    'common_trigger_run',
    'common_trigger_quality_item',
    'stock_trigger_context_snapshot',
    'index_trigger_context_snapshot',
    'board_trigger_context_snapshot',
    'common_trigger_state',
    'common_trigger_match',
    'stock_trigger_replay_audit',
    'index_trigger_replay_audit',
    'board_trigger_replay_audit'
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
          'N2 directional-incremental rollback blocked: N4 context/state/match refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- N5 action, confirmation, tracking, position, and projection metrics are
  -- also permanent downstream consumers for an N2 rollback.
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
        'SELECT count(*) FROM public.%I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_table
      )
      INTO v_count
      USING '%' || v_run_id || '%';

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 directional-incremental rollback blocked: N5 action/tracking refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- N6 projection, delivery, simulation, and compatibility consumers are
  -- guarded independently of the event infrastructure.
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
    'n6_virtual_pnl_snapshot',
    'n6_stock_display_cache',
    'n6_index_display_cache',
    'n6_board_display_cache'
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
          'N2 directional-incremental rollback blocked: N6 projection refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- Direct display-basis ids can be FK-like even when a downstream row does
  -- not retain the target run id in JSON. Guard all known N6 consumers first.
  IF to_regclass('public.user_signal_projection') IS NOT NULL
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
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
        'N2 directional-incremental rollback blocked: N6 display-basis refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'n6_stock_display_cache',
    'n6_index_display_cache',
    'n6_board_display_cache'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL
       AND EXISTS (
         SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = v_table
           AND column_name = 'source_condition_display_basis_id'
       ) THEN
      IF v_table = 'n6_stock_display_cache' THEN
        EXECUTE $sql$
          SELECT count(*)
          FROM public.n6_stock_display_cache AS c
          WHERE c.source_condition_display_basis_id IN (
            SELECT stock_condition_display_basis_id
            FROM public.stock_condition_display_basis
            WHERE run_id = $1
          )
        $sql$ INTO v_count USING v_run_id;
      ELSIF v_table = 'n6_index_display_cache' THEN
        EXECUTE $sql$
          SELECT count(*)
          FROM public.n6_index_display_cache AS c
          WHERE c.source_condition_display_basis_id IN (
            SELECT index_condition_display_basis_id
            FROM public.index_condition_display_basis
            WHERE run_id = $1
          )
        $sql$ INTO v_count USING v_run_id;
      ELSE
        EXECUTE $sql$
          SELECT count(*)
          FROM public.n6_board_display_cache AS c
          WHERE c.source_condition_display_basis_id IN (
            SELECT board_condition_display_basis_id
            FROM public.board_condition_display_basis
            WHERE run_id = $1
          )
        $sql$ INTO v_count USING v_run_id;
      END IF;

      IF v_count <> 0 THEN
        RAISE EXCEPTION
          'N2 directional-incremental rollback blocked: N6 cache display-basis refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- Reject every direct FK from an unknown non-N2 table into any target-owned
  -- table. This covers future downstream additions without deleting them.
  FOREACH v_parent_table IN ARRAY ARRAY[
    'common_condition_run',
    'stock_monitor_target', 'index_monitor_target', 'board_monitor_target',
    'stock_condition_basis', 'index_condition_basis', 'board_condition_basis',
    'stock_condition_pool', 'index_condition_pool', 'board_condition_pool',
    'stock_minute_target_scope', 'index_minute_target_scope', 'board_minute_target_scope',
    'stock_condition_display_basis', 'index_condition_display_basis', 'board_condition_display_basis'
  ]
  LOOP
    SELECT count(*)
    INTO v_count
    FROM pg_constraint AS con
    WHERE con.contype = 'f'
      AND con.confrelid = to_regclass('public.' || v_parent_table)
      AND array_length(con.conkey, 1) <> 1;

    IF v_count <> 0 THEN
      RAISE EXCEPTION
        'N2 directional-incremental rollback blocked: unsupported composite FK shape references target-owned table %',
        v_parent_table;
    END IF;

    v_parent_filter_column := CASE
      WHEN v_parent_table IN ('stock_monitor_target', 'index_monitor_target', 'board_monitor_target')
        THEN 'source_version'
      ELSE 'run_id'
    END;

    FOR v_fk_schema, v_fk_table, v_fk_column, v_parent_column IN
      SELECT ns.nspname, rel.relname, child_att.attname, parent_att.attname
      FROM pg_constraint AS con
      JOIN pg_class AS rel ON rel.oid = con.conrelid
      JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace
      JOIN pg_attribute AS child_att
        ON child_att.attrelid = con.conrelid
       AND child_att.attnum = con.conkey[1]
      JOIN pg_attribute AS parent_att
        ON parent_att.attrelid = con.confrelid
       AND parent_att.attnum = con.confkey[1]
      WHERE con.contype = 'f'
        AND con.confrelid = to_regclass('public.' || v_parent_table)
        AND array_length(con.conkey, 1) = 1
    LOOP
      IF NOT (v_fk_schema = 'public' AND v_fk_table = ANY(v_n2_owned_tables)) THEN
        EXECUTE format(
          'SELECT count(*) FROM %I.%I AS child WHERE child.%I IN (SELECT parent.%I FROM public.%I AS parent WHERE parent.%I = $1)',
          v_fk_schema,
          v_fk_table,
          v_fk_column,
          v_parent_column,
          v_parent_table,
          v_parent_filter_column
        )
        INTO v_count
        USING v_run_id;

        IF v_count <> 0 THEN
          RAISE EXCEPTION
            'N2 directional-incremental rollback blocked: downstream/FK refs in %.% via target-owned table % = %',
            v_fk_schema, v_fk_table, v_parent_table, v_count;
        END IF;
      END IF;
    END LOOP;
  END LOOP;
END
$pre_mutation_guards$;

-- Transaction-local proof that no non-target common_condition_run changes
-- while the canonical target-only deletes execute.
CREATE TEMP TABLE _n2_directional_incremental_20260715_rollback_guard
ON COMMIT DROP AS
SELECT
  'condition_layer_20260714_source_20260714_for_20260715_v1'::text AS run_id,
  count(*)::bigint AS other_condition_run_count,
  md5(COALESCE(string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id), ''))
    AS other_condition_run_hash
FROM public.common_condition_run AS r
WHERE r.run_id <> 'condition_layer_20260714_source_20260714_for_20260715_v1';

-- Canonical N2 FULL_ROLLBACK_ORDER. Every mutation is constrained to the
-- transaction-local exact target and does not alter active-lineage statuses.
DELETE FROM public.stock_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.index_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.board_condition_display_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DELETE FROM public.stock_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.board_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.index_minute_target_scope
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DELETE FROM public.board_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.index_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.stock_condition_pool
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DELETE FROM public.board_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.index_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.stock_condition_basis
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DELETE FROM public.board_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.index_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.stock_monitor_target
WHERE source_version = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DELETE FROM public.common_condition_quality_item
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);
DELETE FROM public.common_condition_run
WHERE run_id = (SELECT run_id FROM _n2_directional_incremental_20260715_rollback_guard);

DO $post_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'condition_layer_20260714_source_20260714_for_20260715_v1';
  v_count bigint;
  v_other_count_before bigint;
  v_other_count_after bigint;
  v_other_hash_before text;
  v_other_hash_after text;
  v_residual_count bigint;
BEGIN
  SELECT other_condition_run_count, other_condition_run_hash
  INTO STRICT v_other_count_before, v_other_hash_before
  FROM _n2_directional_incremental_20260715_rollback_guard;

  SELECT count(*) INTO v_count
  FROM public.common_condition_run
  WHERE run_id = v_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION
      'N2 directional-incremental rollback failed: target common_condition_run remains for %, count=%',
      v_run_id, v_count;
  END IF;

  SELECT
    count(*)::bigint,
    md5(COALESCE(string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id), ''))
  INTO v_other_count_after, v_other_hash_after
  FROM public.common_condition_run AS r
  WHERE r.run_id <> v_run_id;

  IF v_other_count_after IS DISTINCT FROM v_other_count_before
     OR v_other_hash_after IS DISTINCT FROM v_other_hash_before THEN
    RAISE EXCEPTION
      'N2 directional-incremental rollback failed: another common_condition_run changed (count %->%, hash %->%)',
      v_other_count_before, v_other_count_after, v_other_hash_before, v_other_hash_after;
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
      'N2 directional-incremental rollback failed: target child/monitor/display rows remain for %, count=%',
      v_run_id, v_residual_count;
  END IF;
END
$post_mutation_guards$;

COMMIT;
