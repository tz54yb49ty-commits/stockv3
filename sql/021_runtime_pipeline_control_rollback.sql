-- Runtime pipeline control-plane schema rollback draft.
-- Execute only after confirming runtime_pipeline_* tables contain no active
-- orchestration rows that need to be preserved for audit.

DO $$
DECLARE
    v_total BIGINT := 0;
    v_count BIGINT := 0;
    v_table TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'runtime_pipeline_timeline',
        'runtime_pipeline_stage',
        'runtime_rollback_registry',
        'runtime_execute_command_registry',
        'runtime_pipeline_run'
    ]
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
        v_total := v_total + v_count;
    END LOOP;

    IF v_total > 0 THEN
        RAISE EXCEPTION 'Runtime control schema rollback blocked: % rows remain. Review audit retention before dropping tables.', v_total;
    END IF;
END $$;

DROP TABLE IF EXISTS runtime_pipeline_timeline;
DROP TABLE IF EXISTS runtime_pipeline_stage;
DROP TABLE IF EXISTS runtime_rollback_registry;
DROP TABLE IF EXISTS runtime_execute_command_registry;
DROP TABLE IF EXISTS runtime_pipeline_run;
