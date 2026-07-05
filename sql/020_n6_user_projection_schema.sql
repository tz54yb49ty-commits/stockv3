-- N6 user projection MVP additive schema draft.
-- Do not execute without explicit user confirmation.
-- Scope: create N6-owned user, projection, notification queue, and shadow sim tables only.
-- Boundary: no N1-N5 mutation, no N5 outbox consumption, no voice/mobile push, no real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS user_account (
  user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  login_name TEXT NOT NULL,
  display_name TEXT,
  password_hash TEXT NOT NULL,
  password_hash_algo TEXT NOT NULL,
  password_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  created_by_user_id BIGINT REFERENCES user_account(user_id),
  deleted_by_user_id BIGINT REFERENCES user_account(user_id),
  deleted_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  user_policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(login_name),
  CHECK (length(login_name) >= 3),
  CHECK (password_hash <> ''),
  CHECK (password_hash_algo <> ''),
  CHECK (jsonb_typeof(user_policy_json) = 'object'),
  CHECK ((status = 'deleted' AND deleted_at IS NOT NULL) OR status <> 'deleted')
);

CREATE TABLE IF NOT EXISTS user_session (
  user_session_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  session_token_hash TEXT NOT NULL,
  session_token_hash_algo TEXT NOT NULL DEFAULT 'sha256',
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  client_info_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(session_token_hash),
  CHECK (session_token_hash <> ''),
  CHECK (session_token_hash_algo <> ''),
  CHECK (expires_at > issued_at),
  CHECK (revoked_at IS NULL OR revoked_at >= issued_at),
  CHECK (jsonb_typeof(client_info_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_filter_profile (
  user_filter_profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  profile_name TEXT NOT NULL DEFAULT 'MVP default',
  is_default BOOLEAN NOT NULL DEFAULT false,
  enable_chase BOOLEAN NOT NULL DEFAULT true,
  enable_ultra_short BOOLEAN NOT NULL DEFAULT true,
  enable_short BOOLEAN NOT NULL DEFAULT true,
  enable_mid BOOLEAN NOT NULL DEFAULT true,
  enable_long BOOLEAN NOT NULL DEFAULT true,
  strong_board_rule_json JSONB NOT NULL DEFAULT '{"period_transition_y":"volume_up","period_transition_q":"volume_up","period_transition_m":"volume_up"}'::JSONB,
  top_index_strategy_rule_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  permission_scope TEXT NOT NULL DEFAULT 'self' CHECK (permission_scope IN ('self', 'admin', 'system')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, profile_name),
  CHECK (profile_name <> ''),
  CHECK (jsonb_typeof(strong_board_rule_json) = 'object'),
  CHECK (jsonb_typeof(top_index_strategy_rule_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_watchlist (
  user_watchlist_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  watchlist_name TEXT NOT NULL,
  watchlist_type TEXT NOT NULL DEFAULT 'manual' CHECK (watchlist_type IN ('manual', 'system', 'strategy')),
  permission_scope TEXT NOT NULL DEFAULT 'self' CHECK (permission_scope IN ('self', 'admin', 'system')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, watchlist_name),
  CHECK (watchlist_name <> '')
);

CREATE TABLE IF NOT EXISTS user_watchlist_item (
  user_watchlist_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_watchlist_id BIGINT NOT NULL REFERENCES user_watchlist(user_watchlist_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT,
  name TEXT,
  board_code TEXT,
  board_name TEXT,
  source_reason TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_watchlist_id, asset_kind, identity_key),
  CHECK (identity_key <> '')
);

CREATE TABLE IF NOT EXISTS user_projection_run (
  user_projection_run_id TEXT PRIMARY KEY,
  projection_contract_version TEXT NOT NULL DEFAULT 'N6-user-projection-mvp-v1',
  source_layer TEXT NOT NULL DEFAULT 'N5_action' CHECK (source_layer = 'N5_action'),
  source_action_run_id TEXT NOT NULL,
  source_n5_outbox_range JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_event_types TEXT[] NOT NULL DEFAULT ARRAY['ActionEvent', 'HintEvent']::TEXT[],
  source_display_condition_run_id TEXT,
  input_event_count INTEGER NOT NULL DEFAULT 0 CHECK (input_event_count >= 0),
  output_projection_count INTEGER NOT NULL DEFAULT 0 CHECK (output_projection_count >= 0),
  p0_count INTEGER NOT NULL DEFAULT 0 CHECK (p0_count >= 0),
  p1_count INTEGER NOT NULL DEFAULT 0 CHECK (p1_count >= 0),
  p2_count INTEGER NOT NULL DEFAULT 0 CHECK (p2_count >= 0),
  quality_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready', 'blocked', 'executing', 'passed', 'failed', 'rolled_back')),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (source_action_run_id <> ''),
  CHECK (source_event_types <@ ARRAY['ActionEvent', 'HintEvent']::TEXT[]),
  CHECK (jsonb_typeof(source_n5_outbox_range) = 'object'),
  CHECK (jsonb_typeof(quality_summary_json) = 'object'),
  CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS user_signal_projection (
  user_signal_projection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_projection_run_id TEXT NOT NULL REFERENCES user_projection_run(user_projection_run_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  user_filter_profile_id BIGINT REFERENCES user_filter_profile(user_filter_profile_id),
  user_watchlist_id BIGINT REFERENCES user_watchlist(user_watchlist_id),
  permission_scope TEXT NOT NULL DEFAULT 'self' CHECK (permission_scope IN ('self', 'admin', 'system')),
  source_layer TEXT NOT NULL DEFAULT 'N5_action' CHECK (source_layer = 'N5_action'),
  source_event_id TEXT NOT NULL,
  source_outbox_id BIGINT,
  source_event_type TEXT NOT NULL CHECK (source_event_type IN ('ActionEvent', 'HintEvent')),
  source_event_schema_version TEXT NOT NULL,
  source_event_dedup_key TEXT NOT NULL,
  source_action_event_id TEXT NOT NULL,
  source_action_run_id TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')),
  target_price NUMERIC,
  current_price NUMERIC,
  expected_return_pct NUMERIC,
  board_identity_key TEXT,
  board_code TEXT,
  board_name TEXT,
  source_display_table TEXT CHECK (source_display_table IS NULL OR source_display_table IN ('stock_condition_display_basis', 'index_condition_display_basis', 'board_condition_display_basis')),
  source_condition_display_basis_id BIGINT,
  source_condition_display_run_id TEXT,
  projection_status TEXT NOT NULL DEFAULT 'visible' CHECK (projection_status IN ('visible', 'hidden', 'suppressed', 'discarded', 'blocked')),
  source_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  display_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_projection_run_id, user_id, source_event_id),
  CHECK (source_event_id <> ''),
  CHECK (source_event_schema_version <> ''),
  CHECK (source_event_dedup_key <> ''),
  CHECK (source_action_event_id <> ''),
  CHECK (source_action_run_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (jsonb_typeof(source_payload_json) = 'object'),
  CHECK (jsonb_typeof(display_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_signal_card (
  user_signal_card_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_signal_projection_id BIGINT NOT NULL REFERENCES user_signal_projection(user_signal_projection_id),
  user_projection_run_id TEXT NOT NULL REFERENCES user_projection_run(user_projection_run_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  card_type TEXT NOT NULL DEFAULT 'signal' CHECK (card_type IN ('signal', 'hint', 'buy_candidate', 'sell_candidate')),
  card_status TEXT NOT NULL DEFAULT 'active' CHECK (card_status IN ('active', 'hidden', 'acknowledged', 'discarded', 'blocked')),
  display_priority INTEGER NOT NULL DEFAULT 100 CHECK (display_priority >= 0),
  title TEXT NOT NULL,
  summary TEXT,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')),
  target_price NUMERIC,
  current_price NUMERIC,
  expected_return_pct NUMERIC,
  board_code TEXT,
  board_name TEXT,
  source_action_run_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  card_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_projection_run_id, user_id, user_signal_projection_id),
  CHECK (title <> ''),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (source_action_run_id <> ''),
  CHECK (source_event_id <> ''),
  CHECK (jsonb_typeof(card_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_signal_decision (
  user_signal_decision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  user_signal_projection_id BIGINT NOT NULL REFERENCES user_signal_projection(user_signal_projection_id),
  user_signal_card_id BIGINT REFERENCES user_signal_card(user_signal_card_id),
  decision_type TEXT NOT NULL CHECK (decision_type IN ('buy', 'sell', 'discard')),
  decision_status TEXT NOT NULL DEFAULT 'recorded' CHECK (decision_status IN ('recorded', 'cancelled')),
  intent_qty NUMERIC,
  intent_amount NUMERIC,
  intent_price NUMERIC,
  execution_mode TEXT NOT NULL DEFAULT 'n6_intent_only' CHECK (execution_mode = 'n6_intent_only'),
  real_trade_status TEXT NOT NULL DEFAULT 'not_applicable' CHECK (real_trade_status = 'not_applicable'),
  decision_note TEXT,
  decision_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (intent_qty IS NULL OR intent_qty >= 0),
  CHECK (intent_amount IS NULL OR intent_amount >= 0),
  CHECK (intent_price IS NULL OR intent_price >= 0),
  CHECK (jsonb_typeof(decision_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_notification_queue (
  user_notification_queue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  user_projection_run_id TEXT REFERENCES user_projection_run(user_projection_run_id),
  user_signal_projection_id BIGINT REFERENCES user_signal_projection(user_signal_projection_id),
  user_signal_card_id BIGINT REFERENCES user_signal_card(user_signal_card_id),
  notification_source TEXT NOT NULL CHECK (notification_source IN ('index_signal', 'board_signal', 'stock_filter_signal', 'n5_action_event', 'n5_hint_event')),
  queue_status TEXT NOT NULL DEFAULT 'queued_only' CHECK (queue_status IN ('queued_only', 'suppressed', 'discarded', 'ready_for_future_push')),
  channel TEXT NOT NULL DEFAULT 'broadcast_queue' CHECK (channel IN ('broadcast_queue', 'voice_future', 'mobile_future', 'in_app_future')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100 CHECK (priority >= 0),
  source_event_id TEXT,
  source_action_run_id TEXT,
  asset_kind TEXT CHECK (asset_kind IS NULL OR asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT,
  notification_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (title <> ''),
  CHECK (message <> ''),
  CHECK (jsonb_typeof(notification_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_sim_account (
  user_sim_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  account_name TEXT NOT NULL DEFAULT 'MVP T+1 shadow account',
  initial_cash NUMERIC NOT NULL DEFAULT 1000000000 CHECK (initial_cash >= 0),
  cash_balance NUMERIC NOT NULL DEFAULT 1000000000 CHECK (cash_balance >= 0),
  frozen_cash NUMERIC NOT NULL DEFAULT 0 CHECK (frozen_cash >= 0),
  settlement_mode TEXT NOT NULL DEFAULT 'T_PLUS_1' CHECK (settlement_mode = 'T_PLUS_1'),
  account_status TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('active', 'disabled', 'deleted')),
  sim_policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, account_name),
  CHECK (account_name <> ''),
  CHECK (jsonb_typeof(sim_policy_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_sim_order (
  user_sim_order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_sim_account_id BIGINT NOT NULL REFERENCES user_sim_account(user_sim_account_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  user_signal_decision_id BIGINT REFERENCES user_signal_decision(user_signal_decision_id),
  user_signal_projection_id BIGINT REFERENCES user_signal_projection(user_signal_projection_id),
  sim_run_id TEXT,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  order_status TEXT NOT NULL DEFAULT 'draft' CHECK (order_status IN ('draft', 'pending_sim', 'filled_sim', 'cancelled', 'discarded', 'rejected')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  order_qty NUMERIC NOT NULL CHECK (order_qty >= 0),
  order_price NUMERIC CHECK (order_price IS NULL OR order_price >= 0),
  order_amount NUMERIC CHECK (order_amount IS NULL OR order_amount >= 0),
  trade_date TEXT,
  t_plus_one_locked BOOLEAN NOT NULL DEFAULT true,
  available_from_trade_date TEXT,
  real_trade_submitted BOOLEAN NOT NULL DEFAULT false CHECK (real_trade_submitted = false),
  order_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (trade_date IS NULL OR trade_date ~ '^[0-9]{8}$'),
  CHECK (available_from_trade_date IS NULL OR available_from_trade_date ~ '^[0-9]{8}$'),
  CHECK (jsonb_typeof(order_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_sim_trade (
  user_sim_trade_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_sim_order_id BIGINT NOT NULL REFERENCES user_sim_order(user_sim_order_id),
  user_sim_account_id BIGINT NOT NULL REFERENCES user_sim_account(user_sim_account_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  sim_run_id TEXT,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  trade_qty NUMERIC NOT NULL CHECK (trade_qty >= 0),
  trade_price NUMERIC NOT NULL CHECK (trade_price >= 0),
  trade_amount NUMERIC NOT NULL CHECK (trade_amount >= 0),
  fee_amount NUMERIC NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
  trade_date TEXT NOT NULL,
  settle_date TEXT,
  t_plus_one_locked BOOLEAN NOT NULL DEFAULT true,
  available_from_trade_date TEXT,
  real_trade_submitted BOOLEAN NOT NULL DEFAULT false CHECK (real_trade_submitted = false),
  trade_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (settle_date IS NULL OR settle_date ~ '^[0-9]{8}$'),
  CHECK (available_from_trade_date IS NULL OR available_from_trade_date ~ '^[0-9]{8}$'),
  CHECK (jsonb_typeof(trade_payload_json) = 'object')
);

CREATE TABLE IF NOT EXISTS user_sim_position (
  user_sim_position_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_sim_account_id BIGINT NOT NULL REFERENCES user_sim_account(user_sim_account_id),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  sim_run_id TEXT,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  total_qty NUMERIC NOT NULL DEFAULT 0 CHECK (total_qty >= 0),
  available_qty NUMERIC NOT NULL DEFAULT 0 CHECK (available_qty >= 0),
  t_plus_one_locked_qty NUMERIC NOT NULL DEFAULT 0 CHECK (t_plus_one_locked_qty >= 0),
  avg_cost NUMERIC CHECK (avg_cost IS NULL OR avg_cost >= 0),
  last_price NUMERIC CHECK (last_price IS NULL OR last_price >= 0),
  market_value NUMERIC CHECK (market_value IS NULL OR market_value >= 0),
  unrealized_pnl NUMERIC,
  opened_trade_date TEXT,
  available_from_trade_date TEXT,
  position_status TEXT NOT NULL DEFAULT 'open' CHECK (position_status IN ('open', 'closed', 'disabled')),
  real_position BOOLEAN NOT NULL DEFAULT false CHECK (real_position = false),
  position_payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_sim_account_id, asset_kind, identity_key),
  CHECK (available_qty <= total_qty),
  CHECK (t_plus_one_locked_qty <= total_qty),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (opened_trade_date IS NULL OR opened_trade_date ~ '^[0-9]{8}$'),
  CHECK (available_from_trade_date IS NULL OR available_from_trade_date ~ '^[0-9]{8}$'),
  CHECK (jsonb_typeof(position_payload_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_user_filter_profile_default
ON user_filter_profile(user_id, is_default);

CREATE INDEX IF NOT EXISTS idx_user_account_status
ON user_account(status, role);

CREATE INDEX IF NOT EXISTS idx_user_session_user_expiry
ON user_session(user_id, expires_at, revoked_at);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_user_status
ON user_watchlist(user_id, status);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_item_identity
ON user_watchlist_item(asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_user_projection_run_source
ON user_projection_run(source_action_run_id, status);

CREATE INDEX IF NOT EXISTS idx_user_signal_projection_user_status
ON user_signal_projection(user_id, projection_status, direction, signal_type);

CREATE INDEX IF NOT EXISTS idx_user_signal_projection_source
ON user_signal_projection(source_action_run_id, source_event_id);

CREATE INDEX IF NOT EXISTS idx_user_signal_projection_identity
ON user_signal_projection(asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_user_signal_card_user_status
ON user_signal_card(user_id, card_status, display_priority);

CREATE INDEX IF NOT EXISTS idx_user_signal_decision_user_type
ON user_signal_decision(user_id, decision_type, decision_status);

CREATE INDEX IF NOT EXISTS idx_user_notification_queue_user_status
ON user_notification_queue(user_id, queue_status, priority);

CREATE INDEX IF NOT EXISTS idx_user_notification_queue_source
ON user_notification_queue(notification_source, source_action_run_id, source_event_id);

CREATE INDEX IF NOT EXISTS idx_user_sim_account_user_status
ON user_sim_account(user_id, account_status);

CREATE INDEX IF NOT EXISTS idx_user_sim_order_account_status
ON user_sim_order(user_sim_account_id, order_status, side);

CREATE INDEX IF NOT EXISTS idx_user_sim_order_identity
ON user_sim_order(asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_user_sim_trade_account_date
ON user_sim_trade(user_sim_account_id, trade_date, side);

CREATE INDEX IF NOT EXISTS idx_user_sim_position_account_identity
ON user_sim_position(user_sim_account_id, asset_kind, identity_key);

COMMIT;
