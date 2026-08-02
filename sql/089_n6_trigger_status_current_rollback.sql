-- Roll back only migration 089 trigger-status objects and its isolated consumer state.
-- Execute only after an external immutable backup has been frozen and verified.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('089_n6_trigger_status_current_v1', 0)
);

DO $preflight$
DECLARE
  target_oid oid := pg_catalog.to_regclass('public.n6_trigger_status_current');
  table_owner text;
  table_comment text;
  unexpected_dependency_count bigint;
  unexpected_scope_count bigint;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '089 rollback owner identity rejected';
  END IF;
  IF target_oid IS NULL THEN
    RAISE EXCEPTION '089 rollback target missing';
  END IF;
  SELECT owner.rolname, pg_catalog.obj_description(relation.oid, 'pg_class')
    INTO table_owner, table_comment
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_roles owner ON owner.oid = relation.relowner
  WHERE relation.oid = target_oid;
  IF table_owner IS DISTINCT FROM 'ashare_v3_user'
     OR table_comment IS DISTINCT FROM
        'migration=089_n6_trigger_status_current.sql;schema_hash=sha256:e50cea0987f7f3b99989e2c23ef2d0f9d526617c688ac7f61a18e765ec439ef2;contract=N5-N6-trigger-status-forward-v1' THEN
    RAISE EXCEPTION '089 rollback schema hash or ownership drift';
  END IF;
  IF (
    SELECT pg_catalog.string_agg(
             attribute.attname || ':' ||
             pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
             ',' ORDER BY attribute.attnum
           )
    FROM pg_catalog.pg_attribute attribute
    WHERE attribute.attrelid = target_oid
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
  ) IS DISTINCT FROM
    'trigger_status_episode_id:bigint,contract_version:text,consumer_name:text,projection_run_id:text,trade_date:text,tracking_state_key:text,entry_trigger_event_id:text,action_eligible_event_id:text,asset_kind:text,identity_key:text,asset_code:text,asset_name:text,direction:text,signal_type:text,condition_key:text,trigger_time:timestamp with time zone,trigger_price:numeric(24,6),trigger_period:text,triggered_periods:text[],action_eligible_outbox_id:bigint,last_status_outbox_id:bigint,last_event_id:text,last_event_type:text,source_action_run_id:text,source_trigger_event_id:text,created_at:timestamp with time zone,updated_at:timestamp with time zone' THEN
    RAISE EXCEPTION '089 rollback column signature drift';
  END IF;
  SELECT count(*) INTO unexpected_dependency_count
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.confrelid = target_oid
    AND constraint_row.conrelid <> target_oid;
  unexpected_dependency_count := unexpected_dependency_count + (
    SELECT count(*)
    FROM pg_catalog.pg_depend dependency
    JOIN pg_catalog.pg_rewrite rewrite_row
      ON dependency.classid = 'pg_catalog.pg_rewrite'::regclass
     AND dependency.objid = rewrite_row.oid
    WHERE dependency.refobjid = target_oid
      AND rewrite_row.ev_class <> target_oid
  );
  IF unexpected_dependency_count <> 0 THEN
    RAISE EXCEPTION '089 rollback blocked by external dependencies: %', unexpected_dependency_count;
  END IF;
  SELECT count(*) INTO unexpected_scope_count
  FROM public.n6_trigger_status_current
  WHERE contract_version <> 'N5-N6-trigger-status-forward-v1'
     OR consumer_name <> 'n6_trigger_status_projection_v1';
  IF unexpected_scope_count <> 0 THEN
    RAISE EXCEPTION '089 rollback runtime scope drift: %', unexpected_scope_count;
  END IF;
  IF EXISTS (
       SELECT 1 FROM public.common_event_inbox
       WHERE consumer_name = 'n6_trigger_status_projection_v1'
         AND source_layer <> 'N5_action'
     ) OR EXISTS (
       SELECT 1 FROM public.common_event_consumer_checkpoint
       WHERE consumer_name = 'n6_trigger_status_projection_v1'
         AND source_layer <> 'N5_action'
     ) THEN
    RAISE EXCEPTION '089 rollback isolated consumer scope drift';
  END IF;
END
$preflight$;

LOCK TABLE public.n6_trigger_status_current IN ACCESS EXCLUSIVE MODE;

DELETE FROM public.common_event_consumer_checkpoint
WHERE consumer_name = 'n6_trigger_status_projection_v1'
  AND source_layer = 'N5_action';

DELETE FROM public.common_event_inbox
WHERE consumer_name = 'n6_trigger_status_projection_v1'
  AND source_layer = 'N5_action';

REVOKE ALL ON TABLE public.n6_trigger_status_current FROM PUBLIC, n6_btrack_web;
REVOKE ALL ON SEQUENCE public.n6_trigger_status_current_trigger_status_episode_id_seq FROM PUBLIC;

DROP TABLE public.n6_trigger_status_current;

DO $postflight$
BEGIN
  IF pg_catalog.to_regclass('public.n6_trigger_status_current') IS NOT NULL
     OR EXISTS (
       SELECT 1 FROM public.common_event_inbox
       WHERE consumer_name = 'n6_trigger_status_projection_v1'
     ) OR EXISTS (
       SELECT 1 FROM public.common_event_consumer_checkpoint
       WHERE consumer_name = 'n6_trigger_status_projection_v1'
     ) THEN
    RAISE EXCEPTION '089 rollback postflight failed';
  END IF;
END
$postflight$;

COMMIT;
