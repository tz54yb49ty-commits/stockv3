-- Exact rollback for N6 B-track migration 065B.
-- Restores the 065 executor apply body and ACL.

BEGIN;

DO $rollback$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
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
        '6e9a42f48d2dafa42c2b7a59de667f75c16acdd5b31b0e318c7fd84f73b3e98a' THEN
    RAISE EXCEPTION '065b_rollback_baseline_drift';
  END IF;

  source_text := function_proc.prosrc;
  old_text := $new_expiry$IF proposal.expires_at <= pg_catalog.clock_timestamp()
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
  new_text := $old_expiry$IF proposal.expires_at <= pg_catalog.clock_timestamp() THEN$old_expiry$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '065b_rollback_apply_expiry_rewrite_mismatch';
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
$rollback$;

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
    RAISE EXCEPTION '065b_rollback_postflight_definition_drift';
  END IF;
END
$postflight$;

COMMIT;
