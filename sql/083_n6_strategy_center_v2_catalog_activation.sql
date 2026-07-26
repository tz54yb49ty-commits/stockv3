-- N6 Strategy Center V2 catalog activation gate.
--
-- This owner-only gate changes catalog authority only:
-- * package_1/package_2 V1: active -> grandfathered
-- * package_1/package_2 V2: selectable -> active
-- * package_1 V2 becomes the sole active default for future principals
--
-- Existing selection revisions/items are immutable in this migration.  The
-- table locks close the compatibility write window: all earlier selection
-- writes finish before the preflight snapshot, and later writes observe the
-- activated V2 catalog.

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
    RAISE EXCEPTION '083 owner migration identity rejected';
  END IF;
END
$identity$;

-- Lock in the same direction as principal creation and selection writes.
-- SHARE blocks INSERT/UPDATE/DELETE while preserving read-only Web access.
LOCK TABLE public.n6_principal IN SHARE MODE;
LOCK TABLE public.n6_user_strategy_selection_revision IN SHARE MODE;
LOCK TABLE public.n6_user_strategy_selection_item IN SHARE MODE;
LOCK TABLE public.n6_strategy_package_catalog IN SHARE MODE;
LOCK TABLE public.n6_strategy_match_projection IN ACCESS SHARE MODE;
LOCK TABLE public.n6_strategy_match_change IN ACCESS SHARE MODE;
LOCK TABLE public.n6_strategy_observation_projection IN ACCESS SHARE MODE;

DO $preflight$
DECLARE
  activation_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
BEGIN
  IF pg_catalog.to_regclass(
       'public.n6_strategy_observation_projection'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.idx_081_n6_strategy_match_v2_grain'
        ) IS NULL
     OR pg_catalog.to_regclass(
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
    RAISE EXCEPTION '083 required 081/082 lineage missing';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_attribute attribute
    WHERE attribute.attrelid =
          'public.n6_strategy_match_projection'::pg_catalog.regclass
      AND attribute.attname = 'coherence_episode_key'
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
  )
     OR NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_attribute attribute
       WHERE attribute.attrelid =
             'public.n6_strategy_match_change'::pg_catalog.regclass
         AND attribute.attname = 'surface_kind'
         AND attribute.attnum > 0
         AND attribute.attnotnull
         AND NOT attribute.attisdropped
     )
     OR (
       SELECT pg_catalog.count(*)
       FROM pg_catalog.pg_constraint constraint_row
       WHERE constraint_row.conrelid =
             'public.n6_user_strategy_selection_revision'
               ::pg_catalog.regclass
         AND constraint_row.conname IN (
           'n6_user_strategy_selection_revision_selection_status_check',
           'n6_user_strategy_selection_revision_check'
         )
         AND constraint_row.convalidated
         AND pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
             LIKE '%abandoned%'
     ) <> 2 THEN
    RAISE EXCEPTION '083 required 081/082 schema authority drift';
  END IF;
  IF activation_trade_date IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date =
             pg_catalog.to_char(activation_trade_date, 'YYYYMMDD')
         AND calendar.is_open = true
     ) THEN
    RAISE EXCEPTION '083 current open trade date required';
  END IF;
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
         AND catalog.effective_from_trade_date <= activation_trade_date
         AND (
           (catalog.package_key = 'package_1'
            AND catalog.policy_hash =
              '0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58')
           OR
           (catalog.package_key = 'package_2'
            AND catalog.policy_hash =
              '12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb')
         )
     ) <> 2
     OR EXISTS (
       SELECT 1
       FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_key IN ('package_1', 'package_2')
         AND catalog.package_version NOT IN ('v1', 'v2')
     ) THEN
    RAISE EXCEPTION '083 catalog authority or activation date drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_status = 'pending'
  )
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.package_version = 'v2'
     ) THEN
    RAISE EXCEPTION '083 selection write window not quiesced';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_status = 'active'
      AND (
        NOT EXISTS (
          SELECT 1
          FROM public.n6_user_strategy_selection_item item
          WHERE item.selection_revision_id =
                revision.selection_revision_id
            AND item.package_version = 'v1'
        )
        OR EXISTS (
          SELECT 1
          FROM public.n6_user_strategy_selection_item item
          WHERE item.selection_revision_id =
                revision.selection_revision_id
            AND (
              item.package_version <> 'v1'
              OR item.package_key NOT IN ('package_1', 'package_2')
            )
        )
      )
  ) THEN
    RAISE EXCEPTION '083 active V1 revision authority drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_principal principal
    JOIN public.user_account account
      ON account.user_id = principal.owner_user_id
    LEFT JOIN public.n6_user_strategy_selection_revision revision
      ON revision.principal_id = principal.principal_id
     AND revision.principal_type = principal.principal_type
     AND revision.user_id = principal.owner_user_id
     AND revision.selection_status = 'active'
    WHERE principal.principal_status = 'active'
      AND principal.principal_type IN ('admin', 'human_user')
      AND account.status = 'active'
    GROUP BY principal.principal_id, principal.principal_type,
             principal.owner_user_id
    HAVING pg_catalog.count(revision.selection_revision_id) <> 1
  ) THEN
    RAISE EXCEPTION '083 active principal selection coverage drift';
  END IF;
END
$preflight$;

UPDATE public.n6_strategy_package_catalog catalog
SET package_status = 'grandfathered',
    default_selected = false,
    updated_at = pg_catalog.clock_timestamp()
WHERE catalog.package_key IN ('package_1', 'package_2')
  AND catalog.package_version = 'v1'
  AND catalog.package_status = 'active';

UPDATE public.n6_strategy_package_catalog catalog
SET package_status = 'active',
    default_selected = (catalog.package_key = 'package_1'),
    updated_at = pg_catalog.clock_timestamp()
WHERE catalog.package_key IN ('package_1', 'package_2')
  AND catalog.package_version = 'v2'
  AND catalog.package_status = 'selectable';

DO $postflight$
DECLARE
  activation_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
BEGIN
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
     ) <> 2
     OR (
       SELECT pg_catalog.count(*)
       FROM public.n6_strategy_package_catalog catalog
       WHERE catalog.package_status = 'active'
         AND catalog.default_selected = true
     ) <> 1
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.package_version = 'v2'
     ) THEN
    RAISE EXCEPTION '083 catalog activation postflight failed';
  END IF;
END
$postflight$;

COMMIT;
