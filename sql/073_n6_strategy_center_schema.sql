-- N6 B-track strategy center display-only schema 073.
-- REVIEW ONLY until a separate runtime_control migration execution gate.
-- Boundary: N6-owned package preferences and display projections only.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_strategy_center_schema_073_v1', 0)
);

DO $preflight$
DECLARE
  required_role record;
  next_open_trade_date date;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '073 owner migration identity rejected';
  END IF;

  IF pg_catalog.to_regclass('public.user_account') IS NULL
     OR pg_catalog.to_regclass('public.n6_principal') IS NULL
     OR pg_catalog.to_regclass('public.user_signal_projection') IS NULL
     OR pg_catalog.to_regclass('public.common_trade_calendar') IS NULL
     OR pg_catalog.to_regclass('public.v_n6_index_membership_fact') IS NULL
     OR pg_catalog.to_regclass('public.v_n6_board_membership_fact') IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_resolve_authority(text)'
        ) IS NULL THEN
    RAISE EXCEPTION '073 requires canonical N6 authority and projection inputs';
  END IF;

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
    RAISE EXCEPTION '073 already applied or partial object conflict';
  END IF;

  FOR required_role IN
    SELECT expected.rolname,
           actual.oid,
           actual.rolcanlogin,
           actual.rolinherit,
           actual.rolsuper,
           actual.rolcreatedb,
           actual.rolcreaterole,
           actual.rolreplication,
           actual.rolbypassrls
    FROM (
      VALUES
        ('n6_btrack_web'::text),
        ('n6_strategy_worker'::text),
        ('n6_virtual_executor'::text),
        ('n6_quote_writer'::text),
        ('n6_ai_agent'::text)
    ) expected(rolname)
    LEFT JOIN pg_catalog.pg_roles actual
      ON actual.rolname = expected.rolname
  LOOP
    IF required_role.oid IS NULL THEN
      RAISE EXCEPTION '073 required role missing: %', required_role.rolname;
    END IF;
    IF NOT required_role.rolcanlogin
       OR required_role.rolinherit
       OR required_role.rolsuper
       OR required_role.rolcreatedb
       OR required_role.rolcreaterole
       OR required_role.rolreplication
       OR required_role.rolbypassrls THEN
      RAISE EXCEPTION '073 role attributes rejected: %', required_role.rolname;
    END IF;
  END LOOP;

  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
    INTO next_open_trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
  IF next_open_trade_date IS NULL THEN
    RAISE EXCEPTION '073 next open trade date unavailable';
  END IF;
END
$preflight$;

