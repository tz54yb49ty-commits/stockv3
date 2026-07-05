-- N6 037 view readonly permission rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: undo only 037 permission changes. Do not remove 036 tables/views.
-- Boundary: no business rows, no N5 outbox change, no N6_UI_v1/API/projection
-- change, no worker, no delivery/push/voice/mobile/sim/position/real trade.

BEGIN;

DO $$
DECLARE
  v_role_oid OID;
  v_owned_object_count BIGINT;
BEGIN
  SELECT to_regrole('n6_ui_readonly_role') INTO v_role_oid;

  IF v_role_oid IS NULL THEN
    RAISE EXCEPTION '037 permission rollback blocked: role n6_ui_readonly_role does not exist';
  END IF;

  IF to_regclass('public.v_n6_stock_condition_display_basis') IS NULL
    OR to_regclass('public.v_n6_index_condition_display_basis') IS NULL
    OR to_regclass('public.v_n6_board_condition_display_basis') IS NULL
    OR to_regclass('public.v_n6_index_membership_fact') IS NULL
    OR to_regclass('public.v_n6_board_membership_fact') IS NULL THEN
    RAISE EXCEPTION '037 permission rollback blocked: one or more 036 views are missing';
  END IF;

  SELECT count(*) INTO v_owned_object_count
  FROM pg_class
  WHERE relowner = v_role_oid;

  IF v_owned_object_count <> 0 THEN
    RAISE EXCEPTION '037 permission rollback blocked: n6_ui_readonly_role owns % objects', v_owned_object_count;
  END IF;
END $$;

REVOKE SELECT ON TABLE
  v_n6_stock_condition_display_basis,
  v_n6_index_condition_display_basis,
  v_n6_board_condition_display_basis,
  v_n6_index_membership_fact,
  v_n6_board_membership_fact
FROM n6_ui_readonly_role;

REVOKE USAGE ON SCHEMA public FROM n6_ui_readonly_role;

DO $$
DECLARE
  v_role_oid OID;
  v_role_comment TEXT;
BEGIN
  SELECT to_regrole('n6_ui_readonly_role') INTO v_role_oid;

  IF v_role_oid IS NOT NULL THEN
    SELECT shobj_description(v_role_oid, 'pg_authid') INTO v_role_comment;

    IF v_role_comment = 'created_by_037_n6_view_readonly_permission' THEN
      DROP ROLE n6_ui_readonly_role;
    END IF;
  END IF;
END $$;

COMMIT;
