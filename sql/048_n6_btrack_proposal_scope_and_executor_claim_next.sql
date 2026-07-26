-- N6 B-track proposal effective-scope authority and function-only FIFO claim.
-- Review-only migration: do not execute from this implementation gate.

BEGIN;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_create(
  p_session_token_hash text, p_source_type text, p_source_id bigint
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  account_id bigint;
  account_count integer;
  current_trade_date text;
  current_trade_date_count integer;
  v_identity_key text;
  v_side text;
  v_reference_kind text;
  v_reference_price numeric(24,8);
  v_target_price numeric(24,8);
  v_position_id bigint;
  v_projection_id bigint;
  v_episode integer;
  v_for_trade_date text;
  v_scope_authority text;
  v_score_json jsonb;
  result_row public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF authority IS NULL
     OR p_source_id IS NULL
     OR p_source_id <= 0
     OR p_source_type NOT IN ('signal', 'manual_position') THEN
    RETURN NULL;
  END IF;

  SELECT min(a.virtual_account_id), count(*)
    INTO account_id, account_count
  FROM public.n6_virtual_account a
  WHERE a.principal_id = (authority->>'principal_id')::bigint
    AND a.principal_type = authority->>'principal_type'
    AND a.virtual_account_status = 'active';
  IF account_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'exactly_one_active_virtual_account_required'
    );
  END IF;

  SELECT min(c.trade_date), count(*)
    INTO current_trade_date, current_trade_date_count
  FROM public.common_trade_calendar c
  WHERE c.trade_date = pg_catalog.to_char(
          pg_catalog.current_timestamp AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        )
    AND c.is_open = true;
  IF current_trade_date_count <> 1 OR current_trade_date IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'current_open_trade_date_required'
    );
  END IF;

  IF p_source_type = 'signal' THEN
    WITH source_projection AS (
      SELECT p.user_signal_projection_id,
             p.identity_key,
             p.direction,
             p.projection_status,
             p.display_payload_json,
             p.target_price AS projection_target_price,
             c.card_payload_json,
             c.target_price AS card_target_price,
             c.card_status,
             p.display_payload_json->>'for_trade_date' AS for_trade_date,
             COALESCE(
               c.card_payload_json->>'action_state',
               p.display_payload_json->>'action_state'
             ) AS action_state,
             COALESCE(
               c.card_payload_json->'score',
               p.display_payload_json->'score'
             ) AS score_json
      FROM public.user_projection_run r
      JOIN public.user_signal_projection p
        ON p.user_projection_run_id = r.user_projection_run_id
      JOIN public.user_signal_card c
        ON c.user_signal_projection_id = p.user_signal_projection_id
       AND c.user_projection_run_id = p.user_projection_run_id
       AND c.user_id = p.user_id
       AND c.asset_kind = p.asset_kind
       AND c.identity_key = p.identity_key
       AND c.direction = p.direction
      WHERE p.user_signal_projection_id = p_source_id
        AND p.user_id = (authority->>'user_id')::bigint
        AND r.status IN ('passed', 'ready')
        AND p.asset_kind = 'stock'
        AND p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
        AND p.direction IN ('buy', 'sell')
        AND p.projection_status IN ('visible', 'blocked')
        AND c.card_status IN ('active', 'blocked')
        AND p.display_payload_json->>'for_trade_date' = current_trade_date
        AND (
          c.card_payload_json->>'for_trade_date' IS NULL
          OR c.card_payload_json->>'for_trade_date' = current_trade_date
        )
    ), approved_batch AS (
      SELECT min(v.source_trade_date::text) AS source_trade_date,
             min(v.for_trade_date::text) AS for_trade_date,
             min(v.run_id::text) AS source_run_id
      FROM public.v_n6_stock_condition_display_basis v
      WHERE v.for_trade_date = (
        SELECT max(current_view.for_trade_date)
        FROM public.v_n6_stock_condition_display_basis current_view
      )
      HAVING count(*) > 0
         AND count(v.source_trade_date) = count(*)
         AND count(v.for_trade_date) = count(*)
         AND count(v.run_id) = count(*)
         AND count(DISTINCT (
               v.source_trade_date::text,
               v.for_trade_date::text,
               v.run_id::text
             )) = 1
    ), approved_identity AS (
      SELECT DISTINCT v.identity_key,
             b.source_trade_date,
             b.for_trade_date,
             b.source_run_id
      FROM approved_batch b
      JOIN public.v_n6_stock_condition_display_basis v
        ON v.source_trade_date::text = b.source_trade_date
       AND v.for_trade_date::text = b.for_trade_date
       AND v.run_id::text = b.source_run_id
      WHERE b.for_trade_date = current_trade_date
    ), authorized_source AS (
      SELECT s.*,
             approved.source_trade_date AS approved_source_trade_date,
             approved.source_run_id AS approved_source_run_id,
             scope.scope_authority,
             scope.virtual_position_id,
             scope.holding_episode_no
      FROM source_projection s
      JOIN approved_identity approved
        ON approved.identity_key = s.identity_key
       AND approved.for_trade_date = s.for_trade_date
      JOIN LATERAL (
        SELECT candidate.scope_authority,
               candidate.virtual_position_id,
               candidate.holding_episode_no
        FROM (
          SELECT 'open_position'::text AS scope_authority,
                 pos.virtual_position_id,
                 pos.holding_episode_no,
                 1 AS scope_priority
          FROM public.n6_virtual_position pos
          WHERE pos.virtual_account_id = account_id
            AND pos.principal_id = (authority->>'principal_id')::bigint
            AND pos.principal_type = authority->>'principal_type'
            AND pos.asset_kind = 'stock'
            AND pos.identity_key = s.identity_key
            AND pos.position_status = 'open_virtual'
            AND pos.quantity > 0
            AND pos.holding_episode_no > 0
            AND (
              s.direction = 'buy'
              OR EXISTS (
                SELECT 1
                FROM public.n6_virtual_position_lot lot
                WHERE lot.virtual_position_id = pos.virtual_position_id
                  AND lot.virtual_account_id = pos.virtual_account_id
                  AND lot.principal_id = pos.principal_id
                  AND lot.principal_type = pos.principal_type
                  AND lot.identity_key = pos.identity_key
                  AND lot.holding_episode_no = pos.holding_episode_no
                  AND lot.remaining_quantity > 0
                  AND lot.available_trade_date <= pg_catalog.to_date(
                    current_trade_date, 'YYYYMMDD'
                  )
                  AND lot.lot_status IN ('locked_t1', 'available')
              )
            )
          UNION ALL
          SELECT 'monitor'::text, NULL::bigint, NULL::integer, 2
          FROM public.user_monitor_stock m
          WHERE s.direction = 'buy'
            AND m.principal_id = (authority->>'principal_id')::bigint
            AND m.principal_type = authority->>'principal_type'
            AND m.user_id = (authority->>'user_id')::bigint
            AND m.asset_kind = 'stock'
            AND m.identity_key = s.identity_key
            AND m.direction = 'buy'
            AND m.status = 'active'
            AND m.quality_status = 'reviewed'
            AND m.valid_source_trade_date = approved.source_trade_date
            AND m.valid_for_trade_date = approved.for_trade_date
            AND m.valid_source_run_id = approved.source_run_id
            AND m.source_run_id = approved.source_run_id
            AND m.source_snapshot_json->>'identity_key' = m.identity_key
            AND m.source_snapshot_json->>'source_trade_date' = approved.source_trade_date
            AND m.source_snapshot_json->>'for_trade_date' = approved.for_trade_date
            AND m.source_snapshot_json->>'source_run_id' = approved.source_run_id
          UNION ALL
          SELECT 'realtime'::text, NULL::bigint, NULL::integer, 3
          FROM public.user_realtime_monitor_scope rs
          WHERE s.direction = 'buy'
            AND rs.principal_id = (authority->>'principal_id')::bigint
            AND rs.principal_type = authority->>'principal_type'
            AND rs.user_id = (authority->>'user_id')::bigint
            AND rs.asset_kind = 'stock'
            AND rs.identity_key = s.identity_key
            AND rs.status = 'active'
            AND rs.deleted_at IS NULL
            AND rs.source_type = 'single_row'
            AND rs.source_snapshot_json->>'identity_key' = rs.identity_key
        ) candidate
        ORDER BY candidate.scope_priority
        LIMIT 1
      ) scope ON true
      WHERE s.for_trade_date = current_trade_date
    )
    SELECT s.identity_key,
           s.direction,
           CASE
             WHEN s.action_state = 'executed' THEN 'action_price'
             WHEN s.action_state = 'eligible' THEN 'trigger_price'
           END,
           CASE
             WHEN s.action_state = 'executed'
              AND COALESCE(
                    s.card_payload_json->>'action_price',
                    s.display_payload_json->>'action_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      s.card_payload_json->>'action_price',
                      s.display_payload_json->>'action_price'
                    )::numeric
             WHEN s.action_state = 'eligible'
              AND COALESCE(
                    s.card_payload_json->>'trigger_price',
                    s.display_payload_json->>'trigger_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      s.card_payload_json->>'trigger_price',
                      s.display_payload_json->>'trigger_price'
                    )::numeric
           END,
           CASE
             WHEN s.card_target_price IS NOT NULL THEN s.card_target_price
             ELSE s.projection_target_price
           END,
           s.user_signal_projection_id,
           s.virtual_position_id,
           s.holding_episode_no,
           s.for_trade_date,
           s.scope_authority,
           s.score_json
      INTO v_identity_key, v_side, v_reference_kind, v_reference_price,
           v_target_price, v_projection_id, v_position_id, v_episode,
           v_for_trade_date, v_scope_authority, v_score_json
    FROM authorized_source s;

    IF v_projection_id IS NULL
       OR v_identity_key IS NULL
       OR v_side IS NULL
       OR v_for_trade_date IS DISTINCT FROM current_trade_date
       OR v_reference_kind IS NULL
       OR v_reference_price IS NULL
       OR v_reference_price <= 0
       OR v_target_price IS NULL
       OR v_target_price <= 0
       OR v_scope_authority IS NULL
       OR (v_side = 'sell' AND (
             v_scope_authority <> 'open_position'
             OR v_position_id IS NULL
             OR v_episode IS NULL
             OR v_episode <= 0
           )) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'signal_not_in_effective_scope'
      );
    END IF;
  ELSE
    SELECT p.identity_key, 'sell', 'manual', NULL,
           p.virtual_position_id, p.holding_episode_no
      INTO v_identity_key, v_side, v_reference_kind, v_reference_price,
           v_position_id, v_episode
    FROM public.n6_virtual_position p
    WHERE p.virtual_position_id = p_source_id
      AND p.virtual_account_id = account_id
      AND p.principal_id = (authority->>'principal_id')::bigint
      AND p.principal_type = authority->>'principal_type'
      AND p.asset_kind = 'stock'
      AND p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND p.position_status = 'open_virtual'
      AND p.quantity > 0
      AND p.holding_episode_no > 0
      AND EXISTS (
        SELECT 1
        FROM public.n6_virtual_position_lot lot
        WHERE lot.virtual_position_id = p.virtual_position_id
          AND lot.virtual_account_id = p.virtual_account_id
          AND lot.principal_id = p.principal_id
          AND lot.principal_type = p.principal_type
          AND lot.identity_key = p.identity_key
          AND lot.holding_episode_no = p.holding_episode_no
          AND lot.remaining_quantity > 0
          AND lot.available_trade_date <= pg_catalog.to_date(
            current_trade_date, 'YYYYMMDD'
          )
          AND lot.lot_status IN ('locked_t1', 'available')
      );
    IF v_position_id IS NULL OR v_episode IS NULL THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'sellable_position_not_found'
      );
    END IF;
    v_for_trade_date := current_trade_date;
    v_scope_authority := 'manual_position';
  END IF;

  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id, principal_type, user_id, virtual_account_id, source_type, source_id,
    source_signal_projection_id, source_virtual_position_id, holding_episode_no,
    asset_kind, identity_key, proposal_side, signal_reference_kind,
    signal_reference_price, locked_target_price, proposal_status, expires_at,
    policy_version, policy_hash, source_lineage_json
  ) VALUES (
    (authority->>'principal_id')::bigint, authority->>'principal_type',
    (authority->>'user_id')::bigint, account_id, p_source_type, p_source_id::text,
    v_projection_id,
    CASE WHEN p_source_type = 'manual_position' THEN v_position_id ELSE NULL END,
    v_episode, 'stock', v_identity_key, v_side, v_reference_kind,
    v_reference_price, v_target_price, 'pending',
    pg_catalog.now() + interval '60 seconds',
    'n6_virtual_trade_proposal_v2_048',
    '4db44fa6cd1cbfd9cdb7e02c697f1354f7b938dd8262c41149c40ee5a409b2a8',
    pg_catalog.jsonb_build_object(
      'source_type', p_source_type,
      'source_id', p_source_id::text,
      'for_trade_date', v_for_trade_date,
      'scope_authority', v_scope_authority,
      'frozen_virtual_position_id', v_position_id,
      'frozen_holding_episode_no', v_episode,
      'frozen_score', v_score_json
    )
  ) RETURNING * INTO result_row;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'created', 'item',
    pg_catalog.jsonb_build_object(
      'proposal_id', result_row.proposal_id,
      'proposal_status', result_row.proposal_status,
      'expires_at', result_row.expires_at,
      'proposal_side', result_row.proposal_side,
      'identity_key', result_row.identity_key,
      'signal_reference_kind', result_row.signal_reference_kind,
      'signal_reference_price', result_row.signal_reference_price
    )
  );