CREATE TABLE public.n6_strategy_package_catalog (
  package_key text NOT NULL,
  package_version text NOT NULL,
  display_name text NOT NULL,
  rule_kind text NOT NULL,
  allowed_board_types text[] NOT NULL,
  default_selected boolean NOT NULL DEFAULT false,
  package_status text NOT NULL DEFAULT 'active',
  rule_json jsonb NOT NULL,
  policy_hash text NOT NULL,
  effective_from_trade_date date NOT NULL,
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (package_key, package_version),
  CHECK (package_key IN ('package_1', 'package_2')),
  CHECK (package_version ~ '^v[1-9][0-9]*$'),
  CHECK (display_name <> ''),
  CHECK (rule_kind IN ('index_and_board_executed', 'board_executed')),
  CHECK (
    allowed_board_types = ARRAY[
      'tdx_industry', 'tdx_concept', 'tdx_region'
    ]::text[]
  ),
  CHECK (package_status IN ('active', 'retired')),
  CHECK (pg_catalog.jsonb_typeof(rule_json) = 'object'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (package_status = 'active' AND retired_at IS NULL)
    OR (package_status = 'retired' AND retired_at IS NOT NULL)
  ),
  CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX idx_073_n6_strategy_package_active_key
ON public.n6_strategy_package_catalog(package_key)
WHERE package_status = 'active';

CREATE UNIQUE INDEX idx_073_n6_strategy_package_one_default
ON public.n6_strategy_package_catalog(default_selected)
WHERE package_status = 'active' AND default_selected = true;

CREATE TABLE public.n6_user_strategy_selection_revision (
  selection_revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES public.user_account(user_id),
  revision_no bigint NOT NULL,
  selection_status text NOT NULL,
  replay_status text NOT NULL,
  request_id text NOT NULL,
  effective_trade_date date NOT NULL,
  previous_revision_id bigint REFERENCES
    public.n6_user_strategy_selection_revision(selection_revision_id),
  selection_policy_hash text NOT NULL,
  created_by_user_id bigint NOT NULL REFERENCES public.user_account(user_id),
  selection_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  activated_at timestamptz,
  superseded_at timestamptz,
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  UNIQUE (principal_id, principal_type, user_id, revision_no),
  UNIQUE (principal_id, principal_type, user_id, request_id),
  UNIQUE (previous_revision_id),
  UNIQUE (selection_revision_id, principal_id, principal_type, user_id),
  CHECK (principal_type IN ('admin', 'human_user')),
  CHECK (revision_no > 0),
  CHECK (selection_status IN ('pending', 'active', 'superseded')),
  CHECK (replay_status IN ('pending', 'running', 'passed', 'failed')),
  CHECK (request_id ~ '^[A-Za-z0-9._:-]{8,160}$'),
  CHECK (selection_policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (pg_catalog.jsonb_typeof(selection_metadata_json) = 'object'),
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
  )
);

CREATE UNIQUE INDEX idx_073_n6_strategy_selection_one_active
ON public.n6_user_strategy_selection_revision(
  principal_id, principal_type, user_id
)
WHERE selection_status = 'active';

CREATE UNIQUE INDEX idx_073_n6_strategy_selection_one_pending
ON public.n6_user_strategy_selection_revision(
  principal_id, principal_type, user_id
)
WHERE selection_status = 'pending';

CREATE INDEX idx_073_n6_strategy_selection_effective_date
ON public.n6_user_strategy_selection_revision(
  effective_trade_date, selection_status, selection_revision_id
);

CREATE TABLE public.n6_user_strategy_selection_item (
  selection_revision_id bigint NOT NULL REFERENCES
    public.n6_user_strategy_selection_revision(selection_revision_id),
  package_key text NOT NULL,
  package_version text NOT NULL,
  selected_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (selection_revision_id, package_key),
  FOREIGN KEY (package_key, package_version)
    REFERENCES public.n6_strategy_package_catalog(package_key, package_version)
);

CREATE INDEX idx_073_n6_strategy_selection_item_package
ON public.n6_user_strategy_selection_item(package_key, package_version);

CREATE TABLE public.n6_strategy_match_projection (
  strategy_match_projection_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  selection_revision_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES public.user_account(user_id),
  trade_date date NOT NULL,
  stock_identity_key text NOT NULL,
  action_episode_key text NOT NULL,
  action_state text NOT NULL,
  source_signal_projection_id bigint NOT NULL REFERENCES
    public.user_signal_projection(user_signal_projection_id),
  source_event_ids text[] NOT NULL,
  matched_packages text[] NOT NULL,
  scope_sources text[] NOT NULL,
  indices_json jsonb NOT NULL,
  matched_boards_json jsonb NOT NULL,
  signal_json jsonb NOT NULL,
  state_timeline_json jsonb NOT NULL,
  mapping_quality text NOT NULL,
  membership_source_trade_date date NOT NULL,
  evaluator_policy_hash text NOT NULL,
  projection_hash text NOT NULL,
  matched_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  FOREIGN KEY (
    selection_revision_id, principal_id, principal_type, user_id
  ) REFERENCES public.n6_user_strategy_selection_revision(
    selection_revision_id, principal_id, principal_type, user_id
  ),
  UNIQUE (
    principal_id,
    principal_type,
    user_id,
    trade_date,
    stock_identity_key,
    action_episode_key,
    selection_revision_id
  ),
  UNIQUE (
    strategy_match_projection_id, principal_id, principal_type, user_id
  ),
  CHECK (principal_type IN ('admin', 'human_user')),
  CHECK (stock_identity_key ~ '^stock:[A-Z]+:[0-9A-Za-z.]+$'),
  CHECK (action_episode_key <> ''),
  CHECK (action_state IN ('eligible', 'executed')),
  CHECK (pg_catalog.cardinality(source_event_ids) > 0),
  CHECK (
    matched_packages = ARRAY['package_1']::text[]
    OR matched_packages = ARRAY['package_2']::text[]
    OR matched_packages = ARRAY['package_1', 'package_2']::text[]
  ),
  CHECK (pg_catalog.cardinality(scope_sources) BETWEEN 1 AND 3),
  CHECK (
    scope_sources <@ ARRAY[
      'monitor', 'realtime_scope', 'virtual_position'
    ]::text[]
  ),
  CHECK (pg_catalog.jsonb_typeof(indices_json) = 'array'),
  CHECK (pg_catalog.jsonb_typeof(matched_boards_json) = 'array'),
  CHECK (pg_catalog.jsonb_typeof(signal_json) = 'object'),
  CHECK (pg_catalog.jsonb_typeof(state_timeline_json) = 'array'),
  CHECK (mapping_quality IN ('passed', 'missing_index', 'degraded')),
  CHECK (membership_source_trade_date = trade_date),
  CHECK (evaluator_policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (projection_hash ~ '^[0-9a-f]{64}$'),
  CHECK (updated_at >= matched_at)
);

CREATE INDEX idx_073_n6_strategy_match_user_date_cursor
ON public.n6_strategy_match_projection(
  principal_id,
  principal_type,
  user_id,
  trade_date,
  strategy_match_projection_id
);

CREATE INDEX idx_073_n6_strategy_match_stock_episode
ON public.n6_strategy_match_projection(
  trade_date, stock_identity_key, action_episode_key
);

CREATE TABLE public.n6_strategy_match_change (
  strategy_match_change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  strategy_match_projection_id bigint,
  selection_revision_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES public.user_account(user_id),
  trade_date date NOT NULL,
  change_type text NOT NULL,
  dedup_key text NOT NULL,
  source_event_id text,
  payload_json jsonb NOT NULL,
  payload_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  -- Deliberately no FK to the rebuildable projection row.  A remove change is
  -- an append-only tombstone and must retain the deleted projection id after
  -- the current projection row is removed.
  FOREIGN KEY (
    selection_revision_id, principal_id, principal_type, user_id
  ) REFERENCES public.n6_user_strategy_selection_revision(
    selection_revision_id, principal_id, principal_type, user_id
  ),
  UNIQUE (principal_id, principal_type, user_id, dedup_key),
  CHECK (principal_type IN ('admin', 'human_user')),
  CHECK (change_type IN ('upsert', 'remove', 'reset')),
  CHECK (dedup_key <> ''),
  CHECK (source_event_id IS NULL OR source_event_id <> ''),
  CHECK (pg_catalog.jsonb_typeof(payload_json) = 'object'),
  CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (change_type IN ('upsert', 'remove')
     AND strategy_match_projection_id IS NOT NULL)
    OR (change_type = 'reset'
        AND strategy_match_projection_id IS NULL)
  )
);

CREATE INDEX idx_073_n6_strategy_change_stream
ON public.n6_strategy_match_change(
  principal_id,
  principal_type,
  user_id,
  strategy_match_change_id
);

WITH package_seed AS (
  SELECT seed.package_key,
         seed.package_version,
         seed.display_name,
         seed.rule_kind,
         seed.default_selected,
         seed.rule_json,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(seed.rule_json::text, 'UTF8')
           ),
           'hex'
         ) AS policy_hash
  FROM (
    VALUES
      (
        'package_1'::text,
        'v1'::text,
        '策略包1'::text,
        'index_and_board_executed'::text,
        true,
        pg_catalog.jsonb_build_object(
          'stock_states', pg_catalog.jsonb_build_array('eligible', 'executed'),
          'trade_date_scope', 'whole_trade_date',
          'direction_match_required', false,
          'index_any_executed_required', true,
          'board_any_executed_required', true,
          'allowed_board_types', pg_catalog.jsonb_build_array(
            'tdx_industry', 'tdx_concept', 'tdx_region'
          ),
          'display_only', true
        )
      ),
      (
        'package_2'::text,
        'v1'::text,
        '策略包2'::text,
        'board_executed'::text,
        false,
        pg_catalog.jsonb_build_object(
          'stock_states', pg_catalog.jsonb_build_array('eligible', 'executed'),
          'trade_date_scope', 'whole_trade_date',
          'direction_match_required', false,
          'index_any_executed_required', false,
          'board_any_executed_required', true,
          'allowed_board_types', pg_catalog.jsonb_build_array(
            'tdx_industry', 'tdx_concept', 'tdx_region'
          ),
          'display_only', true
        )
      )
  ) seed(
    package_key,
    package_version,
    display_name,
    rule_kind,
    default_selected,
    rule_json
  )
)
INSERT INTO public.n6_strategy_package_catalog (
  package_key,
  package_version,
  display_name,
  rule_kind,
  allowed_board_types,
  default_selected,
  package_status,
  rule_json,
  policy_hash,
  effective_from_trade_date
)
SELECT package_seed.package_key,
       package_seed.package_version,
       package_seed.display_name,
       package_seed.rule_kind,
       ARRAY['tdx_industry', 'tdx_concept', 'tdx_region']::text[],
       package_seed.default_selected,
       'active',
       package_seed.rule_json,
       package_seed.policy_hash,
       (
         SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
         FROM public.common_trade_calendar calendar
         WHERE calendar.is_open = true
           AND calendar.trade_date ~ '^[0-9]{8}$'
           AND calendar.trade_date >= pg_catalog.to_char(
                 pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
                 'YYYYMMDD'
               )
       )
