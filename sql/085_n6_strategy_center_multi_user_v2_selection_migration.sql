-- N6 Strategy Center: owner-isolated, one-scope V2 selection migration.
-- This migration installs tooling only. It does not create a revision or
-- write projection/change rows; callers must invoke the function once per
-- principal/user under a separate fail-closed runtime policy.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_multi_user_v2_selection_migration_085_v1', 0
  )
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '085 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '085 migration function already installed';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_trade_date_authority_v1()'
     ) IS NULL THEN
    RAISE EXCEPTION '085 requires 084 date authority';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_user_strategy_selection_revision'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_item'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_package_catalog'
        ) IS NULL THEN
    RAISE EXCEPTION '085 selection schema missing';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_key IN ('package_1', 'package_2')
      AND catalog.package_version = 'v1'
      AND catalog.package_status <> 'grandfathered'
  ) OR (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_key IN ('package_1', 'package_2')
      AND catalog.package_version = 'v2'
      AND catalog.package_status = 'active'
  ) <> 2 THEN
    RAISE EXCEPTION '085 V2 catalog authority missing';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_status = 'pending'
  ) THEN
    RAISE EXCEPTION '085 pending selection must be zero at install';
  END IF;
END
$preflight$;

CREATE FUNCTION public.n6_strategy_center_migrate_v2_selection_v1(
  p_principal_id bigint,
  p_user_id bigint,
  p_expected_revision_id bigint,
  p_expected_revision_no bigint,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  principal_row public.n6_principal%ROWTYPE;
  account_status text;
  active_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  existing_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  new_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  package_keys text[];
  package_count integer;
  catalog_hash text;
  authority jsonb;
  effective_trade_date date;
BEGIN
  IF CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '085 function identity rejected';
  END IF;
  IF p_principal_id IS NULL OR p_principal_id <= 0
     OR p_user_id IS NULL OR p_user_id <= 0
     OR p_expected_revision_id IS NULL OR p_expected_revision_id <= 0
     OR p_expected_revision_no IS NULL OR p_expected_revision_no <= 0
     OR p_request_id IS NULL
     OR p_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' THEN
    RAISE EXCEPTION '085 bounded migration arguments invalid';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'n6_strategy_center_v2_migration:' || p_principal_id || ':' || p_user_id,
      0
    )
  );

  SELECT principal.* INTO principal_row
  FROM public.n6_principal principal
  WHERE principal.principal_id = p_principal_id
    AND principal.owner_user_id = p_user_id
    AND principal.principal_status = 'active'
    AND principal.principal_type IN ('admin', 'human_user');
  IF NOT FOUND THEN
    RAISE EXCEPTION '085 principal user authority missing';
  END IF;
  SELECT account.status INTO account_status
  FROM public.user_account account
  WHERE account.user_id = p_user_id;
  IF account_status IS DISTINCT FROM 'active' THEN
    RAISE EXCEPTION '085 user account inactive';
  END IF;

  SELECT revision.* INTO existing_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.principal_id = p_principal_id
    AND revision.principal_type = principal_row.principal_type
    AND revision.user_id = p_user_id
    AND revision.request_id = p_request_id;
  IF FOUND THEN
    IF existing_revision.previous_revision_id IS DISTINCT FROM p_expected_revision_id
       OR existing_revision.revision_no <> p_expected_revision_no + 1
       OR existing_revision.selection_status <> 'pending'
       OR existing_revision.replay_status <> 'pending'
       OR NOT EXISTS (
         SELECT 1
         FROM public.n6_user_strategy_selection_item item
         WHERE item.selection_revision_id = existing_revision.selection_revision_id
           AND item.package_version = 'v2'
       ) THEN
      RAISE EXCEPTION '085 idempotency conflict';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'selection_revision_id', existing_revision.selection_revision_id,
      'revision_no', existing_revision.revision_no,
      'selection_status', existing_revision.selection_status,
      'replay_status', existing_revision.replay_status,
      'effective_trade_date', existing_revision.effective_trade_date,
      'idempotent_replay', true
    );
  END IF;

  SELECT revision.* INTO active_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.selection_revision_id = p_expected_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.principal_type = principal_row.principal_type
    AND revision.user_id = p_user_id
    AND revision.revision_no = p_expected_revision_no
    AND revision.selection_status = 'active'
    AND revision.replay_status IN ('pending', 'passed')
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION '085 predecessor CAS mismatch';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.principal_id = p_principal_id
      AND revision.principal_type = principal_row.principal_type
      AND revision.user_id = p_user_id
      AND revision.selection_status = 'pending'
  ) THEN
    RAISE EXCEPTION '085 pending revision already exists';
  END IF;

  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
    INTO package_keys
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = active_revision.selection_revision_id
    AND item.package_version = 'v1';
  SELECT pg_catalog.cardinality(package_keys) INTO package_count;
  IF package_count IS NULL OR package_count < 1 OR package_count > 2
     OR EXISTS (
       SELECT 1
       FROM unnest(package_keys) key(value)
       WHERE key.value NOT IN ('package_1', 'package_2')
     )
     OR (
       SELECT count(*)
       FROM public.n6_user_strategy_selection_item item
       WHERE item.selection_revision_id = active_revision.selection_revision_id
     ) <> package_count THEN
    RAISE EXCEPTION '085 predecessor package authority invalid';
  END IF;

  authority := public.n6_strategy_center_trade_date_authority_v1();
  effective_trade_date := pg_catalog.to_date(
    authority->>'for_trade_date', 'YYYYMMDD'
  );
  SELECT pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(
               pg_catalog.string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ), 'UTF8'
             )
           ), 'hex'
         )
    INTO catalog_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(package_keys)
    AND catalog.package_version = 'v2'
    AND catalog.package_status = 'active';
  IF catalog_hash IS NULL OR (
    SELECT count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_key = ANY(package_keys)
      AND catalog.package_version = 'v2'
      AND catalog.package_status = 'active'
  ) <> package_count THEN
    RAISE EXCEPTION '085 V2 package authority invalid';
  END IF;

  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id, principal_type, user_id, revision_no,
    selection_status, replay_status, request_id, effective_trade_date,
    previous_revision_id, selection_policy_hash, created_by_user_id,
    selection_metadata_json
  ) VALUES (
    p_principal_id, principal_row.principal_type, p_user_id,
    active_revision.revision_no + 1, 'pending', 'pending', p_request_id,
    effective_trade_date, active_revision.selection_revision_id,
    catalog_hash, p_user_id,
    pg_catalog.jsonb_build_object(
      'source', 'n6_strategy_center_multi_user_v2_migration_085',
      'authority', authority,
      'package_version_transition', 'v1_to_v2',
      'projection_change_write', false
    )
  ) RETURNING * INTO new_revision;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id, package_key, package_version
  )
  SELECT new_revision.selection_revision_id, key.value, 'v2'
  FROM unnest(package_keys) key(value)
  ORDER BY key.value;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', new_revision.selection_revision_id,
    'revision_no', new_revision.revision_no,
    'selection_status', new_revision.selection_status,
    'replay_status', new_revision.replay_status,
    'effective_trade_date', new_revision.effective_trade_date,
    'selected_package_keys', package_keys,
    'idempotent_replay', false
  );
END
$function$;

ALTER FUNCTION public.n6_strategy_center_migrate_v2_selection_v1(
  bigint, bigint, bigint, bigint, text
) OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION public.n6_strategy_center_migrate_v2_selection_v1(
  bigint, bigint, bigint, bigint, text
) FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

DO $postflight$
BEGIN
  IF pg_catalog.pg_get_userbyid(
       (SELECT procedure.proowner FROM pg_catalog.pg_proc procedure
        WHERE procedure.oid = pg_catalog.to_regprocedure(
          'public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)'
        ))
     ) IS DISTINCT FROM 'ashare_v3_user'
     OR pg_catalog.has_function_privilege(
          'n6_strategy_worker',
          'public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)',
          'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_btrack_web',
          'public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)',
          'EXECUTE'
        ) THEN
    RAISE EXCEPTION '085 owner-only function ACL failed';
  END IF;
END
$postflight$;

COMMIT;
