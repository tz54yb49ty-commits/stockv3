-- N6 Temporal Confluence V2 additive schema and selectable catalog.
-- REVIEW ONLY: do not apply in this gate.
--
-- Compatibility contract:
-- * V1 remains active and is still the only version visible to the running V1
--   evaluator and selection functions.
-- * V2 is registered as selectable, but this migration creates no user
--   revision and does not activate V2 for any principal.
-- * A later, separately authorized activation migration may change V1 to
--   grandfathered and V2 to active after the V2 evaluator is deployed.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_temporal_confluence_v2_catalog_081_v2', 0
  )
);

DO $preflight$
DECLARE
  target_table record;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '081 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regclass('public.n6_strategy_package_catalog') IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_revision'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_user_strategy_selection_item'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_match_projection'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_match_change'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_strategy_observation_projection'
        ) IS NOT NULL THEN
    RAISE EXCEPTION '081 schema lineage rejected';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_status = 'active'
      AND catalog.package_version = 'v1'
      AND catalog.package_key IN ('package_1', 'package_2')
  ) <> 2 THEN
    RAISE EXCEPTION '081 active v1 package authority rejected';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v2'
  ) THEN
    RAISE EXCEPTION '081 v2 catalog already exists';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_attribute attribute
    WHERE attribute.attrelid IN (
      'public.n6_strategy_match_projection'::pg_catalog.regclass,
      'public.n6_strategy_match_change'::pg_catalog.regclass
    )
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
      AND attribute.attname IN (
        'strategy_version', 'coherence_episode_key', 'direction',
        'coherence_level', 'freshness_status', 'confluence_json',
        'package_evidence_json', 'surface_kind',
        'strategy_observation_projection_id'
      )
  ) THEN
    RAISE EXCEPTION '081 additive columns already exist or drifted';
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
    RAISE EXCEPTION '081 match projection authority rejected';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint constraint_row
    WHERE constraint_row.conrelid =
          'public.n6_strategy_match_projection'::pg_catalog.regclass
      AND constraint_row.conname =
          'n6_strategy_match_projection_principal_id_principal_type_us_key'
      AND constraint_row.contype = 'u'
  ) THEN
    RAISE EXCEPTION '081 original match grain constraint rejected';
  END IF;
END
$preflight$;

ALTER TABLE public.n6_strategy_package_catalog
  DROP CONSTRAINT n6_strategy_package_catalog_package_status_check;

ALTER TABLE public.n6_strategy_package_catalog
  DROP CONSTRAINT n6_strategy_package_catalog_check;

ALTER TABLE public.n6_strategy_package_catalog
  ADD CONSTRAINT n6_strategy_package_catalog_package_status_check
  CHECK (
    package_status IN ('active', 'selectable', 'grandfathered', 'retired')
  );

ALTER TABLE public.n6_strategy_package_catalog
  ADD CONSTRAINT n6_strategy_package_catalog_check
  CHECK (
    (package_status IN ('active', 'selectable', 'grandfathered')
     AND retired_at IS NULL)
    OR (package_status = 'retired' AND retired_at IS NOT NULL)
  );

ALTER TABLE public.n6_strategy_match_projection
  ADD COLUMN strategy_version text NOT NULL DEFAULT 'v1',
  ADD COLUMN coherence_episode_key text,
  ADD COLUMN direction text,
  ADD COLUMN coherence_level text,
  ADD COLUMN freshness_status text,
  ADD COLUMN confluence_json jsonb,
  ADD COLUMN package_evidence_json jsonb;

ALTER TABLE public.n6_strategy_match_projection
  DROP CONSTRAINT
    n6_strategy_match_projection_principal_id_principal_type_us_key;

ALTER TABLE public.n6_strategy_match_projection
  ADD CONSTRAINT n6_strategy_match_projection_strategy_version_check
  CHECK (strategy_version IN ('v1', 'v2')),
  ADD CONSTRAINT n6_strategy_match_projection_v2_confluence_check
  CHECK (
    strategy_version = 'v1'
    OR (
      coherence_episode_key IS NOT NULL
      AND coherence_episode_key <> ''
      AND direction IN ('buy', 'sell')
      AND coherence_level IN ('STRONG', 'MEDIUM')
      AND freshness_status = 'fresh'
      AND pg_catalog.jsonb_typeof(confluence_json) = 'object'
      AND pg_catalog.jsonb_typeof(package_evidence_json) = 'array'
      AND NOT signal_json ? 'strategy_center_temporal_confluence'
      AND confluence_json->>'direction' = direction
      AND confluence_json->>'coherence_level' = coherence_level
      AND confluence_json->>'freshness_status' = freshness_status
      AND confluence_json->>'evaluator_policy_hash' = evaluator_policy_hash
      AND confluence_json->'package_evidence' = package_evidence_json
    )
  );

