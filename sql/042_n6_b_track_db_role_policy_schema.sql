-- N6 B-track Product V3 principal-scoped database role policy.
-- Roles and credentials are provisioned by a separate runtime-control gate.
-- This migration defines function-only authority; it never creates or alters roles.

BEGIN;

DO $role_preflight$
DECLARE
  role_row record;
  relation_privilege record;
  sequence_privilege record;
BEGIN
  FOR role_row IN
    SELECT required.rolname AS required_role_name,
           actual.oid,
           actual.rolcanlogin,
           actual.rolinherit,
           actual.rolsuper,
           actual.rolcreatedb,
           actual.rolcreaterole,
           actual.rolreplication,
           actual.rolbypassrls
    FROM (VALUES ('n6_btrack_web'::text), ('n6_virtual_executor'::text)) required(rolname)
    LEFT JOIN pg_catalog.pg_roles actual ON actual.rolname = required.rolname
  LOOP
    IF role_row.oid IS NULL THEN
      RAISE EXCEPTION '042 required role missing: %', role_row.required_role_name;
    END IF;
    IF NOT role_row.rolcanlogin
       OR role_row.rolinherit
       OR role_row.rolsuper
       OR role_row.rolcreatedb
       OR role_row.rolcreaterole
       OR role_row.rolreplication
       OR role_row.rolbypassrls THEN
      RAISE EXCEPTION '042 role attributes rejected: %', role_row.required_role_name;
    END IF;

    SELECT n.nspname AS schema_name,
           c.relname AS object_name,
           c.relkind AS object_kind,
           required_privilege.privilege_name
      INTO relation_privilege
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN (
      VALUES
        ('SELECT'::text),
        ('INSERT'::text),
        ('UPDATE'::text),
        ('DELETE'::text),
        ('TRUNCATE'::text),
        ('REFERENCES'::text),
        ('TRIGGER'::text)
    ) required_privilege(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND pg_catalog.has_table_privilege(
            role_row.oid,
            c.oid,
            required_privilege.privilege_name
          )
    ORDER BY c.relname, required_privilege.privilege_name
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION '042 relation privilege rejected: role=% object=%.% kind=% privilege=%',
        role_row.required_role_name,
        relation_privilege.schema_name,
        relation_privilege.object_name,
        relation_privilege.object_kind,
        relation_privilege.privilege_name;
    END IF;

    SELECT n.nspname AS schema_name,
           c.relname AS object_name,
           required_privilege.privilege_name
      INTO sequence_privilege
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN (
      VALUES
        ('USAGE'::text),
        ('SELECT'::text),
        ('UPDATE'::text)
    ) required_privilege(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind = 'S'
      AND pg_catalog.has_sequence_privilege(
            role_row.oid,
            c.oid,
            required_privilege.privilege_name
          )
    ORDER BY c.relname, required_privilege.privilege_name
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION '042 sequence privilege rejected: role=% object=%.% privilege=%',
        role_row.required_role_name,
        sequence_privilege.schema_name,
        sequence_privilege.object_name,
        sequence_privilege.privilege_name;
    END IF;
  END LOOP;
END
$role_preflight$;

CREATE OR REPLACE FUNCTION public.n6_btrack_resolve_authority(p_session_token_hash text)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH valid_session AS (
    SELECT s.user_session_id,
           s.user_id,
           u.display_name,
           u.login_name
    FROM public.user_session s
    JOIN public.user_account u ON u.user_id = s.user_id
    WHERE p_session_token_hash ~ '^[0-9a-f]{64}$'
      AND s.session_token_hash = p_session_token_hash
      AND s.session_token_hash_algo = 'sha256'
      AND s.revoked_at IS NULL
      AND s.expires_at > pg_catalog.clock_timestamp()
      AND u.status = 'active'
  ), scoped AS (
    SELECT s.user_session_id,
           s.user_id,
           p.principal_id,
           p.principal_type,
           p.principal_status,
           COALESCE(p.principal_label, s.display_name, s.login_name) AS display_name,
           count(*) OVER () AS principal_count
    FROM valid_session s
    JOIN public.n6_principal p
      ON p.owner_user_id = s.user_id
     AND p.principal_status = 'active'
     AND p.principal_type IN ('admin', 'human_user')
  )
  SELECT pg_catalog.jsonb_build_object(
           'user_session_id', user_session_id,
           'user_id', user_id,
           'principal_id', principal_id,
           'principal_type', principal_type,
           'principal_status', principal_status,
           'display_name', display_name
         )
  FROM scoped
  WHERE principal_count = 1
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_monitor_list(
  p_session_token_hash text,
  p_asset_kind text DEFAULT NULL,
  p_limit integer DEFAULT 500
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH authority AS (
    SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value
  ), rows AS (
    SELECT m.monitor_id, m.asset_kind, m.identity_key, m.direction, m.source_type,
           m.condition_key, m.status, m.quality_status, m.valid_source_trade_date,
           m.valid_for_trade_date, m.valid_source_run_id, m.created_at, m.updated_at
    FROM public.user_monitor_stock m, authority a
    WHERE a.value IS NOT NULL
      AND m.principal_id = (a.value->>'principal_id')::bigint
      AND m.principal_type = a.value->>'principal_type'
      AND m.user_id = (a.value->>'user_id')::bigint
      AND m.status <> 'removed'
      AND (p_asset_kind IS NULL OR p_asset_kind = 'stock')
    UNION ALL
    SELECT m.monitor_id, m.asset_kind, m.identity_key, m.direction, m.source_type,
           m.condition_key, m.status, m.quality_status, m.valid_source_trade_date,
           m.valid_for_trade_date, m.valid_source_run_id, m.created_at, m.updated_at
    FROM public.user_monitor_index m, authority a
    WHERE a.value IS NOT NULL
      AND m.principal_id = (a.value->>'principal_id')::bigint
      AND m.principal_type = a.value->>'principal_type'
      AND m.user_id = (a.value->>'user_id')::bigint
      AND m.status <> 'removed'
      AND (p_asset_kind IS NULL OR p_asset_kind = 'index')
    UNION ALL
    SELECT m.monitor_id, m.asset_kind, m.identity_key, m.direction, m.source_type,
           m.condition_key, m.status, m.quality_status, m.valid_source_trade_date,
           m.valid_for_trade_date, m.valid_source_run_id, m.created_at, m.updated_at
    FROM public.user_monitor_board m, authority a
    WHERE a.value IS NOT NULL
      AND m.principal_id = (a.value->>'principal_id')::bigint
      AND m.principal_type = a.value->>'principal_type'
      AND m.user_id = (a.value->>'user_id')::bigint
      AND m.status <> 'removed'
      AND (p_asset_kind IS NULL OR p_asset_kind = 'board')
  ), limited AS (
    SELECT * FROM rows
    ORDER BY created_at DESC, monitor_id DESC
    LIMIT LEAST(GREATEST(p_limit, 1), 1000)
  )
  SELECT CASE WHEN (SELECT value FROM authority) IS NULL THEN NULL
         ELSE pg_catalog.jsonb_build_object(
           'tables_ready', true,
           'items', COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
             'monitor_id', monitor_id,
             'asset_kind', asset_kind,
             'identity_key', identity_key,
             'direction', direction,
             'source', source_type,
             'condition_key', condition_key,
             'status', status,
             'quality_status', quality_status,
             'valid_source_trade_date', valid_source_trade_date,
             'valid_for_trade_date', valid_for_trade_date,
             'valid_source_run_id', valid_source_run_id,
             'created_at', created_at,
             'updated_at', updated_at
           ) ORDER BY created_at DESC, monitor_id DESC), '[]'::jsonb)
         ) END
  FROM limited
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_monitor_upsert(
  p_session_token_hash text,
  p_asset_kind text,
  p_identity_key text,
  p_direction text,
  p_for_trade_date text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  expected_trade_date text;
  result_id bigint;
BEGIN
  IF authority IS NULL THEN RETURN NULL; END IF;
  IF p_asset_kind NOT IN ('stock', 'index', 'board')
     OR p_direction NOT IN ('buy', 'sell')
     OR p_identity_key !~ ('^' || p_asset_kind || ':[^:]+:[^:]+$') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;
  IF p_asset_kind = 'stock' AND p_direction <> 'buy' THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_direction');
  END IF;
  IF p_asset_kind = 'stock' THEN
    SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_stock_condition_display_basis;
  ELSIF p_asset_kind = 'index' THEN
    SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_index_condition_display_basis;
  ELSE
    SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_board_condition_display_basis;
  END IF;
  IF expected_trade_date IS NULL OR p_for_trade_date IS DISTINCT FROM expected_trade_date THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'current_for_trade_date_required');
  END IF;

  IF p_asset_kind = 'stock' THEN
    INSERT INTO public.user_monitor_stock (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    ) VALUES (
      (authority->>'principal_id')::bigint, authority->>'principal_type',
      (authority->>'user_id')::bigint, 'stock', p_identity_key, p_direction,
      'single_row', 'active', 'reviewed',
      pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
      p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    ) RETURNING monitor_id INTO result_id;
  ELSIF p_asset_kind = 'index' THEN
    INSERT INTO public.user_monitor_index (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    ) VALUES (
      (authority->>'principal_id')::bigint, authority->>'principal_type',
      (authority->>'user_id')::bigint, 'index', p_identity_key, p_direction,
      'single_row', 'active', 'reviewed',
      pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
      p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    ) RETURNING monitor_id INTO result_id;
  ELSE
    INSERT INTO public.user_monitor_board (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    ) VALUES (
      (authority->>'principal_id')::bigint, authority->>'principal_type',
      (authority->>'user_id')::bigint, 'board', p_identity_key, p_direction,
      'single_row', 'active', 'reviewed',
      pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
      p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    ) RETURNING monitor_id INTO result_id;
  END IF;
  RETURN pg_catalog.jsonb_build_object('ok', true, 'status', 'active', 'item',
    pg_catalog.jsonb_build_object('monitor_id', result_id, 'asset_kind', p_asset_kind,
      'identity_key', p_identity_key, 'direction', p_direction));
