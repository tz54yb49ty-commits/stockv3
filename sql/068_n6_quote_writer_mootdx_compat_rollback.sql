-- Roll back only N6 migration 068 quote scope compatibility.
-- Preserve all proposal, order, trade, cash, position and quote history.

BEGIN;

DO $preflight$
DECLARE
  scope_oid oid;
  scope_proc record;
BEGIN
  scope_oid := pg_catalog.to_regprocedure(
    'public.n6_quote_writer_scope(timestamptz)'
  );
  IF scope_oid IS NULL THEN
    RAISE EXCEPTION '068_rollback_required_function_missing';
  END IF;
  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proconfig,
         owner.rolname AS owner_name
    INTO scope_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = scope_oid;
  IF scope_proc.owner_name <> current_user
     OR scope_proc.prosecdef IS DISTINCT FROM true
     OR scope_proc.provolatile <> 'v'
     OR scope_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(scope_proc.prosrc, 'UTF8')
          ), 'hex'
        ) <> '856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1'
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
            COALESCE(
              (SELECT p.proacl FROM pg_catalog.pg_proc p WHERE p.oid = scope_oid),
              pg_catalog.acldefault(
                'f',
                (SELECT p.proowner FROM pg_catalog.pg_proc p WHERE p.oid = scope_oid)
              )
            )
          ) acl
          WHERE acl.grantee = 0
            AND acl.privilege_type = 'EXECUTE'
        )
     OR NOT pg_catalog.has_function_privilege(
          'n6_quote_writer', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_btrack_web', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_ai_agent', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_virtual_executor', scope_oid, 'EXECUTE'
        ) THEN
    RAISE EXCEPTION '068_rollback_definition_drift';
  END IF;
END
$preflight$;

