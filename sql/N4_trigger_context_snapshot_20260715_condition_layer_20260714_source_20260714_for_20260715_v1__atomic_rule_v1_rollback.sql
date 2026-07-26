-- N4 period-escalation context rollback artifact for one exact planned run.
-- Target N4 run:
--   trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1
-- Feature commit: 093dcbd6669196cd1cd3439b4b0248977b059348
--
-- Historical N4 rollback artifacts for other runs are immutable evidence.
-- They do not authorize, constrain, or replace this artifact.
--
-- DO NOT EXECUTE without a dedicated rollback execute gate and both exact
-- transaction settings below:
--   SET ashare_v3.allow_n4_context_rollback_run_id =
--     'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1';
--   SET ashare_v3.allow_n4_context_rollback_artifact =
--     'N4_trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1_rollback.sql';
--
-- This artifact deletes only N4 context-localization rows owned by the exact
-- target run. It never deletes or changes N2/N3 facts, N4 runtime trigger
-- state/matches/events, downstream N5/N6 rows, or another N4 run.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL TIME ZONE 'Asia/Shanghai';

DO $authorization_guard$
DECLARE
  v_run_id CONSTANT text :=
    'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1';
  v_artifact_id CONSTANT text :=
    'N4_trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1_rollback.sql';
  v_allowed_run_id text :=
    current_setting('ashare_v3.allow_n4_context_rollback_run_id', true);
  v_allowed_artifact text :=
    current_setting('ashare_v3.allow_n4_context_rollback_artifact', true);
BEGIN
  IF v_allowed_run_id IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION
      'N4 context rollback blocked: set ashare_v3.allow_n4_context_rollback_run_id=% before mutation',
      v_run_id;
  END IF;

  IF v_allowed_artifact IS DISTINCT FROM v_artifact_id THEN
    RAISE EXCEPTION
      'N4 context rollback blocked: set ashare_v3.allow_n4_context_rollback_artifact=% before mutation',
      v_artifact_id;
  END IF;
END
$authorization_guard$;

DO $pre_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1';
  v_count bigint;
  v_table text;
  v_parent_table text;
  v_fk_schema text;
  v_fk_table text;
  v_fk_column text;
  v_parent_column text;
  v_n4_context_owned_tables CONSTANT text[] := ARRAY[
    'common_trigger_quality_item',
    'stock_trigger_context_snapshot',
    'index_trigger_context_snapshot',
    'board_trigger_context_snapshot'
  ];
