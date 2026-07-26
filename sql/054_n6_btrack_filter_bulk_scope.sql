-- N6 B-track filter-result bulk scope operations.
-- Additive only: three function-only entrypoints for n6_btrack_web.

BEGIN;

DO $block$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_btrack_web') THEN
    RAISE EXCEPTION 'required role n6_btrack_web is missing';
  END IF;
END
$block$;

CREATE OR REPLACE FUNCTION public.n6_btrack_scope_bulk_preview(
  p_session_token_hash text,
  p_target_scope text,
  p_asset_kind text,
  p_identity_keys text[],
  p_for_trade_date text,
  p_source_run_id text,
  p_selection_sha256 text
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  input_count integer := pg_catalog.cardinality(p_identity_keys);
  approved_count integer := 0;
  v_source_trade_date text;
  v_source_run_id text;
  lineage_count integer := 0;
  direction_row_count integer := 0;
  write_row_count integer := 0;
  already_active_count integer := 0;
  reactivated_count integer := 0;
  will_add_count integer := 0;
BEGIN
  IF authority IS NULL THEN RETURN NULL; END IF;
  IF p_target_scope NOT IN ('monitor', 'realtime')
     OR p_asset_kind NOT IN ('stock', 'index', 'board')
     OR input_count IS NULL OR input_count < 1 OR input_count > 10000
     OR p_for_trade_date !~ '^[0-9]{8}$'
     OR pg_catalog.length(pg_catalog.btrim(p_source_run_id)) < 1
     OR p_selection_sha256 !~ '^[0-9a-f]{64}$'
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
       WHERE input.identity_key !~ ('^' || p_asset_kind || ':[^:]+:[^:]+$')
     )
     OR (
       SELECT pg_catalog.count(DISTINCT input.identity_key)
       FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
     ) <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;

  IF p_asset_kind = 'stock' THEN
    SELECT pg_catalog.min(source_trade_date::text),
           pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_stock_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_stock_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT approved.identity_key)
      INTO approved_count
    FROM public.v_n6_stock_condition_display_basis approved
    WHERE approved.for_trade_date::text = p_for_trade_date
      AND approved.source_trade_date::text = v_source_trade_date
      AND approved.run_id::text = v_source_run_id
      AND approved.identity_key = ANY(p_identity_keys);
  ELSIF p_asset_kind = 'index' THEN
    SELECT pg_catalog.min(source_trade_date::text),
           pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_index_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_index_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT approved.identity_key)
      INTO approved_count
    FROM public.v_n6_index_condition_display_basis approved
    WHERE approved.for_trade_date::text = p_for_trade_date
      AND approved.source_trade_date::text = v_source_trade_date
      AND approved.run_id::text = v_source_run_id
      AND approved.identity_key = ANY(p_identity_keys);
  ELSE
    SELECT pg_catalog.min(source_trade_date::text),
           pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_board_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_board_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT approved.identity_key)
      INTO approved_count
    FROM public.v_n6_board_condition_display_basis approved
    WHERE approved.for_trade_date::text = p_for_trade_date
      AND approved.source_trade_date::text = v_source_trade_date
      AND approved.run_id::text = v_source_run_id
      AND approved.identity_key = ANY(p_identity_keys);
  END IF;

  IF lineage_count <> 1 OR v_source_trade_date IS NULL OR v_source_run_id IS NULL
     OR v_source_run_id <> p_source_run_id
     OR approved_count <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'filter_snapshot_stale');
  END IF;

  direction_row_count := input_count * CASE WHEN p_asset_kind = 'stock' THEN 1 ELSE 2 END;
  IF p_target_scope = 'monitor' THEN
    write_row_count := direction_row_count;
    IF p_asset_kind = 'stock' THEN
      SELECT pg_catalog.count(*) INTO already_active_count
      FROM public.user_monitor_stock monitor
      WHERE monitor.principal_id = (authority->>'principal_id')::bigint
        AND monitor.principal_type = authority->>'principal_type'
        AND monitor.user_id = (authority->>'user_id')::bigint
        AND monitor.identity_key = ANY(p_identity_keys)
        AND monitor.direction = 'buy'
        AND monitor.status <> 'removed'
        AND monitor.valid_source_trade_date = v_source_trade_date
        AND monitor.valid_for_trade_date = p_for_trade_date
        AND monitor.valid_source_run_id = v_source_run_id;
    ELSIF p_asset_kind = 'index' THEN
      SELECT pg_catalog.count(*) INTO already_active_count
      FROM public.user_monitor_index monitor
      WHERE monitor.principal_id = (authority->>'principal_id')::bigint
        AND monitor.principal_type = authority->>'principal_type'
        AND monitor.user_id = (authority->>'user_id')::bigint
        AND monitor.identity_key = ANY(p_identity_keys)
        AND monitor.direction IN ('buy', 'sell')
        AND monitor.status <> 'removed'
        AND monitor.valid_source_trade_date = v_source_trade_date
        AND monitor.valid_for_trade_date = p_for_trade_date
        AND monitor.valid_source_run_id = v_source_run_id;
    ELSE
      SELECT pg_catalog.count(*) INTO already_active_count
      FROM public.user_monitor_board monitor
      WHERE monitor.principal_id = (authority->>'principal_id')::bigint
        AND monitor.principal_type = authority->>'principal_type'
        AND monitor.user_id = (authority->>'user_id')::bigint
        AND monitor.identity_key = ANY(p_identity_keys)
        AND monitor.direction IN ('buy', 'sell')
        AND monitor.status <> 'removed'
        AND monitor.valid_source_trade_date = v_source_trade_date
        AND monitor.valid_for_trade_date = p_for_trade_date
        AND monitor.valid_source_run_id = v_source_run_id;
    END IF;
    will_add_count := write_row_count - already_active_count;
  ELSE
    write_row_count := input_count;
    SELECT pg_catalog.count(*) FILTER (WHERE scope.status = 'active'),
           pg_catalog.count(*) FILTER (WHERE scope.status = 'deleted')
      INTO already_active_count, reactivated_count
    FROM public.user_realtime_monitor_scope scope
    WHERE scope.principal_id = (authority->>'principal_id')::bigint
      AND scope.principal_type = authority->>'principal_type'
      AND scope.user_id = (authority->>'user_id')::bigint
      AND scope.asset_kind = p_asset_kind
      AND scope.identity_key = ANY(p_identity_keys);
    will_add_count := write_row_count - already_active_count - reactivated_count;
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'preview',
    'target_scope', p_target_scope,
    'asset_kind', p_asset_kind,
    'for_trade_date', p_for_trade_date,
    'source_trade_date', v_source_trade_date,
    'source_run_id', v_source_run_id,
    'selection_sha256', p_selection_sha256,
    'matched_count', input_count,
    'direction_row_count', direction_row_count,
    'write_row_count', write_row_count,
    'already_active_count', already_active_count,
    'reactivated_count', reactivated_count,
    'will_add_count', will_add_count
  );
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_monitor_bulk_upsert(
  p_session_token_hash text,
  p_asset_kind text,
  p_identity_keys text[],
  p_for_trade_date text,
  p_source_run_id text,
  p_selection_sha256 text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  input_count integer := pg_catalog.cardinality(p_identity_keys);
  approved_count integer := 0;
  v_source_trade_date text;
  v_source_run_id text;
  lineage_count integer := 0;
  inserted_count integer := 0;
  direction_row_count integer := 0;
BEGIN
  IF authority IS NULL THEN RETURN NULL; END IF;
  IF p_asset_kind NOT IN ('stock', 'index', 'board')
     OR input_count IS NULL OR input_count < 1 OR input_count > 10000
     OR p_for_trade_date !~ '^[0-9]{8}$'
     OR pg_catalog.length(pg_catalog.btrim(p_source_run_id)) < 1
     OR p_selection_sha256 !~ '^[0-9a-f]{64}$'
     OR EXISTS (
       SELECT 1 FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
       WHERE input.identity_key !~ ('^' || p_asset_kind || ':[^:]+:[^:]+$')
     )
     OR (
       SELECT pg_catalog.count(DISTINCT input.identity_key)
       FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
     ) <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;

  IF p_asset_kind = 'stock' THEN
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_stock_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_stock_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_stock_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  ELSIF p_asset_kind = 'index' THEN
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_index_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_index_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_index_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  ELSE
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_board_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_board_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_board_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  END IF;

  IF lineage_count <> 1 OR v_source_trade_date IS NULL OR v_source_run_id IS NULL
     OR v_source_run_id <> p_source_run_id
     OR approved_count <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'filter_snapshot_stale');
  END IF;

  direction_row_count := input_count * CASE WHEN p_asset_kind = 'stock' THEN 1 ELSE 2 END;
  IF p_asset_kind = 'stock' THEN
    INSERT INTO public.user_monitor_stock (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'stock', input.identity_key, 'buy',
           'filtered_result_bulk', v_source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', input.identity_key, 'source_trade_date', v_source_trade_date,
             'for_trade_date', p_for_trade_date, 'source_run_id', v_source_run_id,
             'selection_sha256', p_selection_sha256, 'selection_count', input_count
           ),
           v_source_trade_date, p_for_trade_date, v_source_run_id,
           pg_catalog.now(), pg_catalog.now()
    FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
    ON CONFLICT DO NOTHING;
  ELSIF p_asset_kind = 'index' THEN
    INSERT INTO public.user_monitor_index (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'index', input.identity_key, direction.value,
           'filtered_result_bulk', v_source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', input.identity_key, 'source_trade_date', v_source_trade_date,
             'for_trade_date', p_for_trade_date, 'source_run_id', v_source_run_id,
             'selection_sha256', p_selection_sha256, 'selection_count', input_count
           ),
           v_source_trade_date, p_for_trade_date, v_source_run_id,
           pg_catalog.now(), pg_catalog.now()
    FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
    CROSS JOIN (VALUES ('buy'), ('sell')) AS direction(value)
    ON CONFLICT DO NOTHING;
  ELSE
    INSERT INTO public.user_monitor_board (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'board', input.identity_key, direction.value,
           'filtered_result_bulk', v_source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', input.identity_key, 'source_trade_date', v_source_trade_date,
             'for_trade_date', p_for_trade_date, 'source_run_id', v_source_run_id,
             'selection_sha256', p_selection_sha256, 'selection_count', input_count
           ),
           v_source_trade_date, p_for_trade_date, v_source_run_id,
           pg_catalog.now(), pg_catalog.now()
    FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
    CROSS JOIN (VALUES ('buy'), ('sell')) AS direction(value)
    ON CONFLICT DO NOTHING;
  END IF;
  GET DIAGNOSTICS inserted_count = ROW_COUNT;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'active', 'target_scope', 'monitor',
    'asset_kind', p_asset_kind, 'for_trade_date', p_for_trade_date,
    'source_trade_date', v_source_trade_date, 'source_run_id', v_source_run_id,
    'selection_sha256', p_selection_sha256, 'matched_count', input_count,
    'direction_row_count', direction_row_count, 'write_row_count', direction_row_count,
    'added_count', inserted_count,
    'already_active_count', direction_row_count - inserted_count,
    'reactivated_count', 0
  );
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_realtime_bulk_upsert(
  p_session_token_hash text,
  p_asset_kind text,
  p_identity_keys text[],
  p_for_trade_date text,
  p_source_run_id text,
  p_selection_sha256 text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  input_count integer := pg_catalog.cardinality(p_identity_keys);
  approved_count integer := 0;
  v_source_trade_date text;
  v_source_run_id text;
  lineage_count integer := 0;
  already_active_count integer := 0;
  reactivated_count integer := 0;
  will_add_count integer := 0;
  affected_count integer := 0;
  direction_row_count integer := 0;
BEGIN
  IF authority IS NULL THEN RETURN NULL; END IF;
  IF p_asset_kind NOT IN ('stock', 'index', 'board')
     OR input_count IS NULL OR input_count < 1 OR input_count > 10000
     OR p_for_trade_date !~ '^[0-9]{8}$'
     OR pg_catalog.length(pg_catalog.btrim(p_source_run_id)) < 1
     OR p_selection_sha256 !~ '^[0-9a-f]{64}$'
     OR EXISTS (
       SELECT 1 FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
       WHERE input.identity_key !~ ('^' || p_asset_kind || ':[^:]+:[^:]+$')
     )
     OR (
       SELECT pg_catalog.count(DISTINCT input.identity_key)
       FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
     ) <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;

  IF p_asset_kind = 'stock' THEN
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_stock_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_stock_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_stock_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  ELSIF p_asset_kind = 'index' THEN
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_index_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_index_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_index_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  ELSE
    SELECT pg_catalog.min(source_trade_date::text), pg_catalog.min(run_id::text),
           pg_catalog.count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text))
      INTO v_source_trade_date, v_source_run_id, lineage_count
    FROM public.v_n6_board_condition_display_basis
    WHERE for_trade_date = (SELECT pg_catalog.max(for_trade_date) FROM public.v_n6_board_condition_display_basis)
      AND for_trade_date::text = p_for_trade_date;
    SELECT pg_catalog.count(DISTINCT identity_key) INTO approved_count
    FROM public.v_n6_board_condition_display_basis
    WHERE for_trade_date::text = p_for_trade_date
      AND source_trade_date::text = v_source_trade_date
      AND run_id::text = v_source_run_id
      AND identity_key = ANY(p_identity_keys);
  END IF;

  IF lineage_count <> 1 OR v_source_trade_date IS NULL OR v_source_run_id IS NULL
     OR v_source_run_id <> p_source_run_id
     OR approved_count <> input_count THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'filter_snapshot_stale');
  END IF;

  SELECT pg_catalog.count(*) FILTER (WHERE scope.status = 'active'),
         pg_catalog.count(*) FILTER (WHERE scope.status = 'deleted')
    INTO already_active_count, reactivated_count
  FROM public.user_realtime_monitor_scope scope
  WHERE scope.principal_id = (authority->>'principal_id')::bigint
    AND scope.principal_type = authority->>'principal_type'
    AND scope.user_id = (authority->>'user_id')::bigint
    AND scope.asset_kind = p_asset_kind
    AND scope.identity_key = ANY(p_identity_keys);
  will_add_count := input_count - already_active_count - reactivated_count;
  direction_row_count := input_count * CASE WHEN p_asset_kind = 'stock' THEN 1 ELSE 2 END;

  INSERT INTO public.user_realtime_monitor_scope (
    principal_id, principal_type, user_id, asset_kind, identity_key, source_type,
    source_snapshot_json, is_default_seed, status, deleted_at, created_at, updated_at
  )
  SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
         (authority->>'user_id')::bigint, p_asset_kind, input.identity_key,
         'filtered_result_bulk',
         pg_catalog.jsonb_build_object(
           'identity_key', input.identity_key, 'source_trade_date', v_source_trade_date,
           'for_trade_date', p_for_trade_date, 'source_run_id', v_source_run_id,
           'selection_sha256', p_selection_sha256, 'selection_count', input_count
         ),
         false, 'active', NULL, pg_catalog.now(), pg_catalog.now()
  FROM pg_catalog.unnest(p_identity_keys) AS input(identity_key)
  ON CONFLICT (principal_id, principal_type, user_id, asset_kind, identity_key)
    DO UPDATE SET status = 'active', deleted_at = NULL,
      source_type = 'filtered_result_bulk',
      source_snapshot_json = EXCLUDED.source_snapshot_json,
      updated_at = pg_catalog.now()
    WHERE public.user_realtime_monitor_scope.status = 'deleted';
  GET DIAGNOSTICS affected_count = ROW_COUNT;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'active', 'target_scope', 'realtime',
    'asset_kind', p_asset_kind, 'for_trade_date', p_for_trade_date,
    'source_trade_date', v_source_trade_date, 'source_run_id', v_source_run_id,
    'selection_sha256', p_selection_sha256, 'matched_count', input_count,
    'direction_row_count', direction_row_count, 'write_row_count', input_count,
    'added_count', will_add_count, 'already_active_count', already_active_count,
    'reactivated_count', reactivated_count, 'affected_count', affected_count
  );
END
$function$;

ALTER FUNCTION public.n6_btrack_scope_bulk_preview(text,text,text,text[],text,text,text)
  OWNER TO ashare_v3_user;
ALTER FUNCTION public.n6_btrack_monitor_bulk_upsert(text,text,text[],text,text,text)
  OWNER TO ashare_v3_user;
ALTER FUNCTION public.n6_btrack_realtime_bulk_upsert(text,text,text[],text,text,text)
  OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION public.n6_btrack_scope_bulk_preview(text,text,text,text[],text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_btrack_monitor_bulk_upsert(text,text,text[],text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_btrack_realtime_bulk_upsert(text,text,text[],text,text,text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.n6_btrack_scope_bulk_preview(text,text,text,text[],text,text,text)
  TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_monitor_bulk_upsert(text,text,text[],text,text,text)
  TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_realtime_bulk_upsert(text,text,text[],text,text,text)
  TO n6_btrack_web;

COMMIT;
