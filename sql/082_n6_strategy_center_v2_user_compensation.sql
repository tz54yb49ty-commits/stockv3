-- N6 Strategy Center V2-to-V1 per-user append-only compensation gate.
-- REVIEW ONLY: execution requires a separate N6_user migration gate.
--
-- The function creates one pending V1 revision for one frozen principal/user
-- scope.  It never supersedes or activates a revision; the bounded evaluator
-- must replay the pending revision and perform the existing atomic CAS switch.

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
    RAISE EXCEPTION '082 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_user_strategy_selection_revision'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_item'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_package_catalog'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_compensate_revision_v1('
          'bigint,text,bigint,bigint,bigint,text,bigint,date,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_strategy_center_abandon_pending_v2('
          'bigint,text,bigint,bigint,bigint,date,text)'
        ) IS NOT NULL THEN
    RAISE EXCEPTION '082 schema lineage rejected';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v1'
      AND catalog.package_key IN ('package_1', 'package_2')
      AND catalog.package_status IN ('active', 'grandfathered')
  ) <> 2 THEN
    RAISE EXCEPTION '082 v1 compensation catalog rejected';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM pg_catalog.pg_constraint constraint_row
    WHERE constraint_row.conrelid =
          'public.n6_user_strategy_selection_revision'::pg_catalog.regclass
      AND constraint_row.conname IN (
        'n6_user_strategy_selection_revision_selection_status_check',
        'n6_user_strategy_selection_revision_check',
        'n6_user_strategy_selection_revision_previous_revision_id_key'
      )
      AND constraint_row.contype = CASE
        WHEN constraint_row.conname =
          'n6_user_strategy_selection_revision_previous_revision_id_key'
        THEN 'u'::"char"
        ELSE 'c'::"char"
      END
      AND constraint_row.convalidated
  ) <> 3 THEN
    RAISE EXCEPTION '082 selection lifecycle constraint drift';
  END IF;
END
$preflight$;

ALTER TABLE public.n6_user_strategy_selection_revision
  DROP CONSTRAINT
    n6_user_strategy_selection_revision_selection_status_check,
  DROP CONSTRAINT n6_user_strategy_selection_revision_check,
  DROP CONSTRAINT
    n6_user_strategy_selection_revision_previous_revision_id_key;

ALTER TABLE public.n6_user_strategy_selection_revision
  ADD CONSTRAINT
    n6_user_strategy_selection_revision_selection_status_check
  CHECK (selection_status IN ('pending', 'active', 'superseded', 'abandoned')),
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
    OR (selection_status = 'abandoned'
        AND activated_at IS NULL
        AND superseded_at IS NOT NULL
        AND superseded_at >= created_at)
  );

CREATE UNIQUE INDEX idx_082_n6_strategy_selection_live_previous_revision
ON public.n6_user_strategy_selection_revision(previous_revision_id)
WHERE previous_revision_id IS NOT NULL
  AND selection_status <> 'abandoned';

