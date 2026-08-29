BEGIN;

ALTER TABLE common_n3_previous_day_context_run
    ADD COLUMN context_version TEXT NOT NULL DEFAULT 'v1';

ALTER TABLE common_n3_previous_day_context_run
    ADD CONSTRAINT common_n3_previous_day_context_run_context_version_check
    CHECK (context_version ~ '^[a-z0-9][a-z0-9._-]{0,63}$');

ALTER TABLE common_n3_previous_day_context_run
    DROP CONSTRAINT common_n3_previous_day_context_run_source_condition_run_id_key;

ALTER TABLE common_n3_previous_day_context_run
    ADD CONSTRAINT common_n3_previous_day_context_run_source_context_version_key
    UNIQUE (source_condition_run_id, context_version);

COMMIT;
