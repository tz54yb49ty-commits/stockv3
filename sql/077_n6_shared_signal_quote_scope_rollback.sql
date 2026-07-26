-- Roll back only N6 migration 077 shared-signal quote scope compatibility.
-- Preserve all proposal, order, trade, cash, position, lot and quote history.

BEGIN;

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
  business_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  FOR expected IN
    SELECT * FROM (VALUES
      ('public.n6_quote_writer_scope(timestamptz)',
       'c7e88b727f49a54aeedcba5bd32bd1e63d9838c916dd221a0b299c03f410de76',
       'n6_quote_writer'),
      ('public.n6_quote_writer_pending_scope(timestamptz)',
       'f7d29a064b4dc149dd6a34a7ace9c5f1583679784ecbfc6675f41304060de14e',
       'n6_quote_writer'),
      ('public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)',
       'fa772cb72c1751060032552865350dc6f8dedcdc413bcab5a4e5e789600bcd3a',
       NULL::text)
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '077_rollback_required_function_missing: %', expected.signature;
    END IF;
    SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
           owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
    WHERE p.oid = function_oid;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(pg_catalog.convert_to(function_proc.prosrc, 'UTF8')),
      'hex'
    );
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '077_rollback_baseline_definition_drift: %', expected.signature;
    END IF;
    SELECT
      CASE WHEN expected.execute_role IS NULL THEN true ELSE EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND role.rolname = expected.execute_role
          AND acl.privilege_type = 'EXECUTE'
          AND acl.is_grantable IS FALSE
      ) END,
      EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            expected.execute_role IS NULL OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.execute_role
            OR acl.is_grantable IS NOT FALSE
          )
      ) INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true OR unexpected_execute THEN
      RAISE EXCEPTION '077_rollback_baseline_acl_drift: %', expected.signature;
    END IF;
  END LOOP;

  FOREACH relation_name IN ARRAY ARRAY[
    'n6_virtual_trade_proposal', 'n6_virtual_order', 'n6_virtual_trade',
    'n6_virtual_cash_ledger', 'n6_virtual_cash_snapshot',
    'n6_virtual_position', 'n6_virtual_position_lot'
  ] LOOP
    IF pg_catalog.to_regclass('public.' || relation_name) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'SELECT count(*) FROM public.%I', relation_name
      ) INTO row_count;
      business_summary := business_summary ||
        pg_catalog.jsonb_build_object(relation_name, row_count);
    END IF;
  END LOOP;
  PERFORM pg_catalog.set_config(
    'n6.rollback_077_business_summary', business_summary::text, true
  );
END
$preflight$;

DO $rewrite$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT p.prosrc INTO source_text
  FROM pg_catalog.pg_proc p
  WHERE p.oid = 'public.n6_quote_writer_scope(timestamptz)'::regprocedure;

  old_text := $human_shared_source_077$    LEFT JOIN public.n6_ai_shared_signal_projection shared_source
      ON shared_source.source_signal_projection_id =
           proposal.source_signal_projection_id
     AND a.principal_type IN ('admin', 'human_user')
     AND shared_source.shared_status = 'active'
     AND shared_source.asset_kind = proposal.asset_kind
     AND shared_source.identity_key = proposal.identity_key
     AND shared_source.direction = proposal.proposal_side
$human_shared_source_077$;
  new_text := $human_owned_source_068$    LEFT JOIN public.user_signal_projection source
      ON source.user_signal_projection_id =
           proposal.source_signal_projection_id
     AND a.principal_type IN ('admin', 'human_user')
     AND source.user_id = proposal.user_id
     AND source.asset_kind = proposal.asset_kind
     AND source.identity_key = proposal.identity_key
     AND source.direction = proposal.proposal_side
$human_owned_source_068$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '077_rollback_human_source_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $human_shared_gate_077$        (
          a.principal_type IN ('admin', 'human_user')
          AND shared_source.source_signal_projection_id IS NOT NULL
          AND public.n6_btrack_manual_signal_buy_current_scope(
                proposal.principal_id,
                proposal.principal_type,
                proposal.user_id,
                proposal.virtual_account_id,
                proposal.source_signal_projection_id,
                proposal.identity_key,
                proposal.signal_reference_kind,
                proposal.signal_reference_price,
                proposal.source_lineage_json->>'for_trade_date'
              )
        )
$human_shared_gate_077$;
  new_text := $human_owned_gate_068$        (
          a.principal_type IN ('admin', 'human_user')
          AND source.user_signal_projection_id IS NOT NULL
        )
$human_owned_gate_068$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '077_rollback_human_gate_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_quote_writer_scope('
    'p_quote_minute timestamptz) '
    'RETURNS TABLE (principal_id bigint,principal_type text,'
    'virtual_account_id bigint,identity_key text) '
    'LANGUAGE sql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L', source_text
  );
END
$rewrite$;

REVOKE ALL ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  TO n6_quote_writer;

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
  before_summary jsonb;
  after_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  FOR expected IN
    SELECT * FROM (VALUES
      ('public.n6_quote_writer_scope(timestamptz)',
       '856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1',
       'n6_quote_writer'),
      ('public.n6_quote_writer_pending_scope(timestamptz)',
       'f7d29a064b4dc149dd6a34a7ace9c5f1583679784ecbfc6675f41304060de14e',
       'n6_quote_writer'),
      ('public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)',
       'fa772cb72c1751060032552865350dc6f8dedcdc413bcab5a4e5e789600bcd3a',
       NULL::text)
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
           owner.rolname AS owner_name INTO function_proc
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles owner
      ON owner.oid = p.proowner WHERE p.oid = function_oid;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(pg_catalog.convert_to(function_proc.prosrc, 'UTF8')),
      'hex'
    );
    IF function_oid IS NULL OR function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '077_rollback_postflight_definition_drift: %', expected.signature;
    END IF;
    SELECT
      CASE WHEN expected.execute_role IS NULL THEN true ELSE EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND role.rolname = expected.execute_role
          AND acl.privilege_type = 'EXECUTE'
          AND acl.is_grantable IS FALSE
      ) END,
      EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            expected.execute_role IS NULL OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.execute_role
            OR acl.is_grantable IS NOT FALSE
          )
      ) INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true OR unexpected_execute THEN
      RAISE EXCEPTION '077_rollback_postflight_acl_drift: %', expected.signature;
    END IF;
  END LOOP;

  before_summary := pg_catalog.current_setting(
    'n6.rollback_077_business_summary', false
  )::jsonb;
  FOR relation_name IN SELECT pg_catalog.jsonb_object_keys(before_summary)
  LOOP
    EXECUTE pg_catalog.format(
      'SELECT count(*) FROM public.%I', relation_name
    ) INTO row_count;
    after_summary := after_summary ||
      pg_catalog.jsonb_build_object(relation_name, row_count);
  END LOOP;
  IF after_summary IS DISTINCT FROM before_summary THEN
    RAISE EXCEPTION '077_rollback_business_summary_drift';
  END IF;
END
$postflight$;

COMMIT;
