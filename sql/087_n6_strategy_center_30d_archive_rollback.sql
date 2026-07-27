-- N6 Strategy Center 30-day archive rollback.
-- Restores the frozen public objects directly; it never calls 081 -> 073.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $preflight$
DECLARE
  manifest n6_strategy_center_archive_30d.archive_manifest%ROWTYPE;
  target_oids oid[];
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '087 rollback owner identity rejected';
  END IF;
  IF NOT pg_catalog.pg_try_advisory_xact_lock(
       pg_catalog.hashtextextended(
         'n6_strategy_center_30d_archive_087_v1', 0
       )
     ) THEN
    RAISE EXCEPTION '087 rollback advisory lock unavailable';
  END IF;
  SELECT * INTO STRICT manifest
  FROM n6_strategy_center_archive_30d.archive_manifest
  WHERE migration_id = '087_n6_strategy_center_30d_archive_v1'
    AND contract_version =
      'n6_strategy_center_30d_archive_retention_v1'
    AND retention_days = 30
    AND automatic_drop = false
    AND rollback_requires_independent_authorization
    AND retention_anchor_at IS NOT NULL
    AND conservative_deadline_at =
      retention_anchor_at + pg_catalog.make_interval(days => 30)
    AND rolled_back_at IS NULL;
  IF pg_catalog.clock_timestamp() >=
       manifest.conservative_deadline_at THEN
    RAISE EXCEPTION '087 30-day rollback window expired';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM n6_strategy_center_archive_30d.table_snapshot snapshot
    WHERE pg_catalog.to_regclass('public.' || snapshot.table_name) IS NOT NULL
       OR pg_catalog.to_regclass(
            'n6_strategy_center_archive_30d.' || snapshot.table_name
          ) IS NULL
  ) THEN
    RAISE EXCEPTION '087 rollback table boundary drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM n6_strategy_center_archive_30d.function_snapshot snapshot
    WHERE pg_catalog.to_regprocedure(
            snapshot.function_signature
          ) IS NOT NULL
  ) OR EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid = 'public.n6_principal'::pg_catalog.regclass
      AND trigger_row.tgname = 'trg_073_n6_strategy_default_selection'
      AND NOT trigger_row.tgisinternal
  ) THEN
    RAISE EXCEPTION '087 rollback public function or trigger conflict';
  END IF;
  SELECT pg_catalog.array_agg(relation.oid ORDER BY relation.relname)
    INTO target_oids
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_namespace namespace
    ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname = 'n6_strategy_center_archive_30d'
    AND relation.relkind = 'r'
    AND relation.relname IN (
      SELECT snapshot.table_name
      FROM n6_strategy_center_archive_30d.table_snapshot snapshot
    );
  IF pg_catalog.cardinality(target_oids) <> 6 THEN
    RAISE EXCEPTION '087 rollback six-table archive scope missing';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_stat_activity activity
    WHERE activity.datname = pg_catalog.current_database()
      AND activity.pid <> pg_catalog.pg_backend_pid()
      AND activity.backend_type = 'client backend'
      AND (
        activity.usename IN ('n6_btrack_web', 'n6_strategy_worker')
        OR pg_catalog.lower(activity.application_name)
             LIKE '%strategy%center%'
        OR pg_catalog.lower(activity.query) LIKE '%n6_strategy_%'
        OR pg_catalog.lower(activity.query)
             LIKE '%n6_user_strategy_selection_%'
      )
  ) THEN
    RAISE EXCEPTION '087 active Strategy Center session detected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_locks lock_row
    WHERE lock_row.pid <> pg_catalog.pg_backend_pid()
      AND lock_row.relation = ANY(target_oids)
  ) THEN
    RAISE EXCEPTION '087 rollback conflicting relation lock detected';
  END IF;
END
$preflight$;

ALTER TABLE n6_strategy_center_archive_30d.n6_strategy_package_catalog
  SET SCHEMA public;
ALTER TABLE n6_strategy_center_archive_30d.n6_user_strategy_selection_revision
  SET SCHEMA public;
ALTER TABLE n6_strategy_center_archive_30d.n6_user_strategy_selection_item
  SET SCHEMA public;
ALTER TABLE n6_strategy_center_archive_30d.n6_strategy_match_projection
  SET SCHEMA public;
ALTER TABLE n6_strategy_center_archive_30d.n6_strategy_observation_projection
  SET SCHEMA public;
ALTER TABLE n6_strategy_center_archive_30d.n6_strategy_match_change
  SET SCHEMA public;

DO $move_owned_sequences$
DECLARE
  snapshot record;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.sequence_snapshot
  LOOP
    IF pg_catalog.to_regclass(
         'n6_strategy_center_archive_30d.' || snapshot.sequence_name
       ) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'ALTER SEQUENCE n6_strategy_center_archive_30d.%I '
        'SET SCHEMA public',
        snapshot.sequence_name
      );
    END IF;
    EXECUTE pg_catalog.format(
      'ALTER SEQUENCE public.%I OWNER TO %I',
      snapshot.sequence_name,
      snapshot.owner_name
    );
  END LOOP;
END
$move_owned_sequences$;

DO $restore_table_owners$
DECLARE
  snapshot record;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.table_snapshot
  LOOP
    EXECUTE pg_catalog.format(
      'ALTER TABLE public.%I OWNER TO %I',
      snapshot.table_name,
      snapshot.owner_name
    );
  END LOOP;
END
$restore_table_owners$;

