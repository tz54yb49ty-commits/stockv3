-- N6 Strategy Center 30-day owner-only archive.
-- Offline artifact: execute only under a separately authorized production gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $preflight$
DECLARE
  target_oids oid[];
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '087 archive owner identity rejected';
  END IF;
  IF NOT pg_catalog.pg_try_advisory_xact_lock(
       pg_catalog.hashtextextended(
         'n6_strategy_center_30d_archive_087_v1', 0
       )
     ) THEN
    RAISE EXCEPTION '087 archive advisory lock unavailable';
  END IF;
  IF pg_catalog.to_regnamespace('n6_strategy_center_archive_v1') IS NOT NULL THEN
    RAISE EXCEPTION '087 archive schema already exists';
  END IF;
  IF NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_btrack_web'
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_strategy_worker'
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_virtual_executor'
     ) THEN
    RAISE EXCEPTION '087 protected runtime role missing';
  END IF;
  IF pg_catalog.to_regclass('public.n6_principal') IS NULL THEN
    RAISE EXCEPTION '087 n6_principal missing';
  END IF;

  SELECT pg_catalog.array_agg(relation.oid ORDER BY relation.relname)
    INTO target_oids
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_namespace namespace
    ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname = 'public'
    AND relation.relkind = 'r'
    AND relation.relname = ANY(ARRAY[
      'n6_strategy_package_catalog',
      'n6_user_strategy_selection_revision',
      'n6_user_strategy_selection_item',
      'n6_strategy_match_projection',
      'n6_strategy_observation_projection',
      'n6_strategy_match_change'
    ]);
  IF pg_catalog.cardinality(target_oids) <> 6 THEN
    RAISE EXCEPTION '087 six-table archive scope missing';
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
    RAISE EXCEPTION '087 conflicting Strategy Center relation lock detected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint constraint_row
    WHERE constraint_row.contype = 'f'
      AND constraint_row.confrelid = ANY(target_oids)
      AND NOT (constraint_row.conrelid = ANY(target_oids))
  ) THEN
    RAISE EXCEPTION '087 external child-table dependency detected';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid = 'public.n6_principal'::pg_catalog.regclass
      AND trigger_row.tgname = 'trg_073_n6_strategy_default_selection'
      AND NOT trigger_row.tgisinternal
  ) THEN
    RAISE EXCEPTION '087 default-selection trigger missing';
  END IF;
END
$preflight$;

CREATE SCHEMA n6_strategy_center_archive_v1
  AUTHORIZATION ashare_v3_user;

REVOKE ALL ON SCHEMA n6_strategy_center_archive_v1
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor;

CREATE TABLE n6_strategy_center_archive_v1.archive_manifest (
  migration_id text PRIMARY KEY,
  contract_version text NOT NULL,
  archive_xid_text text NOT NULL,
  archive_started_at timestamptz NOT NULL,
  retention_days integer NOT NULL CHECK (retention_days = 30),
  automatic_drop boolean NOT NULL CHECK (automatic_drop = false),
  rollback_requires_independent_authorization boolean NOT NULL,
  retention_anchor_at timestamptz,
  conservative_deadline_at timestamptz,
  rolled_back_at timestamptz
);

CREATE TABLE n6_strategy_center_archive_v1.function_snapshot (
  function_signature text PRIMARY KEY,
  function_name text NOT NULL,
  function_definition text NOT NULL,
  owner_name text NOT NULL,
  restore_order integer NOT NULL,
  optional_at_archive boolean NOT NULL
);

CREATE TABLE n6_strategy_center_archive_v1.trigger_snapshot (
  trigger_name text PRIMARY KEY,
  trigger_definition text NOT NULL
);

CREATE TABLE n6_strategy_center_archive_v1.object_acl_snapshot (
  object_kind text NOT NULL,
  object_identity text NOT NULL,
  grantee_name text NOT NULL,
  privilege_type text NOT NULL,
  is_grantable boolean NOT NULL,
  PRIMARY KEY (
    object_kind, object_identity, grantee_name, privilege_type
  )
);

CREATE TABLE n6_strategy_center_archive_v1.table_snapshot (
  table_name text PRIMARY KEY,
  owner_name text NOT NULL,
  row_count bigint NOT NULL,
  row_hash text NOT NULL
);