FROM package_seed;

CREATE FUNCTION public.n6_strategy_default_selection_on_principal_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  default_package public.n6_strategy_package_catalog%ROWTYPE;
  effective_trade_date date;
  new_revision_id bigint;
BEGIN
  IF NEW.principal_status <> 'active'
     OR NEW.principal_type NOT IN ('admin', 'human_user') THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.user_account account
    WHERE account.user_id = NEW.owner_user_id
      AND account.status = 'active'
  ) THEN
    RAISE EXCEPTION 'strategy_default_selection_owner_user_not_active';
  END IF;

  SELECT catalog.*
    INTO default_package
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = 'package_1'
    AND catalog.package_version = 'v1'
    AND catalog.package_status = 'active'
    AND catalog.default_selected = true;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_default_selection_catalog_missing';
  END IF;

  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
    INTO effective_trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
  IF effective_trade_date IS NULL THEN
    RAISE EXCEPTION 'strategy_default_selection_next_open_trade_date_missing';
  END IF;

  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id,
    principal_type,
    user_id,
    revision_no,
    selection_status,
    replay_status,
    request_id,
    effective_trade_date,
    previous_revision_id,
    selection_policy_hash,
    created_by_user_id,
    selection_metadata_json,
    activated_at
  ) VALUES (
    NEW.principal_id,
    NEW.principal_type,
    NEW.owner_user_id,
    1,
    'active',
    'pending',
    'principal-default-package-1-' || NEW.principal_id::text,
    effective_trade_date,
    NULL,
    default_package.policy_hash,
    NEW.owner_user_id,
    pg_catalog.jsonb_build_object(
      'source', 'n6_principal_default_strategy_selection',
      'default_package', 'package_1',
      'requires_current_trade_date_replay', true
    ),
    pg_catalog.clock_timestamp()
  ) RETURNING selection_revision_id INTO new_revision_id;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id,
    package_key,
    package_version
  ) VALUES (new_revision_id, 'package_1', 'v1');
  RETURN NEW;
