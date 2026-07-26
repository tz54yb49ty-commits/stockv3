-- N6 owner-scoped atomic proposal batch cancellation interface.
-- REVIEWED MIGRATION: execute only through a separately authorized N6 gate.
-- This migration changes function definitions and privileges only. It does not
-- cancel, create, claim or execute any proposal.

BEGIN;

DO $preflight$
DECLARE
  guard_oid oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_proposal_transition_guard()'
  );
  guard_proc record;
  actual_sha text;
  business_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  IF current_user <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '078_owner_execution_required';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_btrack_proposals_cancel(text,bigint[])'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '078_candidate_already_occupied';
  END IF;
  IF guard_oid IS NULL THEN
    RAISE EXCEPTION '078_transition_guard_missing';
  END IF;

  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO guard_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = guard_oid;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(guard_proc.prosrc, 'UTF8')),
    'hex'
  );
  IF guard_proc.owner_name <> 'ashare_v3_user'
     OR guard_proc.prosecdef IS DISTINCT FROM true
     OR guard_proc.provolatile <> 'v'
     OR guard_proc.proparallel <> 'u'
     OR guard_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'c93231dd1bd456c34c954769016442d7e7fb04f0c040a18ca3a346b6e9745a9c'
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc target
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              target.proacl,
              pg_catalog.acldefault('f', target.proowner)
            )
          ) acl
          WHERE target.oid = guard_oid
            AND acl.privilege_type = 'EXECUTE'
            AND acl.grantee <> target.proowner
        ) THEN
    RAISE EXCEPTION '078_transition_guard_baseline_drift';
  END IF;
  IF pg_catalog.has_table_privilege(
       'n6_btrack_web', 'public.n6_virtual_trade_proposal',
       'INSERT,UPDATE,DELETE'
     ) THEN
    RAISE EXCEPTION '078_web_role_direct_proposal_dml_detected';
  END IF;

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
    'n6.migration_078_business_summary', business_summary::text, true
  );
END
$preflight$;

DO $guard_rewrite$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT p.prosrc INTO source_text
  FROM pg_catalog.pg_proc p
  WHERE p.oid =
        'public.n6_btrack_proposal_transition_guard()'::regprocedure;

  old_text := $guard_web_064$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF OLD.proposal_status='pending'
       AND NEW.proposal_status IN ('confirmed','expired') THEN
$guard_web_064$;
  new_text := $guard_web_078$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF OLD.proposal_status IN ('pending', 'confirmed')
       AND NEW.proposal_status = 'rejected'
       AND NEW.failure_reason = 'cancelled_by_user'
       AND OLD.executed_virtual_order_id IS NULL
       AND NEW.executed_virtual_order_id IS NULL
       AND OLD.executed_virtual_trade_id IS NULL
       AND NEW.executed_virtual_trade_id IS NULL
       AND OLD.executor_run_id IS NULL
       AND NEW.executor_run_id IS NULL
       AND pg_catalog.jsonb_typeof(
             NEW.source_lineage_json->'cancellation_audit'
           ) = 'array'
       AND pg_catalog.jsonb_array_length(
             NEW.source_lineage_json->'cancellation_audit'
           ) = (CASE
                 WHEN pg_catalog.jsonb_typeof(
                        OLD.source_lineage_json->'cancellation_audit'
                      ) = 'array'
                 THEN pg_catalog.jsonb_array_length(
                        OLD.source_lineage_json->'cancellation_audit'
                      ) + 1
                 ELSE 1
               END)
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancelled_at'
           ) IS NOT NULL
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancelled_by_principal_id'
           ) = NEW.principal_id::text
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancellation_policy_version'
           ) =
             'n6_btrack_proposal_cancel_078_v1' THEN
      NULL;
    ELSIF OLD.proposal_status='pending'
       AND NEW.proposal_status IN ('confirmed','expired') THEN
$guard_web_078$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '078_transition_guard_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_btrack_proposal_transition_guard() '
    'RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$guard_rewrite$;

