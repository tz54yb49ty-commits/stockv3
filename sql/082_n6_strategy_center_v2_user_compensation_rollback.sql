-- Logical rollback for the 082 owner-only compensation function.
-- Existing compensation revisions are append-only audit evidence and block
-- rollback; they must never be deleted to make this rollback pass.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_v2_user_compensation_082_v1', 0
  )
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '082 rollback owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_compensate_revision_v1('
       'bigint,text,bigint,bigint,bigint,text,bigint,date,text)'
     ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_abandon_pending_v2('
          'bigint,text,bigint,bigint,bigint,date,text)'
        ) IS NULL THEN
    RAISE EXCEPTION '082 rollback function missing';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_metadata_json->>'source' =
          'n6_strategy_center_v2_to_v1_compensation_gate'
       OR revision.selection_metadata_json->>'abandon_source' =
          'n6_strategy_center_pending_v2_compensation_gate'
       OR revision.selection_status = 'abandoned'
  ) THEN
    RAISE EXCEPTION '082 rollback blocked by compensation audit history';
  END IF;
END
$preflight$;

DROP FUNCTION public.n6_strategy_center_compensate_revision_v1(
  bigint,text,bigint,bigint,bigint,text,bigint,date,text
), public.n6_strategy_center_abandon_pending_v2(
  bigint,text,bigint,bigint,bigint,date,text
);

DROP INDEX public.idx_082_n6_strategy_selection_live_previous_revision;

ALTER TABLE public.n6_user_strategy_selection_revision
  DROP CONSTRAINT
    n6_user_strategy_selection_revision_selection_status_check,
  DROP CONSTRAINT n6_user_strategy_selection_revision_check;

ALTER TABLE public.n6_user_strategy_selection_revision
  ADD CONSTRAINT
    n6_user_strategy_selection_revision_selection_status_check
  CHECK (selection_status IN ('pending', 'active', 'superseded')),
  ADD CONSTRAINT n6_user_strategy_selection_revision_check
  CHECK (
    (selection_status = 'pending'
     AND activated_at IS NULL
     AND superseded_at IS NULL)
    OR (selection_status = 'active'
        AND activated_at IS NOT NULL
        AND superseded_at IS NULL)
    OR (selection_status = 'superseded'
        AND activated_at IS NOT NULL
        AND superseded_at IS NOT NULL
        AND superseded_at >= activated_at)
  ),
  ADD CONSTRAINT
    n6_user_strategy_selection_revision_previous_revision_id_key
  UNIQUE (previous_revision_id);

DO $postflight$
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_compensate_revision_v1('
       'bigint,text,bigint,bigint,bigint,text,bigint,date,text)'
     ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_abandon_pending_v2('
          'bigint,text,bigint,bigint,bigint,date,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_082_n6_strategy_selection_live_previous_revision'
        ) IS NOT NULL
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.pg_constraint constraint_row
       WHERE constraint_row.conrelid =
             'public.n6_user_strategy_selection_revision'::pg_catalog.regclass
         AND constraint_row.conname IN (
           'n6_user_strategy_selection_revision_selection_status_check',
           'n6_user_strategy_selection_revision_check'
         )
         AND pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
             LIKE '%abandoned%'
     ) THEN
    RAISE EXCEPTION '082 rollback postflight failed';
  END IF;
END
$postflight$;

COMMIT;
