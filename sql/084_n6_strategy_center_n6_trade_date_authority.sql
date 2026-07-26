-- N6 Strategy Center reviewed-display trade-date authority.
--
-- This additive migration removes the active Strategy Center runtime
-- dependency on common_trade_calendar.  Historical migrations remain
-- immutable.  The business date is the fail-closed consensus of the latest
-- complete stock/index/board reviewed display-view batches.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_n6_trade_date_authority_084_v1', 0
  )
);

DO $preflight$
DECLARE
  function_signature text;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '084 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_trade_date_authority_v1()'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '084 trade-date authority already installed';
  END IF;
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    IF pg_catalog.to_regprocedure(function_signature) IS NULL THEN
      RAISE EXCEPTION '084 active function missing: %', function_signature;
    END IF;
    IF pg_catalog.pg_get_userbyid(
         (
           SELECT procedure.proowner
           FROM pg_catalog.pg_proc procedure
           WHERE procedure.oid =
                 pg_catalog.to_regprocedure(function_signature)
         )
       ) IS DISTINCT FROM 'ashare_v3_user'
       OR pg_catalog.strpos(
            pg_catalog.pg_get_functiondef(
              pg_catalog.to_regprocedure(function_signature)
            ),
            'common_trade_calendar'
          ) = 0 THEN
      RAISE EXCEPTION '084 active function authority drift: %',
        function_signature;
    END IF;
  END LOOP;
  IF pg_catalog.to_regclass(
       'public.v_n6_stock_condition_display_basis'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.v_n6_index_condition_display_basis'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.v_n6_board_condition_display_basis'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.common_trade_calendar'
        ) IS NULL THEN
    RAISE EXCEPTION '084 source relation lineage missing';
  END IF;
  IF NOT pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.common_trade_calendar',
       'SELECT'
     )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_stock_condition_display_basis',
          'SELECT'
        )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_index_condition_display_basis',
          'SELECT'
        )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_board_condition_display_basis',
          'SELECT'
        ) THEN
    RAISE EXCEPTION '084 worker source ACL baseline drift';
  END IF;
END
$preflight$;

CREATE FUNCTION public.n6_strategy_center_trade_date_authority_v1()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb;
BEGIN
  WITH stock_latest AS MATERIALIZED (
    SELECT pg_catalog.max(basis.for_trade_date::text) AS for_trade_date
    FROM public.v_n6_stock_condition_display_basis basis
  ), stock_batch AS MATERIALIZED (
    SELECT 1::integer AS asset_order,
           'stock'::text AS asset_kind,
           pg_catalog.min(basis.source_trade_date::text)
             AS source_trade_date,
           pg_catalog.min(basis.for_trade_date::text) AS for_trade_date,
           pg_catalog.min(basis.run_id::text) AS source_run_id,
           pg_catalog.count(*)::bigint AS row_count
    FROM public.v_n6_stock_condition_display_basis basis
    CROSS JOIN stock_latest latest
    WHERE basis.for_trade_date::text = latest.for_trade_date
    HAVING pg_catalog.count(*) > 0
       AND pg_catalog.count(basis.source_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.for_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.run_id) = pg_catalog.count(*)
       AND pg_catalog.count(DISTINCT (
             basis.source_trade_date::text,
             basis.for_trade_date::text,
             basis.run_id::text
           )) = 1
  ), index_latest AS MATERIALIZED (
    SELECT pg_catalog.max(basis.for_trade_date::text) AS for_trade_date
    FROM public.v_n6_index_condition_display_basis basis
  ), index_batch AS MATERIALIZED (
    SELECT 2::integer AS asset_order,
           'index'::text AS asset_kind,
           pg_catalog.min(basis.source_trade_date::text)
             AS source_trade_date,
           pg_catalog.min(basis.for_trade_date::text) AS for_trade_date,
           pg_catalog.min(basis.run_id::text) AS source_run_id,
           pg_catalog.count(*)::bigint AS row_count
    FROM public.v_n6_index_condition_display_basis basis
    CROSS JOIN index_latest latest
    WHERE basis.for_trade_date::text = latest.for_trade_date
    HAVING pg_catalog.count(*) > 0
       AND pg_catalog.count(basis.source_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.for_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.run_id) = pg_catalog.count(*)
       AND pg_catalog.count(DISTINCT (
             basis.source_trade_date::text,
             basis.for_trade_date::text,
             basis.run_id::text
           )) = 1
  ), board_latest AS MATERIALIZED (
    SELECT pg_catalog.max(basis.for_trade_date::text) AS for_trade_date
    FROM public.v_n6_board_condition_display_basis basis
  ), board_batch AS MATERIALIZED (
    SELECT 3::integer AS asset_order,
           'board'::text AS asset_kind,
           pg_catalog.min(basis.source_trade_date::text)
             AS source_trade_date,
           pg_catalog.min(basis.for_trade_date::text) AS for_trade_date,
           pg_catalog.min(basis.run_id::text) AS source_run_id,
           pg_catalog.count(*)::bigint AS row_count
    FROM public.v_n6_board_condition_display_basis basis
    CROSS JOIN board_latest latest
    WHERE basis.for_trade_date::text = latest.for_trade_date
    HAVING pg_catalog.count(*) > 0
       AND pg_catalog.count(basis.source_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.for_trade_date) = pg_catalog.count(*)
       AND pg_catalog.count(basis.run_id) = pg_catalog.count(*)
       AND pg_catalog.count(DISTINCT (
             basis.source_trade_date::text,
             basis.for_trade_date::text,
             basis.run_id::text
           )) = 1
  ), batches AS MATERIALIZED (
    SELECT * FROM stock_batch
    UNION ALL
    SELECT * FROM index_batch
    UNION ALL
    SELECT * FROM board_batch
  ), validated AS (
    SELECT pg_catalog.min(batch.for_trade_date) AS for_trade_date,
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'asset_kind', batch.asset_kind,
               'source_trade_date', batch.source_trade_date,
               'for_trade_date', batch.for_trade_date,
               'source_run_id', batch.source_run_id,
               'row_count', batch.row_count
             )
             ORDER BY batch.asset_order
           ) AS batches
    FROM batches batch
    HAVING pg_catalog.count(*) = 3
       AND pg_catalog.count(DISTINCT batch.asset_kind) = 3
       AND pg_catalog.count(DISTINCT batch.for_trade_date) = 1
       AND pg_catalog.bool_and(
             batch.source_trade_date ~ '^[0-9]{8}$'
             AND batch.for_trade_date ~ '^[0-9]{8}$'
             AND pg_catalog.to_char(
                   pg_catalog.to_date(
                     batch.source_trade_date, 'YYYYMMDD'
                   ),
                   'YYYYMMDD'
                 ) = batch.source_trade_date
             AND pg_catalog.to_char(
                   pg_catalog.to_date(
                     batch.for_trade_date, 'YYYYMMDD'
                   ),
                   'YYYYMMDD'
                 ) = batch.for_trade_date
             AND batch.source_trade_date <= batch.for_trade_date
             AND pg_catalog.btrim(batch.source_run_id) <> ''
           )
  )
  SELECT pg_catalog.jsonb_build_object(
           'authority_version',
             'n6_strategy_center_trade_date_authority_v1',
           'for_trade_date', validated.for_trade_date,
           'batches', validated.batches
         )
    INTO authority
  FROM validated;

  IF authority IS NULL
     OR authority->>'for_trade_date' IS NULL
     OR pg_catalog.jsonb_array_length(authority->'batches') <> 3 THEN
    RAISE EXCEPTION 'n6_strategy_center_trade_date_authority_invalid';
  END IF;
  RETURN authority;
