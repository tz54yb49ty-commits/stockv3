-- Exact rollback for N6 migration 066.
-- Restores the 065B all-day manual BUY definitions and privileges.
-- Historical proposal, order, trade, cash, position and lot rows are retained.

BEGIN;

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_proposal_create(text,text,bigint)',
        '6c43e9c2426867d8d31d0827de83147893395ae923bb1b1bf83ea4b81654fd10'
      ),
      (
        'public.n6_btrack_proposal_confirm(text,bigint,text)',
        '2857c7437c45f0b280f60d0f577d835529185d0be6e24a67bbc9ab6ff51f9f06'
      ),
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        '3ba1cc351e64e8ae6aebafdb33f577f4cc7bd2a97d46c31203893994503f75cf'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        '4768dbe91a2902fcfc372b72efcb736dd3bb073106c9fe0af45f5fcc6b9aa934'
      ),
      (
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        'd9cfbc4e07efce566e40fc642c60ef8ef5720aa2ca2aab942c3d0f4151c76366'
      ),
      (
        'public.n6_btrack_regular_trade_session_open()',
        '316ed7080aea0f343a7231b338a82f95fbec05755743bb46948583d9c93cac76'
      )
    ) AS expected_functions(signature, source_sha)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '066_rollback_required_function_missing: %',
        expected.signature;
    END IF;
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
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '066_rollback_baseline_definition_drift: %',
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
        'public.n6_btrack_proposal_create(text,text,bigint)'::regprocedure;

  old_text := $create_session_066$  IF NOT public.n6_btrack_regular_trade_session_open() THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'outside_trading_session'
    );
  END IF;
$create_session_066$;
  new_text := $create_session_065b$  IF NOT (
    p_source_type = 'signal'
    AND v_side = 'buy'
    AND authority->>'principal_type' IN ('admin', 'human_user')
  )
  AND NOT (
    shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'
    OR shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'outside_trading_session'
    );
  END IF;
$create_session_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_create_session_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_create('
    'p_session_token_hash text,p_source_type text,p_source_id bigint) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_confirm(text,bigint,text)'::regprocedure;

  old_text := $confirm_session_066$  IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_found','error','proposal_not_found'); END IF;
  IF NOT public.n6_btrack_regular_trade_session_open() THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'outside_trading_session'
    );
  END IF;
  IF row_value.proposal_status IN ('pending', 'confirmed')
$confirm_session_066$;
  new_text := $confirm_session_065b$  IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_found','error','proposal_not_found'); END IF;
  IF row_value.proposal_status IN ('pending', 'confirmed')
