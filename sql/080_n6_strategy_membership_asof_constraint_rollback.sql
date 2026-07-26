-- Restore the 073 same-day membership constraint only when all rows comply.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_membership_asof_constraint_080_v1', 0
  )
);

DO $preflight$
DECLARE
  target_constraint record;
  target_table record;
  target_column record;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '080 rollback owner migration identity rejected';
  END IF;

  IF pg_catalog.to_regclass(
       'public.n6_strategy_match_projection'
     ) IS NULL THEN
    RAISE EXCEPTION '080 rollback strategy projection table missing';
  END IF;

  SELECT relation.relkind,
         pg_catalog.pg_get_userbyid(relation.relowner) AS owner_name
    INTO target_table
  FROM pg_catalog.pg_class relation
  WHERE relation.oid =
        'public.n6_strategy_match_projection'::pg_catalog.regclass;
  IF NOT FOUND
     OR target_table.relkind <> 'r'
     OR target_table.owner_name <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '080 rollback strategy projection authority rejected';
  END IF;

  SELECT attribute.attnotnull,
         attribute.atttypid = 'pg_catalog.date'::pg_catalog.regtype
           AS is_date
    INTO target_column
  FROM pg_catalog.pg_attribute attribute
  WHERE attribute.attrelid =
        'public.n6_strategy_match_projection'::pg_catalog.regclass
    AND attribute.attname = 'membership_source_trade_date'
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped;
  IF NOT FOUND
     OR NOT target_column.attnotnull
     OR NOT target_column.is_date THEN
    RAISE EXCEPTION '080 rollback membership source date contract rejected';
  END IF;

  SELECT constraint_row.contype,
         constraint_row.convalidated,
         constraint_row.condeferrable,
         constraint_row.condeferred,
         pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
           AS constraint_definition
    INTO target_constraint
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.conrelid =
        'public.n6_strategy_match_projection'::pg_catalog.regclass
    AND constraint_row.conname = 'n6_strategy_match_projection_check';
  IF NOT FOUND
     OR target_constraint.contype <> 'c'
     OR NOT target_constraint.convalidated
     OR target_constraint.condeferrable
     OR target_constraint.condeferred
     OR target_constraint.constraint_definition IS DISTINCT FROM
        'CHECK (membership_source_trade_date IS NOT NULL AND membership_source_trade_date <= trade_date)' THEN
    RAISE EXCEPTION '080 rollback membership constraint drift';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_strategy_match_projection projection
    WHERE projection.membership_source_trade_date
          IS DISTINCT FROM projection.trade_date
  ) THEN
    RAISE EXCEPTION '080 rollback incompatible as-of rows present';
  END IF;
END
$preflight$;

ALTER TABLE public.n6_strategy_match_projection
  DROP CONSTRAINT n6_strategy_match_projection_check;

ALTER TABLE public.n6_strategy_match_projection
  ADD CONSTRAINT n6_strategy_match_projection_check
  CHECK (membership_source_trade_date = trade_date);

DO $postflight$
DECLARE
  target_constraint record;
BEGIN
  SELECT constraint_row.contype,
         constraint_row.convalidated,
         constraint_row.condeferrable,
         constraint_row.condeferred,
         pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
           AS constraint_definition
    INTO target_constraint
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.conrelid =
        'public.n6_strategy_match_projection'::pg_catalog.regclass
    AND constraint_row.conname = 'n6_strategy_match_projection_check';
  IF NOT FOUND
     OR target_constraint.contype <> 'c'
     OR NOT target_constraint.convalidated
     OR target_constraint.condeferrable
     OR target_constraint.condeferred
     OR target_constraint.constraint_definition IS DISTINCT FROM
        'CHECK (membership_source_trade_date = trade_date)' THEN
    RAISE EXCEPTION '080 rollback membership constraint postflight failed';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_strategy_match_projection projection
    WHERE projection.membership_source_trade_date
          IS DISTINCT FROM projection.trade_date
  ) THEN
    RAISE EXCEPTION '080 rollback membership data postflight failed';
  END IF;
END
$postflight$;

COMMIT;
