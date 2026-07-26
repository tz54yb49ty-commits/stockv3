-- Roll back only N6 strategy center schema objects created by migration 073.
-- REVIEW ONLY until a separate runtime_control rollback execution gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_strategy_center_schema_073_v1', 0)
);

DO $preflight$
DECLARE
  object_count integer;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '073 rollback owner identity rejected';
  END IF;

  SELECT count(*)
    INTO object_count
  FROM (
    VALUES
      (pg_catalog.to_regclass('public.n6_strategy_package_catalog')),
      (pg_catalog.to_regclass(
        'public.n6_user_strategy_selection_revision'
      )),
      (pg_catalog.to_regclass(
        'public.n6_user_strategy_selection_item'
      )),
      (pg_catalog.to_regclass('public.n6_strategy_match_projection')),
      (pg_catalog.to_regclass('public.n6_strategy_match_change'))
  ) object(oid)
  WHERE object.oid IS NOT NULL;
  IF object_count <> 5
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_center_state(text)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_center_changes(text,bigint,integer)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_default_selection_on_principal_insert()'
        ) IS NULL THEN
    RAISE EXCEPTION '073 rollback requires complete applied object set';
  END IF;
END
$preflight$;

LOCK TABLE
  public.n6_strategy_package_catalog,
  public.n6_user_strategy_selection_revision,
  public.n6_user_strategy_selection_item,
  public.n6_strategy_match_projection,
  public.n6_strategy_match_change
IN ACCESS EXCLUSIVE MODE;

REVOKE ALL ON FUNCTION
  public.n6_btrack_strategy_center_state(text),
  public.n6_btrack_strategy_center_changes(text,bigint,integer),
  public.n6_btrack_strategy_selection_put(text,text[],bigint,text),
  public.n6_strategy_default_selection_on_principal_insert()
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

DROP TRIGGER trg_073_n6_strategy_default_selection ON public.n6_principal;
DROP FUNCTION public.n6_strategy_default_selection_on_principal_insert();

DROP FUNCTION public.n6_btrack_strategy_selection_put(
  text,
  text[],
  bigint,
  text
);
DROP FUNCTION public.n6_btrack_strategy_center_changes(text,bigint,integer);
DROP FUNCTION public.n6_btrack_strategy_center_state(text);

DROP TABLE public.n6_strategy_match_change;
DROP TABLE public.n6_strategy_match_projection;
DROP TABLE public.n6_user_strategy_selection_item;
DROP TABLE public.n6_user_strategy_selection_revision;
DROP TABLE public.n6_strategy_package_catalog;

DO $postflight$
BEGIN
  IF pg_catalog.to_regclass('public.n6_strategy_package_catalog') IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_revision'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_item'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_match_projection'
        ) IS NOT NULL
     OR pg_catalog.to_regclass('public.n6_strategy_match_change') IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_center_state(text)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_center_changes(text,bigint,integer)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_default_selection_on_principal_insert()'
        ) IS NOT NULL THEN
    RAISE EXCEPTION '073 rollback left strategy center objects behind';
  END IF;
END
$postflight$;

COMMIT;
