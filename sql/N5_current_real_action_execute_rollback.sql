-- N5 current-real action execute rollback.
-- Execute only after an explicitly approved N5 execute run needs rollback.
-- Scope:
--   action_run_id: action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
--   source_trigger_run_id: trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
--   consumer_name: n5_action_consumer_v1
-- Boundary:
--   Deletes only N5 action-layer rows and this N5 consumer's inbox/checkpoint
--   rows for the scoped N4 source run. It does not mutate N4 trigger facts,
--   N4 outbox status, N3 facts, user projection, voice, sim, mobile, or
--   true-trade tables.

BEGIN;

\set action_run_id 'action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249'
\set source_trigger_run_id 'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249'
\set consumer_name 'n5_action_consumer_v1'

SELECT 'common_action_run' AS table_name, count(*) AS row_count
FROM common_action_run
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'stock_action_fact', count(*)
FROM stock_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'index_action_fact', count(*)
FROM index_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'board_action_fact', count(*)
FROM board_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_inbox_n5_consumer', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
  UNION
  SELECT event_id
  FROM common_event_ledger
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
)
DELETE FROM common_event_delivery_attempt
WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);

WITH scoped_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_name'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_trigger_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_partitions);

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_action_event
WHERE run_id = :'action_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id';

COMMIT;