END
$function$;

CREATE TRIGGER trg_073_n6_strategy_default_selection
AFTER INSERT ON public.n6_principal
FOR EACH ROW
EXECUTE FUNCTION public.n6_strategy_default_selection_on_principal_insert();

WITH next_open AS (
  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD')) AS trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        )
), default_package AS (
  SELECT catalog.policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = 'package_1'
    AND catalog.package_version = 'v1'
    AND catalog.package_status = 'active'
    AND catalog.default_selected = true
)
INSERT INTO public.n6_user_strategy_selection_revision (
  principal_id,
  principal_type,
  user_id,
  revision_no,
  selection_status,
  replay_status,
  request_id,
  effective_trade_date,
  previous_revision_id,
  selection_policy_hash,
  created_by_user_id,
  selection_metadata_json,
  activated_at
)
SELECT principal.principal_id,
       principal.principal_type,
       principal.owner_user_id,
       1,
       'active',
       'pending',
       'migration-073-default-package-1-' || principal.principal_id::text,
       next_open.trade_date,
       NULL,
       default_package.policy_hash,
       principal.owner_user_id,
       pg_catalog.jsonb_build_object(
         'source', 'migration_073_default_selection',
         'default_package', 'package_1',
         'requires_current_trade_date_replay', true
       ),
       pg_catalog.clock_timestamp()
FROM public.n6_principal principal
JOIN public.user_account account
  ON account.user_id = principal.owner_user_id
CROSS JOIN next_open
CROSS JOIN default_package
WHERE principal.principal_status = 'active'
  AND principal.principal_type IN ('admin', 'human_user')
  AND account.status = 'active'
ORDER BY principal.principal_id;

INSERT INTO public.n6_user_strategy_selection_item (
  selection_revision_id,
  package_key,
  package_version
)
SELECT revision.selection_revision_id,
       'package_1',
       'v1'
FROM public.n6_user_strategy_selection_revision revision
WHERE revision.request_id LIKE 'migration-073-default-package-1-%'
ORDER BY revision.selection_revision_id;