CREATE FUNCTION public.n6_strategy_center_compensate_revision_v1(
  p_principal_id bigint,
  p_principal_type text,
  p_user_id bigint,
  p_expected_active_v2_revision_id bigint,
  p_expected_active_v2_revision_no bigint,
  p_expected_active_v2_policy_hash text,
  p_target_v1_revision_id bigint,
  p_trade_date date,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
DECLARE
  active_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  target_v1_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  existing_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  new_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  selected_keys text[];
  existing_keys text[];
  existing_versions text[];
  active_v2_keys text[];
  active_v2_catalog_count integer;
  active_v2_policy_hash text;
  v1_catalog_count integer;
  v1_policy_hash text;
BEGIN
  IF SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION 'strategy_compensation_owner_only';
  END IF;
  IF p_principal_id IS NULL OR p_principal_id <= 0
     OR p_user_id IS NULL OR p_user_id <= 0
     OR p_expected_active_v2_revision_id IS NULL
     OR p_expected_active_v2_revision_id <= 0
     OR p_expected_active_v2_revision_no IS NULL
     OR p_expected_active_v2_revision_no <= 0
     OR p_expected_active_v2_policy_hash IS NULL
     OR p_expected_active_v2_policy_hash !~ '^[0-9a-f]{64}$'
     OR p_target_v1_revision_id IS NULL
     OR p_target_v1_revision_id <= 0
     OR p_principal_type NOT IN ('admin', 'human_user') THEN
    RAISE EXCEPTION 'strategy_compensation_scope_invalid';
  END IF;
  IF p_request_id IS NULL
     OR p_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' THEN
    RAISE EXCEPTION 'strategy_compensation_request_id_invalid';
  END IF;
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM (
       pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
     )::date
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date = pg_catalog.to_char(
               p_trade_date, 'YYYYMMDD'
             )
         AND calendar.is_open = true
     ) THEN
    RAISE EXCEPTION 'strategy_compensation_current_open_trade_date_required';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'n6_strategy_selection:' || p_principal_id::text || ':' ||
      p_user_id::text,
      0
    )
  );

  SELECT revision.*
    INTO existing_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.principal_id = p_principal_id
    AND revision.principal_type = p_principal_type
    AND revision.user_id = p_user_id
    AND revision.request_id = p_request_id;
  IF FOUND THEN
    SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key),
           pg_catalog.array_agg(
             item.package_version ORDER BY item.package_key
           )
      INTO existing_keys, existing_versions
    FROM public.n6_user_strategy_selection_item item
    WHERE item.selection_revision_id =
          existing_revision.selection_revision_id;
    IF existing_revision.previous_revision_id IS DISTINCT FROM
         p_expected_active_v2_revision_id
       OR existing_revision.effective_trade_date IS DISTINCT FROM p_trade_date
       OR existing_revision.selection_status NOT IN ('pending', 'active')
       OR existing_revision.replay_status NOT IN ('pending', 'passed')
       OR existing_revision.selection_metadata_json->>'source'
          IS DISTINCT FROM
            'n6_strategy_center_v2_to_v1_compensation_gate'
       OR existing_revision.selection_metadata_json->>'target_v1_revision_id'
          IS DISTINCT FROM p_target_v1_revision_id::text
       OR existing_revision.selection_metadata_json->>
            'expected_active_v2_revision_no'
          IS DISTINCT FROM p_expected_active_v2_revision_no::text
       OR existing_revision.selection_metadata_json->>
            'expected_active_v2_policy_hash'
          IS DISTINCT FROM p_expected_active_v2_policy_hash
       OR existing_revision.revision_no IS DISTINCT FROM
          p_expected_active_v2_revision_no + 1
       OR existing_revision.selection_metadata_json->>'target_v1_policy_hash'
          IS DISTINCT FROM existing_revision.selection_policy_hash
       OR existing_revision.selection_metadata_json->'target_package_keys'
          IS DISTINCT FROM pg_catalog.to_jsonb(existing_keys)
       OR existing_versions IS DISTINCT FROM
          pg_catalog.array_fill(
            'v1'::text,
            ARRAY[pg_catalog.cardinality(existing_keys)]
          ) THEN
      RAISE EXCEPTION 'strategy_compensation_idempotency_conflict';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'selection_revision_id', existing_revision.selection_revision_id,
      'revision_no', existing_revision.revision_no,
      'selection_status', existing_revision.selection_status,
      'replay_status', existing_revision.replay_status,
      'effective_trade_date', existing_revision.effective_trade_date,
      'selected_package_keys', existing_keys,
      'selected_package_version', 'v1',
      'compensates_revision_id', p_expected_active_v2_revision_id,
      'target_v1_revision_id', p_target_v1_revision_id
    );
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.principal_id = p_principal_id
      AND revision.principal_type = p_principal_type
      AND revision.user_id = p_user_id
      AND revision.selection_status = 'pending'
  ) THEN
    RAISE EXCEPTION 'strategy_compensation_pending_revision_exists';
  END IF;

  SELECT revision.*
    INTO active_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.selection_revision_id = p_expected_active_v2_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.principal_type = p_principal_type
    AND revision.user_id = p_user_id
    AND revision.selection_status = 'active'
    AND revision.replay_status = 'passed'
    AND revision.revision_no = p_expected_active_v2_revision_no
    AND revision.selection_policy_hash = p_expected_active_v2_policy_hash
    AND revision.effective_trade_date <= p_trade_date
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_compensation_active_v2_revision_drift';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision child
    WHERE child.previous_revision_id = active_revision.selection_revision_id
      AND child.selection_status <> 'abandoned'
  ) THEN
    RAISE EXCEPTION 'strategy_compensation_active_v2_child_drift';
  END IF;

  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
    INTO active_v2_keys
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = active_revision.selection_revision_id
    AND item.package_version = 'v2';
  IF pg_catalog.cardinality(active_v2_keys) NOT BETWEEN 1 AND 2
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.selection_revision_id = active_revision.selection_revision_id
         AND (
           item.package_version <> 'v2'
           OR item.package_key NOT IN ('package_1', 'package_2')
         )
     ) THEN
    RAISE EXCEPTION 'strategy_compensation_active_v2_items_invalid';
  END IF;
  SELECT pg_catalog.count(*)::integer,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(
               pg_catalog.string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ),
               'UTF8'
             )
           ),
           'hex'
         )
    INTO active_v2_catalog_count, active_v2_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(active_v2_keys)
    AND catalog.package_version = 'v2'
    AND catalog.package_status IN ('active', 'selectable')
    AND catalog.effective_from_trade_date <= p_trade_date;
  IF active_v2_catalog_count <> pg_catalog.cardinality(active_v2_keys)
     OR active_v2_policy_hash IS DISTINCT FROM
        p_expected_active_v2_policy_hash THEN
    RAISE EXCEPTION 'strategy_compensation_active_v2_catalog_drift';
  END IF;

  WITH RECURSIVE lineage AS (
    SELECT revision.selection_revision_id,
           revision.previous_revision_id,
           0 AS lineage_depth
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.selection_revision_id =
          active_revision.selection_revision_id
      AND revision.principal_id = p_principal_id
      AND revision.principal_type = p_principal_type
      AND revision.user_id = p_user_id
    UNION ALL
    SELECT predecessor.selection_revision_id,
           predecessor.previous_revision_id,
           current_revision.lineage_depth + 1
    FROM public.n6_user_strategy_selection_revision predecessor
    JOIN lineage current_revision
      ON predecessor.selection_revision_id =
         current_revision.previous_revision_id
    WHERE predecessor.principal_id = p_principal_id
      AND predecessor.principal_type = p_principal_type
      AND predecessor.user_id = p_user_id
  )
  SELECT revision.*
    INTO target_v1_revision
  FROM public.n6_user_strategy_selection_revision revision
  JOIN lineage
    ON lineage.selection_revision_id = revision.selection_revision_id
  WHERE revision.selection_revision_id = p_target_v1_revision_id
    AND revision.selection_status = 'superseded'
    AND revision.replay_status = 'passed'
    AND revision.effective_trade_date <= p_trade_date
    AND lineage.lineage_depth = (
      SELECT min(candidate.lineage_depth)
      FROM lineage candidate
      WHERE NOT EXISTS (
        SELECT 1
        FROM public.n6_user_strategy_selection_item candidate_item
        WHERE candidate_item.selection_revision_id =
              candidate.selection_revision_id
          AND candidate_item.package_version <> 'v1'
      )
        AND EXISTS (
          SELECT 1
          FROM public.n6_user_strategy_selection_item candidate_item
          WHERE candidate_item.selection_revision_id =
                candidate.selection_revision_id
            AND candidate_item.package_version = 'v1'
        )
    );
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_compensation_target_v1_lineage_invalid';
  END IF;

  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
    INTO selected_keys
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = target_v1_revision.selection_revision_id
    AND item.package_version = 'v1';
  IF pg_catalog.cardinality(selected_keys) NOT BETWEEN 1 AND 2
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.selection_revision_id =
             target_v1_revision.selection_revision_id
         AND (
           item.package_version <> 'v1'
           OR item.package_key NOT IN ('package_1', 'package_2')
         )
     ) THEN
    RAISE EXCEPTION 'strategy_compensation_target_v1_items_invalid';
  END IF;

  SELECT pg_catalog.count(*)::integer,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(
               pg_catalog.string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ),
               'UTF8'
             )
           ),
           'hex'
         )
    INTO v1_catalog_count, v1_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(selected_keys)
    AND catalog.package_version = 'v1'
    AND catalog.package_status IN ('active', 'grandfathered')
    AND catalog.effective_from_trade_date <= p_trade_date;
  IF v1_catalog_count <> pg_catalog.cardinality(selected_keys)
     OR v1_policy_hash IS NULL
     OR target_v1_revision.selection_policy_hash IS DISTINCT FROM
        v1_policy_hash THEN
    RAISE EXCEPTION 'strategy_compensation_v1_catalog_authority_missing';
  END IF;

  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id, principal_type, user_id, revision_no,
    selection_status, replay_status, request_id, effective_trade_date,
    previous_revision_id, selection_policy_hash, created_by_user_id,
    selection_metadata_json
  ) VALUES (
    p_principal_id, p_principal_type, p_user_id,
    active_revision.revision_no + 1,
    'pending', 'pending', p_request_id, p_trade_date,
    active_revision.selection_revision_id, v1_policy_hash, p_user_id,
    pg_catalog.jsonb_build_object(
      'source', 'n6_strategy_center_v2_to_v1_compensation_gate',
      'compensates_revision_id', active_revision.selection_revision_id,
      'target_v1_revision_id', target_v1_revision.selection_revision_id,
      'expected_active_v2_revision_no', active_revision.revision_no,
      'expected_active_v2_policy_hash', active_revision.selection_policy_hash,
      'target_v1_policy_hash', v1_policy_hash,
      'target_package_keys', pg_catalog.to_jsonb(selected_keys),
      'target_package_version', 'v1',
      'requires_current_trade_date_replay', true
    )
  ) RETURNING * INTO new_revision;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id, package_key, package_version
  )
  SELECT new_revision.selection_revision_id, key.value, 'v1'
  FROM pg_catalog.unnest(selected_keys) key(value)
  ORDER BY key.value;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', new_revision.selection_revision_id,
    'revision_no', new_revision.revision_no,
    'selection_status', new_revision.selection_status,
    'replay_status', new_revision.replay_status,
    'effective_trade_date', new_revision.effective_trade_date,
    'selected_package_keys', selected_keys,
    'selected_package_version', 'v1',
    'compensates_revision_id', active_revision.selection_revision_id,
    'target_v1_revision_id', target_v1_revision.selection_revision_id
  );
