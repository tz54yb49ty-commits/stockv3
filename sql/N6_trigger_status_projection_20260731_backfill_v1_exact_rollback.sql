-- Exact rollback for the frozen empty-baseline 20260731 trigger-status backfill.
-- This is not migration 089 rollback and does not uninstall the feature.
-- OFFLINE REVIEWED ARTIFACT: execute only in a later independently authorized gate.
--
-- Before execution, freeze and verify an immutable external backup plus SHA256
-- fingerprints for common_event_outbox, common_event_inbox,
-- common_event_consumer_checkpoint, and n6_trigger_status_current.  The backup
-- evidence must bind the database/owner, migration-089 table comment and column
-- signature, the exact constants below, pre/post row counts, and rollback SQL hash.
-- This artifact intentionally performs no backup operation itself.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_trigger_status_projection_v1:trigger-status:20260731', 0
  )
);

LOCK TABLE public.n6_trigger_status_current IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.common_event_inbox IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.common_event_consumer_checkpoint IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.common_event_outbox IN SHARE MODE;

DO $exact_rollback$
DECLARE
  target_oid oid := pg_catalog.to_regclass('public.n6_trigger_status_current');
  table_owner text;
  table_comment text;
  column_signature text;
  target_inbox_count bigint;
  target_date_inbox_count bigint;
  eligible_count bigint;
  executed_count bigint;
  updated_count bigint;
  invalidated_count bigint;
  minimum_outbox_id bigint;
  maximum_outbox_id bigint;
  malformed_inbox_count bigint;
  unmatched_updated_count bigint;
  unmatched_invalidated_count bigint;
  distinct_invalidated_entry_count bigint;
  expected_active_count bigint;
  target_current_count bigint;
  current_mismatch_count bigint;
  exact_checkpoint_count bigint;
  checkpoint_mismatch_count bigint;
  before_outbox_range_count bigint;
  after_outbox_range_count bigint;
  before_outbox_range_fingerprint text;
  after_outbox_range_fingerprint text;
  deleted_current_count bigint;
  deleted_inbox_count bigint;
  deleted_checkpoint_count bigint;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '20260731 exact rollback database or owner identity rejected';
  END IF;

  IF target_oid IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_trigger_status_current_trigger_status_episode_id_seq'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.idx_089_n6_trigger_status_public_group'
        ) IS NULL THEN
    RAISE EXCEPTION '20260731 exact rollback migration 089 object identity missing';
  END IF;

  SELECT owner.rolname, pg_catalog.obj_description(relation.oid, 'pg_class')
    INTO table_owner, table_comment
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_roles owner ON owner.oid = relation.relowner
  WHERE relation.oid = target_oid;

  SELECT pg_catalog.string_agg(
           attribute.attname || ':' ||
           pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
           ',' ORDER BY attribute.attnum
         )
    INTO column_signature
  FROM pg_catalog.pg_attribute attribute
  WHERE attribute.attrelid = target_oid
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped;

  IF table_owner IS DISTINCT FROM 'ashare_v3_user'
     OR table_comment IS DISTINCT FROM
        'migration=089_n6_trigger_status_current.sql;schema_hash=sha256:e50cea0987f7f3b99989e2c23ef2d0f9d526617c688ac7f61a18e765ec439ef2;contract=N5-N6-trigger-status-forward-v1'
     OR column_signature IS DISTINCT FROM
        'trigger_status_episode_id:bigint,contract_version:text,consumer_name:text,projection_run_id:text,trade_date:text,tracking_state_key:text,entry_trigger_event_id:text,action_eligible_event_id:text,asset_kind:text,identity_key:text,asset_code:text,asset_name:text,direction:text,signal_type:text,condition_key:text,trigger_time:timestamp with time zone,trigger_price:numeric(24,6),trigger_period:text,triggered_periods:text[],action_eligible_outbox_id:bigint,last_status_outbox_id:bigint,last_event_id:text,last_event_type:text,source_action_run_id:text,source_trigger_event_id:text,created_at:timestamp with time zone,updated_at:timestamp with time zone'
     OR NOT pg_catalog.has_table_privilege(
          'n6_btrack_web', 'public.n6_trigger_status_current', 'SELECT'
        )
     OR pg_catalog.has_table_privilege(
          'n6_btrack_web', 'public.n6_trigger_status_current',
          'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
        ) THEN
    RAISE EXCEPTION '20260731 exact rollback migration 089 schema identity drift';
  END IF;

  WITH target_scope AS (
    SELECT outbox.outbox_id, outbox.event_id, outbox.event_type,
           outbox.event_schema_version, outbox.trade_date, outbox.source_layer,
           outbox.source_run_id, outbox.dedup_key, outbox.partition_key,
           outbox.event_time, outbox.payload_json, inbox.inbox_id,
           inbox.status AS inbox_status, inbox.attempt_count,
           inbox.event_type AS inbox_event_type,
           inbox.event_schema_version AS inbox_schema_version,
           inbox.source_run_id AS inbox_source_run_id,
           inbox.dedup_key AS inbox_dedup_key,
           inbox.partition_key AS inbox_partition_key,
           inbox.payload_json AS inbox_payload_json,
           inbox.raw_json
    FROM public.common_event_outbox outbox
    JOIN public.common_event_inbox inbox
      ON inbox.consumer_name = 'n6_trigger_status_projection_v1'
     AND inbox.source_layer = 'N5_action'
     AND inbox.event_id = outbox.event_id
    WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616
      AND outbox.trade_date = '20260731'
      AND outbox.source_layer = 'N5_action'
      AND outbox.event_type IN (
        'ActionEligible', 'ActionExecuted',
        'TriggerStatusUpdated', 'TriggerStatusInvalidated'
      )
  )
  SELECT count(*),
         count(*) FILTER (WHERE event_type = 'ActionEligible'),
         count(*) FILTER (WHERE event_type = 'ActionExecuted'),
         count(*) FILTER (WHERE event_type = 'TriggerStatusUpdated'),
         count(*) FILTER (WHERE event_type = 'TriggerStatusInvalidated'),
         min(outbox_id), max(outbox_id),
         count(*) FILTER (
           WHERE inbox_status IS DISTINCT FROM 'processed'
              OR attempt_count IS DISTINCT FROM 1
              OR inbox_event_type IS DISTINCT FROM event_type
              OR inbox_schema_version IS DISTINCT FROM event_schema_version
              OR inbox_source_run_id IS DISTINCT FROM source_run_id
              OR inbox_dedup_key IS DISTINCT FROM dedup_key
              OR inbox_partition_key IS DISTINCT FROM partition_key
              OR inbox_payload_json IS DISTINCT FROM payload_json
              OR raw_json ->> 'outbox_id' IS DISTINCT FROM outbox_id::text
              OR raw_json ->> 'event_id' IS DISTINCT FROM event_id
              OR raw_json ->> 'event_type' IS DISTINCT FROM event_type
              OR raw_json ->> 'trade_date' IS DISTINCT FROM trade_date
              OR raw_json ->> 'source_layer' IS DISTINCT FROM source_layer
              OR raw_json -> 'payload_json' IS DISTINCT FROM payload_json
         )
    INTO target_inbox_count, eligible_count, executed_count, updated_count,
         invalidated_count, minimum_outbox_id, maximum_outbox_id,
         malformed_inbox_count
  FROM target_scope;

  SELECT count(*)
    INTO target_date_inbox_count
  FROM public.common_event_inbox inbox
  JOIN public.common_event_outbox outbox ON outbox.event_id = inbox.event_id
  WHERE inbox.consumer_name = 'n6_trigger_status_projection_v1'
    AND inbox.source_layer = 'N5_action'
    AND outbox.trade_date = '20260731';

  IF target_inbox_count <> 2296
     OR target_date_inbox_count <> 2296
     OR eligible_count <> 1042
     OR executed_count <> 723
     OR updated_count <> 194
     OR invalidated_count <> 337
     OR minimum_outbox_id IS DISTINCT FROM 4103761
     OR maximum_outbox_id IS DISTINCT FROM 4107616
     OR malformed_inbox_count <> 0 THEN
    RAISE EXCEPTION
      '20260731 exact rollback input/inbox scope drift: target=%, date=%, eligible=%, executed=%, updated=%, invalidated=%, min=%, max=%, malformed=%',
      target_inbox_count, target_date_inbox_count, eligible_count,
      executed_count, updated_count, invalidated_count,
      minimum_outbox_id, maximum_outbox_id, malformed_inbox_count;
  END IF;

  WITH target_scope AS (
    SELECT outbox.outbox_id, outbox.event_id, outbox.event_type,
           outbox.payload_json
    FROM public.common_event_outbox outbox
    JOIN public.common_event_inbox inbox
      ON inbox.consumer_name = 'n6_trigger_status_projection_v1'
     AND inbox.source_layer = 'N5_action'
     AND inbox.event_id = outbox.event_id
    WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616
      AND outbox.trade_date = '20260731'
      AND outbox.source_layer = 'N5_action'
      AND outbox.event_type IN (
        'ActionEligible', 'ActionExecuted',
        'TriggerStatusUpdated', 'TriggerStatusInvalidated'
      )
  ), eligible AS (
    SELECT * FROM target_scope WHERE event_type = 'ActionEligible'
  ), updated AS (
    SELECT * FROM target_scope WHERE event_type = 'TriggerStatusUpdated'
  ), invalidated AS (
    SELECT * FROM target_scope WHERE event_type = 'TriggerStatusInvalidated'
  )
  SELECT
    (SELECT count(*)
     FROM updated status_row
     LEFT JOIN eligible entry
       ON entry.event_id = status_row.payload_json ->> 'action_eligible_event_id'
     WHERE entry.event_id IS NULL),
    (SELECT count(*)
     FROM invalidated status_row
     LEFT JOIN eligible entry
       ON entry.event_id = status_row.payload_json ->> 'action_eligible_event_id'
     WHERE entry.event_id IS NULL),
    (SELECT count(DISTINCT payload_json ->> 'action_eligible_event_id')
     FROM invalidated),
    (SELECT count(*)
     FROM eligible entry
     WHERE NOT EXISTS (
       SELECT 1 FROM invalidated status_row
       WHERE status_row.payload_json ->> 'action_eligible_event_id' = entry.event_id
     ))
    INTO unmatched_updated_count, unmatched_invalidated_count,
         distinct_invalidated_entry_count, expected_active_count;

  IF unmatched_updated_count <> 0
     OR unmatched_invalidated_count <> 0
     OR distinct_invalidated_entry_count <> 337
     OR expected_active_count <> 705 THEN
    RAISE EXCEPTION
      '20260731 exact rollback event lineage drift: unmatched_updated=%, unmatched_invalidated=%, distinct_invalidated=%, expected_active=%',
      unmatched_updated_count, unmatched_invalidated_count,
      distinct_invalidated_entry_count, expected_active_count;
  END IF;

  SELECT count(*)
    INTO target_current_count
  FROM public.n6_trigger_status_current current_row
  WHERE current_row.consumer_name = 'n6_trigger_status_projection_v1'
    AND current_row.projection_run_id =
        'n6_trigger_status_projection_20260731_backfill_v1'
    AND current_row.trade_date = '20260731';

  WITH target_scope AS (
    SELECT outbox.outbox_id, outbox.event_id, outbox.event_type,
           outbox.source_run_id, outbox.payload_json
    FROM public.common_event_outbox outbox
    JOIN public.common_event_inbox inbox
      ON inbox.consumer_name = 'n6_trigger_status_projection_v1'
     AND inbox.source_layer = 'N5_action'
     AND inbox.event_id = outbox.event_id
    WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616
      AND outbox.trade_date = '20260731'
      AND outbox.source_layer = 'N5_action'
      AND outbox.event_type IN (
        'ActionEligible', 'ActionExecuted',
        'TriggerStatusUpdated', 'TriggerStatusInvalidated'
      )
  ), eligible AS (
    SELECT * FROM target_scope WHERE event_type = 'ActionEligible'
  ), invalidated AS (
    SELECT * FROM target_scope WHERE event_type = 'TriggerStatusInvalidated'
  ), expected_active AS (
    SELECT entry.*
    FROM eligible entry
    WHERE NOT EXISTS (
      SELECT 1 FROM invalidated status_row
      WHERE status_row.payload_json ->> 'action_eligible_event_id' = entry.event_id
    )
  ), target_current AS (
    SELECT *
    FROM public.n6_trigger_status_current current_row
    WHERE current_row.consumer_name = 'n6_trigger_status_projection_v1'
      AND current_row.projection_run_id =
          'n6_trigger_status_projection_20260731_backfill_v1'
      AND current_row.trade_date = '20260731'
  ), compared AS (
    SELECT current_row.trigger_status_episode_id, entry.event_id AS expected_event_id,
           current_row.action_eligible_outbox_id,
           current_row.last_status_outbox_id,
           current_row.last_event_id, current_row.last_event_type,
           current_row.source_action_run_id, current_row.source_trigger_event_id,
           current_row.tracking_state_key, current_row.entry_trigger_event_id,
           current_row.asset_kind, current_row.identity_key, current_row.direction,
           current_row.signal_type, current_row.condition_key,
           entry.outbox_id AS expected_eligible_outbox_id,
           entry.source_run_id AS expected_source_run_id,
           entry.payload_json AS eligible_payload,
           latest_update.outbox_id AS update_outbox_id,
           latest_update.event_id AS update_event_id,
           latest_update.payload_json AS update_payload
    FROM target_current current_row
    FULL JOIN expected_active entry
      ON current_row.action_eligible_event_id = entry.event_id
    LEFT JOIN LATERAL (
      SELECT update_row.outbox_id, update_row.event_id, update_row.payload_json
      FROM target_scope update_row
      WHERE update_row.event_type = 'TriggerStatusUpdated'
        AND update_row.payload_json ->> 'action_eligible_event_id' = entry.event_id
      ORDER BY update_row.outbox_id DESC
      LIMIT 1
    ) latest_update ON true
  )
  SELECT count(*)
    INTO current_mismatch_count
  FROM compared
  WHERE trigger_status_episode_id IS NULL
     OR expected_event_id IS NULL
     OR action_eligible_outbox_id IS DISTINCT FROM expected_eligible_outbox_id
     OR last_status_outbox_id IS DISTINCT FROM
        COALESCE(update_outbox_id, expected_eligible_outbox_id)
     OR last_event_id IS DISTINCT FROM COALESCE(update_event_id, expected_event_id)
     OR last_event_type IS DISTINCT FROM
        CASE WHEN update_event_id IS NULL
             THEN 'ActionEligible' ELSE 'TriggerStatusUpdated' END
     OR source_action_run_id IS DISTINCT FROM expected_source_run_id
     OR source_trigger_event_id IS DISTINCT FROM
        COALESCE(
          update_payload ->> 'source_trigger_event_id',
          eligible_payload -> 'action_entry_trigger_matched_ref'
                           ->> 'source_trigger_event_id'
        )
     OR tracking_state_key IS DISTINCT FROM
        COALESCE(
          eligible_payload -> 'trace_json' ->> 'tracking_state_key',
          eligible_payload ->> 'action_key'
        )
     OR entry_trigger_event_id IS DISTINCT FROM
        eligible_payload -> 'action_entry_trigger_matched_ref'
                         ->> 'source_trigger_event_id'
     OR asset_kind IS DISTINCT FROM eligible_payload ->> 'asset_kind'
     OR identity_key IS DISTINCT FROM eligible_payload ->> 'identity_key'
     OR direction IS DISTINCT FROM eligible_payload ->> 'direction'
     OR signal_type IS DISTINCT FROM eligible_payload ->> 'signal_type'
     OR condition_key IS DISTINCT FROM eligible_payload ->> 'condition_key';

  IF target_current_count <> 705 OR current_mismatch_count <> 0 THEN
    RAISE EXCEPTION
      '20260731 exact rollback projection success state drift: current=%, mismatches=%',
      target_current_count, current_mismatch_count;
  END IF;

  SELECT count(*),
         count(*) FILTER (
           WHERE checkpoint.last_outbox_id IS DISTINCT FROM 4107616
              OR checkpoint.last_event_id IS DISTINCT FROM outbox.event_id
              OR checkpoint.last_event_time IS DISTINCT FROM outbox.event_time
              OR checkpoint.checkpoint_payload IS DISTINCT FROM
                 pg_catalog.jsonb_build_object(
                   'contract_version', 'N5-N6-trigger-status-forward-v1',
                   'projection_run_id',
                     'n6_trigger_status_projection_20260731_backfill_v1',
                   'trade_date', '20260731'
                 )
         )
    INTO exact_checkpoint_count, checkpoint_mismatch_count
  FROM public.common_event_consumer_checkpoint checkpoint
  LEFT JOIN public.common_event_outbox outbox
    ON outbox.outbox_id = checkpoint.last_outbox_id
  WHERE checkpoint.consumer_name = 'n6_trigger_status_projection_v1'
    AND checkpoint.partition_key = 'trigger-status:20260731'
    AND checkpoint.source_layer = 'N5_action';

  IF exact_checkpoint_count <> 1 OR checkpoint_mismatch_count <> 0 THEN
    RAISE EXCEPTION
      '20260731 exact rollback checkpoint drift: count=%, mismatches=%',
      exact_checkpoint_count, checkpoint_mismatch_count;
  END IF;

  SELECT count(*),
         pg_catalog.md5(
           COALESCE(
             pg_catalog.string_agg(
               outbox.outbox_id::text || '|' || outbox.event_id || '|' ||
               outbox.event_type || '|' || outbox.status || '|' ||
               outbox.payload_json::text,
               E'\n' ORDER BY outbox.outbox_id
             ),
             ''
           )
         )
    INTO before_outbox_range_count, before_outbox_range_fingerprint
  FROM public.common_event_outbox outbox
  WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616;

  WITH target_eligible AS (
    SELECT outbox.event_id
    FROM public.common_event_outbox outbox
    JOIN public.common_event_inbox inbox
      ON inbox.consumer_name = 'n6_trigger_status_projection_v1'
     AND inbox.source_layer = 'N5_action'
     AND inbox.event_id = outbox.event_id
    WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616
      AND outbox.trade_date = '20260731'
      AND outbox.source_layer = 'N5_action'
      AND outbox.event_type = 'ActionEligible'
  )
  DELETE FROM public.n6_trigger_status_current current_row
  USING target_eligible entry
  WHERE current_row.consumer_name = 'n6_trigger_status_projection_v1'
    AND current_row.projection_run_id =
        'n6_trigger_status_projection_20260731_backfill_v1'
    AND current_row.trade_date = '20260731'
    AND current_row.action_eligible_event_id = entry.event_id;
  GET DIAGNOSTICS deleted_current_count = ROW_COUNT;

  DELETE FROM public.common_event_inbox inbox
  USING public.common_event_outbox outbox
  WHERE inbox.consumer_name = 'n6_trigger_status_projection_v1'
    AND inbox.source_layer = 'N5_action'
    AND inbox.event_id = outbox.event_id
    AND outbox.outbox_id BETWEEN 4103761 AND 4107616
    AND outbox.trade_date = '20260731'
    AND outbox.source_layer = 'N5_action'
    AND outbox.event_type IN (
      'ActionEligible', 'ActionExecuted',
      'TriggerStatusUpdated', 'TriggerStatusInvalidated'
    );
  GET DIAGNOSTICS deleted_inbox_count = ROW_COUNT;

  DELETE FROM public.common_event_consumer_checkpoint checkpoint
  WHERE checkpoint.consumer_name = 'n6_trigger_status_projection_v1'
    AND checkpoint.partition_key = 'trigger-status:20260731'
    AND checkpoint.source_layer = 'N5_action';
  GET DIAGNOSTICS deleted_checkpoint_count = ROW_COUNT;

  IF deleted_current_count <> 705
     OR deleted_inbox_count <> 2296
     OR deleted_checkpoint_count <> 1 THEN
    RAISE EXCEPTION
      '20260731 exact rollback effect count drift: current=%, inbox=%, checkpoint=%',
      deleted_current_count, deleted_inbox_count, deleted_checkpoint_count;
  END IF;

  IF EXISTS (
       SELECT 1 FROM public.n6_trigger_status_current current_row
       WHERE current_row.consumer_name = 'n6_trigger_status_projection_v1'
         AND current_row.projection_run_id =
             'n6_trigger_status_projection_20260731_backfill_v1'
         AND current_row.trade_date = '20260731'
     )
     OR EXISTS (
       SELECT 1
       FROM public.common_event_inbox inbox
       JOIN public.common_event_outbox outbox ON outbox.event_id = inbox.event_id
       WHERE inbox.consumer_name = 'n6_trigger_status_projection_v1'
         AND inbox.source_layer = 'N5_action'
         AND outbox.trade_date = '20260731'
     )
     OR EXISTS (
       SELECT 1 FROM public.common_event_consumer_checkpoint checkpoint
       WHERE checkpoint.consumer_name = 'n6_trigger_status_projection_v1'
         AND checkpoint.partition_key = 'trigger-status:20260731'
         AND checkpoint.source_layer = 'N5_action'
     ) THEN
    RAISE EXCEPTION '20260731 exact rollback postflight target residue';
  END IF;

  SELECT count(*),
         pg_catalog.md5(
           COALESCE(
             pg_catalog.string_agg(
               outbox.outbox_id::text || '|' || outbox.event_id || '|' ||
               outbox.event_type || '|' || outbox.status || '|' ||
               outbox.payload_json::text,
               E'\n' ORDER BY outbox.outbox_id
             ),
             ''
           )
         )
    INTO after_outbox_range_count, after_outbox_range_fingerprint
  FROM public.common_event_outbox outbox
  WHERE outbox.outbox_id BETWEEN 4103761 AND 4107616;

  IF after_outbox_range_count IS DISTINCT FROM before_outbox_range_count
     OR after_outbox_range_fingerprint IS DISTINCT FROM
        before_outbox_range_fingerprint
     OR pg_catalog.to_regclass('public.n6_trigger_status_current')
        IS DISTINCT FROM target_oid
     OR pg_catalog.to_regclass(
          'public.n6_trigger_status_current_trigger_status_episode_id_seq'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.idx_089_n6_trigger_status_public_group'
        ) IS NULL THEN
    RAISE EXCEPTION '20260731 exact rollback outbox or migration 089 postflight drift';
  END IF;

  RAISE NOTICE
    '20260731 exact rollback PASS: current_deleted=%, inbox_deleted=%, checkpoint_deleted=%, outbox_updates=0',
    deleted_current_count, deleted_inbox_count, deleted_checkpoint_count;
END
$exact_rollback$;

COMMIT;