CREATE UNIQUE INDEX idx_081_n6_strategy_match_v1_grain
ON public.n6_strategy_match_projection(
  principal_id, principal_type, user_id, trade_date,
  stock_identity_key, action_episode_key, selection_revision_id
)
WHERE strategy_version = 'v1';

CREATE UNIQUE INDEX idx_081_n6_strategy_match_v2_grain
ON public.n6_strategy_match_projection(
  principal_id, principal_type, user_id, trade_date,
  stock_identity_key, action_episode_key, coherence_episode_key,
  selection_revision_id
)
WHERE strategy_version = 'v2';

CREATE TABLE public.n6_strategy_observation_projection (
  strategy_observation_projection_id bigint
    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  selection_revision_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES public.user_account(user_id),
  trade_date date NOT NULL,
  stock_identity_key text NOT NULL,
  action_episode_key text NOT NULL,
  coherence_episode_key text NOT NULL,
  action_state text NOT NULL,
  source_signal_projection_id bigint NOT NULL REFERENCES
    public.user_signal_projection(user_signal_projection_id),
  source_event_ids text[] NOT NULL,
  observed_packages text[] NOT NULL,
  scope_sources text[] NOT NULL,
  indices_json jsonb NOT NULL,
  observed_boards_json jsonb NOT NULL,
  signal_json jsonb NOT NULL,
  state_timeline_json jsonb NOT NULL,
  mapping_quality text NOT NULL,
  membership_source_trade_date date NOT NULL,
  strategy_version text NOT NULL DEFAULT 'v2',
  direction text NOT NULL,
  coherence_level text NOT NULL,
  freshness_status text NOT NULL,
  qualification_status text NOT NULL DEFAULT 'observation_only',
  confluence_json jsonb NOT NULL,
  package_evidence_json jsonb NOT NULL,
  evaluator_policy_hash text NOT NULL,
  observation_hash text NOT NULL,
  observation_kind text NOT NULL,
  observed_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  FOREIGN KEY (
    selection_revision_id, principal_id, principal_type, user_id
  ) REFERENCES public.n6_user_strategy_selection_revision(
    selection_revision_id, principal_id, principal_type, user_id
  ),
  UNIQUE (
    principal_id, principal_type, user_id, trade_date,
    stock_identity_key, action_episode_key, coherence_episode_key,
    observation_kind, selection_revision_id
  ),
  UNIQUE (
    strategy_observation_projection_id,
    principal_id, principal_type, user_id
  ),
  CHECK (principal_type IN ('admin', 'human_user')),
  CHECK (stock_identity_key ~ '^stock:[A-Z]+:[0-9A-Za-z.]+$'),
  CHECK (action_episode_key <> ''),
  CHECK (coherence_episode_key <> ''),
  CHECK (action_state IN ('eligible', 'executed')),
  CHECK (pg_catalog.cardinality(source_event_ids) > 0),
  CHECK (
    observed_packages = ARRAY['package_1']::text[]
    OR observed_packages = ARRAY['package_2']::text[]
    OR observed_packages = ARRAY['package_1', 'package_2']::text[]
  ),
  CHECK (pg_catalog.cardinality(scope_sources) BETWEEN 1 AND 3),
  CHECK (
    scope_sources <@ ARRAY[
      'monitor', 'realtime_scope', 'virtual_position'
    ]::text[]
  ),
  CHECK (pg_catalog.jsonb_typeof(indices_json) = 'array'),
  CHECK (pg_catalog.jsonb_typeof(observed_boards_json) = 'array'),
  CHECK (pg_catalog.jsonb_typeof(signal_json) = 'object'),
  CHECK (pg_catalog.jsonb_typeof(state_timeline_json) = 'array'),
  CHECK (mapping_quality IN ('passed', 'missing_index', 'degraded')),
  CHECK (membership_source_trade_date <= trade_date),
  CHECK (strategy_version = 'v2'),
  CHECK (direction IN ('buy', 'sell')),
  CHECK (coherence_level IN ('STRONG', 'MEDIUM', 'WEAK')),
  CHECK (freshness_status IN ('fresh', 'stale')),
  CHECK (qualification_status = 'observation_only'),
  CHECK (pg_catalog.jsonb_typeof(confluence_json) = 'object'),
  CHECK (pg_catalog.jsonb_typeof(package_evidence_json) = 'array'),
  CHECK (NOT signal_json ? 'strategy_center_temporal_confluence'),
  CHECK (confluence_json->>'direction' = direction),
  CHECK (confluence_json->>'coherence_level' = coherence_level),
  CHECK (confluence_json->>'freshness_status' = freshness_status),
  CHECK (confluence_json->>'evaluator_policy_hash' = evaluator_policy_hash),
  CHECK (confluence_json->'package_evidence' = package_evidence_json),
  CHECK (evaluator_policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (observation_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (observation_kind = 'weak_span' AND coherence_level = 'WEAK')
    OR (
      observation_kind = 'stale_after_confirmation'
      AND coherence_level IN ('STRONG', 'MEDIUM')
      AND freshness_status = 'stale'
    )
  ),
  CHECK (updated_at >= observed_at)
);

CREATE INDEX idx_081_n6_strategy_observation_user_date
ON public.n6_strategy_observation_projection(
  principal_id, principal_type, user_id, trade_date,
  strategy_observation_projection_id
);

ALTER TABLE public.n6_strategy_match_change
  ADD COLUMN surface_kind text NOT NULL DEFAULT 'qualified_match',
  ADD COLUMN strategy_observation_projection_id bigint;

ALTER TABLE public.n6_strategy_match_change
  DROP CONSTRAINT n6_strategy_match_change_check;

ALTER TABLE public.n6_strategy_match_change
  ADD CONSTRAINT n6_strategy_match_change_surface_kind_check
  CHECK (surface_kind IN ('qualified_match', 'observation')),
  ADD CONSTRAINT n6_strategy_match_change_check
  CHECK (
    (change_type = 'reset'
     AND strategy_match_projection_id IS NULL
     AND strategy_observation_projection_id IS NULL)
    OR (
      change_type IN ('upsert', 'remove')
      AND surface_kind = 'qualified_match'
      AND strategy_match_projection_id IS NOT NULL
      AND strategy_observation_projection_id IS NULL
    )
    OR (
      change_type IN ('upsert', 'remove')
      AND surface_kind = 'observation'
      AND strategy_match_projection_id IS NULL
      AND strategy_observation_projection_id IS NOT NULL
    )
  );

INSERT INTO public.n6_strategy_package_catalog (
  package_key, package_version, display_name, rule_kind,
  allowed_board_types, default_selected, package_status, rule_json,
  policy_hash, effective_from_trade_date
)
VALUES
  (
    'package_1', 'v2', '时序共振策略包1 V2',
    'index_and_board_executed',
    ARRAY['tdx_industry', 'tdx_concept', 'tdx_region']::text[],
    false, 'selectable',
    $json${"market_heat_indices":["index:SH:000001","index:SZ:399001"],"market_heat_policy":{"affects":["heat_label","candidate_ranking"],"creates_candidate":false,"event_selection":"latest_not_after_confirmation","freshness_window_trading_minutes":30,"membership_required":false,"rank_order":["MARKET_HEAT_SUPPORTIVE","MARKET_HEAT_NEUTRAL","MARKET_HEAT_MIXED","MARKET_HEAT_ADVERSE"],"states":["MARKET_HEAT_SUPPORTIVE","MARKET_HEAT_ADVERSE","MARKET_HEAT_MIXED","MARKET_HEAT_NEUTRAL"]},"membership_indices":["index:SH:000016","index:SH:000300","index:SH:000688","index:SH:000852","index:SH:000905","index:SZ:399006","index:SZ:399303"],"package_1_rule":{"maximum_qualified_span":30,"maximum_qualified_span_seconds":1800,"requires":["stock_signal","member_board_signal","at_least_one_member_index_signal"],"same_direction_required":true},"package_id":"N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723","package_key":"package_1","package_version":"v2","proposed_policy":"n6_strategy_center_matcher_v2","risk_boundaries":{"autonomous_trading_authorized":false,"display_only":true,"missing_lineage_or_time_policy":"fail_closed","order_authorized":false,"position_or_cash_mutation_authorized":false,"proposal_authorized":false,"real_trading_authorized":false,"scheduler_scope":"single_principal_user_revision_per_tick","shadow_only":true,"trade_authorized":false,"version_migration":"v1_grandfathered_v2_per_user_pending_atomic_switch"},"rules":{"arrival_order_authority":"user_signal_projection_id_monotonic","candidate_stale_after_trading_minutes":30,"coherence_levels":{"EXPIRED":">60","MEDIUM":"16-30","STRONG":"0-15","WEAK":"31-60"},"confirmation_time":"latest_required_event_time","cross_surface_uniqueness":"one_coherence_episode_one_surface","cross_trade_date_allowed":false,"direction_match_required":true,"eligible_to_executed_policy":"same_coherence_episode_state_update_without_parent_reselection","event_lineage_frozen":true,"event_selection":"first_confirmation_then_minimum_span","event_time_authority":"n5_standard_event_time_only","exclude_midday_break":true,"freshness_statuses":["fresh","stale"],"frozen_episode_authority":"persisted_match_or_observation_projection","heat_evidence_frozen_per_episode":true,"invalid_or_midday_event_time_policy":"fail_closed","lookahead_allowed":false,"mixed_package_level_policy":"qualified_if_any_package_qualified_weak_evidence_retained","new_parent_evidence_policy":"new_coherence_episode_without_overwrite","observation_reasons":["weak_span","stale_after_confirmation"],"observation_retention":"same_trade_date_close","qualified_levels":["STRONG","MEDIUM"],"signal_dto_policy":"canonical_signals_dto_byte_equivalent","sse_surface_kinds":["qualified_match","observation"],"stale_policy":"observation_until_trade_date_close","stock_state_upgrade_creates_episode":false,"strategy_fields_surface":"top_level_confluence","successive_episode_trigger":"new_qualification_parent_projection_only","time_basis":"a_share_trading_minutes","time_precision":"trading_seconds","valid_sessions":["09:30:00-11:30:00","13:00:00-15:00:00"],"weak_policy":"display_only_not_qualified"},"strategy_version":"N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2"}$json$::jsonb,
    '0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58',
    (SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
     FROM public.common_trade_calendar calendar
     WHERE calendar.is_open = true
       AND calendar.trade_date ~ '^[0-9]{8}$'
       AND calendar.trade_date >= pg_catalog.to_char(
         pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
         'YYYYMMDD'
       ))
  ),
  (
    'package_2', 'v2', '时序共振策略包2 V2', 'board_executed',
    ARRAY['tdx_industry', 'tdx_concept', 'tdx_region']::text[],
    false, 'selectable',
    $json${"market_heat_indices":["index:SH:000001","index:SZ:399001"],"market_heat_policy":{"affects":["heat_label","candidate_ranking"],"creates_candidate":false,"event_selection":"latest_not_after_confirmation","freshness_window_trading_minutes":30,"membership_required":false,"rank_order":["MARKET_HEAT_SUPPORTIVE","MARKET_HEAT_NEUTRAL","MARKET_HEAT_MIXED","MARKET_HEAT_ADVERSE"],"states":["MARKET_HEAT_SUPPORTIVE","MARKET_HEAT_ADVERSE","MARKET_HEAT_MIXED","MARKET_HEAT_NEUTRAL"]},"membership_indices":["index:SH:000016","index:SH:000300","index:SH:000688","index:SH:000852","index:SH:000905","index:SZ:399006","index:SZ:399303"],"package_2_rule":{"maximum_qualified_span":30,"maximum_qualified_span_seconds":1800,"requires":["stock_signal","member_board_signal"],"same_direction_required":true},"package_id":"N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723","package_key":"package_2","package_version":"v2","proposed_policy":"n6_strategy_center_matcher_v2","risk_boundaries":{"autonomous_trading_authorized":false,"display_only":true,"missing_lineage_or_time_policy":"fail_closed","order_authorized":false,"position_or_cash_mutation_authorized":false,"proposal_authorized":false,"real_trading_authorized":false,"scheduler_scope":"single_principal_user_revision_per_tick","shadow_only":true,"trade_authorized":false,"version_migration":"v1_grandfathered_v2_per_user_pending_atomic_switch"},"rules":{"arrival_order_authority":"user_signal_projection_id_monotonic","candidate_stale_after_trading_minutes":30,"coherence_levels":{"EXPIRED":">60","MEDIUM":"16-30","STRONG":"0-15","WEAK":"31-60"},"confirmation_time":"latest_required_event_time","cross_surface_uniqueness":"one_coherence_episode_one_surface","cross_trade_date_allowed":false,"direction_match_required":true,"eligible_to_executed_policy":"same_coherence_episode_state_update_without_parent_reselection","event_lineage_frozen":true,"event_selection":"first_confirmation_then_minimum_span","event_time_authority":"n5_standard_event_time_only","exclude_midday_break":true,"freshness_statuses":["fresh","stale"],"frozen_episode_authority":"persisted_match_or_observation_projection","heat_evidence_frozen_per_episode":true,"invalid_or_midday_event_time_policy":"fail_closed","lookahead_allowed":false,"mixed_package_level_policy":"qualified_if_any_package_qualified_weak_evidence_retained","new_parent_evidence_policy":"new_coherence_episode_without_overwrite","observation_reasons":["weak_span","stale_after_confirmation"],"observation_retention":"same_trade_date_close","qualified_levels":["STRONG","MEDIUM"],"signal_dto_policy":"canonical_signals_dto_byte_equivalent","sse_surface_kinds":["qualified_match","observation"],"stale_policy":"observation_until_trade_date_close","stock_state_upgrade_creates_episode":false,"strategy_fields_surface":"top_level_confluence","successive_episode_trigger":"new_qualification_parent_projection_only","time_basis":"a_share_trading_minutes","time_precision":"trading_seconds","valid_sessions":["09:30:00-11:30:00","13:00:00-15:00:00"],"weak_policy":"display_only_not_qualified"},"strategy_version":"N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2"}$json$::jsonb,
    '12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb',
    (SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
     FROM public.common_trade_calendar calendar
     WHERE calendar.is_open = true
       AND calendar.trade_date ~ '^[0-9]{8}$'
       AND calendar.trade_date >= pg_catalog.to_char(
         pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
         'YYYYMMDD'
       ))
  );

CREATE OR REPLACE FUNCTION public.n6_strategy_default_selection_on_principal_insert()
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
    principal_id, principal_type, user_id, revision_no,
    selection_status, replay_status, request_id, effective_trade_date,
    previous_revision_id, selection_policy_hash, created_by_user_id,
    selection_metadata_json, activated_at
  ) VALUES (
    NEW.principal_id, NEW.principal_type, NEW.owner_user_id, 1,
    'active', 'pending',
    'principal-default-package-1-' || NEW.principal_id::text,
    effective_trade_date, NULL, default_package.policy_hash,
    NEW.owner_user_id,
    pg_catalog.jsonb_build_object(
      'source', 'n6_principal_default_strategy_selection',
      'default_package', 'package_1',
      'package_version', default_package.package_version,
      'requires_current_trade_date_replay', true
    ),
    pg_catalog.clock_timestamp()
  ) RETURNING selection_revision_id INTO new_revision_id;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id, package_key, package_version
  ) VALUES (
    new_revision_id, 'package_1', default_package.package_version
  );
  RETURN NEW;
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_strategy_center_state(
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
    SELECT catalog.package_key, catalog.package_version,
           catalog.display_name, catalog.rule_kind,
           catalog.allowed_board_types, catalog.default_selected,
           catalog.package_status, catalog.policy_hash, catalog.rule_json
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_status = 'selectable'
       OR (
         catalog.package_status = 'active'
         AND NOT EXISTS (
           SELECT 1
           FROM public.n6_strategy_package_catalog selectable
           WHERE selectable.package_key = catalog.package_key
             AND selectable.package_status = 'selectable'
         )
       )
  ), match_rows AS (
    SELECT projection.*
    FROM public.n6_strategy_match_projection projection
    JOIN active_revision revision
      ON revision.selection_revision_id = projection.selection_revision_id
    CROSS JOIN resolved_trade_date
    WHERE projection.trade_date = resolved_trade_date.value
      AND (
        projection.strategy_version = 'v1'
        OR projection.freshness_status = 'fresh'
      )
  ), observation_rows AS (
    SELECT observation.*
    FROM public.n6_strategy_observation_projection observation
    JOIN active_revision revision
      ON revision.selection_revision_id = observation.selection_revision_id
    CROSS JOIN resolved_trade_date
    WHERE observation.trade_date = resolved_trade_date.value
  )
  SELECT CASE
    WHEN (SELECT value FROM authority) IS NULL THEN NULL
    ELSE pg_catalog.jsonb_build_object(
      'trade_date', (SELECT value FROM resolved_trade_date),
      'packages', COALESCE((
        SELECT pg_catalog.jsonb_agg(
          pg_catalog.to_jsonb(package_rows)
          ORDER BY package_rows.package_key, package_rows.package_version
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
          ), '[]'::jsonb),
          'selected_packages', COALESCE((
            SELECT pg_catalog.jsonb_agg(
              pg_catalog.jsonb_build_object(
                'package_key', item.package_key,
                'package_version', item.package_version
              ) ORDER BY item.package_key
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
          ), '[]'::jsonb),
          'selected_packages', COALESCE((
            SELECT pg_catalog.jsonb_agg(
              pg_catalog.jsonb_build_object(
                'package_key', item.package_key,
                'package_version', item.package_version
              ) ORDER BY item.package_key
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
          FROM applicable_scope scope WHERE scope.scope_source = 'monitor'
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
            'coherence_episode_key', row.coherence_episode_key,
            'action_state', row.action_state,
            'strategy_version', row.strategy_version,
            'direction', row.direction,
            'coherence_level', row.coherence_level,
            'freshness_status', row.freshness_status,
            'evaluator_policy_hash', row.evaluator_policy_hash,
            'matched_packages', row.matched_packages,
            'scope_sources', row.scope_sources,
            'indices', row.indices_json,
            'matched_boards', row.matched_boards_json,
            'signal', row.signal_json,
            'confluence', row.confluence_json,
            'package_evidence', row.package_evidence_json,
            'state_timeline', row.state_timeline_json,
            'mapping_quality', row.mapping_quality,
            'matched_at', row.matched_at,
            'updated_at', row.updated_at
          ) ORDER BY
            COALESCE(
              (row.confluence_json->>'market_heat_rank')::integer,
              999
            ),
            row.matched_at,
            row.stock_identity_key,
            row.action_episode_key,
            row.coherence_episode_key,
            row.strategy_match_projection_id
        ) FROM match_rows row
      ), '[]'::jsonb),
      'observations', COALESCE((
        SELECT pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'strategy_observation_projection_id',
              row.strategy_observation_projection_id,
            'trade_date', row.trade_date,
            'stock_identity_key', row.stock_identity_key,
            'action_episode_key', row.action_episode_key,
            'coherence_episode_key', row.coherence_episode_key,
            'action_state', row.action_state,
            'strategy_version', row.strategy_version,
            'direction', row.direction,
            'coherence_level', row.coherence_level,
            'freshness_status', row.freshness_status,
            'evaluator_policy_hash', row.evaluator_policy_hash,
            'qualification_status', row.qualification_status,
            'observation_kind', row.observation_kind,
            'observed_packages', row.observed_packages,
            'scope_sources', row.scope_sources,
            'indices', row.indices_json,
            'observed_boards', row.observed_boards_json,
            'signal', row.signal_json,
            'confluence', row.confluence_json,
            'package_evidence', row.package_evidence_json,
            'state_timeline', row.state_timeline_json,
            'mapping_quality', row.mapping_quality,
            'observed_at', row.observed_at,
            'updated_at', row.updated_at
          ) ORDER BY
            COALESCE(
              (row.confluence_json->>'market_heat_rank')::integer,
              999
            ),
            row.observed_at,
            row.stock_identity_key,
            row.action_episode_key,
            row.coherence_episode_key,
            row.observation_kind,
            row.strategy_observation_projection_id
        ) FROM observation_rows row
      ), '[]'::jsonb),
      'surface_counts', pg_catalog.jsonb_build_object(
        'qualified_match_count', (SELECT pg_catalog.count(*) FROM match_rows),
        'observation_count', (SELECT pg_catalog.count(*) FROM observation_rows),
        'weak_count', (
          SELECT pg_catalog.count(*) FROM observation_rows row
          WHERE row.observation_kind = 'weak_span'
        ),
        'stale_count', (
          SELECT pg_catalog.count(*) FROM observation_rows row
          WHERE row.observation_kind = 'stale_after_confirmation'
        )
      ),
      'watermark', COALESCE((
        SELECT max(change.strategy_match_change_id)
        FROM public.n6_strategy_match_change change, authority
        WHERE change.principal_id = (authority.value->>'principal_id')::bigint
          AND change.principal_type = authority.value->>'principal_type'
          AND change.user_id = (authority.value->>'user_id')::bigint
      ), 0),
      'watermarks', pg_catalog.jsonb_build_object(
        'qualified_match', COALESCE((
          SELECT max(change.strategy_match_change_id)
          FROM public.n6_strategy_match_change change, authority
          WHERE change.principal_id =
                (authority.value->>'principal_id')::bigint
            AND change.principal_type = authority.value->>'principal_type'
            AND change.user_id = (authority.value->>'user_id')::bigint
            AND change.surface_kind = 'qualified_match'
        ), 0),
        'observation', COALESCE((
          SELECT max(change.strategy_match_change_id)
          FROM public.n6_strategy_match_change change, authority
          WHERE change.principal_id =
                (authority.value->>'principal_id')::bigint
            AND change.principal_type = authority.value->>'principal_type'
            AND change.user_id = (authority.value->>'user_id')::bigint
            AND change.surface_kind = 'observation'
        ), 0)
      ),
      'quality', pg_catalog.jsonb_build_object(
        'qualified_match', pg_catalog.jsonb_build_object(
          'status', CASE
            WHEN EXISTS (SELECT 1 FROM pending_revision) THEN 'rebuilding'
            WHEN NOT EXISTS (SELECT 1 FROM active_revision) THEN 'not_ready'
            WHEN EXISTS (
              SELECT 1 FROM active_revision
              WHERE replay_status <> 'passed'
            ) THEN 'pending'
            ELSE 'ready'
          END,
          'row_count', (SELECT pg_catalog.count(*) FROM match_rows),
          'levels', pg_catalog.jsonb_build_array('STRONG', 'MEDIUM')
        ),
        'observation', pg_catalog.jsonb_build_object(
          'status', CASE
            WHEN EXISTS (SELECT 1 FROM pending_revision) THEN 'rebuilding'
            WHEN NOT EXISTS (SELECT 1 FROM active_revision) THEN 'not_ready'
            WHEN EXISTS (
              SELECT 1 FROM active_revision
              WHERE replay_status <> 'passed'
            ) THEN 'pending'
            ELSE 'ready'
          END,
          'row_count', (SELECT pg_catalog.count(*) FROM observation_rows),
          'weak_count', (
            SELECT pg_catalog.count(*) FROM observation_rows row
            WHERE row.observation_kind = 'weak_span'
          ),
          'stale_count', (
            SELECT pg_catalog.count(*) FROM observation_rows row
            WHERE row.observation_kind = 'stale_after_confirmation'
          )
        )
      )
    )
  END
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_strategy_center_changes(
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
           change.surface_kind,
           change.selection_revision_id,
           change.strategy_match_projection_id,
           change.strategy_observation_projection_id,
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
            'surface_kind', row.surface_kind,
            'trade_date', row.trade_date,
            'selection_revision_id', row.selection_revision_id,
            'strategy_match_projection_id',
              row.strategy_match_projection_id,
            'strategy_observation_projection_id',
              row.strategy_observation_projection_id,
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

CREATE OR REPLACE FUNCTION public.n6_btrack_strategy_selection_put(
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
  existing_versions text[];
  existing_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  active_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  new_revision public.n6_user_strategy_selection_revision%ROWTYPE;
  effective_trade_date date;
  target_package_version text;
  target_package_status text;
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
    SELECT pg_catalog.array_agg(item.package_key ORDER BY item.package_key),
           pg_catalog.array_agg(
             item.package_version ORDER BY item.package_key
           )
      INTO existing_keys, existing_versions
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
      'selected_package_keys', existing_keys,
      'selected_package_versions', existing_versions
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

  SELECT catalog.package_version, catalog.package_status
    INTO STRICT target_package_version, target_package_status
  FROM public.n6_strategy_package_catalog catalog
  WHERE catalog.package_key = 'package_1'
    AND catalog.package_status IN ('selectable', 'active')
  ORDER BY CASE catalog.package_status
             WHEN 'selectable' THEN 0
             ELSE 1
           END,
           catalog.package_version DESC
  LIMIT 1;

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
    AND catalog.package_version = target_package_version
    AND catalog.package_status = target_package_status;
  IF selection_catalog_count <> pg_catalog.cardinality(normalized_keys)
     OR selection_policy_hash IS NULL THEN
    RAISE EXCEPTION 'strategy_selection_catalog_authority_missing';
  END IF;

  INSERT INTO public.n6_user_strategy_selection_revision (
    principal_id, principal_type, user_id, revision_no,
    selection_status, replay_status, request_id, effective_trade_date,
    previous_revision_id, selection_policy_hash, created_by_user_id,
    selection_metadata_json
  ) VALUES (
    (authority->>'principal_id')::bigint,
    authority->>'principal_type',
    (authority->>'user_id')::bigint,
    active_revision.revision_no + 1,
    'pending', 'pending', p_request_id, effective_trade_date,
    active_revision.selection_revision_id, selection_policy_hash,
    (authority->>'user_id')::bigint,
    pg_catalog.jsonb_build_object(
      'source', 'n6_strategy_center_selection_api',
      'package_version', target_package_version,
      'package_status', target_package_status,
      'requires_current_trade_date_replay', true
    )
  ) RETURNING * INTO new_revision;

  INSERT INTO public.n6_user_strategy_selection_item (
    selection_revision_id, package_key, package_version
  )
  SELECT new_revision.selection_revision_id,
         key.value,
         target_package_version
  FROM pg_catalog.unnest(normalized_keys) key(value)
  ORDER BY key.value;

  RETURN pg_catalog.jsonb_build_object(
    'selection_revision_id', new_revision.selection_revision_id,
    'revision_no', new_revision.revision_no,
    'selection_status', new_revision.selection_status,
    'replay_status', new_revision.replay_status,
    'effective_trade_date', new_revision.effective_trade_date,
    'selected_package_keys', normalized_keys,
    'selected_package_version', target_package_version
  );
END
$function$;

REVOKE ALL ON TABLE public.n6_strategy_observation_projection
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;
REVOKE ALL ON SEQUENCE
  public.n6_strategy_observation_proje_strategy_observation_projecti_seq
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;
REVOKE ALL ON FUNCTION
  public.n6_btrack_strategy_center_state(text),
  public.n6_btrack_strategy_center_changes(text,bigint,integer),
  public.n6_btrack_strategy_selection_put(text,text[],bigint,text)
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

GRANT EXECUTE ON FUNCTION
  public.n6_btrack_strategy_center_state(text),
  public.n6_btrack_strategy_center_changes(text,bigint,integer),
  public.n6_btrack_strategy_selection_put(text,text[],bigint,text)
TO n6_btrack_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.n6_strategy_observation_projection
TO n6_strategy_worker;
GRANT USAGE, SELECT ON SEQUENCE
  public.n6_strategy_observation_proje_strategy_observation_projecti_seq
TO n6_strategy_worker;

DO $postflight$
BEGIN
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v2'
      AND catalog.package_status = 'selectable'
      AND catalog.default_selected = false
      AND catalog.policy_hash IN (
        '0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58',
        '12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb'
      )
  ) <> 2 THEN
    RAISE EXCEPTION '081 v2 catalog postflight failed';
  END IF;
  IF (
    SELECT pg_catalog.count(*)
    FROM public.n6_strategy_package_catalog catalog
    WHERE catalog.package_version = 'v1'
      AND catalog.package_status = 'active'
      AND catalog.package_key IN ('package_1', 'package_2')
  ) <> 2 THEN
    RAISE EXCEPTION '081 v1 compatibility postflight failed';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.n6_user_strategy_selection_item item
    WHERE item.package_version = 'v2'
  ) THEN
    RAISE EXCEPTION '081 unexpectedly created a v2 user selection';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_strategy_observation_projection'
     ) IS NULL
     OR NOT EXISTS (
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
     ) THEN
    RAISE EXCEPTION '081 additive schema postflight failed';
  END IF;
  IF NOT pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.n6_strategy_observation_projection',
       'SELECT,INSERT,UPDATE,DELETE'
     )
     OR pg_catalog.has_table_privilege(
       'n6_btrack_web',
       'public.n6_strategy_observation_projection',
       'SELECT,INSERT,UPDATE,DELETE'
     )
     OR pg_catalog.has_table_privilege(
       'n6_virtual_executor',
       'public.n6_strategy_observation_projection',
       'SELECT,INSERT,UPDATE,DELETE'
     ) THEN
    RAISE EXCEPTION '081 least privilege postflight failed';
  END IF;
END
$postflight$;

COMMIT;
