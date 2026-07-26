-- 086 rollback: remove tooling only; never delete selection data.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_owner_pending_v2_086_v1', 0
  )
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '086 rollback identity rejected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_metadata_json->>'migration_kind' =
      '086_owner_pending_v2'
  ) THEN
    RAISE EXCEPTION '086 rollback blocked by created revision dependencies';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_owner_create_pending_v2('
       'bigint,bigint,bigint,bigint,text,text,text)'
     ) IS NULL THEN
    RAISE EXCEPTION '086 rollback function missing';
  END IF;
END
$preflight$;

REVOKE ALL ON FUNCTION
  public.n6_strategy_center_owner_create_pending_v2(
    bigint,bigint,bigint,bigint,text,text,text
  )
FROM PUBLIC, n6_strategy_worker, n6_btrack_web, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;
DROP FUNCTION public.n6_strategy_center_owner_create_pending_v2(
  bigint,bigint,bigint,bigint,text,text,text
);
COMMIT;
