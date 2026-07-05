-- N6 Track B owner/principal/account additive schema draft.
-- Do not execute without explicit user confirmation.
-- Scope: create N6-owned Track B principal/account/AI/strategy/watchlist objects
-- and N6 read-only display/membership views only.
-- Boundary: no N6_UI_v1/API/projection/shadow-pipeline change, no N5 outbox
-- status change, no worker, no delivery/push/voice/mobile/sim/position/real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_principal (
  principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('human_user', 'ai_user', 'admin', 'system')),
  owner_user_id BIGINT REFERENCES user_account(user_id),
  principal_status TEXT NOT NULL DEFAULT 'active'
    CHECK (principal_status IN ('active', 'disabled', 'deleted', 'system_reserved')),
  principal_label TEXT,
  principal_policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(principal_id, principal_type),
  CHECK (principal_label IS NULL OR principal_label <> ''),
  CHECK (jsonb_typeof(principal_policy_json) = 'object'),
  CHECK (
    (principal_type IN ('human_user', 'admin') AND owner_user_id IS NOT NULL)
    OR (principal_type IN ('ai_user', 'system') AND owner_user_id IS NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_n6_principal_owner_user
ON n6_principal(principal_type, owner_user_id)
WHERE owner_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_n6_principal_type_status
ON n6_principal(principal_type, principal_status);

CREATE TABLE IF NOT EXISTS n6_ai_user (
  ai_user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL UNIQUE,
  principal_type TEXT NOT NULL DEFAULT 'ai_user' CHECK (principal_type = 'ai_user'),
  ai_name TEXT NOT NULL,
  strategy_profile_id BIGINT,
  status TEXT NOT NULL DEFAULT 'sandbox_only'
    CHECK (status IN ('active', 'disabled', 'deleted', 'sandbox_only')),
  readable_scope_policy JSONB NOT NULL DEFAULT '{
    "allowed_sources": [
      "v_n6_stock_condition_display_basis",
      "v_n6_index_condition_display_basis",
      "v_n6_board_condition_display_basis",
      "v_n6_index_membership_fact",
      "v_n6_board_membership_fact",
      "user_projection_run",
      "user_signal_projection",
      "user_signal_card",
      "user_notification_queue",
      "reviewed_artifacts"
    ],
    "forbidden_sources": [
      "raw_k",
      "live_market_data_direct",
      "condition_basis",
      "condition_pool",
      "minute_target_scope",
      "n3_raw_facts",
      "n4_raw_facts",
      "n5_raw_facts",
      "real_account",
      "real_funds",
      "real_position",
      "broker_session",
      "real_trade_api"
    ]
  }'::JSONB,
  readable_scope_policy_version TEXT NOT NULL DEFAULT 'n6_ai_readable_scope_policy_v1',
  readable_scope_policy_hash TEXT,
  created_by_user_id BIGINT REFERENCES user_account(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (ai_name <> ''),
  CHECK (readable_scope_policy_version <> ''),
  CHECK (readable_scope_policy_hash IS NULL OR readable_scope_policy_hash <> ''),
  CHECK (jsonb_typeof(readable_scope_policy) = 'object'),
  CHECK (readable_scope_policy ? 'allowed_sources'),
  CHECK (readable_scope_policy ? 'forbidden_sources'),
  CHECK (jsonb_typeof(readable_scope_policy->'allowed_sources') = 'array'),
  CHECK (jsonb_typeof(readable_scope_policy->'forbidden_sources') = 'array')
);

CREATE INDEX IF NOT EXISTS idx_n6_ai_user_status
ON n6_ai_user(status);

CREATE INDEX IF NOT EXISTS idx_n6_ai_user_strategy_profile
ON n6_ai_user(strategy_profile_id)
WHERE strategy_profile_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS n6_principal_account (
  account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  account_type TEXT NOT NULL CHECK (account_type IN ('virtual', 'ai_virtual', 'admin_shadow')),
  virtual_account_id BIGINT,
  virtual_account_source TEXT NOT NULL DEFAULT 'future_virtual_account'
    CHECK (virtual_account_source IN ('future_virtual_account', 'user_sim_account_adapter')),
  account_status TEXT NOT NULL DEFAULT 'active'
    CHECK (account_status IN ('active', 'disabled', 'deleted', 'closed')),
  account_policy_version TEXT NOT NULL DEFAULT 'n6_virtual_account_policy_v1',
  account_policy_hash TEXT,
  account_policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(principal_id, account_type, virtual_account_source, virtual_account_id),
  CHECK (virtual_account_id IS NULL OR virtual_account_id > 0),
  CHECK (account_policy_version <> ''),
  CHECK (account_policy_hash IS NULL OR account_policy_hash <> ''),
  CHECK (jsonb_typeof(account_policy_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_n6_principal_account_owner_status
ON n6_principal_account(principal_id, account_status);

CREATE INDEX IF NOT EXISTS idx_n6_principal_account_type_status
ON n6_principal_account(account_type, account_status);

CREATE INDEX IF NOT EXISTS idx_n6_principal_account_virtual_ref
ON n6_principal_account(virtual_account_source, virtual_account_id)
WHERE virtual_account_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS n6_watchlist_ownership (
  watchlist_ownership_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  watchlist_id BIGINT NOT NULL REFERENCES user_watchlist(user_watchlist_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  visibility TEXT NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('private', 'shared', 'admin', 'public_leaderboard')),
  ownership_status TEXT NOT NULL DEFAULT 'active'
    CHECK (ownership_status IN ('active', 'disabled', 'deleted')),
  ownership_policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(watchlist_id, principal_id),
  CHECK (jsonb_typeof(ownership_policy_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_n6_watchlist_ownership_principal
ON n6_watchlist_ownership(principal_id, visibility, ownership_status);

CREATE INDEX IF NOT EXISTS idx_n6_watchlist_ownership_watchlist
ON n6_watchlist_ownership(watchlist_id, ownership_status);

CREATE TABLE IF NOT EXISTS n6_strategy (
  strategy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  strategy_name TEXT NOT NULL,
  strategy_type TEXT NOT NULL
    CHECK (strategy_type IN ('manual_filter', 'ai_generated', 'marketplace', 'system_default')),
  policy_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'reviewed', 'active', 'disabled', 'archived', 'deleted')),
  visibility TEXT NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('private', 'shared', 'admin', 'public_leaderboard')),
  risk_labels TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  strategy_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_by_principal_id BIGINT REFERENCES n6_principal(principal_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(principal_id, strategy_name, policy_version),
  CHECK (strategy_name <> ''),
  CHECK (policy_version <> ''),
  CHECK (policy_hash <> ''),
  CHECK (risk_labels <@ ARRAY[
    'high_volatility',
    'drawdown_risk',
    'insufficient_history',
    'experimental',
    'ai_generated'
  ]::TEXT[]),
  CHECK (jsonb_typeof(strategy_payload_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_n6_strategy_owner_status
ON n6_strategy(principal_id, status);

CREATE INDEX IF NOT EXISTS idx_n6_strategy_type_status
ON n6_strategy(strategy_type, status);

CREATE INDEX IF NOT EXISTS idx_n6_strategy_policy
ON n6_strategy(policy_hash, policy_version);

DO $$
BEGIN
  IF to_regclass('public.v_n6_stock_condition_display_basis') IS NULL THEN
    EXECUTE $view$
      CREATE VIEW v_n6_stock_condition_display_basis AS
      SELECT
        'stock'::TEXT AS asset_kind,
        stock_condition_display_basis_id AS source_display_basis_id,
        run_id,
        for_trade_date,
        source_trade_date,
        prev_trade_date,
        stock_identity_key AS identity_key,
        stock_identity_key,
        code,
        exchange,
        name,
        display_code,
        display_name,
        display_title,
        display_summary,
        selected_directions,
        selected_condition_keys,
        selected_signal_types,
        selected_lanes,
        selected_monitor_types,
        condition_summary_json,
        target_price_summary_json,
        reference_period_summary_json,
        period_grade_summary_json,
        period_transition_summary_json,
        period_grade_y,
        period_grade_q,
        period_grade_m,
        period_grade_w,
        period_grade_d,
        period_transition_y,
        period_transition_q,
        period_transition_m,
        period_transition_w,
        period_transition_d,
        buy_target_price,
        sell_target_price,
        up_sell_reference_period,
        down_buy_reference_period,
        clear_sell_ref_period,
        total_mv,
        circ_mv,
        score,
        recommendation_level,
        recommendation_reason,
        main_index_identity_key,
        main_index_code,
        main_index_name,
        preferred_board_identity_key,
        preferred_board_code,
        preferred_board_name,
        linked_board_identity_keys,
        display_policy_name,
        display_policy_hash,
        condition_pool_policy_name,
        condition_pool_policy_hash,
        scope_policy_name,
        scope_policy_hash,
        display_scope_reason,
        selected_reason,
        excluded_reason,
        source_version,
        display_status,
        quality_status,
        quality_reason,
        missing_fields_json,
        created_at,
        updated_at
      FROM stock_condition_display_basis
    $view$;
  END IF;
END $$;

DO $$
BEGIN
  IF to_regclass('public.v_n6_index_condition_display_basis') IS NULL THEN
    EXECUTE $view$
      CREATE VIEW v_n6_index_condition_display_basis AS
      SELECT
        'index'::TEXT AS asset_kind,
        index_condition_display_basis_id AS source_display_basis_id,
        run_id,
        for_trade_date,
        source_trade_date,
        prev_trade_date,
        index_identity_key AS identity_key,
        index_identity_key,
        code,
        exchange,
        name,
        display_code,
        display_name,
        display_title,
        display_summary,
        fixed_index_member,
        selected_directions,
        selected_condition_keys,
        selected_signal_types,
        selected_lanes,
        selected_monitor_types,
        condition_summary_json,
        target_price_summary_json,
        reference_period_summary_json,
        period_grade_summary_json,
        period_transition_summary_json,
        period_grade_y,
        period_grade_q,
        period_grade_m,
        period_grade_w,
        period_grade_d,
        period_transition_y,
        period_transition_q,
        period_transition_m,
        period_transition_w,
        period_transition_d,
        buy_target_price,
        sell_target_price,
        up_sell_reference_period,
        down_buy_reference_period,
        clear_sell_ref_period,
        display_policy_name,
        display_policy_hash,
        condition_pool_policy_name,
        condition_pool_policy_hash,
        scope_policy_name,
        scope_policy_hash,
        display_scope_reason,
        selected_reason,
        excluded_reason,
        source_version,
        display_status,
        quality_status,
        quality_reason,
        missing_fields_json,
        created_at,
        updated_at
      FROM index_condition_display_basis
    $view$;
  END IF;
END $$;

DO $$
BEGIN
  IF to_regclass('public.v_n6_board_condition_display_basis') IS NULL THEN
    EXECUTE $view$
      CREATE VIEW v_n6_board_condition_display_basis AS
      SELECT
        'board'::TEXT AS asset_kind,
        board_condition_display_basis_id AS source_display_basis_id,
        run_id,
        for_trade_date,
        source_trade_date,
        prev_trade_date,
        board_identity_key AS identity_key,
        board_identity_key,
        board_code,
        board_name,
        board_type,
        display_code,
        display_name,
        display_title,
        display_summary,
        is_industry_board,
        selected_directions,
        selected_condition_keys,
        selected_signal_types,
        selected_lanes,
        selected_monitor_types,
        condition_summary_json,
        target_price_summary_json,
        reference_period_summary_json,
        period_grade_summary_json,
        period_transition_summary_json,
        period_grade_y,
        period_grade_q,
        period_grade_m,
        period_grade_w,
        period_grade_d,
        period_transition_y,
        period_transition_q,
        period_transition_m,
        period_transition_w,
        period_transition_d,
        buy_target_price,
        sell_target_price,
        up_sell_reference_period,
        down_buy_reference_period,
        clear_sell_ref_period,
        display_policy_name,
        display_policy_hash,
        condition_pool_policy_name,
        condition_pool_policy_hash,
        scope_policy_name,
        scope_policy_hash,
        display_scope_reason,
        selected_reason,
        excluded_reason,
        source_version,
        display_status,
        quality_status,
        quality_reason,
        missing_fields_json,
        created_at,
        updated_at
      FROM board_condition_display_basis
      WHERE board_type IN ('tdx_industry', 'tdx_concept', 'tdx_region', 'tdx_other')
    $view$;
  END IF;
END $$;

DO $$
BEGIN
  IF to_regclass('public.v_n6_index_membership_fact') IS NULL THEN
    EXECUTE $view$
      CREATE VIEW v_n6_index_membership_fact AS
      SELECT
        trade_date,
        index_identity_key,
        stock_identity_key,
        index_code,
        index_name,
        stock_code,
        stock_name,
        source,
        source_file,
        source_batch_id,
        source_version,
        created_at
      FROM index_membership_fact
    $view$;
  END IF;
END $$;

DO $$
BEGIN
  IF to_regclass('public.v_n6_board_membership_fact') IS NULL THEN
    EXECUTE $view$
      CREATE VIEW v_n6_board_membership_fact AS
      SELECT
        trade_date,
        board_identity_key,
        stock_identity_key,
        board_code,
        board_name,
        board_type,
        stock_code,
        stock_name,
        source,
        source_file,
        source_batch_id,
        source_version,
        created_at
      FROM board_membership_fact
      WHERE board_type IN ('tdx_industry', 'tdx_concept', 'tdx_region', 'tdx_other')
    $view$;
  END IF;
END $$;

COMMIT;