CREATE TABLE n6_strategy_center_archive_v1.sequence_snapshot (
  sequence_name text PRIMARY KEY,
  owner_name text NOT NULL,
  owned_table_name text NOT NULL,
  owned_column_name text NOT NULL
);

CREATE TABLE n6_strategy_center_archive_v1.index_snapshot (
  index_name text PRIMARY KEY,
  table_name text NOT NULL,
  index_definition text NOT NULL
);

INSERT INTO n6_strategy_center_archive_v1.archive_manifest (
  migration_id,
  contract_version,
  archive_xid_text,
  archive_started_at,
  retention_days,
  automatic_drop,
  rollback_requires_independent_authorization
) VALUES (
  '087_n6_strategy_center_30d_archive_v1',
  'n6_strategy_center_30d_archive_retention_v1',
  pg_catalog.pg_current_xact_id()::text,
  pg_catalog.clock_timestamp(),
  30,
  false,
  true
);

DO $freeze_functions$
DECLARE
  function_row record;
  function_oid oid;
BEGIN
  FOR function_row IN
    SELECT *
    FROM (
      VALUES
        ('public.n6_strategy_center_trade_date_authority_v1()',
         'n6_strategy_center_trade_date_authority_v1', 10, false),
        ('public.n6_strategy_default_selection_on_principal_insert()',
         'n6_strategy_default_selection_on_principal_insert', 20, false),
        ('public.n6_btrack_strategy_center_state(text)',
         'n6_btrack_strategy_center_state', 30, false),
        ('public.n6_btrack_strategy_center_changes(text,bigint,integer)',
         'n6_btrack_strategy_center_changes', 40, false),
        ('public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
         'n6_btrack_strategy_selection_put', 50, false),
        ('public.n6_strategy_center_compensate_revision_v1(bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
         'n6_strategy_center_compensate_revision_v1', 60, false),
        ('public.n6_strategy_center_abandon_pending_v2(bigint,text,bigint,bigint,bigint,date,text)',
         'n6_strategy_center_abandon_pending_v2', 70, false),
        ('public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)',
         'n6_strategy_center_migrate_v2_selection_v1', 80, true),
        ('public.n6_strategy_center_owner_create_pending_v2(bigint,bigint,bigint,bigint,text,text,text)',
         'n6_strategy_center_owner_create_pending_v2', 90, true)
    ) AS required_functions(
      function_signature, function_name, restore_order, optional_at_archive
    )
    ORDER BY restore_order
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      function_row.function_signature
    );
    IF function_oid IS NULL THEN
      IF function_row.optional_at_archive THEN
        CONTINUE;
      END IF;
      RAISE EXCEPTION '087 required function missing: %',
        function_row.function_signature;
    END IF;
    IF pg_catalog.pg_get_userbyid(
         (SELECT procedure.proowner
          FROM pg_catalog.pg_proc procedure
          WHERE procedure.oid = function_oid)
       ) IS DISTINCT FROM 'ashare_v3_user' THEN
      RAISE EXCEPTION '087 function owner drift: %',
        function_row.function_signature;
    END IF;
    INSERT INTO n6_strategy_center_archive_v1.function_snapshot (
      function_signature,
      function_name,
      function_definition,
      owner_name,
      restore_order,
      optional_at_archive
    )
    SELECT function_row.function_signature,
           function_row.function_name,
           pg_catalog.pg_get_functiondef(function_oid),
           pg_catalog.pg_get_userbyid(procedure.proowner),
           function_row.restore_order,
           function_row.optional_at_archive
    FROM pg_catalog.pg_proc procedure
    WHERE procedure.oid = function_oid;
  END LOOP;
END
$freeze_functions$;

INSERT INTO n6_strategy_center_archive_v1.trigger_snapshot (
  trigger_name, trigger_definition
)
SELECT trigger_row.tgname,
       pg_catalog.pg_get_triggerdef(trigger_row.oid, true)
FROM pg_catalog.pg_trigger trigger_row
WHERE trigger_row.tgrelid = 'public.n6_principal'::pg_catalog.regclass
  AND trigger_row.tgname = 'trg_073_n6_strategy_default_selection'
  AND NOT trigger_row.tgisinternal;

