-- A-share monitor v3 N3T action-confirmation schema rollback draft.
-- Stage: N3T Option A draft only. Requires a later explicit final rollback gate.
-- Boundary: N3_market_data N3T tables only; no DB operation is authorized by this file.
-- n3t action-confirmation schema rollback blocked until an explicit migration rollback gate approves execution.

DROP TABLE IF EXISTS stock_n3t_action_confirmation_metric;
DROP TABLE IF EXISTS index_n3t_action_confirmation_metric;
DROP TABLE IF EXISTS board_n3t_action_confirmation_metric;