EXCEPTION WHEN unique_violation THEN
  RETURN pg_catalog.jsonb_build_object(
    'ok', false, 'status', 'conflict', 'error', 'proposal_already_exists'
  );
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_claim_next_proposal(
  p_executor_run_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  row_value public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF p_executor_run_id IS NULL
     OR pg_catalog.btrim(p_executor_run_id) = ''
     OR pg_catalog.length(p_executor_run_id) > 200 THEN
    RETURN NULL;
  END IF;

  WITH claimable AS (
    SELECT p.proposal_id
    FROM public.n6_virtual_trade_proposal p
    WHERE p.proposal_status = 'confirmed'
      AND p.expires_at > pg_catalog.now()
    ORDER BY p.confirmed_at ASC NULLS LAST, p.created_at ASC, p.proposal_id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE public.n6_virtual_trade_proposal p
     SET proposal_status = 'processing',
         executor_run_id = p_executor_run_id,
         updated_at = pg_catalog.now()
    FROM claimable
   WHERE p.proposal_id = claimable.proposal_id
  RETURNING p.* INTO row_value;

  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'no_claimable_proposal'
    );
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'processing',
    'proposal_id', row_value.proposal_id,
    'principal_id', row_value.principal_id,
    'principal_type', row_value.principal_type,
    'virtual_account_id', row_value.virtual_account_id,
    'identity_key', row_value.identity_key,
    'proposal_side', row_value.proposal_side
  );
