-- N6 B-track confirmed manual BUY apply scope fix.
-- REVIEWED MIGRATION: execute only through the separately authorized N6 gate.
-- This migration changes no proposal, order, trade, cash or position rows.

BEGIN;

DO $preflight$
DECLARE
  function_proc record;
  actual_sha text;
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
    RAISE EXCEPTION '065b_apply_baseline_definition_drift';
  END IF;

  IF pg_catalog.encode(
       pg_catalog.sha256(
         pg_catalog.convert_to(
           (
             SELECT function_row.prosrc
             FROM pg_catalog.pg_proc function_row
             WHERE function_row.oid =
                   'public.n6_executor_claim_proposal(bigint,text)'::regprocedure
           ),
           'UTF8'
         )
       ),
       'hex'
     ) <>
     'a7c2b375cbea5546a699829a3605d0a83c5a92df3e32279bec876320ce968f20'
     OR pg_catalog.encode(
       pg_catalog.sha256(
         pg_catalog.convert_to(
           (
             SELECT function_row.prosrc
             FROM pg_catalog.pg_proc function_row
             WHERE function_row.oid =
                   'public.n6_executor_claim_next_proposal(text)'::regprocedure
           ),
           'UTF8'
         )
       ),
       'hex'
     ) <>
     '45c8405c9d0d5d9daa4812234c5113fb9a4544430975578f54699e21c10e2eaa' THEN
    RAISE EXCEPTION '065b_claim_function_baseline_drift';
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
        'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure;

  old_text := $old_expiry$IF proposal.expires_at <= pg_catalog.clock_timestamp() THEN$old_expiry$;
  new_text := $new_expiry$IF proposal.expires_at <= pg_catalog.clock_timestamp()
     AND NOT (
       proposal.principal_type IN ('admin', 'human_user')
       AND proposal.user_id IS NOT NULL
       AND proposal.actor_ai_user_id IS NULL
       AND proposal.source_ai_decision_id IS NULL
       AND proposal.source_type = 'signal'
       AND proposal.proposal_side = 'buy'
       AND proposal.source_signal_projection_id IS NOT NULL
       AND proposal.source_virtual_position_id IS NULL
       AND public.n6_btrack_manual_signal_buy_current_scope(
         proposal.principal_id, proposal.principal_type,
         proposal.user_id, proposal.virtual_account_id,
         proposal.source_signal_projection_id, proposal.identity_key,
         proposal.signal_reference_kind,
         proposal.signal_reference_price,
         proposal.source_lineage_json->>'for_trade_date'
       )
     ) THEN$new_expiry$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '065b_apply_expiry_rewrite_mismatch';
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
  function_proc record;
  actual_sha text;
  executor_execute boolean;
  unexpected_execute boolean;
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
        '6e9a42f48d2dafa42c2b7a59de667f75c16acdd5b31b0e318c7fd84f73b3e98a' THEN
    RAISE EXCEPTION '065b_apply_postflight_definition_drift';
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
    JOIN pg_catalog.pg_roles role
      ON role.oid = acl.grantee
    WHERE target.oid =
          'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure
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
    LEFT JOIN pg_catalog.pg_roles role
      ON role.oid = acl.grantee
    WHERE target.oid =
          'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0
        OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
        OR acl.is_grantable IS NOT FALSE
      )
  )
    INTO executor_execute, unexpected_execute;
  IF executor_execute IS DISTINCT FROM true OR unexpected_execute THEN
    RAISE EXCEPTION '065b_apply_postflight_acl_drift';
  END IF;
END
$postflight$;

COMMIT;