CREATE FUNCTION public.n6_btrack_strategy_center_state(
  p_session_token_hash text
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH authority AS (
    SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value
  ), resolved_trade_date AS (
    SELECT max(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD')) AS value
    FROM public.common_trade_calendar calendar
    WHERE calendar.is_open = true
      AND calendar.trade_date ~ '^[0-9]{8}$'
      AND calendar.trade_date <= pg_catalog.to_char(
            pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
            'YYYYMMDD'
          )
  ), current_stock_approved_batch AS (
    SELECT min(approved.source_trade_date::text) AS source_trade_date,
           min(approved.for_trade_date::text) AS for_trade_date,
           min(approved.run_id::text) AS source_run_id
    FROM public.v_n6_stock_condition_display_basis approved
    CROSS JOIN resolved_trade_date
    WHERE pg_catalog.replace(approved.for_trade_date::text, '-', '') =
          pg_catalog.to_char(resolved_trade_date.value, 'YYYYMMDD')
    HAVING pg_catalog.count(*) > 0
       AND pg_catalog.count(approved.source_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(approved.for_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(approved.run_id) = pg_catalog.count(*)
       AND pg_catalog.count(DISTINCT (
         approved.source_trade_date::text,
         approved.for_trade_date::text,
         approved.run_id::text
       )) = 1
  ), monitor_scope AS (
    SELECT DISTINCT monitor.identity_key AS stock_identity_key,
           'monitor'::text AS scope_source
    FROM public.user_monitor_stock monitor
    JOIN current_stock_approved_batch batch
      ON monitor.valid_source_trade_date::text = batch.source_trade_date
     AND monitor.valid_for_trade_date::text = batch.for_trade_date
     AND monitor.valid_source_run_id::text = batch.source_run_id
     AND monitor.source_run_id::text = batch.source_run_id
    CROSS JOIN authority
    WHERE authority.value IS NOT NULL
      AND monitor.principal_id = (authority.value->>'principal_id')::bigint
      AND monitor.principal_type = authority.value->>'principal_type'
      AND monitor.user_id = (authority.value->>'user_id')::bigint
      AND monitor.asset_kind = 'stock'
      AND monitor.status = 'active'
      AND EXISTS (
        SELECT 1
        FROM public.v_n6_stock_condition_display_basis approved
        WHERE approved.identity_key = monitor.identity_key
          AND approved.source_trade_date::text = batch.source_trade_date
          AND approved.for_trade_date::text = batch.for_trade_date
          AND approved.run_id::text = batch.source_run_id
      )
  ), realtime_scope AS (
    SELECT DISTINCT realtime.identity_key AS stock_identity_key,
           'realtime_scope'::text AS scope_source
    FROM public.user_realtime_monitor_scope realtime
    CROSS JOIN authority
    WHERE authority.value IS NOT NULL
      AND realtime.principal_id = (authority.value->>'principal_id')::bigint
      AND realtime.principal_type = authority.value->>'principal_type'
      AND realtime.user_id = (authority.value->>'user_id')::bigint
      AND realtime.asset_kind = 'stock'
      AND realtime.status = 'active'
  ), virtual_position_scope AS (
    SELECT DISTINCT position.identity_key AS stock_identity_key,
           'virtual_position'::text AS scope_source
    FROM public.n6_virtual_account account
    JOIN public.n6_virtual_position position
      ON position.virtual_account_id = account.virtual_account_id
     AND position.principal_id = account.principal_id
     AND position.principal_type = account.principal_type
    CROSS JOIN authority
    WHERE authority.value IS NOT NULL
      AND account.principal_id = (authority.value->>'principal_id')::bigint
      AND account.principal_type = authority.value->>'principal_type'
      AND account.virtual_account_status = 'active'
      AND position.asset_kind = 'stock'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
  ), applicable_scope AS (
    SELECT * FROM monitor_scope
    UNION ALL
    SELECT * FROM realtime_scope
    UNION ALL
    SELECT * FROM virtual_position_scope
  ), active_revision AS (
    SELECT revision.*
    FROM public.n6_user_strategy_selection_revision revision, authority
    WHERE authority.value IS NOT NULL
      AND revision.principal_id = (authority.value->>'principal_id')::bigint
      AND revision.principal_type = authority.value->>'principal_type'
      AND revision.user_id = (authority.value->>'user_id')::bigint
      AND revision.selection_status = 'active'
  ), pending_revision AS (
    SELECT revision.*
    FROM public.n6_user_strategy_selection_revision revision, authority
    WHERE authority.value IS NOT NULL
      AND revision.principal_id = (authority.value->>'principal_id')::bigint
      AND revision.principal_type = authority.value->>'principal_type'
      AND revision.user_id = (authority.value->>'user_id')::bigint
      AND revision.selection_status = 'pending'
  ), package_rows AS (
    SELECT catalog.package_key,
           catalog.package_version,
           catalog.display_name,
           catalog.rule_kind,
           catalog.allowed_board_types,
           catalog.default_selected,
           catalog.policy_hash,
           catalog.rule_json
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_status = 'active'
  ), match_rows AS (
    SELECT projection.*
    FROM public.n6_strategy_match_projection projection
    JOIN active_revision revision
      ON revision.selection_revision_id = projection.selection_revision_id
    CROSS JOIN resolved_trade_date
    WHERE projection.trade_date = resolved_trade_date.value
  )
  SELECT CASE
    WHEN (SELECT value FROM authority) IS NULL THEN NULL
    ELSE pg_catalog.jsonb_build_object(
      'trade_date', (SELECT value FROM resolved_trade_date),
      'packages', COALESCE((
        SELECT pg_catalog.jsonb_agg(
          pg_catalog.to_jsonb(package_rows)
          ORDER BY package_rows.package_key
        )
        FROM package_rows
      ), '[]'::jsonb),
      'active_selection', (
        SELECT pg_catalog.jsonb_build_object(
          'selection_revision_id', revision.selection_revision_id,
          'revision_no', revision.revision_no,
          'selection_status', revision.selection_status,
          'replay_status', revision.replay_status,
          'effective_trade_date', revision.effective_trade_date,
          'selected_package_keys', COALESCE((
            SELECT pg_catalog.jsonb_agg(
              item.package_key ORDER BY item.package_key
            )
            FROM public.n6_user_strategy_selection_item item
            WHERE item.selection_revision_id = revision.selection_revision_id
          ), '[]'::jsonb)
        )
        FROM active_revision revision
      ),
      'pending_selection', (
        SELECT pg_catalog.jsonb_build_object(
          'selection_revision_id', revision.selection_revision_id,
          'revision_no', revision.revision_no,
          'selection_status', revision.selection_status,
          'replay_status', revision.replay_status,
          'effective_trade_date', revision.effective_trade_date,
          'selected_package_keys', COALESCE((
            SELECT pg_catalog.jsonb_agg(
              item.package_key ORDER BY item.package_key
            )
            FROM public.n6_user_strategy_selection_item item
            WHERE item.selection_revision_id = revision.selection_revision_id
          ), '[]'::jsonb)
        )
        FROM pending_revision revision
      ),
      'scope', pg_catalog.jsonb_build_object(
        'mode', 'monitor_union_realtime_scope_union_virtual_position',
        'stock_count', (
          SELECT pg_catalog.count(DISTINCT scope.stock_identity_key)
          FROM applicable_scope scope
        ),
        'monitor_count', (
          SELECT pg_catalog.count(DISTINCT scope.stock_identity_key)
          FROM applicable_scope scope
          WHERE scope.scope_source = 'monitor'
        ),
        'realtime_scope_count', (
          SELECT pg_catalog.count(DISTINCT scope.stock_identity_key)
          FROM applicable_scope scope
          WHERE scope.scope_source = 'realtime_scope'
        ),
        'virtual_position_count', (
          SELECT pg_catalog.count(DISTINCT scope.stock_identity_key)
          FROM applicable_scope scope
          WHERE scope.scope_source = 'virtual_position'
        ),
        'multi_source_count', (
          SELECT pg_catalog.count(*)
          FROM (
            SELECT scope.stock_identity_key
            FROM applicable_scope scope
            GROUP BY scope.stock_identity_key
            HAVING pg_catalog.count(DISTINCT scope.scope_source) > 1
          ) multi_source
        )
      ),
      'matches', COALESCE((
        SELECT pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'strategy_match_projection_id', row.strategy_match_projection_id,
            'trade_date', row.trade_date,
            'stock_identity_key', row.stock_identity_key,
            'action_episode_key', row.action_episode_key,
            'action_state', row.action_state,
            'matched_packages', row.matched_packages,
            'scope_sources', row.scope_sources,
            'indices', row.indices_json,
            'matched_boards', row.matched_boards_json,
            'signal', row.signal_json,
            'state_timeline', row.state_timeline_json,
            'mapping_quality', row.mapping_quality,
            'matched_at', row.matched_at,
            'updated_at', row.updated_at
          ) ORDER BY row.strategy_match_projection_id
        )
        FROM match_rows row
      ), '[]'::jsonb),
      'watermark', COALESCE((
        SELECT max(change.strategy_match_change_id)
        FROM public.n6_strategy_match_change change, authority
        WHERE change.principal_id = (authority.value->>'principal_id')::bigint
          AND change.principal_type = authority.value->>'principal_type'
          AND change.user_id = (authority.value->>'user_id')::bigint
      ), 0)
    )
  END
$function$;

CREATE FUNCTION public.n6_btrack_strategy_center_changes(
  p_session_token_hash text,
  p_after_change_id bigint,
  p_limit integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH authority AS (
    SELECT public.n6_btrack_resolve_authority(p_session_token_hash) AS value
  ), normalized AS (
    SELECT GREATEST(
             COALESCE(p_after_change_id, 0::bigint), 0::bigint
           ) AS after_change_id,
           LEAST(
             GREATEST(COALESCE(p_limit, 100), 1), 500
           ) AS row_limit
  ), candidate AS (
    SELECT change.strategy_match_change_id,
           change.trade_date,
           change.change_type,
           change.selection_revision_id,
           change.strategy_match_projection_id,
           change.source_event_id,
           change.payload_json,
           change.payload_hash,
           change.created_at,
           row_number() OVER (
             ORDER BY change.strategy_match_change_id
           ) AS result_rank
    FROM public.n6_strategy_match_change change
    CROSS JOIN authority
    CROSS JOIN normalized
    WHERE authority.value IS NOT NULL
      AND change.principal_id = (authority.value->>'principal_id')::bigint
      AND change.principal_type = authority.value->>'principal_type'
      AND change.user_id = (authority.value->>'user_id')::bigint
      AND change.strategy_match_change_id > normalized.after_change_id
    ORDER BY change.strategy_match_change_id
    LIMIT (SELECT row_limit + 1 FROM normalized)
  ), visible AS (
    SELECT candidate.*
    FROM candidate, normalized
    WHERE candidate.result_rank <= normalized.row_limit
  )
  SELECT CASE
    WHEN (SELECT value FROM authority) IS NULL THEN NULL
    ELSE pg_catalog.jsonb_build_object(
      'events', COALESCE((
        SELECT pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'change_id', row.strategy_match_change_id,
            'event', row.change_type,
            'trade_date', row.trade_date,
            'selection_revision_id', row.selection_revision_id,
            'strategy_match_projection_id',
              row.strategy_match_projection_id,
            'source_event_id', row.source_event_id,
            'data', row.payload_json,
            'payload_hash', row.payload_hash,
            'created_at', row.created_at
          ) ORDER BY row.strategy_match_change_id
        )
        FROM visible row
      ), '[]'::jsonb),
      'watermark', COALESCE(
        (SELECT max(row.strategy_match_change_id) FROM visible row),
        (SELECT after_change_id FROM normalized)
      ),
      'has_more', (
        SELECT pg_catalog.count(*) > (SELECT row_limit FROM normalized)
        FROM candidate
      )
    )
  END
$function$;

CREATE FUNCTION public.n6_btrack_strategy_selection_put(
  p_session_token_hash text,
  p_selected_package_keys text[],
  p_expected_revision bigint,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb;
  normalized_keys text[];
  existing_keys text[];
  existing_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  active_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  new_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  effective_trade_date date;
  selection_policy_hash text;
  selection_catalog_count integer;
BEGIN
  authority := public.n6_btrack_resolve_authority(p_session_token_hash);
  IF authority IS NULL THEN
    RAISE EXCEPTION 'strategy_selection_unauthorized';
  END IF;

  IF p_request_id IS NULL
     OR p_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' THEN
    RAISE EXCEPTION 'strategy_selection_request_id_invalid';
  END IF;
  IF p_expected_revision IS NULL OR p_expected_revision < 0 THEN
    RAISE EXCEPTION 'strategy_selection_expected_revision_invalid';
  END IF;
  IF p_selected_package_keys IS NULL
     OR pg_catalog.cardinality(p_selected_package_keys) NOT BETWEEN 1 AND 2
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.unnest(p_selected_package_keys) key(value)
       WHERE key.value IS NULL OR key.value NOT IN ('package_1', 'package_2')
     ) THEN
    RAISE EXCEPTION 'strategy_selection_package_keys_invalid';
  END IF;

  SELECT pg_catalog.array_agg(DISTINCT key.value ORDER BY key.value)
    INTO normalized_keys
  FROM pg_catalog.unnest(p_selected_package_keys) key(value);
  IF pg_catalog.cardinality(normalized_keys)
       IS DISTINCT FROM pg_catalog.cardinality(p_selected_package_keys) THEN
    RAISE EXCEPTION 'strategy_selection_package_keys_duplicate';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'n6_strategy_selection:' || (authority->>'principal_id') || ':' ||
      (authority->>'user_id'),
      0
    )
  );

  SELECT revision.*
    INTO existing_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.principal_id = (authority->>'principal_id')::bigint
    AND revision.principal_type = authority->>'principal_type'
    AND revision.user_id = (authority->>'user_id')::bigint
    AND revision.request_id = p_request_id;
  IF FOUND THEN
    SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key)
      INTO existing_keys
    FROM public.n6_user_strategy_selection_item item
    WHERE item.selection_revision_id = existing_revision.selection_revision_id;
    IF existing_keys IS DISTINCT FROM normalized_keys
       OR existing_revision.revision_no <> p_expected_revision + 1 THEN
      RAISE EXCEPTION 'strategy_selection_idempotency_conflict';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'selection_revision_id', existing_revision.selection_revision_id,
      'revision_no', existing_revision.revision_no,
      'selection_status', existing_revision.selection_status,
      'replay_status', existing_revision.replay_status,
      'effective_trade_date', existing_revision.effective_trade_date,
      'selected_package_keys', existing_keys
    );
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    WHERE revision.principal_id = (authority->>'principal_id')::bigint
      AND revision.principal_type = authority->>'principal_type'
      AND revision.user_id = (authority->>'user_id')::bigint
      AND revision.selection_status = 'pending'
  ) THEN
    RAISE EXCEPTION 'strategy_selection_replay_pending';
  END IF;

  SELECT revision.*
    INTO active_revision
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.principal_id = (authority->>'principal_id')::bigint
    AND revision.principal_type = authority->>'principal_type'
    AND revision.user_id = (authority->>'user_id')::bigint
    AND revision.selection_status = 'active'
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'strategy_selection_active_revision_missing';
  END IF;
  IF active_revision.revision_no <> p_expected_revision THEN
    RAISE EXCEPTION 'strategy_selection_revision_conflict';
  END IF;

  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
    INTO effective_trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
  IF effective_trade_date IS NULL THEN
    RAISE EXCEPTION 'strategy_selection_next_open_trade_date_missing';
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
    INTO selection_catalog_count, selection_policy_hash
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = ANY(normalized_keys)
    AND catalog.package_version = 'v1'
    AND catalog.package_status = 'active';
  IF selection_catalog_count <> pg_catalog.cardinality(normalized_keys)
     OR selection_policy_hash IS NULL THEN
    RAISE EXCEPTION 'strategy_selection_catalog_authority_missing';
  END IF;

  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id,
    principal_type,
    user_id,
    revision_no,
    selection_status,
    replay_status,
    request_id,
    effective_trade_date,
    previous_revision_id,
    selection_policy_hash,
    created_by_user_id,
    selection_metadata_json
  ) VALUES (
    (authority->>'principal_id')::bigint,
    authority->>'principal_type',
    (authority->>'user_id')::bigint,
    active_revision.revision_no + 1,
    'pending',
    'pending',
    p_request_id,
    effective_trade_date,
    active_revision.selection_revision_id,
    selection_policy_hash,
    (authority->>'user_id')::bigint,
    pg_catalog.jsonb_build_object(
      'source', 'n6_strategy_center_selection_api',
      'requires_current_trade_date_replay', true
    )
  ) RETURNING * INTO new_revision;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id,
    package_key,
    package_version
  )
  SELECT new_revision.selection_revision_id,
         key.value,
         'v1'
  FROM pg_catalog.unnest(normalized_keys) key(value)
  ORDER BY key.value;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', new_revision.selection_revision_id,
    'revision_no', new_revision.revision_no,
    'selection_status', new_revision.selection_status,
    'replay_status', new_revision.replay_status,
    'effective_trade_date', new_revision.effective_trade_date,
    'selected_package_keys', normalized_keys
  );
