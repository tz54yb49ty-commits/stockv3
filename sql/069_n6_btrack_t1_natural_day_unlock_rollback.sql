-- Exact rollback for N6 migration 069.
-- Restores the 066 executor function definition and privileges.
-- Historical proposal, order, trade, cash, position and lot rows are retained;
-- natural-day lots already written by 069 are not rewritten.

BEGIN;

DO $preflight$
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
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        '759dfdf9c5422a55d1b4d6d183a4f6a2bca88039265374794d8e66f6f6c833c2',
        'n6_virtual_executor'
      ),
      (
        'public.n6_btrack_regular_trade_session_open()',
        '316ed7080aea0f343a7231b338a82f95fbec05755743bb46948583d9c93cac76',
        NULL::text
      ),
      (
        'public.n6_quote_writer_scope(timestamptz)',
        '856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1',
        'n6_quote_writer'
      )
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '069_rollback_required_function_missing: %',
        expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.provolatile,
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
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '069_rollback_baseline_definition_drift: %',
        expected.signature;
    END IF;

    SELECT
      CASE
        WHEN expected.execute_role IS NULL THEN true
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
            AND role.rolname = expected.execute_role
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
            expected.execute_role IS NULL
            OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.execute_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '069_rollback_baseline_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
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
        'public.n6_executor_apply_claimed_proposal(bigint,text)'
        ::regprocedure;

  old_text := $trade_date_declaration$  trade_date_date date;
$trade_date_declaration$;
  new_text := $next_trade_date_declaration$  trade_date_date date;
  next_trade_date date;
$next_trade_date_declaration$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '069_rollback_next_trade_date_declaration_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $episode_start$    episode_no := CASE
$episode_start$;
  new_text := $future_calendar_dependency$    SELECT pg_catalog.to_date(min(trade_date)::text, 'YYYYMMDD') INTO next_trade_date
    FROM public.common_trade_calendar
    WHERE trade_date > trade_date_integer::text AND is_open = true;
    IF next_trade_date IS NULL THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'next_trade_date_not_ready');
    END IF;
    episode_no := CASE
$future_calendar_dependency$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '069_rollback_future_calendar_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $natural_day_lot$      trade_date_date, trade_date_date + 1, fill_quantity, fill_quantity,
      fill_price,
$natural_day_lot$;
  new_text := $future_open_day_lot$      trade_date_date, next_trade_date, fill_quantity, fill_quantity, fill_price,
$future_open_day_lot$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '069_rollback_lot_available_date_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := 'n6_btrack_t1_natural_day_unlock_069_v1';
  new_text := 'n6_btrack_regular_session_manual_buy_066_v1';
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 15 THEN
    RAISE EXCEPTION '069_rollback_apply_policy_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_executor_apply_claimed_proposal('
    'p_proposal_id bigint,p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rewrite$;

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
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        'd9cfbc4e07efce566e40fc642c60ef8ef5720aa2ca2aab942c3d0f4151c76366',
        'n6_virtual_executor'
      ),
      (
        'public.n6_btrack_regular_trade_session_open()',
        '316ed7080aea0f343a7231b338a82f95fbec05755743bb46948583d9c93cac76',
        NULL::text
      ),
      (
        'public.n6_quote_writer_scope(timestamptz)',
        '856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1',
        'n6_quote_writer'
      )
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '069_rollback_postflight_function_missing: %',
        expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.provolatile,
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
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '069_rollback_postflight_definition_drift: %',
        expected.signature;
    END IF;

    SELECT
      CASE
        WHEN expected.execute_role IS NULL THEN true
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
            AND role.rolname = expected.execute_role
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
            expected.execute_role IS NULL
            OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.execute_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '069_rollback_postflight_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