EXCEPTION WHEN unique_violation THEN
  RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'conflict');
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_monitor_remove(p_session_token_hash text, p_monitor_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  affected integer := 0;
BEGIN
  IF authority IS NULL OR p_monitor_id <= 0 THEN RETURN NULL; END IF;
  UPDATE public.user_monitor_stock SET status='removed', removed_at=pg_catalog.now(), updated_at=pg_catalog.now()
   WHERE monitor_id=p_monitor_id AND principal_id=(authority->>'principal_id')::bigint
     AND principal_type=authority->>'principal_type' AND user_id=(authority->>'user_id')::bigint AND status<>'removed';
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected = 0 THEN
    UPDATE public.user_monitor_index SET status='removed', removed_at=pg_catalog.now(), updated_at=pg_catalog.now()
     WHERE monitor_id=p_monitor_id AND principal_id=(authority->>'principal_id')::bigint
       AND principal_type=authority->>'principal_type' AND user_id=(authority->>'user_id')::bigint AND status<>'removed';
    GET DIAGNOSTICS affected = ROW_COUNT;
  END IF;
  IF affected = 0 THEN
    UPDATE public.user_monitor_board SET status='removed', removed_at=pg_catalog.now(), updated_at=pg_catalog.now()
     WHERE monitor_id=p_monitor_id AND principal_id=(authority->>'principal_id')::bigint
       AND principal_type=authority->>'principal_type' AND user_id=(authority->>'user_id')::bigint AND status<>'removed';
    GET DIAGNOSTICS affected = ROW_COUNT;
  END IF;
  RETURN pg_catalog.jsonb_build_object('ok', affected=1, 'status', CASE WHEN affected=1 THEN 'removed' ELSE 'not_found' END, 'monitor_id', p_monitor_id);
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_realtime_list(p_session_token_hash text, p_limit integer DEFAULT 500)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH authority AS (SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value),
  rows AS (
    SELECT r.realtime_scope_id, r.asset_kind, r.identity_key, r.display_name,
           r.source_type, r.is_default_seed, r.status, r.created_at, r.updated_at
    FROM public.user_realtime_monitor_scope r, authority a
    WHERE a.value IS NOT NULL
      AND r.principal_id=(a.value->>'principal_id')::bigint
      AND r.principal_type=a.value->>'principal_type'
      AND r.user_id=(a.value->>'user_id')::bigint
      AND r.status='active'
    ORDER BY r.created_at DESC, r.realtime_scope_id DESC
    LIMIT LEAST(GREATEST(p_limit,1),1000)
  )
  SELECT CASE WHEN (SELECT value FROM authority) IS NULL THEN NULL ELSE
    pg_catalog.jsonb_build_object('tables_ready',true,'items',COALESCE(pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object('realtime_scope_id',realtime_scope_id,'asset_kind',asset_kind,
        'identity_key',identity_key,'display_name',display_name,'source',source_type,
        'is_default_seed',is_default_seed,'status',status,'created_at',created_at,'updated_at',updated_at)
      ORDER BY created_at DESC,realtime_scope_id DESC),'[]'::jsonb)) END
  FROM rows
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_realtime_upsert(
  p_session_token_hash text, p_asset_kind text, p_identity_key text, p_for_trade_date text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  expected_trade_date text;
  result_id bigint;
BEGIN
  IF authority IS NULL THEN RETURN NULL; END IF;
  IF p_asset_kind NOT IN ('stock','index','board') OR p_identity_key !~ ('^'||p_asset_kind||':[^:]+:[^:]+$') THEN
    RETURN pg_catalog.jsonb_build_object('ok',false,'status','invalid_request');
  END IF;
  IF p_asset_kind='stock' THEN SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_stock_condition_display_basis;
  ELSIF p_asset_kind='index' THEN SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_index_condition_display_basis;
  ELSE SELECT max(for_trade_date)::text INTO expected_trade_date FROM public.v_n6_board_condition_display_basis; END IF;
  IF expected_trade_date IS NULL OR p_for_trade_date IS DISTINCT FROM expected_trade_date THEN
    RETURN pg_catalog.jsonb_build_object('ok',false,'status','current_for_trade_date_required');
  END IF;
  INSERT INTO public.user_realtime_monitor_scope (
    principal_id,principal_type,user_id,asset_kind,identity_key,source_type,
    source_snapshot_json,is_default_seed,status,deleted_at,created_at,updated_at
  ) VALUES (
    (authority->>'principal_id')::bigint,authority->>'principal_type',(authority->>'user_id')::bigint,
    p_asset_kind,p_identity_key,'single_row',
    pg_catalog.jsonb_build_object('identity_key',p_identity_key,'for_trade_date',p_for_trade_date),
    false,'active',NULL,pg_catalog.now(),pg_catalog.now()
  ) ON CONFLICT (principal_id,principal_type,user_id,asset_kind,identity_key)
    DO UPDATE SET status='active',deleted_at=NULL,source_type='single_row',
      source_snapshot_json=EXCLUDED.source_snapshot_json,updated_at=pg_catalog.now()
  RETURNING realtime_scope_id INTO result_id;
  RETURN pg_catalog.jsonb_build_object('ok',true,'status','active','item',
    pg_catalog.jsonb_build_object('realtime_scope_id',result_id,'asset_kind',p_asset_kind,'identity_key',p_identity_key));
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_realtime_remove(p_session_token_hash text, p_realtime_scope_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash); affected integer;
BEGIN
  IF authority IS NULL OR p_realtime_scope_id <= 0 THEN RETURN NULL; END IF;
  UPDATE public.user_realtime_monitor_scope SET status='deleted',deleted_at=pg_catalog.now(),updated_at=pg_catalog.now()
   WHERE realtime_scope_id=p_realtime_scope_id AND principal_id=(authority->>'principal_id')::bigint
     AND principal_type=authority->>'principal_type' AND user_id=(authority->>'user_id')::bigint AND status='active';
  GET DIAGNOSTICS affected = ROW_COUNT;
  RETURN pg_catalog.jsonb_build_object('ok',affected=1,'status',CASE WHEN affected=1 THEN 'deleted' ELSE 'not_found' END,
    'realtime_scope_id',p_realtime_scope_id);
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_list(p_session_token_hash text, p_limit integer DEFAULT 100)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH authority AS (SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value), rows AS (
    SELECT p.proposal_id,p.source_type,p.source_id,p.source_signal_projection_id,p.source_virtual_position_id,
           p.holding_episode_no,p.asset_kind,p.identity_key,p.proposal_side,p.signal_reference_kind,
           p.signal_reference_price,p.proposal_status,p.expires_at,p.confirmed_at,
           p.executed_virtual_order_id,p.executed_virtual_trade_id,p.failure_reason,p.created_at,p.updated_at
    FROM public.n6_virtual_trade_proposal p,authority a
    WHERE a.value IS NOT NULL AND p.principal_id=(a.value->>'principal_id')::bigint
      AND p.principal_type=a.value->>'principal_type' AND p.user_id=(a.value->>'user_id')::bigint
    ORDER BY p.created_at DESC,p.proposal_id DESC LIMIT LEAST(GREATEST(p_limit,1),500)
  ) SELECT CASE WHEN (SELECT value FROM authority) IS NULL THEN NULL ELSE
    pg_catalog.jsonb_build_object('tables_ready',true,'items',COALESCE(pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object('proposal_id',proposal_id,'source_type',source_type,'source_id',source_id,
        'source_signal_projection_id',source_signal_projection_id,'source_virtual_position_id',source_virtual_position_id,
        'holding_episode_no',holding_episode_no,'asset_kind',asset_kind,'identity_key',identity_key,
        'proposal_side',proposal_side,'signal_reference_kind',signal_reference_kind,
        'signal_reference_price',signal_reference_price,'proposal_status',proposal_status,'expires_at',expires_at,
        'confirmed_at',confirmed_at,'executed_virtual_order_id',executed_virtual_order_id,
        'executed_virtual_trade_id',executed_virtual_trade_id,'failure_reason',failure_reason,
        'created_at',created_at,'updated_at',updated_at) ORDER BY created_at DESC,proposal_id DESC),'[]'::jsonb)) END FROM rows
