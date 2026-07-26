-- Exact rollback for N6 B-track migration 065A.
-- Restores the original expiry-only claim functions and ACL.
-- Historical proposals, orders, trades and positions are preserved.

BEGIN;

DO $rollback$
DECLARE
  expected record;
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
  function_proc record;
  actual_sha text;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        'a7c2b375cbea5546a699829a3605d0a83c5a92df3e32279bec876320ce968f20'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        '45c8405c9d0d5d9daa4812234c5113fb9a4544430975578f54699e21c10e2eaa'
      )
    ) AS expected_functions(signature, source_sha)
  LOOP
    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = expected.signature::regprocedure;
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
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '065a_rollback_baseline_drift: %',
        expected.signature;
    END IF;
  END LOOP;

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_proposal(bigint,text)'::regprocedure;
  old_text := $new_explicit$WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND (expires_at>pg_catalog.now() OR (principal_type IN ('admin','human_user') AND user_id IS NOT NULL AND actor_ai_user_id IS NULL AND source_ai_decision_id IS NULL AND source_type='signal' AND proposal_side='buy' AND source_signal_projection_id IS NOT NULL AND source_virtual_position_id IS NULL AND public.n6_btrack_manual_signal_buy_current_scope(principal_id,principal_type,user_id,virtual_account_id,source_signal_projection_id,identity_key,signal_reference_kind,signal_reference_price,source_lineage_json->>'for_trade_date'))) RETURNING * INTO row_value;$new_explicit$;
  new_text := $old_explicit$WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND expires_at>pg_catalog.now() RETURNING * INTO row_value;$old_explicit$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '065a_rollback_explicit_claim_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_claim_proposal('
    'p_proposal_id bigint,p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_next_proposal(text)'::regprocedure;
  old_text := $new_next$WHERE p.proposal_status = 'confirmed'
      AND (
        p.expires_at > pg_catalog.now()
        OR (
          p.principal_type IN ('admin', 'human_user')
          AND p.user_id IS NOT NULL
          AND p.actor_ai_user_id IS NULL
          AND p.source_ai_decision_id IS NULL
          AND p.source_type = 'signal'
          AND p.proposal_side = 'buy'
          AND p.source_signal_projection_id IS NOT NULL
          AND p.source_virtual_position_id IS NULL
          AND public.n6_btrack_manual_signal_buy_current_scope(
            p.principal_id, p.principal_type, p.user_id,
            p.virtual_account_id, p.source_signal_projection_id,
            p.identity_key, p.signal_reference_kind,
            p.signal_reference_price,
            p.source_lineage_json->>'for_trade_date'
          )
        )
      )$new_next$;
  new_text := $old_next$WHERE p.proposal_status = 'confirmed'
      AND p.expires_at > pg_catalog.now()$old_next$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '065a_rollback_next_claim_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_claim_next_proposal('
    'p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rollback$;

REVOKE ALL ON FUNCTION
  public.n6_executor_claim_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_claim_proposal(bigint,text)
  TO n6_virtual_executor;

REVOKE ALL ON FUNCTION
  public.n6_executor_claim_next_proposal(text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_claim_next_proposal(text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  expected record;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        'fc3bed9cb3f66dfe722e8869062100d62843542bc77828ccc8c581b0e37f00f0'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        '77db38fea32888e5ec4c81698858409171ed319c0fb292aa12dd5b4f0c7c9c2e'
      )
    ) AS expected_functions(signature, source_sha)
  LOOP
    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = expected.signature::regprocedure;
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
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '065a_rollback_postflight_definition_drift: %',
        expected.signature;
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
      WHERE target.oid = expected.signature::regprocedure
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
      WHERE target.oid = expected.signature::regprocedure
        AND acl.privilege_type = 'EXECUTE'
        AND acl.grantee <> target.proowner
        AND (
          acl.grantee = 0
          OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
          OR acl.is_grantable IS NOT FALSE
        )
    )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '065a_rollback_postflight_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