END
$function$;

CREATE FUNCTION public.n6_strategy_center_abandon_pending_v2(
  p_principal_id bigint,
  p_principal_type text,
  p_user_id bigint,
  p_expected_pending_v2_revision_id bigint,
  p_expected_active_v1_revision_id bigint,
  p_trade_date date,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
DECLARE
  active_v1 public.n6_user_strategy_selection_revision%ROWTYPE;
  pending_v2 public.n6_user_strategy_selection_revision%ROWTYPE;
  active_v1_keys text[];
  pending_v2_keys text[];
  active_v1_catalog_count integer;
  pending_v2_catalog_count integer;
  active_v1_policy_hash text;
  pending_v2_policy_hash text;
BEGIN
  IF SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION 'strategy_pending_abandon_owner_only';
  END IF;
  IF p_principal_id IS NULL OR p_principal_id <= 0
     OR p_user_id IS NULL OR p_user_id <= 0
     OR p_expected_pending_v2_revision_id IS NULL
     OR p_expected_pending_v2_revision_id <= 0
     OR p_expected_active_v1_revision_id IS NULL
     OR p_expected_active_v1_revision_id <= 0
     OR p_principal_type NOT IN ('admin', 'human_user') THEN
    RAISE EXCEPTION 'strategy_pending_abandon_scope_invalid';
  END IF;
  IF p_request_id IS NULL
     OR p_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' THEN
    RAISE EXCEPTION 'strategy_pending_abandon_request_id_invalid';
  END IF;
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM (
       pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
     )::date
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date = pg_catalog.to_char(
               p_trade_date, 'YYYYMMDD'
             )
         AND calendar.is_open = true
     ) THEN
    RAISE EXCEPTION 'strategy_pending_abandon_current_open_trade_date_required';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'n6_strategy_selection:' || p_principal_id::text || ':' ||
      p_user_id::text,
      0
    )
  );

  SELECT revision.*
    INTO active_v1
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.selection_revision_id = p_expected_active_v1_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.principal_type = p_principal_type
    AND revision.user_id = p_user_id
    AND revision.selection_status = 'active'
    AND revision.replay_status = 'passed'
    AND revision.effective_trade_date <= p_trade_date
  FOR UPDATE;
  IF NOT FOUND OR EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_item item
    WHERE item.selection_revision_id = active_v1.selection_revision_id
      AND (
        item.package_version <> 'v1'
        OR item.package_key NOT IN ('package_1', 'package_2')
      )
  ) THEN
    RAISE EXCEPTION 'strategy_pending_abandon_active_v1_drift';
  END IF;
  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
    INTO active_v1_keys
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = active_v1.selection_revision_id
    AND item.package_version = 'v1';
  IF active_v1_keys IS NULL
     OR pg_catalog.cardinality(active_v1_keys) NOT BETWEEN 1 AND 2 THEN
    RAISE EXCEPTION 'strategy_pending_abandon_active_v1_items_invalid';
  END IF;
  SELECT pg_catalog.count(*)::integer,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(
               pg_catalog.string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ),
               'UTF8'
             )
           ),
           'hex'
         )
    INTO active_v1_catalog_count, active_v1_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(active_v1_keys)
    AND catalog.package_version = 'v1'
    AND catalog.package_status IN ('active', 'grandfathered')
    AND catalog.effective_from_trade_date <= p_trade_date;
  IF active_v1_catalog_count <> pg_catalog.cardinality(active_v1_keys)
     OR active_v1_policy_hash IS NULL
     OR active_v1.selection_policy_hash IS DISTINCT FROM
        active_v1_policy_hash THEN
    RAISE EXCEPTION 'strategy_pending_abandon_active_v1_catalog_drift';
  END IF;

  SELECT revision.*
    INTO pending_v2
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.selection_revision_id = p_expected_pending_v2_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.principal_type = p_principal_type
    AND revision.user_id = p_user_id
    AND revision.previous_revision_id = active_v1.selection_revision_id
    AND revision.revision_no = active_v1.revision_no + 1
    AND revision.effective_trade_date = p_trade_date
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_pending_abandon_v2_revision_drift';
  END IF;
  SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
    INTO pending_v2_keys
  FROM public.n6_user_strategy_selection_item item
  WHERE item.selection_revision_id = pending_v2.selection_revision_id
    AND item.package_version = 'v2';
  IF pending_v2_keys IS NULL
     OR pg_catalog.cardinality(pending_v2_keys) NOT BETWEEN 1 AND 2
     OR EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_item item
       WHERE item.selection_revision_id = pending_v2.selection_revision_id
         AND (
           item.package_version <> 'v2'
           OR item.package_key NOT IN ('package_1', 'package_2')
         )
     ) THEN
    RAISE EXCEPTION 'strategy_pending_abandon_v2_items_invalid';
  END IF;
  SELECT pg_catalog.count(*)::integer,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(
               pg_catalog.string_agg(
                 catalog.package_key || ':' || catalog.package_version || ':' ||
                 catalog.policy_hash,
                 '|' ORDER BY catalog.package_key
               ),
               'UTF8'
             )
           ),
           'hex'
         )
    INTO pending_v2_catalog_count, pending_v2_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(pending_v2_keys)
    AND catalog.package_version = 'v2'
    AND catalog.package_status IN ('active', 'selectable')
    AND catalog.effective_from_trade_date <= p_trade_date;
  IF pending_v2_catalog_count <> pg_catalog.cardinality(pending_v2_keys)
     OR pending_v2_policy_hash IS NULL
     OR pending_v2.selection_policy_hash IS DISTINCT FROM
        pending_v2_policy_hash THEN
    RAISE EXCEPTION 'strategy_pending_abandon_v2_catalog_drift';
  END IF;
  IF pending_v2.selection_status = 'abandoned' THEN
    IF pending_v2.replay_status <> 'failed'
       OR pending_v2.selection_metadata_json->>'abandon_source'
          IS DISTINCT FROM
            'n6_strategy_center_pending_v2_compensation_gate'
       OR pending_v2.selection_metadata_json->>'abandon_request_id'
          IS DISTINCT FROM p_request_id
       OR pending_v2.selection_metadata_json->>'abandoned_for_trade_date'
          IS DISTINCT FROM p_trade_date::text
       OR pending_v2.selection_metadata_json->>'abandoned_principal_id'
          IS DISTINCT FROM p_principal_id::text
       OR pending_v2.selection_metadata_json->>'abandoned_principal_type'
          IS DISTINCT FROM p_principal_type
       OR pending_v2.selection_metadata_json->>'abandoned_user_id'
          IS DISTINCT FROM p_user_id::text
       OR pending_v2.selection_metadata_json->>
            'preserved_active_v1_revision_id'
          IS DISTINCT FROM active_v1.selection_revision_id::text
       OR pending_v2.selection_metadata_json->>
            'preserved_active_v1_revision_no'
          IS DISTINCT FROM active_v1.revision_no::text
       OR pending_v2.selection_metadata_json->>
            'preserved_active_v1_policy_hash'
          IS DISTINCT FROM active_v1_policy_hash
       OR pending_v2.selection_metadata_json->
            'preserved_active_v1_package_keys'
          IS DISTINCT FROM pg_catalog.to_jsonb(active_v1_keys)
       OR pending_v2.selection_metadata_json->>
            'abandoned_pending_v2_revision_no'
          IS DISTINCT FROM pending_v2.revision_no::text
       OR pending_v2.selection_metadata_json->>
            'abandoned_pending_v2_policy_hash'
          IS DISTINCT FROM pending_v2_policy_hash
       OR pending_v2.selection_metadata_json->
            'abandoned_pending_v2_package_keys'
          IS DISTINCT FROM pg_catalog.to_jsonb(pending_v2_keys)
       OR pending_v2.selection_metadata_json->>
            'abandoned_pending_v2_package_version'
          IS DISTINCT FROM 'v2' THEN
      RAISE EXCEPTION 'strategy_pending_abandon_idempotency_conflict';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'selection_revision_id', pending_v2.selection_revision_id,
      'selection_status', pending_v2.selection_status,
      'replay_status', pending_v2.replay_status,
      'active_v1_revision_id', active_v1.selection_revision_id,
      'abandon_request_id', p_request_id
    );
  END IF;
  IF pending_v2.selection_status <> 'pending'
     OR pending_v2.replay_status NOT IN ('pending', 'failed') THEN
    RAISE EXCEPTION 'strategy_pending_abandon_v2_revision_not_abandonable';
  END IF;
  IF pending_v2.selection_metadata_json ?|
       ARRAY[
         'abandon_source',
         'abandon_request_id',
         'abandoned_for_trade_date',
         'abandoned_principal_id',
         'abandoned_principal_type',
         'abandoned_user_id',
         'preserved_active_v1_revision_id',
         'preserved_active_v1_revision_no',
         'preserved_active_v1_policy_hash',
         'preserved_active_v1_package_keys',
         'abandoned_pending_v2_revision_no',
         'abandoned_pending_v2_policy_hash',
         'abandoned_pending_v2_package_keys',
         'abandoned_pending_v2_package_version'
       ]::text[] THEN
    RAISE EXCEPTION 'strategy_pending_abandon_reserved_metadata_drift';
  END IF;

  UPDATE public.n6_user_strategy_selection_revision revision
  SET selection_status = 'abandoned',
      replay_status = 'failed',
      superseded_at = pg_catalog.clock_timestamp(),
      selection_metadata_json = revision.selection_metadata_json ||
        pg_catalog.jsonb_build_object(
          'abandon_source',
            'n6_strategy_center_pending_v2_compensation_gate',
          'abandon_request_id', p_request_id,
          'abandoned_for_trade_date', p_trade_date,
          'abandoned_principal_id', p_principal_id,
          'abandoned_principal_type', p_principal_type,
          'abandoned_user_id', p_user_id,
          'preserved_active_v1_revision_id', active_v1.selection_revision_id,
          'preserved_active_v1_revision_no', active_v1.revision_no,
          'preserved_active_v1_policy_hash', active_v1_policy_hash,
          'preserved_active_v1_package_keys',
            pg_catalog.to_jsonb(active_v1_keys),
          'abandoned_pending_v2_revision_no', pending_v2.revision_no,
          'abandoned_pending_v2_policy_hash', pending_v2_policy_hash,
          'abandoned_pending_v2_package_keys',
            pg_catalog.to_jsonb(pending_v2_keys),
          'abandoned_pending_v2_package_version', 'v2'
        )
  WHERE revision.selection_revision_id = pending_v2.selection_revision_id
    AND revision.principal_id = p_principal_id
    AND revision.principal_type = p_principal_type
    AND revision.user_id = p_user_id
    AND revision.selection_status = 'pending'
    AND revision.replay_status IN ('pending', 'failed');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_pending_abandon_cas_failed';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', pending_v2.selection_revision_id,
    'selection_status', 'abandoned',
    'replay_status', 'failed',
    'active_v1_revision_id', active_v1.selection_revision_id,
    'abandon_request_id', p_request_id
  );