DO $freeze_tables$
DECLARE
  table_name text;
  table_owner text;
  frozen_count bigint;
  frozen_hash text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'n6_strategy_package_catalog',
    'n6_user_strategy_selection_revision',
    'n6_user_strategy_selection_item',
    'n6_strategy_match_projection',
    'n6_strategy_observation_projection',
    'n6_strategy_match_change'
  ] LOOP
    SELECT pg_catalog.pg_get_userbyid(relation.relowner)
      INTO table_owner
    FROM pg_catalog.pg_class relation
    WHERE relation.oid =
      pg_catalog.to_regclass('public.' || table_name);
    IF table_owner IS DISTINCT FROM 'ashare_v3_user' THEN
      RAISE EXCEPTION '087 table owner drift: %', table_name;
    END IF;
    EXECUTE pg_catalog.format(
      'SELECT pg_catalog.count(*), '
      'pg_catalog.md5(coalesce('
      'pg_catalog.string_agg(pg_catalog.to_jsonb(row_value)::text, '
      '''|'' ORDER BY pg_catalog.to_jsonb(row_value)::text), '''')) '
      'FROM public.%I row_value',
      table_name
    ) INTO frozen_count, frozen_hash;
    INSERT INTO n6_strategy_center_archive_v1.table_snapshot (
      table_name, owner_name, row_count, row_hash
    ) VALUES (
      table_name, table_owner, frozen_count, frozen_hash
    );
  END LOOP;
END
$freeze_tables$;

INSERT INTO n6_strategy_center_archive_v1.sequence_snapshot (
  sequence_name, owner_name, owned_table_name, owned_column_name
)
SELECT sequence.relname,
       pg_catalog.pg_get_userbyid(sequence.relowner),
       target.relname,
       attribute.attname
FROM pg_catalog.pg_class sequence
JOIN pg_catalog.pg_namespace sequence_namespace
  ON sequence_namespace.oid = sequence.relnamespace
JOIN pg_catalog.pg_depend dependency
  ON dependency.classid = 'pg_class'::pg_catalog.regclass
 AND dependency.objid = sequence.oid
 AND dependency.refclassid = 'pg_class'::pg_catalog.regclass
 AND dependency.deptype IN ('a', 'i')
JOIN pg_catalog.pg_class target
  ON target.oid = dependency.refobjid
JOIN pg_catalog.pg_namespace target_namespace
  ON target_namespace.oid = target.relnamespace
JOIN pg_catalog.pg_attribute attribute
  ON attribute.attrelid = target.oid
 AND attribute.attnum = dependency.refobjsubid
WHERE sequence.relkind = 'S'
  AND sequence_namespace.nspname = 'public'
  AND target_namespace.nspname = 'public'
  AND target.relname = ANY(ARRAY[
    'n6_strategy_package_catalog',
    'n6_user_strategy_selection_revision',
    'n6_user_strategy_selection_item',
    'n6_strategy_match_projection',
    'n6_strategy_observation_projection',
    'n6_strategy_match_change'
  ]);

INSERT INTO n6_strategy_center_archive_v1.index_snapshot (
  index_name, table_name, index_definition
)
SELECT index_relation.relname,
       table_relation.relname,
       pg_catalog.pg_get_indexdef(index_relation.oid)
FROM pg_catalog.pg_index index_row
JOIN pg_catalog.pg_class index_relation
  ON index_relation.oid = index_row.indexrelid
JOIN pg_catalog.pg_class table_relation
  ON table_relation.oid = index_row.indrelid
JOIN pg_catalog.pg_namespace namespace
  ON namespace.oid = table_relation.relnamespace
WHERE namespace.nspname = 'public'
  AND table_relation.relname = ANY(ARRAY[
    'n6_strategy_package_catalog',
    'n6_user_strategy_selection_revision',
    'n6_user_strategy_selection_item',
    'n6_strategy_match_projection',
    'n6_strategy_observation_projection',
    'n6_strategy_match_change'
  ]);

INSERT INTO n6_strategy_center_archive_v1.object_acl_snapshot (
  object_kind,
  object_identity,
  grantee_name,
  privilege_type,
  is_grantable
)
SELECT CASE WHEN relation.relkind = 'S' THEN 'sequence' ELSE 'table' END,
       relation.relname,
       CASE
         WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE pg_catalog.pg_get_userbyid(acl.grantee)
       END,
       acl.privilege_type,
       acl.is_grantable
