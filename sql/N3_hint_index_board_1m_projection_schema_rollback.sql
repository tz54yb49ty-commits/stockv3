-- Rollback for N3 index/board 1m HINT projection proof additive schema draft.
-- Scope: drop only objects introduced by N3_hint_index_board_1m_projection_schema.sql.

DROP TABLE IF EXISTS board_realtime_hint_projection_metric;
DROP TABLE IF EXISTS index_realtime_hint_projection_metric;
