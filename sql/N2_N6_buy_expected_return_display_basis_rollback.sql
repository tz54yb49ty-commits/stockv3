-- Roll back N2 -> N6 buy_expected_return_pct display-basis pass-through.
-- Scope: remove only the additive display-basis column and rebuild N6 readonly views.
-- Do not execute without explicit rollback approval.

BEGIN;

DROP VIEW IF EXISTS v_n6_stock_condition_display_basis;
DROP VIEW IF EXISTS v_n6_index_condition_display_basis;
DROP VIEW IF EXISTS v_n6_board_condition_display_basis;

ALTER TABLE stock_condition_display_basis
  DROP COLUMN IF EXISTS buy_expected_return_pct;
ALTER TABLE index_condition_display_basis
  DROP COLUMN IF EXISTS buy_expected_return_pct;
ALTER TABLE board_condition_display_basis
  DROP COLUMN IF EXISTS buy_expected_return_pct;

CREATE OR REPLACE VIEW v_n6_stock_condition_display_basis AS
SELECT
  'stock'::TEXT AS asset_kind,
  display.stock_condition_display_basis_id AS source_display_basis_id,
  display.stock_identity_key AS identity_key,
  display.*
FROM stock_condition_display_basis AS display;

CREATE OR REPLACE VIEW v_n6_index_condition_display_basis AS
SELECT
  'index'::TEXT AS asset_kind,
  display.index_condition_display_basis_id AS source_display_basis_id,
  display.index_identity_key AS identity_key,
  display.*
FROM index_condition_display_basis AS display;

CREATE OR REPLACE VIEW v_n6_board_condition_display_basis AS
SELECT
  'board'::TEXT AS asset_kind,
  display.board_condition_display_basis_id AS source_display_basis_id,
  display.board_identity_key AS identity_key,
  display.*
FROM board_condition_display_basis AS display
WHERE display.board_type IN ('tdx_industry', 'tdx_concept', 'tdx_region', 'tdx_other');

GRANT SELECT ON TABLE
  v_n6_stock_condition_display_basis,
  v_n6_index_condition_display_basis,
  v_n6_board_condition_display_basis
TO n6_ui_readonly_role;

COMMIT;
