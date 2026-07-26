-- N6 post-083 remaining-user pending V2 selection function.
-- Review-only until an independent N6_user execution gate authorizes it.
-- This migration installs tooling only; it creates no revision or item.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_owner_pending_v2_086_v1', 0
  )
);

DO $preflight$
DECLARE
  signature text :=
    'public.n6_strategy_center_owner_create_pending_v2('
    'bigint,bigint,bigint,bigint,text,text,text)';
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '086 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regprocedure(signature) IS NOT NULL THEN
    RAISE EXCEPTION '086 function already installed';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_trade_date_authority_v1()'
     ) IS NULL THEN
    RAISE EXCEPTION '086 N6 authority function missing';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_user_strategy_selection_revision'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_item'
        ) IS NULL
     OR pg_catalog.to_regclass('public.n6_strategy_package_catalog') IS NULL
     OR pg_catalog.to_regclass('public.n6_principal') IS NULL
     OR pg_catalog.to_regclass('public.user_account') IS NULL THEN
    RAISE EXCEPTION '086 selection lineage missing';
  END IF;
  IF NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles
       WHERE rolname = 'n6_strategy_worker'
     ) THEN
    RAISE EXCEPTION '086 worker role missing';
  END IF;
  IF EXISTS (
       SELECT 1
       FROM pg_catalog.pg_roles role_row
       WHERE role_row.rolname = 'n6_strategy_worker'
         AND (role_row.rolsuper OR role_row.rolinherit
              OR role_row.rolcreatedb OR role_row.rolcreaterole
              OR role_row.rolreplication OR role_row.rolbypassrls)
     ) THEN
    RAISE EXCEPTION '086 worker role attributes rejected';
  END IF;
  IF has_table_privilege(
       'n6_strategy_worker',
       'public.n6_user_strategy_selection_revision', 'INSERT'
     )
     OR has_table_privilege(
          'n6_strategy_worker',
          'public.n6_user_strategy_selection_revision', 'UPDATE'
        )
     OR has_table_privilege(
          'n6_strategy_worker',
          'public.n6_user_strategy_selection_item', 'INSERT'
        ) THEN
    RAISE EXCEPTION '086 worker selection table DML baseline drift';
  END IF;
END
$preflight$;

