-- N6 readonly view field widening rollback draft.
-- Scope: restore the original 036-era N6 readonly view definitions.
-- Boundary: no base table mutation, no N1/N2/N3/N4/N5/N6 fact mutation, no event infra mutation.
-- Do not execute without explicit rollback final gate approval and user confirmation.

BEGIN;

DO $$
DECLARE
  dependent_count INTEGER;
BEGIN
  IF to_regclass('public.v_n6_stock_condition_display_basis') IS NULL
     OR to_regclass('public.v_n6_index_condition_display_basis') IS NULL
     OR to_regclass('public.v_n6_board_condition_display_basis') IS NULL
     OR to_regclass('public.v_n6_index_membership_fact') IS NULL
     OR to_regclass('public.v_n6_board_membership_fact') IS NULL THEN
    RAISE EXCEPTION 'N6 readonly view field widening rollback blocked: one or more target views do not exist';
  END IF;

  SELECT COUNT(*)
    INTO dependent_count
  FROM pg_depend d
  JOIN pg_rewrite r ON r.oid = d.objid
  JOIN pg_class dependent_view ON dependent_view.oid = r.ev_class
  WHERE d.refobjid IN (
    to_regclass('public.v_n6_stock_condition_display_basis'),
    to_regclass('public.v_n6_index_condition_display_basis'),
    to_regclass('public.v_n6_board_condition_display_basis'),
    to_regclass('public.v_n6_index_membership_fact'),
    to_regclass('public.v_n6_board_membership_fact')
  )
  AND dependent_view.relname NOT IN (
    'v_n6_stock_condition_display_basis',
    'v_n6_index_condition_display_basis',
    'v_n6_board_condition_display_basis',
    'v_n6_index_membership_fact',
    'v_n6_board_membership_fact'
  );

  IF dependent_count > 0 THEN
    RAISE EXCEPTION 'N6 readonly view field widening rollback blocked: dependent views/functions exist (%)', dependent_count;
  END IF;
END $$;

DROP VIEW IF EXISTS v_n6_stock_condition_display_basis;
DROP VIEW IF EXISTS v_n6_index_condition_display_basis;
DROP VIEW IF EXISTS v_n6_board_condition_display_basis;
DROP VIEW IF EXISTS v_n6_index_membership_fact;
DROP VIEW IF EXISTS v_n6_board_membership_fact;

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
FROM stock_condition_display_basis;

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
FROM index_condition_display_basis;

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
WHERE board_type IN ('tdx_industry', 'tdx_concept', 'tdx_region', 'tdx_other');

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
FROM index_membership_fact;

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
WHERE board_type IN ('tdx_industry', 'tdx_concept', 'tdx_region', 'tdx_other');

GRANT SELECT ON TABLE
  v_n6_stock_condition_display_basis,
  v_n6_index_condition_display_basis,
  v_n6_board_condition_display_basis,
  v_n6_index_membership_fact,
  v_n6_board_membership_fact
TO n6_ui_readonly_role;

COMMIT;
