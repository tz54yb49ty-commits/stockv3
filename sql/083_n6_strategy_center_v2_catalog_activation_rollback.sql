-- Logical rollback for the N6 Strategy Center V2 catalog activation gate.
--
-- Rollback is safe only before any V2 selection history exists.  It restores
-- catalog authority but never deletes or rewrites a selection revision/item.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_v2_catalog_activation_083_v1', 0
  )
);

DO $identity$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '083 rollback owner migration identity rejected';
  END IF;
END
$identity$;

LOCK TABLE public.n6_principal IN SHARE MODE;
LOCK TABLE public.n6_user_strategy_selection_revision IN SHARE MODE;
LOCK TABLE public.n6_user_strategy_selection_item IN SHARE MODE;
LOCK TABLE public.n6_strategy_package_catalog IN SHARE MODE;

DO $preflight$
DECLARE
  activation_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
BEGIN
  IF pg_catalog.to_regclass(
       'public.idx_082_n6_strategy_selection_live_previous_revision'
     ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_compensate_revision_v1('
          'bigint,text,bigint,bigint,bigint,text,bigint,date,text)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_abandon_pending_v2('
          'bigint,text,bigint,bigint,bigint,date,text)'
        ) IS NULL THEN
    RAISE EXCEPTION '083 rollback required 082 lineage missing';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date =
          pg_catalog.to_char(activation_trade_date, 'YYYYMMDD')
      AND calendar.is_open = true
  ) THEN
    RAISE EXCEPTION '083 rollback current open trade date required';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_key IN ('package_1', 'package_2')
      AND catalog.package_version = 'v1'
      AND catalog.package_status = 'grandfathered'
      AND catalog.default_selected = false
      AND catalog.retired_at IS NULL
  ) <> 2
     OR (
       SELECT pg_catalog.count(*)
       FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_key IN ('package_1', 'package_2')
         AND catalog.package_version = 'v2'
         AND catalog.package_status = 'active'
         AND catalog.retired_at IS NULL
         AND catalog.effective_from_trade_date <= activation_trade_date
         AND (
           (catalog.package_key = 'package_1'
            AND catalog.default_selected = true
            AND catalog.policy_hash =
              '0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58')
           OR
           (catalog.package_key = 'package_2'
            AND catalog.default_selected = false
            AND catalog.policy_hash =
              '12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb')
         )
     ) <> 2 THEN
    RAISE EXCEPTION '083 rollback catalog authority drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_item item
    WHERE item.package_version = 'v2'
  )
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_revision revision
       WHERE revision.selection_metadata_json->>'package_version' = 'v2'
          OR revision.selection_metadata_json->>
               'abandoned_pending_v2_package_version' = 'v2'
     ) THEN
    RAISE EXCEPTION '083 rollback blocked by V2 selection history';
  END IF;
END
$preflight$;

UPDATE public.n6_strategy_package_catalog catalog
SET package_status = 'selectable',
    default_selected = false,
    updated_at = pg_catalog.clock_timestamp()
WHERE catalog.package_key IN ('package_1', 'package_2')
  AND catalog.package_version = 'v2'
  AND catalog.package_status = 'active';

UPDATE public.n6_strategy_package_catalog catalog
SET package_status = 'active',
    default_selected = (catalog.package_key = 'package_1'),
    updated_at = pg_catalog.clock_timestamp()
WHERE catalog.package_key IN ('package_1', 'package_2')
  AND catalog.package_version = 'v1'
  AND catalog.package_status = 'grandfathered';

DO $postflight$
BEGIN
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_key IN ('package_1', 'package_2')
      AND catalog.package_version = 'v1'
      AND catalog.package_status = 'active'
      AND catalog.retired_at IS NULL
      AND (
        (catalog.package_key = 'package_1'
         AND catalog.default_selected = true)
        OR (catalog.package_key = 'package_2'
            AND catalog.default_selected = false)
      )
  ) <> 2
     OR (
       SELECT pg_catalog.count(*)
       FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_key IN ('package_1', 'package_2')
         AND catalog.package_version = 'v2'
         AND catalog.package_status = 'selectable'
         AND catalog.default_selected = false
         AND catalog.retired_at IS NULL
     ) <> 2
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.package_version = 'v2'
     ) THEN
    RAISE EXCEPTION '083 rollback postflight failed';
  END IF;
END
$postflight$;

COMMIT;