FROM pg_catalog.pg_class relation
JOIN pg_catalog.pg_namespace namespace
  ON namespace.oid = relation.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(
  coalesce(
    relation.relacl,
    pg_catalog.acldefault(
      CASE WHEN relation.relkind = 'S' THEN 'S'::"char"
           ELSE 'r'::"char" END,
      relation.relowner
    )
  )
) acl
WHERE namespace.nspname = 'public'
  AND (
    relation.relname IN (
      SELECT snapshot.table_name
      FROM n6_strategy_center_archive_v1.table_snapshot snapshot
    )
    OR relation.relname IN (
      SELECT snapshot.sequence_name
      FROM n6_strategy_center_archive_v1.sequence_snapshot snapshot
    )
  );

INSERT INTO n6_strategy_center_archive_v1.object_acl_snapshot (
  object_kind,
  object_identity,
  grantee_name,
  privilege_type,
  is_grantable
)
SELECT 'function',
       snapshot.function_signature,
       CASE
         WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE pg_catalog.pg_get_userbyid(acl.grantee)
       END,
       acl.privilege_type,
       acl.is_grantable
FROM n6_strategy_center_archive_v1.function_snapshot snapshot
JOIN pg_catalog.pg_proc procedure
  ON procedure.oid =
     pg_catalog.to_regprocedure(snapshot.function_signature)
CROSS JOIN LATERAL pg_catalog.aclexplode(
  coalesce(
    procedure.proacl,
    pg_catalog.acldefault('f', procedure.proowner)
  )
) acl;

DROP TRIGGER trg_073_n6_strategy_default_selection
ON public.n6_principal;

DO $drop_functions$
DECLARE
  snapshot record;
BEGIN
  FOR snapshot IN
    SELECT function_signature
    FROM n6_strategy_center_archive_v1.function_snapshot
    ORDER BY restore_order DESC
  LOOP
    EXECUTE 'REVOKE ALL ON FUNCTION ' || snapshot.function_signature ||
            ' FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor';
    EXECUTE 'DROP FUNCTION ' || snapshot.function_signature;
  END LOOP;
END
$drop_functions$;

REVOKE ALL ON TABLE
  public.n6_strategy_package_catalog,
  public.n6_user_strategy_selection_revision,
  public.n6_user_strategy_selection_item,
  public.n6_strategy_match_projection,
  public.n6_strategy_observation_projection,
  public.n6_strategy_match_change
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor;

DO $revoke_sequences$
DECLARE
  sequence_row record;
BEGIN
  FOR sequence_row IN
    SELECT sequence_name
    FROM n6_strategy_center_archive_v1.sequence_snapshot
  LOOP
    EXECUTE pg_catalog.format(
      'REVOKE ALL ON SEQUENCE public.%I '
      'FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor',
      sequence_row.sequence_name
    );
  END LOOP;
END
$revoke_sequences$;

ALTER TABLE public.n6_strategy_match_change
  SET SCHEMA n6_strategy_center_archive_v1;
ALTER TABLE public.n6_strategy_observation_projection
  SET SCHEMA n6_strategy_center_archive_v1;
ALTER TABLE public.n6_strategy_match_projection
  SET SCHEMA n6_strategy_center_archive_v1;
ALTER TABLE public.n6_user_strategy_selection_item
  SET SCHEMA n6_strategy_center_archive_v1;
ALTER TABLE public.n6_user_strategy_selection_revision
  SET SCHEMA n6_strategy_center_archive_v1;
ALTER TABLE public.n6_strategy_package_catalog
  SET SCHEMA n6_strategy_center_archive_v1;

DO $move_owned_sequences$
DECLARE
  sequence_row record;
BEGIN
  FOR sequence_row IN
    SELECT sequence_name
    FROM n6_strategy_center_archive_v1.sequence_snapshot
  LOOP
    IF pg_catalog.to_regclass(
         'public.' || sequence_row.sequence_name
       ) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'ALTER SEQUENCE public.%I '
        'SET SCHEMA n6_strategy_center_archive_v1',
        sequence_row.sequence_name
      );
    END IF;
  END LOOP;
END
$move_owned_sequences$;

REVOKE ALL ON ALL TABLES IN SCHEMA n6_strategy_center_archive_v1
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA n6_strategy_center_archive_v1
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor;

DO $postflight$
DECLARE
  snapshot record;
  archived_count bigint;
  archived_hash text;
