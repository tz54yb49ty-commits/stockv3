BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_multi_user_v2_selection_migration_085_v1', 0
  )
);

DO $preflight$
BEGIN
  IF CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '085 rollback identity rejected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    JOIN public.n6_user_strategy_selection_item item
      ON item.selection_revision_id = revision.selection_revision_id
    WHERE revision.selection_metadata_json->>'source' =
      'n6_strategy_center_multi_user_v2_migration_085'
  ) THEN
    RAISE EXCEPTION '085 rollback requires no created revision';
  END IF;
END
$preflight$;

DROP FUNCTION public.n6_strategy_center_migrate_v2_selection_v1(
  bigint, bigint, bigint, bigint, text
);

COMMIT;
