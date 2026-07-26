-- N6 Web-created user principal backfill 072.
-- Do not execute without the separately approved runtime_control deployment gate.
-- The deployment preflight must freeze and compare the exact ordered candidate
-- set before this file is executed; the currently expected count alone is not
-- sufficient authority for a live migration.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_web_user_principal_backfill_072_v1', 0)
);

LOCK TABLE
  public.user_account,
  public.n6_principal
IN SHARE ROW EXCLUSIVE MODE;

DO $migration$
DECLARE
  candidate_count bigint;
  candidate_user_ids bigint[];
  inserted_count bigint;
  invalid_principal_count bigint;
  provenance constant jsonb := pg_catalog.jsonb_build_object(
    'source', 'n6_web_user_principal_backfill',
    'contract_version', 'n6-web-user-principal-v1',
    'migration_gate', '072',
    'migration_run_id', 'n6_web_user_principal_backfill_072_v1'
  );
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '072 owner migration identity rejected';
  END IF;

  SELECT count(*),
         COALESCE(
           pg_catalog.array_agg(candidate.user_id ORDER BY candidate.user_id),
           ARRAY[]::bigint[]
         )
    INTO candidate_count, candidate_user_ids
  FROM (
    SELECT user_row.user_id
    FROM public.user_account user_row
    WHERE user_row.status = 'active'
      AND user_row.role IN ('user', 'admin')
      AND user_row.user_policy_json @> '{"n6_web_created":true}'::jsonb
      AND NOT EXISTS (
        SELECT 1
        FROM public.n6_principal principal
        WHERE principal.owner_user_id = user_row.user_id
      )
  ) candidate;

  INSERT INTO public.n6_principal (
    principal_type,
    owner_user_id,
    principal_status,
    principal_label,
    principal_policy_json
  )
  SELECT CASE user_row.role
           WHEN 'admin' THEN 'admin'
           ELSE 'human_user'
         END,
         user_row.user_id,
         'active',
         COALESCE(
           NULLIF(pg_catalog.btrim(user_row.display_name), ''),
           user_row.login_name
         ),
         provenance || pg_catalog.jsonb_build_object(
           'created_by_user_id', user_row.created_by_user_id
         )
  FROM public.user_account user_row
  WHERE user_row.user_id = ANY(candidate_user_ids)
  ORDER BY user_row.user_id;

  GET DIAGNOSTICS inserted_count = ROW_COUNT;
  IF inserted_count <> candidate_count THEN
    RAISE EXCEPTION
      '072 inserted row count mismatch: expected=% actual=%',
      candidate_count,
      inserted_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_catalog.unnest(candidate_user_ids) candidate(user_id)
    JOIN public.user_account user_row
      ON user_row.user_id = candidate.user_id
    LEFT JOIN public.n6_principal principal
      ON principal.owner_user_id = user_row.user_id
    WHERE principal.principal_id IS NULL
       OR principal.principal_type IS DISTINCT FROM CASE user_row.role
            WHEN 'admin' THEN 'admin'
            ELSE 'human_user'
          END
       OR principal.principal_status IS DISTINCT FROM 'active'
       OR principal.principal_label IS DISTINCT FROM COALESCE(
            NULLIF(pg_catalog.btrim(user_row.display_name), ''),
            user_row.login_name
          )
       OR principal.principal_policy_json IS DISTINCT FROM
            provenance || pg_catalog.jsonb_build_object(
              'created_by_user_id', user_row.created_by_user_id
            )
  ) THEN
    RAISE EXCEPTION '072 inserted principal provenance or field validation failed';
  END IF;

  SELECT count(*)
    INTO invalid_principal_count
  FROM (
    SELECT user_row.user_id
    FROM public.user_account user_row
    LEFT JOIN public.n6_principal principal
      ON principal.owner_user_id = user_row.user_id
    WHERE user_row.status = 'active'
      AND user_row.role IN ('user', 'admin')
      AND user_row.user_policy_json @> '{"n6_web_created":true}'::jsonb
    GROUP BY user_row.user_id, user_row.role
    HAVING count(*) FILTER (
             WHERE principal.principal_status = 'active'
               AND principal.principal_type = CASE user_row.role
                 WHEN 'admin' THEN 'admin'
                 ELSE 'human_user'
               END
           ) <> 1
        OR count(*) FILTER (
             WHERE principal.principal_status = 'active'
               AND principal.principal_type IN ('admin', 'human_user')
           ) <> 1
  ) invalid_user;

  IF invalid_principal_count <> 0 THEN
    RAISE EXCEPTION
      '072 active Web-created user principal invariant failed: %',
      invalid_principal_count;
  END IF;
END
$migration$;

COMMIT;