CREATE FUNCTION public.n6_btrack_proposals_cancel(
  p_session_token_hash text,
  p_proposal_ids bigint[]
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb :=
    public.n6_btrack_resolve_authority(p_session_token_hash);
  sorted_ids bigint[];
  requested_count integer;
  account_count integer;
  account_id bigint;
  locked_count integer := 0;
  cancelable_count integer := 0;
  idempotent_count integer := 0;
  affected_count integer;
  proposal_row public.n6_virtual_trade_proposal%ROWTYPE;
  cancellation_audit jsonb;
  last_audit jsonb;
  has_order_or_trade boolean;
  cancelled_at timestamptz := pg_catalog.clock_timestamp();
  v_cancellation_policy_version constant text :=
    'n6_btrack_proposal_cancel_078_v1';
BEGIN
  IF authority IS NULL THEN
    RETURN NULL;
  END IF;
  requested_count := pg_catalog.cardinality(p_proposal_ids);
  IF p_proposal_ids IS NULL OR requested_count IS NULL
     OR requested_count = 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_request',
      'error', 'proposal_ids_required'
    );
  END IF;
  IF requested_count > 100 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_request',
      'error', 'proposal_ids_limit_exceeded'
    );
  END IF;
  IF EXISTS (
       SELECT 1 FROM pg_catalog.unnest(p_proposal_ids) requested(proposal_id)
       WHERE requested.proposal_id IS NULL OR requested.proposal_id <= 0
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_request',
      'error', 'proposal_id_invalid'
    );
  END IF;
  IF (
       SELECT count(DISTINCT requested.proposal_id)
       FROM pg_catalog.unnest(p_proposal_ids) requested(proposal_id)
     ) <> requested_count THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_request',
      'error', 'proposal_ids_duplicate'
    );
  END IF;
  SELECT pg_catalog.array_agg(requested.proposal_id ORDER BY requested.proposal_id)
    INTO sorted_ids
  FROM pg_catalog.unnest(p_proposal_ids) requested(proposal_id);

  SELECT count(*), min(account.virtual_account_id)
    INTO account_count, account_id
  FROM public.n6_virtual_account account
  WHERE account.principal_id = (authority->>'principal_id')::bigint
    AND account.principal_type = authority->>'principal_type'
    AND account.virtual_account_status = 'active';
  IF account_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'active_virtual_account_not_unique'
    );
  END IF;

  FOR proposal_row IN
    SELECT proposal.*
    FROM public.n6_virtual_trade_proposal proposal
    JOIN pg_catalog.unnest(sorted_ids) requested(proposal_id)
      ON requested.proposal_id = proposal.proposal_id
    ORDER BY proposal.proposal_id
    FOR UPDATE OF proposal
  LOOP
    locked_count := locked_count + 1;
    IF proposal_row.user_id IS DISTINCT FROM
         (authority->>'user_id')::bigint
       OR proposal_row.principal_id IS DISTINCT FROM
         (authority->>'principal_id')::bigint
       OR proposal_row.principal_type IS DISTINCT FROM
         authority->>'principal_type'
       OR proposal_row.virtual_account_id IS DISTINCT FROM account_id THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'proposal_owner_mismatch'
      );
    END IF;
    SELECT
      EXISTS (
        SELECT 1 FROM public.n6_virtual_order existing_order
        WHERE existing_order.source_proposal_id = proposal_row.proposal_id
      ) OR EXISTS (
        SELECT 1 FROM public.n6_virtual_trade existing_trade
        WHERE existing_trade.source_proposal_id = proposal_row.proposal_id
      )
      INTO has_order_or_trade;
    IF proposal_row.executor_run_id IS NOT NULL
       OR proposal_row.executed_virtual_order_id IS NOT NULL
       OR proposal_row.executed_virtual_trade_id IS NOT NULL
       OR has_order_or_trade THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'conflict',
        'error', 'proposal_execution_reference_exists'
      );
    END IF;

    IF proposal_row.proposal_status IN ('pending', 'confirmed') THEN
      cancelable_count := cancelable_count + 1;
    ELSIF proposal_row.proposal_status = 'rejected'
          AND proposal_row.failure_reason = 'cancelled_by_user' THEN
      cancellation_audit :=
        proposal_row.source_lineage_json->'cancellation_audit';
      IF pg_catalog.jsonb_typeof(cancellation_audit) <> 'array'
         OR pg_catalog.jsonb_array_length(cancellation_audit) = 0 THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'conflict',
          'error', 'proposal_status_not_cancelable'
        );
      END IF;
      last_audit := cancellation_audit ->
        (pg_catalog.jsonb_array_length(cancellation_audit) - 1);
      IF last_audit->>'cancelled_at' IS NULL
         OR last_audit->>'cancelled_by_principal_id' IS DISTINCT FROM
            (authority->>'principal_id')
         OR last_audit->>'cancellation_policy_version' IS DISTINCT FROM
            v_cancellation_policy_version THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'conflict',
          'error', 'proposal_status_not_cancelable'
        );
      END IF;
      idempotent_count := idempotent_count + 1;
    ELSE
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'conflict',
        'error', 'proposal_status_not_cancelable'
      );
    END IF;
  END LOOP;

  IF locked_count <> requested_count THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_found',
      'error', 'proposal_not_found'
    );
  END IF;
  IF cancelable_count > 0 AND idempotent_count > 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'conflict',
      'error', 'mixed_cancellation_state'
    );
  END IF;
  IF idempotent_count = requested_count THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'cancelled', 'idempotent', true,
      'cancelled_count', requested_count,
      'proposal_ids', pg_catalog.to_jsonb(sorted_ids)
    );
  END IF;

  UPDATE public.n6_virtual_trade_proposal proposal
  SET proposal_status = 'rejected',
      failure_reason = 'cancelled_by_user',
      source_lineage_json =
        COALESCE(proposal.source_lineage_json, '{}'::jsonb) ||
        pg_catalog.jsonb_build_object(
          'cancellation_audit',
          CASE
            WHEN pg_catalog.jsonb_typeof(
                   proposal.source_lineage_json->'cancellation_audit'
                 ) = 'array'
            THEN proposal.source_lineage_json->'cancellation_audit'
            ELSE '[]'::jsonb
          END || pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
              'cancelled_at', cancelled_at,
              'cancelled_by_principal_id',
                (authority->>'principal_id')::bigint,
              'cancellation_policy_version', v_cancellation_policy_version
            )
          )
        ),
      updated_at = cancelled_at
  WHERE proposal.proposal_id = ANY(sorted_ids)
    AND proposal.proposal_status IN ('pending', 'confirmed');
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> requested_count THEN
    RAISE EXCEPTION '078_atomic_update_count_mismatch';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'cancelled', 'idempotent', false,
    'cancelled_count', affected_count,
    'proposal_ids', pg_catalog.to_jsonb(sorted_ids)
  );