END
$function$;

DO $postflight$
DECLARE
  expected_principal_count bigint;
  seeded_revision_count bigint;
  seeded_item_count bigint;
BEGIN
  SELECT count(*)
    INTO expected_principal_count
  FROM public.n6_principal principal
  JOIN public.user_account account
    ON account.user_id = principal.owner_user_id
  WHERE principal.principal_status = 'active'
    AND principal.principal_type IN ('admin', 'human_user')
    AND account.status = 'active';

  SELECT count(*)
    INTO seeded_revision_count
  FROM public.n6_user_strategy_selection_revision revision
  WHERE revision.request_id LIKE 'migration-073-default-package-1-%'
    AND revision.selection_status = 'active'
    AND revision.replay_status = 'pending';

  SELECT count(*)
    INTO seeded_item_count
  FROM public.n6_user_strategy_selection_item item
  JOIN public.n6_user_strategy_selection_revision revision
    ON revision.selection_revision_id = item.selection_revision_id
  WHERE revision.request_id LIKE 'migration-073-default-package-1-%'
    AND item.package_key = 'package_1'
    AND item.package_version = 'v1';

  IF expected_principal_count <> seeded_revision_count
     OR expected_principal_count <> seeded_item_count THEN
    RAISE EXCEPTION
      '073 default selection seed mismatch expected=% revisions=% items=%',
      expected_principal_count,
      seeded_revision_count,
      seeded_item_count;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_user_strategy_selection_revision revision
    JOIN public.n6_user_strategy_selection_item item
      ON item.selection_revision_id = revision.selection_revision_id
    WHERE revision.request_id LIKE 'migration-073-default-package-1-%'
      AND item.package_key <> 'package_1'
  ) THEN
    RAISE EXCEPTION '073 default selection contains non-package-1 item';
  END IF;