BEGIN
  SELECT count(*)
  INTO v_count
  FROM public.common_trigger_run
  WHERE run_id = v_run_id;

  IF v_count <> 1 THEN
    RAISE EXCEPTION
      'N4 context rollback blocked: expected exactly one target common_trigger_run row for %, found %',
      v_run_id,
      v_count;
  END IF;

  -- Lock only the exact target while every no-reference guard is evaluated.
  PERFORM 1
  FROM public.common_trigger_run
  WHERE run_id = v_run_id
  FOR UPDATE;

  -- Event infrastructure is immutable to this rollback. Delivered/delivering
  -- outbox rows receive a dedicated blocker because they are externally
  -- observable; any other event reference blocks as well.
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
        'N4 context rollback blocked: event-ledger refs for % = %',
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
        'N4 context rollback blocked: delivered/delivering outbox refs for % = %',
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
        'N4 context rollback blocked: outbox refs for % = %',
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
        'N4 context rollback blocked: inbox refs for % = %',
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
        'N4 context rollback blocked: checkpoint refs for % = %',
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
        'N4 context rollback blocked: delivery-attempt refs for % = %',
        v_run_id, v_count;
    END IF;
  END IF;

  -- N4 runtime state, matches, and replay audits are downstream of context
  -- localization and must never be deleted by this artifact.
  FOREACH v_table IN ARRAY ARRAY[
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
          'N4 context rollback blocked: N4 state/match/replay refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- N5 action, confirmation, tracking, position, and risk rows are immutable
  -- downstream consumers of N4 context/runtime lineage.
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
          'N4 context rollback blocked: N5 action/tracking refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- N6 projection, delivery, simulation, virtual-account, and display-cache
  -- consumers are guarded independently of event infrastructure.
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
    'n6_display_cache_run',
    'n6_stock_display_cache',
    'n6_index_display_cache',
    'n6_board_display_cache',
    'n6_index_membership_display_cache',
    'n6_board_membership_display_cache'
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
          'N4 context rollback blocked: N6 projection/delivery refs in % for % = %',
          v_table, v_run_id, v_count;
      END IF;
    END IF;
  END LOOP;

  -- Reject every direct FK from an unknown non-context table into a row this
  -- artifact would delete. Internal context/quality FKs to common_trigger_run
  -- are the only allowed FK references at mutation time.
  FOREACH v_parent_table IN ARRAY ARRAY[
    'common_trigger_run',
    'common_trigger_quality_item',
    'stock_trigger_context_snapshot',
    'index_trigger_context_snapshot',
    'board_trigger_context_snapshot'
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
        'N4 context rollback blocked: unsupported composite FK references target-owned table %',
        v_parent_table;
    END IF;

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
      IF NOT (
        v_fk_schema = 'public'
        AND v_fk_table = ANY(v_n4_context_owned_tables)
      ) THEN
        EXECUTE format(
          'SELECT count(*) FROM %I.%I AS child WHERE child.%I IN (SELECT parent.%I FROM public.%I AS parent WHERE parent.run_id = $1)',
          v_fk_schema,
          v_fk_table,
          v_fk_column,
          v_parent_column,
          v_parent_table
        )
        INTO v_count
        USING v_run_id;

        IF v_count <> 0 THEN
          RAISE EXCEPTION
            'N4 context rollback blocked: downstream/FK refs in %.% via target-owned table % for % = %',
            v_fk_schema, v_fk_table, v_parent_table, v_run_id, v_count;
        END IF;
      END IF;
    END LOOP;
  END LOOP;
END
$pre_mutation_guards$;

-- Transaction-local proof that no non-target common_trigger_run changes while
-- the exact target-only context deletes execute.
CREATE TEMP TABLE _n4_period_escalation_20260715_rollback_guard
ON COMMIT DROP AS
SELECT
  'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1'::text
    AS run_id,
  count(*)::bigint AS other_trigger_run_count,
  md5(COALESCE(string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id), ''))
    AS other_trigger_run_hash
FROM public.common_trigger_run AS r
WHERE r.run_id <>
  'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1';

-- Child-before-parent target-only deletion order. No event, runtime trigger,
-- N2/N3, N5, or N6 table is mutated.
DELETE FROM public.common_trigger_quality_item
WHERE run_id = (
  SELECT run_id FROM _n4_period_escalation_20260715_rollback_guard
);

DELETE FROM public.stock_trigger_context_snapshot
WHERE run_id = (
  SELECT run_id FROM _n4_period_escalation_20260715_rollback_guard
);

DELETE FROM public.index_trigger_context_snapshot
WHERE run_id = (
  SELECT run_id FROM _n4_period_escalation_20260715_rollback_guard
);

DELETE FROM public.board_trigger_context_snapshot
WHERE run_id = (
  SELECT run_id FROM _n4_period_escalation_20260715_rollback_guard
);

DELETE FROM public.common_trigger_run
WHERE run_id = (
  SELECT run_id FROM _n4_period_escalation_20260715_rollback_guard
);

DO $post_mutation_guards$
DECLARE
  v_run_id CONSTANT text :=
    'trigger_context_snapshot_20260715_condition_layer_20260714_source_20260714_for_20260715_v1__atomic_rule_v1';
  v_target_residual_count bigint;
  v_other_count_before bigint;
  v_other_count_after bigint;
  v_other_hash_before text;
  v_other_hash_after text;
BEGIN
  SELECT other_trigger_run_count, other_trigger_run_hash
  INTO STRICT v_other_count_before, v_other_hash_before
  FROM _n4_period_escalation_20260715_rollback_guard;

  SELECT
      (SELECT count(*) FROM public.common_trigger_run WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.common_trigger_quality_item WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.stock_trigger_context_snapshot WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.index_trigger_context_snapshot WHERE run_id = v_run_id)
    + (SELECT count(*) FROM public.board_trigger_context_snapshot WHERE run_id = v_run_id)
  INTO v_target_residual_count;

  IF v_target_residual_count <> 0 THEN
    RAISE EXCEPTION
      'N4 context rollback failed: target N4 run/quality/context rows remain for %, count=%',
      v_run_id, v_target_residual_count;
  END IF;

  SELECT
    count(*)::bigint,
    md5(COALESCE(string_agg(md5(to_jsonb(r)::text), '' ORDER BY r.run_id), ''))
  INTO v_other_count_after, v_other_hash_after
  FROM public.common_trigger_run AS r
  WHERE r.run_id <> v_run_id;

  IF v_other_count_after IS DISTINCT FROM v_other_count_before
     OR v_other_hash_after IS DISTINCT FROM v_other_hash_before THEN
    RAISE EXCEPTION
      'N4 context rollback failed: another common_trigger_run changed (count %->%, hash %->%)',
      v_other_count_before,
      v_other_count_after,
      v_other_hash_before,
      v_other_hash_after;
  END IF;
END
$post_mutation_guards$;

COMMIT;
