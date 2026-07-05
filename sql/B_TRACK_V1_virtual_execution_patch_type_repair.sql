-- B_TRACK_V1 virtual execution patch type repair migration draft.
-- Scope: repair three zero-value legacy V2 date columns before V1 patch.

BEGIN;

-- old type preflight
DO $$
DECLARE
  v_mismatch RECORD;
BEGIN
  SELECT
    e.table_name,
    e.column_name,
    e.expected_udt_name,
    c.udt_name AS actual_udt_name
  INTO v_mismatch
  FROM (
    VALUES
      ('n6_virtual_order', 'source_for_trade_date', 'text'),
      ('n6_virtual_position_event', 'trade_date', 'int4'),
      ('n6_virtual_position_event', 'available_date', 'int4')
  ) AS e(table_name, column_name, expected_udt_name)
  LEFT JOIN information_schema.columns c
    ON c.table_schema = 'public'
   AND c.table_name = e.table_name
   AND c.column_name = e.column_name
  WHERE c.column_name IS NULL
     OR c.udt_name <> e.expected_udt_name
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair old type preflight failed: %.% expected %, found %',
      v_mismatch.table_name,
      v_mismatch.column_name,
      v_mismatch.expected_udt_name,
      v_mismatch.actual_udt_name;
  END IF;
END
$$;

-- business value guard
DO $$
DECLARE
  v_count BIGINT := 0;
BEGIN
  SELECT count(*) INTO v_count
  FROM public.n6_virtual_order
  WHERE source_for_trade_date IS NOT NULL;

  IF v_count > 0 THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair blocked: n6_virtual_order.source_for_trade_date has % business value rows',
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM public.n6_virtual_position_event
  WHERE trade_date IS NOT NULL;

  IF v_count > 0 THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair blocked: n6_virtual_position_event.trade_date has % business value rows',
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM public.n6_virtual_position_event
  WHERE available_date IS NOT NULL;

  IF v_count > 0 THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair blocked: n6_virtual_position_event.available_date has % business value rows',
      v_count;
  END IF;
END
$$;

-- dependency guard
DO $$
DECLARE
  v_dependency RECORD;
BEGIN
  WITH target AS (
    SELECT c.oid AS table_oid, c.relname AS table_name, a.attnum, a.attname
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public'
      AND (
        (c.relname = 'n6_virtual_order' AND a.attname = 'source_for_trade_date')
        OR (
          c.relname = 'n6_virtual_position_event'
          AND a.attname IN ('trade_date', 'available_date')
        )
      )
  )
  SELECT 'index' AS dependency_kind, t.table_name, t.attname AS column_name, i.relname AS object_name
  INTO v_dependency
  FROM target t
  JOIN pg_catalog.pg_index ix ON ix.indrelid = t.table_oid
  JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
  WHERE t.attnum = ANY(ix.indkey)
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair dependency guard failed: % %.% used by %',
      v_dependency.dependency_kind,
      v_dependency.table_name,
      v_dependency.column_name,
      v_dependency.object_name;
  END IF;

  WITH target AS (
    SELECT c.oid AS table_oid, c.relname AS table_name, a.attnum, a.attname
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public'
      AND (
        (c.relname = 'n6_virtual_order' AND a.attname = 'source_for_trade_date')
        OR (
          c.relname = 'n6_virtual_position_event'
          AND a.attname IN ('trade_date', 'available_date')
        )
      )
  )
  SELECT 'constraint' AS dependency_kind, t.table_name, t.attname AS column_name, con.conname AS object_name
  INTO v_dependency
  FROM target t
  JOIN pg_catalog.pg_constraint con ON con.conrelid = t.table_oid
  WHERE t.attnum = ANY(con.conkey)
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair dependency guard failed: % %.% used by %',
      v_dependency.dependency_kind,
      v_dependency.table_name,
      v_dependency.column_name,
      v_dependency.object_name;
  END IF;

  WITH target AS (
    SELECT c.oid AS table_oid, c.relname AS table_name, a.attnum, a.attname
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public'
      AND (
        (c.relname = 'n6_virtual_order' AND a.attname = 'source_for_trade_date')
        OR (
          c.relname = 'n6_virtual_position_event'
          AND a.attname IN ('trade_date', 'available_date')
        )
      )
  )
  SELECT 'view' AS dependency_kind, t.table_name, t.attname AS column_name, vc.relname AS object_name
  INTO v_dependency
  FROM target t
  JOIN pg_catalog.pg_depend d ON d.refobjid = t.table_oid AND d.refobjsubid = t.attnum
  JOIN pg_catalog.pg_rewrite r ON r.oid = d.objid
  JOIN pg_catalog.pg_class vc ON vc.oid = r.ev_class
  WHERE vc.relkind IN ('v', 'm')
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair dependency guard failed: % %.% used by %',
      v_dependency.dependency_kind,
      v_dependency.table_name,
      v_dependency.column_name,
      v_dependency.object_name;
  END IF;

  WITH target AS (
    SELECT c.oid AS table_oid, c.relname AS table_name, a.attnum, a.attname
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public'
      AND (
        (c.relname = 'n6_virtual_order' AND a.attname = 'source_for_trade_date')
        OR (
          c.relname = 'n6_virtual_position_event'
          AND a.attname IN ('trade_date', 'available_date')
        )
      )
  )
  SELECT 'trigger' AS dependency_kind, t.table_name, t.attname AS column_name, tr.tgname AS object_name
  INTO v_dependency
  FROM target t
  JOIN pg_catalog.pg_trigger tr ON tr.tgrelid = t.table_oid
  WHERE NOT tr.tgisinternal
    AND (t.attnum = ANY(tr.tgattr) OR pg_get_triggerdef(tr.oid) ILIKE '%' || t.attname || '%')
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair dependency guard failed: % %.% used by %',
      v_dependency.dependency_kind,
      v_dependency.table_name,
      v_dependency.column_name,
      v_dependency.object_name;
  END IF;

  SELECT 'function' AS dependency_kind, 'public' AS table_name, 'target_column' AS column_name, p.oid::regprocedure::TEXT AS object_name
  INTO v_dependency
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND (
      (p.prosrc ILIKE '%n6_virtual_order%' AND p.prosrc ILIKE '%source_for_trade_date%')
      OR (
        p.prosrc ILIKE '%n6_virtual_position_event%'
        AND (p.prosrc ILIKE '%trade_date%' OR p.prosrc ILIKE '%available_date%')
      )
    )
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 type repair dependency guard failed: % reference exists in %',
      v_dependency.dependency_kind,
      v_dependency.object_name;
  END IF;
END
$$;

ALTER TABLE public.n6_virtual_order DROP COLUMN source_for_trade_date;
ALTER TABLE public.n6_virtual_order ADD COLUMN source_for_trade_date DATE;

ALTER TABLE public.n6_virtual_position_event DROP COLUMN trade_date;
ALTER TABLE public.n6_virtual_position_event ADD COLUMN trade_date DATE;

ALTER TABLE public.n6_virtual_position_event DROP COLUMN available_date;
ALTER TABLE public.n6_virtual_position_event ADD COLUMN available_date DATE;

COMMIT;
