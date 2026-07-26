-- N6 B-track deterministic registration of legacy human principals 3-6.
-- Execute only in the dedicated 043 migration canary gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE public.user_account IN SHARE MODE;
LOCK TABLE public.n6_principal IN SHARE ROW EXCLUSIVE MODE;

DO $migration$
DECLARE
  active_user_mismatch_count bigint;
  existing_exact_count bigint;
  inserted_count bigint;
  legacy_mismatch_count bigint;
  registered_count bigint;
  sequence_name text;
  sequence_last_value bigint;
  sequence_is_called boolean;
  sequence_result bigint;
  registration_marker constant jsonb := pg_catalog.jsonb_build_object(
    'registration_source',
    '043_n6_btrack_legacy_principal_registration_v1',
    'registration_mode',
    'deterministic_principal_id_equals_user_id'
  );
BEGIN
  PERFORM u.user_id
  FROM public.user_account u
  WHERE u.user_id IN (3, 4, 5, 6)
  ORDER BY u.user_id
  FOR SHARE;

  WITH expected(user_id, role) AS (
    VALUES
      (1::bigint, 'admin'::text),
      (3::bigint, 'user'::text),
      (4::bigint, 'user'::text),
      (5::bigint, 'user'::text),
      (6::bigint, 'user'::text)
  ),
  actual AS (
    SELECT u.user_id, u.role
    FROM public.user_account u
    WHERE u.status = 'active'
      AND u.role IN ('admin', 'user')
  )
  SELECT count(*)
    INTO active_user_mismatch_count
  FROM expected e
  FULL JOIN actual a USING (user_id)
  WHERE e.user_id IS NULL
     OR a.user_id IS NULL
     OR a.role IS DISTINCT FROM e.role;

  IF active_user_mismatch_count <> 0 THEN
    RAISE EXCEPTION '043 active admin/user authority set drifted';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id = 1
      AND p.principal_type = 'admin'
      AND p.owner_user_id = 1
      AND p.principal_status = 'active'
  ) THEN
    RAISE EXCEPTION '043 principal 1 authority mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id = 2
      AND p.principal_type = 'system'
      AND p.owner_user_id IS NULL
      AND p.principal_status = 'system_reserved'
  ) THEN
    RAISE EXCEPTION '043 principal 2 authority mismatch';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id IN (3, 4, 5, 6)
      AND NOT (
        p.principal_type = 'human_user'
        AND p.owner_user_id = p.principal_id
        AND p.principal_status = 'active'
        AND p.principal_label IS NULL
        AND p.principal_policy_json = registration_marker
      )
  ) THEN
    RAISE EXCEPTION '043 target principal id collision or marker/field drift';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.owner_user_id IN (3, 4, 5, 6)
      AND (
        p.principal_status = 'active'
        OR p.principal_type = 'human_user'
      )
      AND NOT (
        p.principal_id = p.owner_user_id
        AND p.principal_type = 'human_user'
        AND p.principal_status = 'active'
        AND p.principal_label IS NULL
        AND p.principal_policy_json = registration_marker
      )
  ) THEN
    RAISE EXCEPTION '043 target owner already has conflicting principal';
  END IF;

  SELECT count(*)
    INTO existing_exact_count
  FROM public.n6_principal p
  WHERE p.principal_id IN (3, 4, 5, 6)
    AND p.principal_type = 'human_user'
    AND p.owner_user_id = p.principal_id
    AND p.principal_status = 'active'
    AND p.principal_label IS NULL
    AND p.principal_policy_json = registration_marker;

  IF existing_exact_count NOT IN (0, 4) THEN
    RAISE EXCEPTION '043 partial registration state rejected: %', existing_exact_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_stock
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_index
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_board
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_realtime_monitor_scope
    ) legacy
    WHERE legacy.principal_id IN (3, 4, 5, 6)
      AND (
        legacy.principal_type <> 'human_user'
        OR legacy.user_id <> legacy.principal_id
      )
  ) THEN
    RAISE EXCEPTION '043 legacy principal ownership mismatch';
  END IF;

  WITH actual(source_name, principal_id, row_count) AS (
    SELECT 'stock', principal_id, count(*)::bigint
    FROM public.user_monitor_stock
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'index', principal_id, count(*)::bigint
    FROM public.user_monitor_index
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'board', principal_id, count(*)::bigint
    FROM public.user_monitor_board
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'realtime', principal_id, count(*)::bigint
    FROM public.user_realtime_monitor_scope
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
  ),
  expected(source_name, principal_id, row_count) AS (
    VALUES
      ('stock'::text, 3::bigint, 1074::bigint),
      ('index'::text, 3::bigint, 79::bigint),
      ('board'::text, 3::bigint, 256::bigint),
      ('realtime'::text, 3::bigint, 1886::bigint),
      ('stock'::text, 4::bigint, 0::bigint),
      ('index'::text, 4::bigint, 0::bigint),
      ('board'::text, 4::bigint, 0::bigint),
      ('realtime'::text, 4::bigint, 9::bigint),
      ('stock'::text, 5::bigint, 2586::bigint),
      ('index'::text, 5::bigint, 18::bigint),
      ('board'::text, 5::bigint, 273::bigint),
      ('realtime'::text, 5::bigint, 0::bigint),
      ('stock'::text, 6::bigint, 1850::bigint),
      ('index'::text, 6::bigint, 0::bigint),
      ('board'::text, 6::bigint, 0::bigint),
      ('realtime'::text, 6::bigint, 9::bigint)
  )
  SELECT count(*)
    INTO legacy_mismatch_count
  FROM expected e
  FULL JOIN actual a
    ON a.source_name = e.source_name
   AND a.principal_id = e.principal_id
  WHERE e.source_name IS NULL
     OR COALESCE(a.row_count, 0) IS DISTINCT FROM e.row_count;

  IF legacy_mismatch_count <> 0 THEN
    RAISE EXCEPTION '043 frozen legacy scope matrix drifted';
  END IF;

  SELECT pg_catalog.pg_get_serial_sequence(
           'public.n6_principal',
           'principal_id'
         )
    INTO sequence_name;
  IF sequence_name IS DISTINCT FROM 'public.n6_principal_principal_id_seq' THEN
    RAISE EXCEPTION '043 principal identity sequence mismatch: %', sequence_name;
  END IF;

  SELECT last_value, is_called
    INTO sequence_last_value, sequence_is_called
  FROM public.n6_principal_principal_id_seq;
  IF sequence_last_value < 1 OR NOT sequence_is_called THEN
    RAISE EXCEPTION '043 principal identity sequence state rejected';
  END IF;

  WITH target(principal_id, principal_type, owner_user_id, principal_status) AS (
    VALUES
      (3::bigint, 'human_user'::text, 3::bigint, 'active'::text),
      (4::bigint, 'human_user'::text, 4::bigint, 'active'::text),
      (5::bigint, 'human_user'::text, 5::bigint, 'active'::text),
      (6::bigint, 'human_user'::text, 6::bigint, 'active'::text)
  )
  INSERT INTO public.n6_principal (
    principal_id,
    principal_type,
    owner_user_id,
    principal_status,
    principal_label,
    principal_policy_json
  )
  OVERRIDING SYSTEM VALUE
  SELECT t.principal_id,
         t.principal_type,
         t.owner_user_id,
         t.principal_status,
         NULL,
         registration_marker
  FROM target t
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id = t.principal_id
      AND p.principal_type = t.principal_type
      AND p.owner_user_id = t.owner_user_id
      AND p.principal_status = t.principal_status
      AND p.principal_label IS NULL
      AND p.principal_policy_json = registration_marker
  )
  ORDER BY t.principal_id;

  GET DIAGNOSTICS inserted_count = ROW_COUNT;
  IF inserted_count <> 4 - existing_exact_count THEN
    RAISE EXCEPTION '043 inserted row count mismatch: expected=% actual=%',
      4 - existing_exact_count,
      inserted_count;
  END IF;

  SELECT count(*)
    INTO registered_count
  FROM public.n6_principal p
  WHERE p.principal_id IN (3, 4, 5, 6)
    AND p.principal_type = 'human_user'
    AND p.owner_user_id = p.principal_id
    AND p.principal_status = 'active'
    AND p.principal_label IS NULL
    AND p.principal_policy_json = registration_marker;
  IF registered_count <> 4 THEN
    RAISE EXCEPTION '043 final registered row count mismatch: %', registered_count;
  END IF;

  SELECT pg_catalog.setval(
           'public.n6_principal_principal_id_seq'::pg_catalog.regclass,
           GREATEST(
             (SELECT last_value FROM public.n6_principal_principal_id_seq),
             (SELECT max(principal_id) FROM public.n6_principal)
           ),
           true
         )
    INTO sequence_result;
  IF sequence_result < 6 OR sequence_result < sequence_last_value THEN
    RAISE EXCEPTION '043 principal identity sequence failed monotonic advance';
  END IF;
END
$migration$;

COMMIT;