END
$postflight$;

REVOKE ALL ON TABLE
  public.n6_strategy_package_catalog,
  public.n6_user_strategy_selection_revision,
  public.n6_user_strategy_selection_item,
  public.n6_strategy_match_projection,
  public.n6_strategy_match_change
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

REVOKE ALL ON SEQUENCE
  public.n6_user_strategy_selection_revision_selection_revision_id_seq,
  public.n6_strategy_match_projection_strategy_match_projection_id_seq,
  public.n6_strategy_match_change_strategy_match_change_id_seq
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

REVOKE ALL ON FUNCTION
  public.n6_btrack_strategy_center_state(text),
  public.n6_btrack_strategy_center_changes(text,bigint,integer),
  public.n6_btrack_strategy_selection_put(text,text[],bigint,text)
FROM PUBLIC, n6_strategy_worker, n6_virtual_executor, n6_quote_writer,
  n6_ai_agent;

REVOKE ALL ON FUNCTION
  public.n6_strategy_default_selection_on_principal_insert()
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

GRANT USAGE ON SCHEMA public TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION
  public.n6_btrack_strategy_center_state(text),
  public.n6_btrack_strategy_center_changes(text,bigint,integer),
  public.n6_btrack_strategy_selection_put(text,text[],bigint,text)
