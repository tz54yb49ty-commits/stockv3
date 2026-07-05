-- N6 037 view readonly permission migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: permission-only repair for 036 N6 Track B read-only views.
-- Boundary: no business rows, no N5 outbox change, no N6_UI_v1/API/projection
-- change, no worker, no delivery/push/voice/mobile/sim/position/real trade.

BEGIN;

DO $$
DECLARE
  v_role_name CONSTANT TEXT := 'n6_ui_readonly_role';
  v_role_exists BOOLEAN;
  v_forbidden_grants BIGINT;
BEGIN
  SELECT to_regrole(v_role_name) IS NOT NULL INTO v_role_exists;

  IF v_role_exists THEN
    SELECT count(*) INTO v_forbidden_grants
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND grantee = v_role_name
      AND (
        (
          table_name IN (
            'v_n6_stock_condition_display_basis',
            'v_n6_index_condition_display_basis',
            'v_n6_board_condition_display_basis',
            'v_n6_index_membership_fact',
            'v_n6_board_membership_fact'
          )
          AND privilege_type <> 'SELECT'
        )
        OR table_name IN (
          'n6_principal',
          'n6_ai_user',
          'n6_principal_account',
          'n6_watchlist_ownership',
          'n6_strategy'
        )
      );

    IF v_forbidden_grants <> 0 THEN
      RAISE EXCEPTION '037 permission migration blocked: role % has % unexpected grants', v_role_name, v_forbidden_grants;
    END IF;
  ELSE
    CREATE ROLE n6_ui_readonly_role NOLOGIN;
    COMMENT ON ROLE n6_ui_readonly_role IS 'created_by_037_n6_view_readonly_permission';
  END IF;
END $$;

REVOKE ALL PRIVILEGES ON TABLE
  v_n6_stock_condition_display_basis,
  v_n6_index_condition_display_basis,
  v_n6_board_condition_display_basis,
  v_n6_index_membership_fact,
  v_n6_board_membership_fact
FROM n6_ui_readonly_role;

REVOKE ALL PRIVILEGES ON TABLE
  n6_principal,
  n6_ai_user,
  n6_principal_account,
  n6_watchlist_ownership,
  n6_strategy
FROM n6_ui_readonly_role;

GRANT USAGE ON SCHEMA public TO n6_ui_readonly_role;

GRANT SELECT ON TABLE
  v_n6_stock_condition_display_basis,
  v_n6_index_condition_display_basis,
  v_n6_board_condition_display_basis,
  v_n6_index_membership_fact,
  v_n6_board_membership_fact
TO n6_ui_readonly_role;

COMMIT;
