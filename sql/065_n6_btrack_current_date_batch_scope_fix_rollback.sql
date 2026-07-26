-- Exact rollback for N6 B-track migration 065.
-- Restores the 064 helper and executor function bodies and ACL.
-- Historical proposals, orders, trades and positions are preserved.

BEGIN;

DO $rollback$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
  actual_sha text;
  function_proc record;
BEGIN
  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid =
        'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)'::regprocedure;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'a12ae3e8e8040ecb7459d08c69d263feb578b10b86d150fdb11488f6b7779d49' THEN
    RAISE EXCEPTION '065_rollback_helper_baseline_drift';
  END IF;

  source_text := function_proc.prosrc;
  old_text := $new_batch_scope$    WHERE basis.for_trade_date::text = current_trade_date
$new_batch_scope$;
  new_text := $old_batch_scope$    WHERE basis.for_trade_date = (
      SELECT max(current_basis.for_trade_date)
      FROM public.v_n6_stock_condition_display_basis current_basis
    )
$old_batch_scope$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '065_rollback_helper_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(
    source_text, old_text, new_text
  );
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_btrack_manual_signal_buy_current_scope('
    'p_principal_id bigint,p_principal_type text,p_user_id bigint,'
    'p_virtual_account_id bigint,p_signal_projection_id bigint,'
    'p_identity_key text,p_signal_reference_kind text,'
    'p_signal_reference_price numeric,p_for_trade_date text) '
    'RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid =
        'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        '2229ac23d823d0f27a08ba7aae18ca682594bfc27515b7a3b10b2a5673023a17' THEN
    RAISE EXCEPTION '065_rollback_executor_baseline_drift';
  END IF;

  source_text := function_proc.prosrc;
  old_text := 'n6_btrack_current_date_batch_scope_fix_065_v1';
  new_text := 'n6_btrack_trade_date_all_day_buy_064_v1';
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 15 THEN
    RAISE EXCEPTION '065_rollback_executor_policy_mismatch';
  END IF;
  source_text := pg_catalog.replace(
    source_text, old_text, new_text
  );
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_executor_apply_claimed_proposal('
    'p_proposal_id bigint,p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rollback$;

REVOKE ALL ON FUNCTION
  public.n6_btrack_manual_signal_buy_current_scope(
    bigint,text,bigint,bigint,bigint,text,text,numeric,text
  )
  FROM PUBLIC, n6_btrack_web, n6_virtual_executor, n6_ai_agent,
       n6_quote_writer;

REVOKE ALL ON FUNCTION
  public.n6_executor_apply_claimed_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_apply_claimed_proposal(bigint,text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)',
        NULL::text,
        'f79363123d2e822666dad722d3fe61860855437f73d0ac8def81e6b865cce8cb'
      ),
      (
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        'n6_virtual_executor',
        'beb59b8a4a19fa1c1d0d0508d0c83fe726774581a1e2966442ce5cecd91b5e9c'
      )
    ) AS expected_functions(signature, allowed_role, source_sha)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    SELECT function_row.prosrc,
           function_row.prosecdef,
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
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '065_rollback_postflight_definition_drift: %',
        expected.signature;
    END IF;

    SELECT
      CASE
        WHEN expected.allowed_role IS NULL THEN true
        ELSE EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc target
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              target.proacl,
              pg_catalog.acldefault('f', target.proowner)
            )
          ) acl
          JOIN pg_catalog.pg_roles role
            ON role.oid = acl.grantee
          WHERE target.oid = function_oid
            AND role.rolname = expected.allowed_role
            AND acl.privilege_type = 'EXECUTE'
            AND acl.is_grantable IS FALSE
        )
      END,
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(
            target.proacl,
            pg_catalog.acldefault('f', target.proowner)
          )
        ) acl
        LEFT JOIN pg_catalog.pg_roles role
          ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            expected.allowed_role IS NULL
            OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.allowed_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '065_rollback_postflight_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