EXCEPTION
  WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RAISE EXCEPTION 'n6_strategy_center_trade_date_authority_invalid';
END
$function$;

ALTER FUNCTION public.n6_strategy_center_trade_date_authority_v1()
OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION
  public.n6_strategy_center_trade_date_authority_v1()
FROM PUBLIC, n6_btrack_web, n6_strategy_worker, n6_virtual_executor,
  n6_quote_writer, n6_ai_agent;

DO $freeze_installation_authority$
DECLARE
  authority jsonb;
  installation jsonb;
BEGIN
  authority := public.n6_strategy_center_trade_date_authority_v1();
  installation := pg_catalog.jsonb_build_object(
    'migration_id',
      '084_n6_strategy_center_n6_trade_date_authority_v1',
    'installed_authority', authority
  );
  EXECUTE pg_catalog.format(
    'COMMENT ON FUNCTION public.'
      'n6_strategy_center_trade_date_authority_v1() IS %L',
    installation::text
  );
  IF (
       pg_catalog.obj_description(
         'public.n6_strategy_center_trade_date_authority_v1()'
           ::pg_catalog.regprocedure,
         'pg_proc'
       )::jsonb
     ) IS DISTINCT FROM installation THEN
    RAISE EXCEPTION '084 installation authority freeze failed';
  END IF;
END
$freeze_installation_authority$;

DO $rewrite$
DECLARE
  function_signature text;
  function_definition text;
  rewritten_definition text;
  old_fragment text;
  new_fragment text;