CREATE OR REPLACE FUNCTION public.n6_quote_writer_scope(
  p_quote_minute timestamptz
)
RETURNS TABLE (
  principal_id bigint,
  principal_type text,
  virtual_account_id bigint,
  identity_key text
)
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH active_account AS (
    SELECT a.virtual_account_id, a.principal_id, a.principal_type,
           principal.owner_user_id, ai.ai_user_id
    FROM public.n6_virtual_account a
    JOIN public.n6_principal principal
      ON principal.principal_id = a.principal_id
     AND principal.principal_type = a.principal_type
     AND principal.principal_status = 'active'
    LEFT JOIN public.n6_ai_user ai
      ON ai.principal_id = principal.principal_id
     AND ai.principal_type = principal.principal_type
     AND ai.status = 'active'
    WHERE a.virtual_account_status = 'active'
      AND (
        (
          a.principal_type IN ('admin', 'human_user')
          AND principal.owner_user_id IS NOT NULL
          AND ai.ai_user_id IS NULL
        )
        OR (
          a.principal_type = 'ai_user'
          AND principal.owner_user_id IS NULL
          AND ai.ai_user_id IS NOT NULL
        )
      )
  ), candidate AS (
    SELECT a.principal_id, a.principal_type, a.virtual_account_id,
           position.identity_key
    FROM active_account a
    JOIN public.n6_virtual_position position
      ON position.virtual_account_id = a.virtual_account_id
     AND position.principal_id = a.principal_id
     AND position.principal_type = a.principal_type
    WHERE position.asset_kind = 'stock'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
      AND position.identity_key ~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
      AND (
        a.principal_type <> 'ai_user'
        OR position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      )

    UNION

    SELECT a.principal_id, a.principal_type, a.virtual_account_id,
           proposal.identity_key
    FROM active_account a
    JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.virtual_account_id = a.virtual_account_id
     AND proposal.principal_id = a.principal_id
     AND proposal.principal_type = a.principal_type
     AND (
       (
         a.principal_type IN ('admin', 'human_user')
         AND proposal.user_id = a.owner_user_id
         AND proposal.actor_ai_user_id IS NULL
         AND proposal.source_ai_decision_id IS NULL
       )
       OR (
         a.principal_type = 'ai_user'
         AND proposal.user_id IS NULL
         AND proposal.actor_ai_user_id = a.ai_user_id
         AND proposal.source_ai_decision_id IS NOT NULL
       )
     )
    LEFT JOIN public.user_signal_projection source
      ON source.user_signal_projection_id =
           proposal.source_signal_projection_id
     AND a.principal_type IN ('admin', 'human_user')
     AND source.user_id = proposal.user_id
     AND source.asset_kind = proposal.asset_kind
     AND source.identity_key = proposal.identity_key
     AND source.direction = proposal.proposal_side
    LEFT JOIN public.n6_ai_shared_signal_projection ai_source
      ON ai_source.source_signal_projection_id =
           proposal.source_signal_projection_id
     AND a.principal_type = 'ai_user'
     AND ai_source.shared_status = 'active'
     AND ai_source.asset_kind = proposal.asset_kind
     AND ai_source.identity_key = proposal.identity_key
     AND ai_source.direction = proposal.proposal_side
    WHERE proposal.asset_kind = 'stock'
      AND proposal.proposal_side = 'buy'
      AND proposal.source_type = 'signal'
      AND proposal.source_id =
            proposal.source_signal_projection_id::text
      AND proposal.source_virtual_position_id IS NULL
      AND (
        (
          a.principal_type IN ('admin', 'human_user')
          AND source.user_signal_projection_id IS NOT NULL
        )
        OR (
          a.principal_type = 'ai_user'
          AND ai_source.source_signal_projection_id IS NOT NULL
        )
      )
      AND proposal.proposal_status IN ('pending', 'confirmed')
      AND proposal.expires_at > pg_catalog.clock_timestamp()
      AND proposal.identity_key ~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
      AND (
        a.principal_type <> 'ai_user'
        OR proposal.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      )
  )
  SELECT candidate.principal_id, candidate.principal_type,
         candidate.virtual_account_id, candidate.identity_key
  FROM candidate
  WHERE p_quote_minute IS NOT NULL
    AND pg_catalog.date_trunc('minute', p_quote_minute) = p_quote_minute
    AND p_quote_minute = (
      pg_catalog.date_trunc(
        'minute',
        pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
      ) AT TIME ZONE 'Asia/Shanghai'
    )
    AND (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::date =
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
    AND (
      (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
        BETWEEN time '09:30' AND time '11:30'
      OR
      (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
        BETWEEN time '13:00' AND time '15:00'
    )
    AND EXISTS (
      SELECT 1
      FROM public.common_trade_calendar calendar
      WHERE calendar.trade_date = pg_catalog.to_char(
              p_quote_minute AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD'
            )
        AND calendar.is_open = true
    )
$function$;

REVOKE ALL ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  TO n6_quote_writer;

DO $postflight$
DECLARE
  scope_oid oid := 'public.n6_quote_writer_scope(timestamptz)'::regprocedure;
  scope_proc record;
BEGIN
  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proconfig,
         owner.rolname AS owner_name
    INTO scope_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = scope_oid;
  IF scope_proc.owner_name <> current_user
     OR scope_proc.prosecdef IS DISTINCT FROM true
     OR scope_proc.provolatile <> 'v'
     OR scope_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(scope_proc.prosrc, 'UTF8')
          ), 'hex'
        ) <> '205c61bdcabb966203eb022f61666d8c79a090ab6ac12bcf7a0e8bfb9da0fe72'
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
            COALESCE(
              (SELECT p.proacl FROM pg_catalog.pg_proc p WHERE p.oid = scope_oid),
              pg_catalog.acldefault(
                'f',
                (SELECT p.proowner FROM pg_catalog.pg_proc p WHERE p.oid = scope_oid)
              )
            )
          ) acl
          WHERE acl.grantee = 0
            AND acl.privilege_type = 'EXECUTE'
        )
     OR NOT pg_catalog.has_function_privilege(
          'n6_quote_writer', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_btrack_web', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_ai_agent', scope_oid, 'EXECUTE'
        )
     OR pg_catalog.has_function_privilege(
          'n6_virtual_executor', scope_oid, 'EXECUTE'
        ) THEN
    RAISE EXCEPTION '068_rollback_postflight_definition_or_acl_drift';
  END IF;
END
$postflight$;

COMMIT;
