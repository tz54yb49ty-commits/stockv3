-- Dynamic N6 projection rollback guard for v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1
DO $$
BEGIN
  IF current_setting('ashare_v3.allow_dynamic_n6_projection_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'blocked: set ashare_v3.allow_dynamic_n6_projection_rollback=true before rollback';
  END IF;
END $$;

DELETE FROM user_notification_queue WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1';
DELETE FROM user_signal_card WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1';
DELETE FROM user_signal_projection WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1';
DELETE FROM user_projection_run WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1';