CREATE FUNCTION public.n6_strategy_center_owner_create_pending_v2(
  p_principal_id bigint,
  p_user_id bigint,
  p_previous_revision_id bigint,
  p_expected_revision_no bigint,
  p_expected_for_trade_date text,
  p_request_id text,
  p_expected_policy_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb;
  authority_trade_date text;
  predecessor public.n6_user_strategy_selection_revision%ROWTYPE;
  existing public.n6_user_strategy_selection_revision%ROWTYPE;
  new_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  package_keys text[];
  package_count integer;
  package_policy_hash text;
  predecessor_v1 boolean;
  expected_metadata jsonb;
BEGIN
  IF p_principal_id IS NULL OR p_principal_id <= 0
     OR p_user_id IS NULL OR p_user_id <= 0
     OR p_previous_revision_id IS NULL OR p_previous_revision_id <= 0
     OR p_expected_revision_no IS NULL OR p_expected_revision_no <= 0 THEN
    RAISE EXCEPTION '086 scope identifiers invalid';
  END IF;
  IF p_expected_for_trade_date IS NULL
     OR p_expected_for_trade_date !~ '^[0-9]{8}$'
     OR p_request_id IS NULL
     OR p_request_id !~ '^[A-Za-z0-9._:-]{8,160}$'
     OR p_expected_policy_hash IS NULL
     OR p_expected_policy_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION '086 input format invalid';
  END IF;

  authority := public.n6_strategy_center_trade_date_authority_v1();
  authority_trade_date := authority->>'for_trade_date';
  IF authority->>'authority_version' IS DISTINCT FROM
       'n6_strategy_center_trade_date_authority_v1'
     OR authority_trade_date IS NULL
     OR authority_trade_date IS DISTINCT FROM p_expected_for_trade_date THEN
    RAISE EXCEPTION '086 authority date drift';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'n6_strategy_selection:' || p_principal_id || ':' || p_user_id, 0
    )
  );

  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.request_id = p_request_id
      AND NOT (
        revision.principal_id = p_principal_id
        AND revision.user_id = p_user_id
        AND revision.previous_revision_id = p_previous_revision_id
        AND revision.revision_no = p_expected_revision_no + 1
        AND revision.effective_trade_date = pg_catalog.to_date(
          p_expected_for_trade_date, 'YYYYMMDD'
        )
        AND revision.selection_policy_hash = p_expected_policy_hash
        AND revision.selection_metadata_json->>'migration_kind' =
          '086_owner_pending_v2'
      )
  ) THEN
    RAISE EXCEPTION '086 request idempotency conflict';
  END IF;
  SELECT revision.* INTO existing
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.request_id = p_request_id
    AND revision.principal_id = p_principal_id
    AND revision.user_id = p_user_id;
  IF FOUND THEN
    SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
      INTO package_keys
    FROM public.n6_user_strategy_selection_item item
    WHERE item.selection_revision_id = existing.selection_revision_id;
    IF existing.revision_no <> p_expected_revision_no + 1
       OR existing.effective_trade_date <> pg_catalog.to_date(
            p_expected_for_trade_date, 'YYYYMMDD'
          )
       OR existing.selection_policy_hash <> p_expected_policy_hash
       OR EXISTS (
            SELECT 1
            FROM public.n6_user_strategy_selection_item item
            WHERE item.selection_revision_id = existing.selection_revision_id
              AND item.package_version <> 'v2'
          ) THEN
      RAISE EXCEPTION '086 request idempotency conflict';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'selection_revision_id', existing.selection_revision_id,
      'revision_no', existing.revision_no,
      'selection_status', existing.selection_status,
      'replay_status', existing.replay_status,
      'effective_trade_date', existing.effective_trade_date,
      'selected_package_keys', package_keys,
      'authority', authority
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.n6_principal principal
    JOIN public.user_account account
      ON account.user_id = principal.owner_user_id
    WHERE principal.principal_id = p_principal_id
      AND principal.owner_user_id = p_user_id
      AND principal.principal_status = 'active'
      AND principal.principal_type IN ('admin', 'human_user')
      AND account.status = 'active'
  ) THEN
    RAISE EXCEPTION '086 principal user ownership rejected';
  END IF;

  SELECT revision.* INTO predecessor
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.selection_revision_id = p_previous_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.user_id = p_user_id
    AND revision.selection_status = 'active'
    AND revision.replay_status = 'passed'
  FOR UPDATE;
  IF NOT FOUND OR predecessor.revision_no <> p_expected_revision_no THEN
    RAISE EXCEPTION '086 predecessor CAS rejected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.principal_id = p_principal_id
      AND revision.user_id = p_user_id
      AND revision.selection_status = 'pending'
  ) THEN
    RAISE EXCEPTION '086 pending revision exists';
  END IF;

  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key),
         pg_catalog.count(*)::integer,
         pg_catalog.bool_and(item.package_version = 'v1')
    INTO package_keys, package_count, predecessor_v1
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = predecessor.selection_revision_id;
  IF package_count NOT BETWEEN 1 AND 2
     OR predecessor_v1 IS DISTINCT FROM true
     OR NOT (package_keys <@ ARRAY['package_1', 'package_2']::text[]) THEN
    RAISE EXCEPTION '086 predecessor package set rejected';
  END IF;

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
    INTO package_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(package_keys)
    AND catalog.package_version = 'v2'
    AND catalog.package_status = 'active';
  IF package_policy_hash IS NULL
     OR package_policy_hash IS DISTINCT FROM p_expected_policy_hash
     OR (
       SELECT count(*) FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_key = ANY(package_keys)
         AND catalog.package_version = 'v2'
         AND catalog.package_status = 'active'
     ) <> package_count THEN
    RAISE EXCEPTION '086 v2 catalog authority rejected';
  END IF;

  expected_metadata := pg_catalog.jsonb_build_object(
    'migration_kind', '086_owner_pending_v2',
    'predecessor_revision_id', predecessor.selection_revision_id,
    'authority', authority,
    'package_keys', package_keys,
    'policy_hash', p_expected_policy_hash
  );
  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id, principal_type, user_id, revision_no,
    selection_status, replay_status, request_id, effective_trade_date,
    previous_revision_id, selection_policy_hash, created_by_user_id,
    selection_metadata_json
  ) VALUES (
    p_principal_id, predecessor.principal_type, p_user_id,
    predecessor.revision_no + 1, 'pending', 'pending', p_request_id,
    pg_catalog.to_date(p_expected_for_trade_date, 'YYYYMMDD'),
    predecessor.selection_revision_id, p_expected_policy_hash, p_user_id,
    expected_metadata
  ) RETURNING * INTO new_revision;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id, package_key, package_version
  )
  SELECT new_revision.selection_revision_id, package_key, 'v2'
  FROM pg_catalog.unnest(package_keys) key(package_key)
  ORDER BY package_key;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', new_revision.selection_revision_id,
    'revision_no', new_revision.revision_no,
    'selection_status', new_revision.selection_status,
    'replay_status', new_revision.replay_status,
    'effective_trade_date', new_revision.effective_trade_date,
    'selected_package_keys', package_keys,
    'authority', authority
  );
