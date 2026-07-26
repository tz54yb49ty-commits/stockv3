-- Rollback draft for 041. Do not execute without exact preflight.
-- Business history is never deleted. Rollback is blocked once proposal/lot rows exist.
-- 041 grants no role privileges, so there is no privilege rollback here.

BEGIN;

DO $$
DECLARE
  proposal_count BIGINT;
  lot_count BIGINT;
  position_v3_count BIGINT;
BEGIN
  SELECT count(*) INTO proposal_count FROM n6_virtual_trade_proposal;
  SELECT count(*) INTO lot_count FROM n6_virtual_position_lot;
  SELECT count(*) INTO position_v3_count
  FROM n6_virtual_position
  WHERE holding_episode_no <> 1
     OR first_open_trade_date IS NOT NULL
     OR locked_target_price IS NOT NULL
     OR target_price_status <> 'not_ready'
     OR target_price_source_signal_projection_id IS NOT NULL
     OR stop_loss_price IS NOT NULL
     OR stop_loss_status <> 'not_ready'
     OR stop_loss_source_quote_snapshot_id IS NOT NULL
     OR stop_loss_frozen_at IS NOT NULL
     OR stop_loss_effective_trade_date IS NOT NULL
     OR stop_loss_policy_version IS NOT NULL
     OR stop_loss_policy_hash IS NOT NULL;
  IF proposal_count <> 0 OR lot_count <> 0 OR position_v3_count <> 0 THEN
    RAISE EXCEPTION '041 rollback blocked: proposal=% lot=% position_v3=%',
      proposal_count, lot_count, position_v3_count;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_041_n6_virtual_trade_source_proposal;
DROP INDEX IF EXISTS idx_041_n6_virtual_order_source_proposal;

ALTER TABLE n6_virtual_trade
  DROP COLUMN IF EXISTS fill_quote_snapshot_id,
  DROP COLUMN IF EXISTS signal_reference_price,
  DROP COLUMN IF EXISTS signal_reference_kind,
  DROP COLUMN IF EXISTS source_proposal_id;

ALTER TABLE n6_virtual_order
  DROP COLUMN IF EXISTS fill_quote_snapshot_id,
  DROP COLUMN IF EXISTS signal_reference_price,
  DROP COLUMN IF EXISTS signal_reference_kind,
  DROP COLUMN IF EXISTS source_proposal_id;

ALTER TABLE n6_virtual_position
  DROP CONSTRAINT IF EXISTS n6_virtual_position_stop_loss_price_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_locked_target_price_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_stop_loss_frozen_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_target_price_frozen_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_stop_loss_status_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_target_price_status_ck,
  DROP CONSTRAINT IF EXISTS n6_virtual_position_holding_episode_no_ck,
  DROP COLUMN IF EXISTS stop_loss_policy_hash,
  DROP COLUMN IF EXISTS stop_loss_policy_version,
  DROP COLUMN IF EXISTS stop_loss_frozen_at,
  DROP COLUMN IF EXISTS stop_loss_effective_trade_date,
  DROP COLUMN IF EXISTS stop_loss_source_quote_snapshot_id,
  DROP COLUMN IF EXISTS stop_loss_status,
  DROP COLUMN IF EXISTS stop_loss_price,
  DROP COLUMN IF EXISTS target_price_source_signal_projection_id,
  DROP COLUMN IF EXISTS target_price_status,
  DROP COLUMN IF EXISTS locked_target_price,
  DROP COLUMN IF EXISTS first_open_trade_date,
  DROP COLUMN IF EXISTS holding_episode_no;

DROP TABLE IF EXISTS n6_virtual_position_lot;
DROP TABLE IF EXISTS n6_virtual_trade_proposal;

COMMIT;
