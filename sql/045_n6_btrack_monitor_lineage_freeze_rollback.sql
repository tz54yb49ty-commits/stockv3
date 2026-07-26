-- Restore the exact monitor function definition published by Schema 044.
-- Preserve the function signature, owner, ACL and all monitor history.
-- Runtime rollout must keep the scope-write feature flag disabled.

BEGIN;

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
    WITH current_batch AS (
      SELECT max(for_trade_date)::text AS for_trade_date
      FROM public.v_n6_stock_condition_display_basis
    ), approved_source AS (
      SELECT DISTINCT current_batch.for_trade_date
      FROM current_batch
      JOIN public.v_n6_stock_condition_display_basis approved
        ON approved.for_trade_date::text = current_batch.for_trade_date
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND approved.identity_key = p_identity_key
    )
    INSERT INTO public.user_monitor_stock (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'stock', p_identity_key, p_direction,
           'single_row', 'active', 'reviewed',
           pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
           p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    FROM approved_source
    RETURNING monitor_id INTO result_id;
  ELSIF p_asset_kind = 'index' THEN
    WITH current_batch AS (
      SELECT max(for_trade_date)::text AS for_trade_date
      FROM public.v_n6_index_condition_display_basis
    ), approved_source AS (
      SELECT DISTINCT current_batch.for_trade_date
      FROM current_batch
      JOIN public.v_n6_index_condition_display_basis approved
        ON approved.for_trade_date::text = current_batch.for_trade_date
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND approved.identity_key = p_identity_key
    )
    INSERT INTO public.user_monitor_index (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'index', p_identity_key, p_direction,
           'single_row', 'active', 'reviewed',
           pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
           p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    FROM approved_source
    RETURNING monitor_id INTO result_id;
  ELSE
    WITH current_batch AS (
      SELECT max(for_trade_date)::text AS for_trade_date
      FROM public.v_n6_board_condition_display_basis
    ), approved_source AS (
      SELECT DISTINCT current_batch.for_trade_date
      FROM current_batch
      JOIN public.v_n6_board_condition_display_basis approved
        ON approved.for_trade_date::text = current_batch.for_trade_date
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND approved.identity_key = p_identity_key
    )
    INSERT INTO public.user_monitor_board (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, status, quality_status, source_snapshot_json,
      valid_for_trade_date, created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'board', p_identity_key, p_direction,
           'single_row', 'active', 'reviewed',
           pg_catalog.jsonb_build_object('identity_key', p_identity_key, 'for_trade_date', p_for_trade_date),
           p_for_trade_date, pg_catalog.now(), pg_catalog.now()
    FROM approved_source
    RETURNING monitor_id INTO result_id;
  END IF;
  IF result_id IS NULL THEN
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
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'source_not_found');
  END IF;
  RETURN pg_catalog.jsonb_build_object('ok', true, 'status', 'active', 'item',
    pg_catalog.jsonb_build_object('monitor_id', result_id, 'asset_kind', p_asset_kind,
      'identity_key', p_identity_key, 'direction', p_direction));
EXCEPTION WHEN unique_violation THEN
  RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'conflict');
END
$function$;\n\nCOMMIT;\n
