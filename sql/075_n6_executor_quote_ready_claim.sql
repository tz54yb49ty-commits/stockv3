-- N6 executor quote-ready claim migration.
-- REVIEWED MIGRATION: execute only through a separately authorized N6 gate.
-- Rewrites one claim function and changes no business rows.

BEGIN;

DO $preflight$
DECLARE
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  function_oid := pg_catalog.to_regprocedure(
    'public.n6_executor_claim_next_proposal(text)'
  );
  IF function_oid IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_virtual_quote_snapshot'
        ) IS NULL THEN
    RAISE EXCEPTION '075_required_dependency_missing';
  END IF;

  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = function_oid;

  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        '4768dbe91a2902fcfc372b72efcb736dd3bb073106c9fe0af45f5fcc6b9aa934' THEN
    RAISE EXCEPTION '075_baseline_definition_drift';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND role.rolname = 'n6_virtual_executor'
      AND acl.privilege_type = 'EXECUTE'
      AND acl.is_grantable IS FALSE
  ), EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0
        OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
        OR acl.is_grantable IS NOT FALSE
      )
  ) INTO expected_execute, unexpected_execute;
  IF expected_execute IS DISTINCT FROM true OR unexpected_execute THEN
    RAISE EXCEPTION '075_baseline_acl_drift';
  END IF;
END
$preflight$;

DO $rewrite$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_next_proposal(text)'::regprocedure;

  old_text := $claim_fifo_066$      )
    ORDER BY p.confirmed_at ASC NULLS LAST, p.created_at ASC, p.proposal_id ASC
$claim_fifo_066$;
  new_text := $claim_quote_ready_075$      )
      AND EXISTS (
        SELECT 1
        FROM public.n6_virtual_quote_snapshot snapshot
        WHERE snapshot.identity_key = p.identity_key
          AND snapshot.exchange =
              pg_catalog.split_part(p.identity_key, ':', 2)
          AND snapshot.exchange IN ('SH', 'SZ')
          AND snapshot.quality_status = 'passed'
          AND snapshot.quality_reason = 'ok'
          AND snapshot.quote_minute <= pg_catalog.clock_timestamp()
          AND snapshot.quote_minute >=
              pg_catalog.clock_timestamp() - interval '2 minutes'
          AND snapshot.fetched_at <= pg_catalog.clock_timestamp()
          AND snapshot.fetched_at >= snapshot.quote_minute
          AND snapshot.fetched_at >=
              pg_catalog.clock_timestamp() - interval '2 minutes'
          AND (
            snapshot.quote_minute AT TIME ZONE 'Asia/Shanghai'
          )::date = (
            pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
          )::date
          AND (
            (
              snapshot.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '09:30' AND time '11:30'
            OR (
              snapshot.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '13:00' AND time '15:00'
          )
          AND snapshot.current_price IS NOT NULL
          AND snapshot.current_price > 0
          AND snapshot.current_price::text NOT IN (
                'NaN', 'Infinity', '-Infinity'
              )
      )
      -- n6_executor_quote_ready_claim_075_v1
    ORDER BY p.confirmed_at ASC NULLS LAST, p.created_at ASC, p.proposal_id ASC
$claim_quote_ready_075$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '075_claim_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_executor_claim_next_proposal('
    'p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rewrite$;

REVOKE ALL ON FUNCTION
  public.n6_executor_claim_next_proposal(text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_claim_next_proposal(text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  function_oid := pg_catalog.to_regprocedure(
    'public.n6_executor_claim_next_proposal(text)'
  );
  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = function_oid;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_oid IS NULL
     OR function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        '1a4e1ad18a987cf5fe5c89135fc064970f54c443ffe5674b8449054696232c3f' THEN
    RAISE EXCEPTION '075_postflight_definition_drift';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND role.rolname = 'n6_virtual_executor'
      AND acl.privilege_type = 'EXECUTE'
      AND acl.is_grantable IS FALSE
  ), EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0
        OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
        OR acl.is_grantable IS NOT FALSE
      )
  ) INTO expected_execute, unexpected_execute;
  IF expected_execute IS DISTINCT FROM true OR unexpected_execute THEN
    RAISE EXCEPTION '075_postflight_acl_drift';
  END IF;
END
$postflight$;

COMMIT;