$confirm_session_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_confirm_session_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_confirm('
    'p_session_token_hash text,p_proposal_id bigint,'
    'p_idempotency_key text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_proposal(bigint,text)'::regprocedure;

  old_text := $claim_explicit_066$WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND public.n6_btrack_regular_trade_session_open() AND (expires_at>pg_catalog.now()$claim_explicit_066$;
  new_text := $claim_explicit_065b$WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND (expires_at>pg_catalog.now()$claim_explicit_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_explicit_claim_rewrite_mismatch';
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

  old_text := $claim_next_066$    WHERE p.proposal_status = 'confirmed'
      AND public.n6_btrack_regular_trade_session_open()
      AND (
$claim_next_066$;
  new_text := $claim_next_065b$    WHERE p.proposal_status = 'confirmed'
      AND (
$claim_next_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_next_claim_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_claim_next_proposal('
    'p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure;

  old_text := $apply_session_066$  IF proposal.proposal_status <> 'processing'
     OR proposal.executor_run_id IS DISTINCT FROM p_executor_run_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'not_claimed');
  END IF;
  IF NOT public.n6_btrack_regular_trade_session_open() THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'trade_session_not_ready'
    );
  END IF;
  IF proposal.expires_at <= pg_catalog.clock_timestamp()
$apply_session_066$;
  new_text := $apply_session_065b$  IF proposal.proposal_status <> 'processing'
     OR proposal.executor_run_id IS DISTINCT FROM p_executor_run_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'not_claimed');
  END IF;
  IF proposal.expires_at <= pg_catalog.clock_timestamp()
$apply_session_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_apply_session_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $manual_fill_066$    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'quote_not_ready'
      );
    END IF;
    fill_price := quote.current_price::numeric(24,6);
    fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
    fill_price_source := 'quote_current_price';
    fill_price_field := 'current_price';
    fill_fallback_reason := NULL;
    fill_policy_id := 'n6_066_fresh_quote_fill_v1';
$manual_fill_066$;
  new_text := $manual_fill_065b$    IF FOUND THEN
      fill_price := quote.current_price::numeric(24,6);
      fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
      fill_price_source := 'quote_current_price';
      fill_price_field := 'current_price';
      fill_fallback_reason := NULL;
      fill_policy_id := 'n6_064_fresh_quote_fill_v1';
    ELSE
      IF (
        current_local_time > time '11:30'
        AND current_local_time < time '13:00'
      )
      OR current_local_time > time '15:00' THEN
        SELECT * INTO quote
        FROM public.n6_virtual_quote_snapshot candidate
        WHERE candidate.identity_key = proposal.identity_key
          AND candidate.quality_status = 'passed'
          AND candidate.quality_reason = 'ok'
          AND candidate.exchange =
              pg_catalog.split_part(
                proposal.identity_key, ':', 2
              )
          AND candidate.quote_minute <= pg_catalog.clock_timestamp()
          AND candidate.fetched_at <= pg_catalog.clock_timestamp()
          AND candidate.fetched_at >= candidate.quote_minute
          AND (
            candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
          )::date = trade_date_date
          AND (
            (
              candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '09:30' AND time '11:30'
            OR (
              candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '13:00' AND time '15:00'
          )
          AND candidate.current_price IS NOT NULL
          AND candidate.current_price > 0
          AND candidate.current_price::text NOT IN (
                'NaN', 'Infinity', '-Infinity'
              )
        ORDER BY candidate.quote_minute DESC,
                 candidate.virtual_quote_snapshot_id DESC
        LIMIT 1
        FOR SHARE;
      END IF;

      IF FOUND THEN
        fill_price := quote.current_price::numeric(24,6);
        fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
        fill_price_source :=
          'same_day_last_quote_current_price';
        fill_price_field := 'current_price';
        fill_fallback_reason := 'fresh_quote_not_ready';
        fill_policy_id :=
          'n6_064_same_day_last_quote_fill_v1';
      ELSE
        fill_price :=
          proposal.signal_reference_price::numeric(24,6);
        fill_quote_snapshot_id := NULL;
        fill_price_source := 'signal_reference_price';
        fill_price_field := proposal.signal_reference_kind;
        fill_fallback_reason := CASE
          WHEN current_local_time < time '09:30'
            THEN 'preopen_no_same_day_quote'
          WHEN (
            current_local_time > time '11:30'
            AND current_local_time < time '13:00'
          )
          OR current_local_time > time '15:00'
            THEN 'outside_session_no_usable_same_day_quote'
          ELSE 'fresh_quote_not_ready'
        END;
        fill_policy_id :=
          'n6_064_signal_reference_fill_v1';
      END IF;
    END IF;
$manual_fill_065b$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '066_rollback_manual_fill_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := 'n6_btrack_regular_session_manual_buy_066_v1';
  new_text := 'n6_btrack_current_date_batch_scope_fix_065_v1';
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 15 THEN
    RAISE EXCEPTION '066_rollback_apply_policy_rewrite_mismatch';
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
  public.n6_btrack_proposal_create(text,text,bigint)
  FROM PUBLIC, n6_virtual_executor, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_btrack_proposal_create(text,text,bigint)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION
  public.n6_btrack_proposal_confirm(text,bigint,text)
  FROM PUBLIC, n6_virtual_executor, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_btrack_proposal_confirm(text,bigint,text)
  TO n6_btrack_web;

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

REVOKE ALL ON FUNCTION
  public.n6_executor_apply_claimed_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_apply_claimed_proposal(bigint,text)
  TO n6_virtual_executor;

DROP FUNCTION public.n6_btrack_regular_trade_session_open();

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
        'public.n6_btrack_proposal_create(text,text,bigint)',
        '56e9979559eaec73bab459cd5fb6b3affa897067f7e40d08787e81701c90a47d',
        'n6_btrack_web'
      ),
      (
        'public.n6_btrack_proposal_confirm(text,bigint,text)',
        '696ad75b2874710d30ecdd3e9ebf2ac7354d9b3698e31e698dbcc51a06d3bee4',
        'n6_btrack_web'
      ),
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        'a7c2b375cbea5546a699829a3605d0a83c5a92df3e32279bec876320ce968f20',
        'n6_virtual_executor'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        '45c8405c9d0d5d9daa4812234c5113fb9a4544430975578f54699e21c10e2eaa',
        'n6_virtual_executor'
      ),
      (
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        '6e9a42f48d2dafa42c2b7a59de667f75c16acdd5b31b0e318c7fd84f73b3e98a',
        'n6_virtual_executor'
      )
    ) AS expected_functions(signature, source_sha, execute_role)
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
    WHERE function_row.oid = function_oid
      AND function_row.prosecdef = true;
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
      RAISE EXCEPTION '066_rollback_postflight_definition_drift: %',
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
      WHERE target.oid = function_oid
        AND role.rolname = expected.execute_role
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
      WHERE target.oid = function_oid
        AND acl.privilege_type = 'EXECUTE'
        AND acl.grantee <> target.proowner
        AND (
          acl.grantee = 0
          OR role.rolname IS DISTINCT FROM expected.execute_role
          OR acl.is_grantable IS NOT FALSE
        )
    )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '066_rollback_postflight_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
  IF pg_catalog.to_regprocedure(
       'public.n6_btrack_regular_trade_session_open()'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '066_rollback_session_helper_not_dropped';
  END IF;
END
$postflight$;

COMMIT;
