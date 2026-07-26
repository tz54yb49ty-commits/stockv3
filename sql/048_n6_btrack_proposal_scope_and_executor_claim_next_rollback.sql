-- Restore the exact Schema 042 proposal-create and claim ACL surface.
-- Preserve Schemas 041-047 and every proposal, order, trade and position row.

BEGIN;

DROP FUNCTION IF EXISTS public.n6_executor_claim_next_proposal(text);

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

REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint) TO n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) TO n6_virtual_executor;

COMMIT;