DO $restore_functions$
DECLARE
  snapshot record;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.function_snapshot
    ORDER BY restore_order
  LOOP
    EXECUTE snapshot.function_definition;
    EXECUTE 'ALTER FUNCTION ' || snapshot.function_signature ||
            pg_catalog.format(' OWNER TO %I', snapshot.owner_name);
    EXECUTE 'REVOKE ALL ON FUNCTION ' || snapshot.function_signature ||
            ' FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor';
  END LOOP;
END
$restore_functions$;

DO $restore_trigger$
DECLARE
  trigger_definition text;
BEGIN
  SELECT snapshot.trigger_definition INTO STRICT trigger_definition
  FROM n6_strategy_center_archive_30d.trigger_snapshot snapshot
  WHERE snapshot.trigger_name =
    'trg_073_n6_strategy_default_selection';
  EXECUTE trigger_definition;
END
$restore_trigger$;

REVOKE ALL ON TABLE
  public.n6_strategy_package_catalog,
  public.n6_user_strategy_selection_revision,
  public.n6_user_strategy_selection_item,
  public.n6_strategy_match_projection,
  public.n6_strategy_observation_projection,
  public.n6_strategy_match_change
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor;

DO $clear_sequence_acl$
DECLARE
  snapshot record;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.sequence_snapshot
  LOOP
    EXECUTE pg_catalog.format(
      'REVOKE ALL ON SEQUENCE public.%I '
      'FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor',
      snapshot.sequence_name
    );
  END LOOP;
END
$clear_sequence_acl$;

DO $restore_acl$
DECLARE
  acl_row record;
  grantee_sql text;
  grant_option_sql text;
BEGIN
  FOR acl_row IN
    SELECT *
    FROM n6_strategy_center_archive_30d.object_acl_snapshot
    ORDER BY object_kind, object_identity, grantee_name, privilege_type
  LOOP
    grantee_sql := CASE
      WHEN acl_row.grantee_name = 'PUBLIC' THEN 'PUBLIC'
      ELSE pg_catalog.quote_ident(acl_row.grantee_name)
    END;
    grant_option_sql := CASE
      WHEN acl_row.is_grantable THEN ' WITH GRANT OPTION'
      ELSE ''
    END;
    IF acl_row.object_kind = 'table' THEN
      EXECUTE pg_catalog.format(
        'GRANT %s ON TABLE public.%I TO %s%s',
        acl_row.privilege_type,
        acl_row.object_identity,
        grantee_sql,
        grant_option_sql
      );
    ELSIF acl_row.object_kind = 'sequence' THEN
      EXECUTE pg_catalog.format(
        'GRANT %s ON SEQUENCE public.%I TO %s%s',
        acl_row.privilege_type,
        acl_row.object_identity,
        grantee_sql,
        grant_option_sql
      );
    ELSIF acl_row.object_kind = 'function' THEN
      EXECUTE pg_catalog.format(
        'GRANT %s ON FUNCTION %s TO %s%s',
        acl_row.privilege_type,
        acl_row.object_identity,
        grantee_sql,
        grant_option_sql
      );
    ELSE
      RAISE EXCEPTION '087 unknown ACL snapshot kind: %',
        acl_row.object_kind;
    END IF;
  END LOOP;
END
$restore_acl$;

DO $postflight$
DECLARE
  snapshot record;
  restored_count bigint;
  restored_hash text;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.table_snapshot
  LOOP
    IF pg_catalog.to_regclass('public.' || snapshot.table_name) IS NULL
       OR pg_catalog.to_regclass(
            'n6_strategy_center_archive_30d.' || snapshot.table_name
          ) IS NOT NULL THEN
      RAISE EXCEPTION '087 rollback table schema restore failed: %',
        snapshot.table_name;
    END IF;
    EXECUTE pg_catalog.format(
      'SELECT pg_catalog.count(*), '
      'pg_catalog.md5(coalesce('
      'pg_catalog.string_agg(pg_catalog.to_jsonb(row_value)::text, '
      '''|'' ORDER BY pg_catalog.to_jsonb(row_value)::text), '''')) '
      'FROM public.%I row_value',
      snapshot.table_name
    ) INTO restored_count, restored_hash;
    IF restored_count IS DISTINCT FROM snapshot.row_count
       OR restored_hash IS DISTINCT FROM snapshot.row_hash THEN
      RAISE EXCEPTION '087 rollback table data drift: %',
        snapshot.table_name;
    END IF;
  END LOOP;
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.function_snapshot
  LOOP
    IF pg_catalog.to_regprocedure(snapshot.function_signature) IS NULL THEN
      RAISE EXCEPTION '087 rollback function restore failed: %',
        snapshot.function_signature;
    END IF;
  END LOOP;
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.sequence_snapshot
  LOOP
    IF pg_catalog.to_regclass('public.' || snapshot.sequence_name) IS NULL THEN
      RAISE EXCEPTION '087 rollback sequence restore failed: %',
        snapshot.sequence_name;
    END IF;
  END LOOP;
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_30d.index_snapshot
  LOOP
    IF pg_catalog.to_regclass('public.' || snapshot.index_name) IS NULL THEN
      RAISE EXCEPTION '087 rollback index restore failed: %',
        snapshot.index_name;
    END IF;
  END LOOP;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid = 'public.n6_principal'::pg_catalog.regclass
      AND trigger_row.tgname = 'trg_073_n6_strategy_default_selection'
      AND NOT trigger_row.tgisinternal
  ) THEN
    RAISE EXCEPTION '087 rollback trigger restore failed';
  END IF;
  UPDATE n6_strategy_center_archive_30d.archive_manifest
  SET rolled_back_at = pg_catalog.clock_timestamp()
  WHERE migration_id = '087_n6_strategy_center_30d_archive_v1';
END
$postflight$;

COMMIT;
