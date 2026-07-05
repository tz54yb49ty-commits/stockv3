-- V3 20260615 N6 full-universe user projection rollback
-- Scope: user_projection_run_id=v3_n6_user_projection_20260615_attachment_rule_canonical_v1
BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'hard-fail: reviewed manual rollback only for v3_n6_user_projection_20260615_attachment_rule_canonical_v1';
END $$;

DELETE FROM user_notification_queue WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_attachment_rule_canonical_v1';
DELETE FROM user_signal_card WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_attachment_rule_canonical_v1';
DELETE FROM user_signal_projection WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_attachment_rule_canonical_v1';
DELETE FROM user_projection_run WHERE user_projection_run_id = 'v3_n6_user_projection_20260615_attachment_rule_canonical_v1';

COMMIT;
