-- Remove only the 054 function entrypoints.
-- Monitor/realtime history and migrations 041-053 are intentionally preserved.

BEGIN;

REVOKE EXECUTE ON FUNCTION public.n6_btrack_scope_bulk_preview(text,text,text,text[],text,text,text)
  FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_monitor_bulk_upsert(text,text,text[],text,text,text)
  FROM n6_btrack_web;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_realtime_bulk_upsert(text,text,text[],text,text,text)
  FROM n6_btrack_web;

DROP FUNCTION IF EXISTS public.n6_btrack_scope_bulk_preview(text,text,text,text[],text,text,text);
DROP FUNCTION IF EXISTS public.n6_btrack_monitor_bulk_upsert(text,text,text[],text,text,text);
DROP FUNCTION IF EXISTS public.n6_btrack_realtime_bulk_upsert(text,text,text[],text,text,text);

COMMIT;