$function$;

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
  account_id bigint; account_count integer;
  v_identity_key text; v_side text; v_reference_kind text; v_reference_price numeric(24,8);
  v_target_price numeric(24,8); v_position_id bigint; v_projection_id bigint; v_episode integer;
  result_row public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF authority IS NULL OR p_source_id <= 0 OR p_source_type NOT IN ('signal','manual_position') THEN RETURN NULL; END IF;
  SELECT min(a.virtual_account_id),count(*) INTO account_id,account_count
  FROM public.n6_virtual_account a
  WHERE a.principal_id=(authority->>'principal_id')::bigint AND a.principal_type=authority->>'principal_type'
    AND a.virtual_account_status='active';
  IF account_count<>1 THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_ready','error','exactly_one_active_virtual_account_required'); END IF;
  IF p_source_type='signal' THEN
    SELECT p.identity_key,p.direction,
           CASE WHEN COALESCE(c.card_payload_json->>'action_state',p.display_payload_json->>'action_state')='executed' THEN 'action_price'
                WHEN COALESCE(c.card_payload_json->>'action_state',p.display_payload_json->>'action_state')='eligible' THEN 'trigger_price' END,
           CASE WHEN COALESCE(c.card_payload_json->>'action_state',p.display_payload_json->>'action_state')='executed'
                  AND COALESCE(c.card_payload_json->>'action_price',p.display_payload_json->>'action_price') ~ '^[0-9]+([.][0-9]+)?$'
                THEN COALESCE(c.card_payload_json->>'action_price',p.display_payload_json->>'action_price')::numeric
                WHEN COALESCE(c.card_payload_json->>'action_state',p.display_payload_json->>'action_state')='eligible'
                  AND COALESCE(c.card_payload_json->>'trigger_price',p.display_payload_json->>'trigger_price') ~ '^[0-9]+([.][0-9]+)?$'
                THEN COALESCE(c.card_payload_json->>'trigger_price',p.display_payload_json->>'trigger_price')::numeric END,
           COALESCE(c.target_price,p.target_price),p.user_signal_projection_id
      INTO v_identity_key,v_side,v_reference_kind,v_reference_price,v_target_price,v_projection_id
    FROM public.user_signal_projection p
    JOIN public.user_projection_run r ON r.user_projection_run_id=p.user_projection_run_id AND r.status IN ('passed','ready')
    LEFT JOIN LATERAL (
      SELECT card_payload_json,target_price FROM public.user_signal_card c0
      WHERE c0.user_signal_projection_id=p.user_signal_projection_id AND c0.user_id=p.user_id
      ORDER BY c0.user_signal_card_id DESC LIMIT 1
    ) c ON true
    WHERE p.user_signal_projection_id=p_source_id AND p.user_id=(authority->>'user_id')::bigint
      AND p.asset_kind='stock' AND p.projection_status IN ('visible','blocked')
      AND EXISTS (SELECT 1 FROM public.user_monitor_stock m WHERE m.principal_id=(authority->>'principal_id')::bigint
        AND m.principal_type=authority->>'principal_type' AND m.user_id=(authority->>'user_id')::bigint
        AND m.identity_key=p.identity_key AND m.direction=p.direction AND m.status='active');
    IF v_projection_id IS NULL OR v_reference_kind IS NULL OR v_reference_price IS NULL OR v_reference_price<=0 THEN
      RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_found','error','signal_not_in_effective_scope');
    END IF;
  ELSE
    SELECT p.identity_key,'sell','manual',NULL,p.virtual_position_id,p.holding_episode_no
      INTO v_identity_key,v_side,v_reference_kind,v_reference_price,v_position_id,v_episode
    FROM public.n6_virtual_position p
    WHERE p.virtual_position_id=p_source_id AND p.virtual_account_id=account_id
      AND p.principal_id=(authority->>'principal_id')::bigint AND p.principal_type=authority->>'principal_type'
      AND p.asset_kind='stock' AND p.position_status='open_virtual' AND p.available_quantity>0;
    IF v_position_id IS NULL THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_found','error','sellable_position_not_found'); END IF;
  END IF;
  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id,principal_type,user_id,virtual_account_id,source_type,source_id,
    source_signal_projection_id,source_virtual_position_id,holding_episode_no,asset_kind,identity_key,
    proposal_side,signal_reference_kind,signal_reference_price,locked_target_price,proposal_status,
    expires_at,policy_version,policy_hash,source_lineage_json
  ) VALUES (
    (authority->>'principal_id')::bigint,authority->>'principal_type',(authority->>'user_id')::bigint,account_id,
    p_source_type,p_source_id::text,v_projection_id,v_position_id,v_episode,'stock',v_identity_key,v_side,
    v_reference_kind,v_reference_price,v_target_price,'pending',pg_catalog.now()+interval '60 seconds',
    'n6_virtual_trade_proposal_v1','60328cf48d00a451d0ca6cf5a511c740a20cfb4c7e5b08c55a30d23353f4fce1',
    pg_catalog.jsonb_build_object('source_type',p_source_type,'source_id',p_source_id::text)
  ) RETURNING * INTO result_row;
  RETURN pg_catalog.jsonb_build_object('ok',true,'status','created','item',pg_catalog.jsonb_build_object(
    'proposal_id',result_row.proposal_id,'proposal_status',result_row.proposal_status,'expires_at',result_row.expires_at,
    'proposal_side',result_row.proposal_side,'identity_key',result_row.identity_key,
    'signal_reference_kind',result_row.signal_reference_kind,'signal_reference_price',result_row.signal_reference_price));
