-- Roll back only the 042 function/grant boundary.
-- Preserve Schema 041, proposal/lot rows, and all virtual-account history.

BEGIN;

DO $rollback_preflight$
DECLARE
  web_connections bigint;
  executor_connections bigint;
  processing_proposals bigint;
BEGIN
  SELECT count(*) INTO web_connections
  FROM pg_catalog.pg_stat_activity
  WHERE usename = 'n6_btrack_web' AND pid <> pg_catalog.pg_backend_pid();

  SELECT count(*) INTO executor_connections
  FROM pg_catalog.pg_stat_activity
  WHERE usename = 'n6_virtual_executor' AND pid <> pg_catalog.pg_backend_pid();

  SELECT count(*) INTO processing_proposals
  FROM public.n6_virtual_trade_proposal
  WHERE proposal_status = 'processing';

  IF web_connections <> 0 OR executor_connections <> 0 OR processing_proposals <> 0 THEN
    RAISE EXCEPTION '042 rollback blocked: web_connections=% executor_connections=% processing_proposals=%',
      web_connections, executor_connections, processing_proposals;
  END IF;
END
$rollback_preflight$;

REVOKE EXECUTE ON FUNCTION public.n6_btrack_resolve_authority(text) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_list(text,text,integer) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_upsert(text,text,text,text,text) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_remove(text,bigint) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_list(text,integer) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_upsert(text,text,text,text) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_remove(text,bigint) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_list(text,integer) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_proposal_confirm(text,bigint,text) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_virtual_trade_list(text,integer) FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text) FROM n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION public.n6_executor_finish_proposal(bigint,text,text,bigint,bigint,text) FROM n6_virtual_executor;
REVOKE USAGE ON SCHEMA public FROM n6_btrack_web, n6_virtual_executor;

DROP TRIGGER IF EXISTS n6_btrack_proposal_transition_guard ON public.n6_virtual_trade_proposal;
DROP FUNCTION IF EXISTS public.n6_btrack_proposal_transition_guard();
DROP FUNCTION IF EXISTS public.n6_executor_finish_proposal(bigint,text,text,bigint,bigint,text);
DROP FUNCTION IF EXISTS public.n6_executor_claim_proposal(bigint,text);
DROP FUNCTION IF EXISTS public.n6_btrack_virtual_trade_list(text,integer);
DROP FUNCTION IF EXISTS public.n6_btrack_proposal_confirm(text,bigint,text);
DROP FUNCTION IF EXISTS public.n6_btrack_proposal_create(text,text,bigint);
DROP FUNCTION IF EXISTS public.n6_btrack_proposal_list(text,integer);
DROP FUNCTION IF EXISTS public.n6_btrack_realtime_remove(text,bigint);
DROP FUNCTION IF EXISTS public.n6_btrack_realtime_upsert(text,text,text,text);
DROP FUNCTION IF EXISTS public.n6_btrack_realtime_list(text,integer);
DROP FUNCTION IF EXISTS public.n6_btrack_monitor_remove(text,bigint);
DROP FUNCTION IF EXISTS public.n6_btrack_monitor_upsert(text,text,text,text,text);
DROP FUNCTION IF EXISTS public.n6_btrack_monitor_list(text,text,integer);
DROP FUNCTION IF EXISTS public.n6_btrack_resolve_authority(text);

COMMIT;