END
$function$;

REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text) FROM n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_next_proposal(text) TO n6_virtual_executor;

DO $postcheck$
DECLARE
  function_name text;
  function_owner text;
  function_security_definer boolean;
  function_config text[];
  public_execute boolean;
BEGIN
  FOREACH function_name IN ARRAY ARRAY[
    'public.n6_btrack_proposal_create(text,text,bigint)',
    'public.n6_executor_claim_next_proposal(text)'
  ]
  LOOP
    SELECT pg_catalog.pg_get_userbyid(p.proowner),
           p.prosecdef,
           p.proconfig,
           EXISTS (
             SELECT 1
             FROM pg_catalog.aclexplode(
               COALESCE(
                 p.proacl,
                 pg_catalog.acldefault('f', p.proowner)
               )
             ) acl
             WHERE acl.grantee = 0
               AND acl.privilege_type = 'EXECUTE'
           )
      INTO function_owner, function_security_definer, function_config,
           public_execute
    FROM pg_catalog.pg_proc p
    WHERE p.oid = function_name::pg_catalog.regprocedure;
    IF function_owner IS DISTINCT FROM 'ashare_v3_user'
       OR function_security_definer IS DISTINCT FROM true
       OR NOT COALESCE(
         'search_path=pg_catalog' = ANY(function_config),
         false
       ) THEN
      RAISE EXCEPTION
        '048 function authority mismatch: function=% owner=% security_definer=% config=%',
        function_name, function_owner, function_security_definer, function_config;
    END IF;
    IF public_execute THEN
      RAISE EXCEPTION '048 PUBLIC execute privilege rejected: %', function_name;
    END IF;
  END LOOP;

  IF NOT pg_catalog.has_function_privilege(
       'n6_btrack_web',
       'public.n6_btrack_proposal_create(text,text,bigint)',
       'EXECUTE'
     )
     OR pg_catalog.has_function_privilege(
       'n6_virtual_executor',
       'public.n6_btrack_proposal_create(text,text,bigint)',
       'EXECUTE'
     )
     OR pg_catalog.has_function_privilege(
       'n6_btrack_web',
       'public.n6_executor_claim_next_proposal(text)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'n6_virtual_executor',
       'public.n6_executor_claim_next_proposal(text)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'n6_virtual_executor',
       'public.n6_executor_claim_proposal(bigint,text)',
       'EXECUTE'
     ) THEN
    RAISE EXCEPTION '048 Web/Executor function ACL drift';
  END IF;
END
$postcheck$;

COMMIT;