EXCEPTION WHEN unique_violation THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','conflict','error','proposal_already_exists');
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_confirm(
  p_session_token_hash text,p_proposal_id bigint,p_idempotency_key text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE authority jsonb:=public.n6_btrack_resolve_authority(p_session_token_hash); row_value public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF authority IS NULL OR p_proposal_id<=0 OR p_idempotency_key !~ '^[A-Za-z0-9._:-]{8,128}$' THEN RETURN NULL; END IF;
  SELECT * INTO row_value FROM public.n6_virtual_trade_proposal
   WHERE proposal_id=p_proposal_id AND principal_id=(authority->>'principal_id')::bigint
     AND principal_type=authority->>'principal_type' AND user_id=(authority->>'user_id')::bigint FOR UPDATE;
  IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_found','error','proposal_not_found'); END IF;
  IF row_value.proposal_status='confirmed' AND row_value.confirm_idempotency_key=p_idempotency_key THEN
    RETURN pg_catalog.jsonb_build_object('ok',true,'status','confirmed','proposal_id',p_proposal_id,'idempotent',true);
  END IF;
  IF row_value.proposal_status<>'pending' THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','conflict','error','proposal_not_pending'); END IF;
  IF row_value.expires_at<=pg_catalog.now() THEN
    UPDATE public.n6_virtual_trade_proposal SET proposal_status='expired',updated_at=pg_catalog.now() WHERE proposal_id=p_proposal_id;
    RETURN pg_catalog.jsonb_build_object('ok',false,'status','expired','error','proposal_expired');
  END IF;
  UPDATE public.n6_virtual_trade_proposal SET proposal_status='confirmed',confirmed_at=pg_catalog.now(),
    confirm_idempotency_key=p_idempotency_key,updated_at=pg_catalog.now() WHERE proposal_id=p_proposal_id RETURNING * INTO row_value;
  RETURN pg_catalog.jsonb_build_object('ok',true,'status','confirmed','idempotent',false,'item',
    pg_catalog.jsonb_build_object('proposal_id',row_value.proposal_id,'proposal_status',row_value.proposal_status,
      'confirmed_at',row_value.confirmed_at,'expires_at',row_value.expires_at));
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_virtual_trade_list(p_session_token_hash text,p_limit integer DEFAULT 200)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $function$
  WITH authority AS (SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value), rows AS (
    SELECT t.virtual_trade_id,t.virtual_order_id,t.virtual_account_id,t.identity_key,t.trade_side,t.filled_quantity,
      t.filled_price,t.gross_amount,t.total_fee_amount,t.net_amount,t.trade_status,t.trade_time,t.source_proposal_id,
      t.signal_reference_kind,t.signal_reference_price,t.fill_quote_snapshot_id
    FROM public.n6_virtual_trade t,authority a WHERE a.value IS NOT NULL
      AND t.principal_id=(a.value->>'principal_id')::bigint AND t.principal_type=a.value->>'principal_type'
    ORDER BY t.trade_time DESC,t.virtual_trade_id DESC LIMIT LEAST(GREATEST(p_limit,1),500)
  ) SELECT CASE WHEN (SELECT value FROM authority) IS NULL THEN NULL ELSE pg_catalog.jsonb_build_object(
    'tables_ready',true,'items',COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
      'virtual_trade_id',virtual_trade_id,'virtual_order_id',virtual_order_id,'virtual_account_id',virtual_account_id,
      'identity_key',identity_key,'trade_side',trade_side,'filled_quantity',filled_quantity,'filled_price',filled_price,
      'gross_amount',gross_amount,'total_fee_amount',total_fee_amount,'net_amount',net_amount,'trade_status',trade_status,
      'trade_time',trade_time,'source_proposal_id',source_proposal_id,'signal_reference_kind',signal_reference_kind,
      'signal_reference_price',signal_reference_price,'fill_quote_snapshot_id',fill_quote_snapshot_id)
      ORDER BY trade_time DESC,virtual_trade_id DESC),'[]'::jsonb)) END FROM rows
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_claim_proposal(p_proposal_id bigint,p_executor_run_id text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $function$
DECLARE row_value public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF p_proposal_id<=0 OR p_executor_run_id IS NULL OR length(p_executor_run_id)>200 THEN RETURN NULL; END IF;
  UPDATE public.n6_virtual_trade_proposal SET proposal_status='processing',executor_run_id=p_executor_run_id,updated_at=pg_catalog.now()
   WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND expires_at>pg_catalog.now() RETURNING * INTO row_value;
  IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok',false,'status','not_claimed'); END IF;
  RETURN pg_catalog.jsonb_build_object('ok',true,'status','processing','proposal_id',row_value.proposal_id,
    'principal_id',row_value.principal_id,'principal_type',row_value.principal_type,'virtual_account_id',row_value.virtual_account_id,
    'identity_key',row_value.identity_key,'proposal_side',row_value.proposal_side);
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_finish_proposal(
  p_proposal_id bigint,p_executor_run_id text,p_final_status text,p_virtual_order_id bigint DEFAULT NULL,
  p_virtual_trade_id bigint DEFAULT NULL,p_failure_reason text DEFAULT NULL
)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $function$
DECLARE affected integer;
BEGIN
  IF p_final_status NOT IN ('executed','failed') THEN RETURN NULL; END IF;
  IF p_final_status='executed' AND (p_virtual_order_id IS NULL OR p_virtual_trade_id IS NULL) THEN RETURN NULL; END IF;
  IF p_final_status='failed' AND (p_failure_reason IS NULL OR btrim(p_failure_reason)='') THEN RETURN NULL; END IF;
  UPDATE public.n6_virtual_trade_proposal SET proposal_status=p_final_status,executed_virtual_order_id=p_virtual_order_id,
    executed_virtual_trade_id=p_virtual_trade_id,failure_reason=CASE WHEN p_final_status='failed' THEN left(p_failure_reason,500) ELSE NULL END,
    updated_at=pg_catalog.now() WHERE proposal_id=p_proposal_id AND proposal_status='processing' AND executor_run_id=p_executor_run_id;
  GET DIAGNOSTICS affected=ROW_COUNT;
  RETURN pg_catalog.jsonb_build_object('ok',affected=1,'status',CASE WHEN affected=1 THEN p_final_status ELSE 'not_finished' END,'proposal_id',p_proposal_id);
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_transition_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $function$
BEGIN
  IF TG_OP='INSERT' AND SESSION_USER='n6_btrack_web' AND NEW.proposal_status<>'pending' THEN
    RAISE EXCEPTION 'web proposal insert must be pending';
  ELSIF TG_OP='INSERT' AND SESSION_USER='n6_virtual_executor' THEN
    RAISE EXCEPTION 'executor cannot create proposal';
  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF NOT (OLD.proposal_status='pending' AND NEW.proposal_status IN ('confirmed','expired')) THEN
      RAISE EXCEPTION 'web proposal transition rejected: % -> %',OLD.proposal_status,NEW.proposal_status;
    END IF;
    IF NEW.executed_virtual_order_id IS DISTINCT FROM OLD.executed_virtual_order_id
       OR NEW.executed_virtual_trade_id IS DISTINCT FROM OLD.executed_virtual_trade_id
       OR NEW.executor_run_id IS DISTINCT FROM OLD.executor_run_id
       OR NEW.failure_reason IS DISTINCT FROM OLD.failure_reason THEN
      RAISE EXCEPTION 'web executor fields rejected';
    END IF;
  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_virtual_executor' THEN
    IF NOT ((OLD.proposal_status='confirmed' AND NEW.proposal_status='processing')
         OR (OLD.proposal_status='processing' AND NEW.proposal_status IN ('executed','failed'))) THEN
      RAISE EXCEPTION 'executor proposal transition rejected: % -> %',OLD.proposal_status,NEW.proposal_status;
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS n6_btrack_proposal_transition_guard ON public.n6_virtual_trade_proposal;
CREATE TRIGGER n6_btrack_proposal_transition_guard
BEFORE INSERT OR UPDATE ON public.n6_virtual_trade_proposal
FOR EACH ROW EXECUTE FUNCTION public.n6_btrack_proposal_transition_guard();

REVOKE EXECUTE ON FUNCTION public.n6_btrack_resolve_authority(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_list(text,text,integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_upsert(text,text,text,text,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_remove(text,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_list(text,integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_upsert(text,text,text,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_remove(text,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_list(text,integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_confirm(text,bigint,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_virtual_trade_list(text,integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_executor_finish_proposal(bigint,text,text,bigint,bigint,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_transition_guard() FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO n6_btrack_web, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_resolve_authority(text) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_monitor_list(text,text,integer) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_monitor_upsert(text,text,text,text,text) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_monitor_remove(text,bigint) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_realtime_list(text,integer) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_realtime_upsert(text,text,text,text) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_realtime_remove(text,bigint) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_list(text,integer) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_confirm(text,bigint,text) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_virtual_trade_list(text,integer) TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) TO n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_executor_finish_proposal(bigint,text,text,bigint,bigint,text) TO n6_virtual_executor;

COMMIT;
