-- Logical rollback for the 081 selectable V2 catalog.
--
-- This rollback deliberately preserves the additive schema, projection rows,
-- append-only change history, and V2 catalog identities. It only retires the
-- still-unused selectable V2 catalog. It fails closed once any V2 revision is
-- active or pending; per-user compensation must then be a new revision.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_temporal_confluence_v2_catalog_081_v2', 0
  )
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '081 rollback owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_strategy_observation_projection'
     ) IS NULL
     OR pg_catalog.to_regclass(
       'public.n6_strategy_match_projection'
     ) IS NULL
     OR pg_catalog.to_regclass(
       'public.n6_strategy_match_change'
     ) IS NULL THEN
    RAISE EXCEPTION '081 rollback additive schema missing';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v2'
      AND catalog.package_status = 'selectable'
      AND catalog.package_key IN ('package_1', 'package_2')
  ) <> 2 THEN
    RAISE EXCEPTION '081 rollback selectable catalog drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_item item
    JOIN public.n6_user_strategy_selection_revision revision
      ON revision.selection_revision_id = item.selection_revision_id
    WHERE item.package_version = 'v2'
      AND revision.selection_status IN ('active', 'pending')
  ) THEN
    RAISE EXCEPTION '081 rollback blocked by live V2 user revision';
  END IF;
END
$preflight$;

UPDATE public.n6_strategy_package_catalog catalog
SET package_status = 'retired',
    retired_at = pg_catalog.clock_timestamp(),
    default_selected = false,
    updated_at = pg_catalog.clock_timestamp()
WHERE catalog.package_version = 'v2'
  AND catalog.package_key IN ('package_1', 'package_2')
  AND catalog.package_status = 'selectable';

DO $postflight$
BEGIN
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v2'
      AND catalog.package_status = 'retired'
      AND catalog.retired_at IS NOT NULL
      AND catalog.package_key IN ('package_1', 'package_2')
  ) <> 2
     OR (
       SELECT pg_catalog.count(*)
       FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_version = 'v1'
         AND catalog.package_status = 'active'
         AND catalog.package_key IN ('package_1', 'package_2')
     ) <> 2
     OR pg_catalog.to_regclass(
          'public.n6_strategy_observation_projection'
        ) IS NULL THEN
    RAISE EXCEPTION '081 rollback postflight failed';
  END IF;
END
$postflight$;

COMMIT;