TO n6_btrack_web;

GRANT USAGE ON SCHEMA public TO n6_strategy_worker;

GRANT SELECT ON TABLE
  public.common_trade_calendar,
  public.n6_principal,
  public.user_account,
  public.user_projection_run,
  public.user_signal_projection,
  public.user_signal_card,
  public.user_monitor_stock,
  public.user_realtime_monitor_scope,
  public.n6_virtual_account,
  public.n6_virtual_position,
  public.v_n6_stock_condition_display_basis,
  public.v_n6_index_membership_fact,
  public.v_n6_board_membership_fact,
  public.n6_strategy_package_catalog,
  public.n6_user_strategy_selection_revision,
  public.n6_user_strategy_selection_item,
  public.n6_strategy_match_projection,
  public.n6_strategy_match_change
TO n6_strategy_worker;

GRANT UPDATE (
  selection_status,
  replay_status,
  activated_at,
  superseded_at
) ON TABLE public.n6_user_strategy_selection_revision
TO n6_strategy_worker;

GRANT INSERT, UPDATE, DELETE ON TABLE
  public.n6_strategy_match_projection
TO n6_strategy_worker;

GRANT INSERT ON TABLE public.n6_strategy_match_change
TO n6_strategy_worker;

GRANT USAGE, SELECT ON SEQUENCE
  public.n6_strategy_match_projection_strategy_match_projection_id_seq,
  public.n6_strategy_match_change_strategy_match_change_id_seq
TO n6_strategy_worker;

COMMIT;