EXCEPTION
  WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RAISE EXCEPTION '086 authority date invalid';
END
$function$;

ALTER FUNCTION public.n6_strategy_center_owner_create_pending_v2(
  bigint,bigint,bigint,bigint,text,text,text
) OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION
  public.n6_strategy_center_owner_create_pending_v2(
    bigint,bigint,bigint,bigint,text,text,text
  )
FROM PUBLIC, n6_btrack_web, n6_virtual_executor, n6_quote_writer,
  n6_ai_agent;
GRANT EXECUTE ON FUNCTION
  public.n6_strategy_center_owner_create_pending_v2(
    bigint,bigint,bigint,bigint,text,text,text
  ) TO n6_strategy_worker;

DO $postflight$
BEGIN
  IF pg_catalog.pg_get_userbyid(
       (
         SELECT procedure.proowner
         FROM pg_catalog.pg_proc procedure
         WHERE procedure.oid = pg_catalog.to_regprocedure(
           'public.n6_strategy_center_owner_create_pending_v2('
           'bigint,bigint,bigint,bigint,text,text,text)'
         )
       )
     ) IS DISTINCT FROM 'ashare_v3_user'
     OR has_function_privilege(
          'n6_strategy_worker',
          'public.n6_strategy_center_owner_create_pending_v2('
          'bigint,bigint,bigint,bigint,text,text,text)',
          'EXECUTE'
        ) IS NOT TRUE
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc procedure
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              procedure.proacl,
              pg_catalog.acldefault('f', procedure.proowner)
            )
          ) privilege
          WHERE procedure.oid = pg_catalog.to_regprocedure(
            'public.n6_strategy_center_owner_create_pending_v2('
            'bigint,bigint,bigint,bigint,text,text,text)'
          )
            AND privilege.grantee = 0
            AND privilege.privilege_type = 'EXECUTE'
        ) THEN
    RAISE EXCEPTION '086 function ACL postflight failed';
  END IF;
  IF has_table_privilege(
       'n6_strategy_worker',
       'public.n6_user_strategy_selection_revision', 'INSERT'
     ) OR has_table_privilege(
       'n6_strategy_worker',
       'public.n6_user_strategy_selection_item', 'INSERT'
     ) THEN
    RAISE EXCEPTION '086 worker DML postflight failed';
  END IF;
END
$postflight$;

COMMIT;