END
$function$;

REVOKE ALL ON FUNCTION
  public.n6_strategy_center_compensate_revision_v1(
    bigint,text,bigint,bigint,bigint,text,bigint,date,text
  ),
  public.n6_strategy_center_abandon_pending_v2(
    bigint,text,bigint,bigint,bigint,date,text
  )
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

DO $postflight$
DECLARE
  function_signature text;
  function_oid pg_catalog.regprocedure;
  function_owner text;
BEGIN
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    function_oid := pg_catalog.to_regprocedure(function_signature);
    SELECT pg_catalog.pg_get_userbyid(procedure.proowner)
      INTO function_owner
    FROM pg_catalog.pg_proc procedure
    WHERE procedure.oid = function_oid;
    IF function_oid IS NULL
       OR function_owner IS DISTINCT FROM 'ashare_v3_user'
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.pg_proc procedure,
                 LATERAL pg_catalog.aclexplode(
                   COALESCE(
                     procedure.proacl,
                     pg_catalog.acldefault('f', procedure.proowner)
                   )
                 ) privilege
            WHERE procedure.oid = function_oid
              AND privilege.grantee = 0
              AND privilege.privilege_type = 'EXECUTE'
          )
       OR pg_catalog.has_function_privilege(
            'n6_btrack_web', function_signature, 'EXECUTE'
          )
       OR pg_catalog.has_function_privilege(
            'n6_strategy_worker', function_signature, 'EXECUTE'
          )
       OR pg_catalog.has_function_privilege(
            'n6_virtual_executor', function_signature, 'EXECUTE'
          ) THEN
      RAISE EXCEPTION '082 compensation function ACL postflight failed: %',
        function_signature;
    END IF;
  END LOOP;
  IF (
    SELECT pg_catalog.count(*)
    FROM pg_catalog.pg_constraint constraint_row
    WHERE constraint_row.conrelid =
          'public.n6_user_strategy_selection_revision'::pg_catalog.regclass
      AND constraint_row.conname IN (
        'n6_user_strategy_selection_revision_selection_status_check',
        'n6_user_strategy_selection_revision_check'
      )
      AND pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
          LIKE '%abandoned%'
  ) <> 2 THEN
    RAISE EXCEPTION '082 abandoned lifecycle postflight failed';
  END IF;
  IF pg_catalog.to_regclass(
       'public.idx_082_n6_strategy_selection_live_previous_revision'
     ) IS NULL THEN
    RAISE EXCEPTION '082 live predecessor index postflight failed';
  END IF;
END
$postflight$;

COMMIT;
