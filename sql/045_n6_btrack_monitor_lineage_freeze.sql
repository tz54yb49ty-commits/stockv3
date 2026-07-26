-- Freeze the exact current approved filter-batch lineage on every new monitor.
-- The published signature, owner, SECURITY DEFINER boundary, search_path and ACL
-- remain unchanged because this migration only replaces the existing function.

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
      SELECT min(source_trade_date::text) AS source_trade_date,
             min(for_trade_date::text) AS for_trade_date,
             min(run_id::text) AS source_run_id
      FROM public.v_n6_stock_condition_display_basis
      WHERE for_trade_date = (SELECT max(for_trade_date) FROM public.v_n6_stock_condition_display_basis)
      HAVING count(*) > 0
         AND count(source_trade_date) = count(*)
         AND count(for_trade_date) = count(*)
         AND count(run_id) = count(*)
         AND count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text)) = 1
    ), approved_source AS (
      SELECT current_batch.source_trade_date,
             current_batch.for_trade_date,
             current_batch.source_run_id
      FROM current_batch
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND EXISTS (
          SELECT 1
          FROM public.v_n6_stock_condition_display_basis approved
          WHERE approved.identity_key = p_identity_key
            AND approved.source_trade_date::text = current_batch.source_trade_date
            AND approved.for_trade_date::text = current_batch.for_trade_date
            AND approved.run_id::text = current_batch.source_run_id
        )
    )
    INSERT INTO public.user_monitor_stock (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'stock', p_identity_key, p_direction,
           'single_row', approved_source.source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', p_identity_key,
             'source_trade_date', approved_source.source_trade_date,
             'for_trade_date', approved_source.for_trade_date,
             'source_run_id', approved_source.source_run_id
           ),
           approved_source.source_trade_date, approved_source.for_trade_date,
           approved_source.source_run_id, pg_catalog.now(), pg_catalog.now()
    FROM approved_source
    RETURNING monitor_id INTO result_id;
  ELSIF p_asset_kind = 'index' THEN
    WITH current_batch AS (
      SELECT min(source_trade_date::text) AS source_trade_date,
             min(for_trade_date::text) AS for_trade_date,
             min(run_id::text) AS source_run_id
      FROM public.v_n6_index_condition_display_basis
      WHERE for_trade_date = (SELECT max(for_trade_date) FROM public.v_n6_index_condition_display_basis)
      HAVING count(*) > 0
         AND count(source_trade_date) = count(*)
         AND count(for_trade_date) = count(*)
         AND count(run_id) = count(*)
         AND count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text)) = 1
    ), approved_source AS (
      SELECT current_batch.source_trade_date,
             current_batch.for_trade_date,
             current_batch.source_run_id
      FROM current_batch
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND EXISTS (
          SELECT 1
          FROM public.v_n6_index_condition_display_basis approved
          WHERE approved.identity_key = p_identity_key
            AND approved.source_trade_date::text = current_batch.source_trade_date
            AND approved.for_trade_date::text = current_batch.for_trade_date
            AND approved.run_id::text = current_batch.source_run_id
        )
    )
    INSERT INTO public.user_monitor_index (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'index', p_identity_key, p_direction,
           'single_row', approved_source.source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', p_identity_key,
             'source_trade_date', approved_source.source_trade_date,
             'for_trade_date', approved_source.for_trade_date,
             'source_run_id', approved_source.source_run_id
           ),
           approved_source.source_trade_date, approved_source.for_trade_date,
           approved_source.source_run_id, pg_catalog.now(), pg_catalog.now()
    FROM approved_source
    RETURNING monitor_id INTO result_id;
  ELSE
    WITH current_batch AS (
      SELECT min(source_trade_date::text) AS source_trade_date,
             min(for_trade_date::text) AS for_trade_date,
             min(run_id::text) AS source_run_id
      FROM public.v_n6_board_condition_display_basis
      WHERE for_trade_date = (SELECT max(for_trade_date) FROM public.v_n6_board_condition_display_basis)
      HAVING count(*) > 0
         AND count(source_trade_date) = count(*)
         AND count(for_trade_date) = count(*)
         AND count(run_id) = count(*)
         AND count(DISTINCT (source_trade_date::text, for_trade_date::text, run_id::text)) = 1
    ), approved_source AS (
      SELECT current_batch.source_trade_date,
             current_batch.for_trade_date,
             current_batch.source_run_id
      FROM current_batch
      WHERE current_batch.for_trade_date = p_for_trade_date
        AND EXISTS (
          SELECT 1
          FROM public.v_n6_board_condition_display_basis approved
          WHERE approved.identity_key = p_identity_key
            AND approved.source_trade_date::text = current_batch.source_trade_date
            AND approved.for_trade_date::text = current_batch.for_trade_date
            AND approved.run_id::text = current_batch.source_run_id
        )
    )
    INSERT INTO public.user_monitor_board (
      principal_id, principal_type, user_id, asset_kind, identity_key, direction,
      source_type, source_run_id, status, quality_status, source_snapshot_json,
      valid_source_trade_date, valid_for_trade_date, valid_source_run_id,
      created_at, updated_at
    )
    SELECT (authority->>'principal_id')::bigint, authority->>'principal_type',
           (authority->>'user_id')::bigint, 'board', p_identity_key, p_direction,
           'single_row', approved_source.source_run_id, 'active', 'reviewed',
           pg_catalog.jsonb_build_object(
             'identity_key', p_identity_key,
             'source_trade_date', approved_source.source_trade_date,
             'for_trade_date', approved_source.for_trade_date,
             'source_run_id', approved_source.source_run_id
           ),
           approved_source.source_trade_date, approved_source.for_trade_date,
           approved_source.source_run_id, pg_catalog.now(), pg_catalog.now()
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
$function$;

COMMIT;