BEGIN
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_v1.table_snapshot
  LOOP
    IF pg_catalog.to_regclass('public.' || snapshot.table_name) IS NOT NULL
       OR pg_catalog.to_regclass(
            'n6_strategy_center_archive_v1.' || snapshot.table_name
          ) IS NULL THEN
      RAISE EXCEPTION '087 table schema move failed: %',
        snapshot.table_name;
    END IF;
    EXECUTE pg_catalog.format(
      'SELECT pg_catalog.count(*), '
      'pg_catalog.md5(coalesce('
      'pg_catalog.string_agg(pg_catalog.to_jsonb(row_value)::text, '
      '''|'' ORDER BY pg_catalog.to_jsonb(row_value)::text), '''')) '
      'FROM n6_strategy_center_archive_v1.%I row_value',
      snapshot.table_name
    ) INTO archived_count, archived_hash;
    IF archived_count IS DISTINCT FROM snapshot.row_count
       OR archived_hash IS DISTINCT FROM snapshot.row_hash THEN
      RAISE EXCEPTION '087 archived table data drift: %',
        snapshot.table_name;
    END IF;
  END LOOP;
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_v1.sequence_snapshot
  LOOP
    IF pg_catalog.to_regclass(
         'n6_strategy_center_archive_v1.' || snapshot.sequence_name
       ) IS NULL THEN
      RAISE EXCEPTION '087 owned sequence move failed: %',
        snapshot.sequence_name;
    END IF;
  END LOOP;
  FOR snapshot IN
    SELECT * FROM n6_strategy_center_archive_v1.index_snapshot
  LOOP
    IF pg_catalog.to_regclass(
         'n6_strategy_center_archive_v1.' || snapshot.index_name
       ) IS NULL THEN
      RAISE EXCEPTION '087 index move failed: %', snapshot.index_name;
    END IF;
  END LOOP;
  IF EXISTS (
    SELECT 1
    FROM n6_strategy_center_archive_v1.function_snapshot function_row
    WHERE pg_catalog.to_regprocedure(
            function_row.function_signature
          ) IS NOT NULL
  ) OR EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid = 'public.n6_principal'::pg_catalog.regclass
      AND trigger_row.tgname = 'trg_073_n6_strategy_default_selection'
      AND NOT trigger_row.tgisinternal
  ) THEN
    RAISE EXCEPTION '087 active function or trigger survived archive';
  END IF;
  IF pg_catalog.has_schema_privilege(
       'n6_btrack_web',
       'n6_strategy_center_archive_v1',
       'USAGE'
     )
     OR pg_catalog.has_schema_privilege(
          'n6_strategy_worker',
          'n6_strategy_center_archive_v1',
          'USAGE'
        )
     OR pg_catalog.has_schema_privilege(
          'n6_virtual_executor',
          'n6_strategy_center_archive_v1',
          'USAGE'
        )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.pg_namespace namespace
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         coalesce(
           namespace.nspacl,
           pg_catalog.acldefault('n', namespace.nspowner)
         )
       ) acl
       WHERE namespace.nspname = 'n6_strategy_center_archive_v1'
         AND acl.grantee = 0
         AND acl.privilege_type = 'USAGE'
  ) THEN
    RAISE EXCEPTION '087 archive schema visibility rejected';
  END IF;
  WITH retention AS (
    SELECT pg_catalog.clock_timestamp() AS anchor_at
  )
  UPDATE n6_strategy_center_archive_v1.archive_manifest manifest
  SET retention_anchor_at = retention.anchor_at,
      conservative_deadline_at =
        retention.anchor_at + pg_catalog.make_interval(days => 30)
  FROM retention
  WHERE manifest.migration_id =
    '087_n6_strategy_center_30d_archive_v1';
  IF NOT EXISTS (
    SELECT 1
    FROM n6_strategy_center_archive_v1.archive_manifest manifest
    WHERE manifest.migration_id =
      '087_n6_strategy_center_30d_archive_v1'
      AND manifest.retention_anchor_at IS NOT NULL
      AND manifest.conservative_deadline_at =
        manifest.retention_anchor_at +
        pg_catalog.make_interval(days => 30)
  ) THEN
    RAISE EXCEPTION '087 conservative retention anchor freeze failed';
  END IF;
END
$postflight$;

COMMIT;