END
$function$;

ALTER FUNCTION public.n6_btrack_proposals_cancel(text,bigint[])
  OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_btrack_proposals_cancel(text,bigint[])
  FROM PUBLIC, n6_ai_agent, n6_quote_writer, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposals_cancel(text,bigint[])
  TO n6_btrack_web;
REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard()
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
  before_summary jsonb := pg_catalog.current_setting(
    'n6.migration_078_business_summary', false
  )::jsonb;
  after_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  FOR expected IN
    SELECT * FROM (VALUES
      ('public.n6_btrack_proposals_cancel(text,bigint[])',
       '38560d8887b0ca6f626a51f4114f36e1de1c1864442b3bedd8db2a0541722b09',
       'n6_btrack_web'),
      ('public.n6_btrack_proposal_transition_guard()',
       '8c0e5f213c7c3e83eb7c488bb3302f94de86db98c4a95901f4776e44aec2ebf8',
       NULL::text)
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '078_postflight_function_missing: %', expected.signature;
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
    IF function_proc.owner_name <> 'ashare_v3_user'
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '078_postflight_definition_drift: %', expected.signature;
    END IF;
    SELECT
      CASE WHEN expected.execute_role IS NULL THEN true ELSE EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl
        JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND role.rolname = expected.execute_role
          AND acl.privilege_type = 'EXECUTE'
          AND acl.is_grantable IS FALSE
      ) END,
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl
        LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
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
      RAISE EXCEPTION '078_postflight_acl_drift: %', expected.signature;
    END IF;
  END LOOP;
  IF pg_catalog.has_table_privilege(
       'n6_btrack_web', 'public.n6_virtual_trade_proposal',
       'INSERT,UPDATE,DELETE'
     ) THEN
    RAISE EXCEPTION '078_postflight_web_direct_dml_detected';
  END IF;

  FOREACH relation_name IN ARRAY ARRAY[
    'n6_virtual_trade_proposal', 'n6_virtual_order', 'n6_virtual_trade',
    'n6_virtual_cash_ledger', 'n6_virtual_cash_snapshot',
    'n6_virtual_position', 'n6_virtual_position_lot'
  ] LOOP
    IF pg_catalog.to_regclass('public.' || relation_name) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'SELECT count(*) FROM public.%I', relation_name
      ) INTO row_count;
      after_summary := after_summary ||
        pg_catalog.jsonb_build_object(relation_name, row_count);
    END IF;
  END LOOP;
  IF after_summary IS DISTINCT FROM before_summary THEN
    RAISE EXCEPTION '078_migration_business_dml_detected';
  END IF;
END
$postflight$;

COMMIT;