BEGIN
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    SELECT pg_catalog.pg_get_functiondef(
             pg_catalog.to_regprocedure(function_signature)
           )
      INTO function_definition;
    IF function_signature =
       'public.n6_btrack_strategy_center_state(text)' THEN
      old_fragment := $old$
  ), resolved_trade_date AS (
    SELECT max(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD')) AS value
    FROM public.common_trade_calendar calendar
    WHERE calendar.is_open = true
      AND calendar.trade_date ~ '^[0-9]{8}$'
      AND calendar.trade_date <= pg_catalog.to_char(
            pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
            'YYYYMMDD'
          )
$old$;
      new_fragment := $new$
  ), n6_trade_date_authority AS MATERIALIZED (
    SELECT public.n6_strategy_center_trade_date_authority_v1() AS value
  ), resolved_trade_date AS (
    SELECT pg_catalog.to_date(
             authority.value->>'for_trade_date', 'YYYYMMDD'
           ) AS value
    FROM n6_trade_date_authority authority
$new$;
    ELSIF function_signature IN (
      'public.n6_strategy_default_selection_on_principal_insert()',
      'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)'
    ) THEN
      old_fragment := $old$
  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
    INTO effective_trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
$old$;
      new_fragment := $new$
  effective_trade_date := pg_catalog.to_date(
    public.n6_strategy_center_trade_date_authority_v1()
      ->>'for_trade_date',
    'YYYYMMDD'
  );
$new$;
    ELSIF function_signature IN (
      'public.n6_strategy_center_compensate_revision_v1('
        'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
      'public.n6_strategy_center_abandon_pending_v2('
        'bigint,text,bigint,bigint,bigint,date,text)'
    ) THEN
      old_fragment := $old$
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM (
       pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
     )::date
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date = pg_catalog.to_char(
               p_trade_date, 'YYYYMMDD'
             )
         AND calendar.is_open = true
     ) THEN
$old$;
      new_fragment := $new$
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM pg_catalog.to_date(
          public.n6_strategy_center_trade_date_authority_v1()
            ->>'for_trade_date',
          'YYYYMMDD'
        ) THEN
$new$;
    ELSE
      RAISE EXCEPTION '084 unsupported function rewrite: %',
        function_signature;
    END IF;
    rewritten_definition := pg_catalog.replace(
      function_definition, old_fragment, new_fragment
    );
    IF rewritten_definition IS NOT DISTINCT FROM function_definition
       OR pg_catalog.strpos(
            rewritten_definition, 'common_trade_calendar'
          ) > 0
       OR pg_catalog.strpos(
            rewritten_definition,
            'n6_strategy_center_trade_date_authority_v1'
          ) = 0 THEN
      RAISE EXCEPTION '084 function rewrite failed: %',
        function_signature;
    END IF;
    EXECUTE rewritten_definition;
  END LOOP;
END
$rewrite$;

REVOKE SELECT ON TABLE public.common_trade_calendar
FROM n6_strategy_worker;

-- Invoke the helper inside the migration transaction.  Invalid or mixed
-- reviewed batches roll back the helper, all function replacements and ACL.
SELECT public.n6_strategy_center_trade_date_authority_v1();

DO $postflight$
DECLARE
  function_signature text;
  function_definition text;
  installation jsonb;
  helper_oid pg_catalog.regprocedure :=
    'public.n6_strategy_center_trade_date_authority_v1()'
      ::pg_catalog.regprocedure;
BEGIN
  installation := pg_catalog.obj_description(helper_oid, 'pg_proc')::jsonb;
  IF pg_catalog.pg_get_userbyid(
       (
         SELECT procedure.proowner
         FROM pg_catalog.pg_proc procedure
         WHERE procedure.oid = helper_oid
       )
     ) IS DISTINCT FROM 'ashare_v3_user'
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc procedure,
               LATERAL pg_catalog.aclexplode(
                 COALESCE(
                   procedure.proacl,
                   pg_catalog.acldefault('f', procedure.proowner)
                 )
               ) privilege
          WHERE procedure.oid = helper_oid
            AND privilege.grantee = 0
            AND privilege.privilege_type = 'EXECUTE'
        ) THEN
    RAISE EXCEPTION '084 helper ACL postflight failed';
  END IF;
  IF installation->>'migration_id' IS DISTINCT FROM
       '084_n6_strategy_center_n6_trade_date_authority_v1'
     OR installation->'installed_authority' IS DISTINCT FROM
       public.n6_strategy_center_trade_date_authority_v1() THEN
    RAISE EXCEPTION '084 installation authority postflight failed';
  END IF;
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    function_definition := pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure(function_signature)
    );
    IF pg_catalog.strpos(
         function_definition, 'common_trade_calendar'
       ) > 0
       OR pg_catalog.strpos(
            function_definition,
            'n6_strategy_center_trade_date_authority_v1'
          ) = 0 THEN
      RAISE EXCEPTION '084 active function postflight failed: %',
        function_signature;
    END IF;
  END LOOP;
  IF pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.common_trade_calendar',
       'SELECT'
     )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_stock_condition_display_basis',
          'SELECT'
        )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_index_condition_display_basis',
          'SELECT'
        )
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.v_n6_board_condition_display_basis',
          'SELECT'
        )
     OR pg_catalog.has_function_privilege(
          'n6_strategy_worker',
          helper_oid,
          'EXECUTE'
        ) THEN
    RAISE EXCEPTION '084 worker ACL postflight failed';
  END IF;
END
$postflight$;

COMMIT;
